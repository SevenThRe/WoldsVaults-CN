"""持久译料层：把 AI 补译的译文与母版 jar 解耦存放。

为什么必须有这一层
------------------
重基底每轮都会 ``_fresh_copy`` 把母版 jar 重新解压到 ``build/cn/work/template``。
任何只写进那个目录的译文，下一轮就被覆盖——AI 翻译的成果会凭空消失，
而且下一轮构建会把**已经翻过的内容再列为待译**，永远清不完。

所以译文必须落在仓库里一个稳定的地方，构建时再叠加到母版载荷之上：

    translations/cn-rebase/lang_zh.tsv        命名空间 \t 键 \t 原文 \t 中文
    translations/cn-rebase/literal_zh_cn.tsv  英文 \t 中文
    translations/cn-rebase/config_zh.tsv      目标路径 \t JSON 指针 \t 原文 \t 中文
    translations/cn-rebase/vendor_lang_zh.tsv 命名空间 \t 键 \t 原文 \t 中文

四份文件对应四个汉化通道，都用 TSV：好 diff、好 review、能手改。

``lang_zh`` 与 ``vendor_lang_zh`` 的区别只在**归属**：前者是整合包本体
（``the_vault`` / ``woldsvaults`` / ``kubejs`` 等，由语言表通道按 delta 合并），
后者是整合包自带的第三方模组（由 ``vendor`` 通道以「模组自带 zh 为底」整份生成）。
分开存是为了让「本体缺键」和「第三方补译」两类工作的进度各自可见。

数据流向
--------
    母版载荷（基线，随 jar 升级更新）
        + translations/cn-rebase/*.tsv（本项目累积的译文）
        → 构建时叠加 → 产物 jar

叠加是**项目译料优先**：母版改了同一处译文时以本层为准，便于在不重新编译
母版的情况下纠正译文。

转义约定
--------
TSV 是行/列分隔的，而译文里会出现换行、制表符与 ``\\x01`` 占位符标记。
三份文件统一做转义（``\\\\ \\n \\r \\t \\x01``），由本模块 ``escape`` /
``unescape`` 成对处理。不做转义的话，一条含换行的译文会在 TSV 里断成两行，
回填时错位到别的条目上——这类错位极难发现，且在游戏里表现为「某句莫名其妙的
中文出现在另一个地方」。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from tools.cnrebase.delta import has_cjk, normalize_literal

#: 译料目录（相对仓库根）
DEFAULT_ROOT = "translations/cn-rebase"
LANG_FILE = "lang_zh.tsv"
LITERAL_FILE = "literal_zh_cn.tsv"
CONFIG_FILE = "config_zh.tsv"
VENDOR_FILE = "vendor_lang_zh.tsv"
#: 「新增配置键」片段：``{目标路径: 要深合并进该目标 JSON 的片段}``。
#: 与 ``config_zh.tsv``（按指针覆盖**已存在**叶子）互补 —— 这个通道
#: 允许**凭空新增**键，用于上游压根没写的条目（如研究说明）。
#: 详见 :mod:`tools.cnrebase.build` 里 ``_merge_extra_keys`` 的「只增不改」约束。
CONFIG_EXTRA_FILE = "config_extra.json"
README_FILE = "README.md"

LANG_HEADER = "namespace\tkey\ten\tzh\n"
LITERAL_HEADER = "en\tzh\n"
CONFIG_HEADER = "target\tpointer\ten\tzh\n"
VENDOR_HEADER = "namespace\tkey\ten\tzh\n"

#: 语言表表头判定用的首列取值（``_read_tsv`` 依赖）
_HEADER_FIRST_COLS = ("namespace", "en", "target")


# --------------------------------------------------------------------------- #
# TSV 转义
# --------------------------------------------------------------------------- #
_ESC_MAP = {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t", "\x01": "\\x01"}
_ESC_RE = re.compile(r"[\\\n\r\t\x01]")
_UNESC_RE = re.compile(r"\\(\\|n|r|t|x01)")
_UNESC_MAP = {"\\": "\\", "n": "\n", "r": "\r", "t": "\t", "x01": "\x01"}


def escape(s: str) -> str:
    return _ESC_RE.sub(lambda m: _ESC_MAP[m.group(0)], s)


def unescape(s: str) -> str:
    return _UNESC_RE.sub(lambda m: _UNESC_MAP[m.group(1)], s)


# --------------------------------------------------------------------------- #
# 译文校验：拦住「译坏占位符」这类只有运行时才暴露的错误
# --------------------------------------------------------------------------- #
#: 需要原样保留的占位符形态。
#: 母版 tsv 实际用到 ``%s`` ``%d`` ``%1$s`` ``%.1f`` ``%%``，以及 KubeJS 侧的 ``{0}``。
#: 注意 ``%%`` 不是占位符而是**转义的字面百分号**，少一个会让 ``String.format``
#: 直接抛 ``UnknownFormatConversionException``，所以它也必须等量保留。
_PLACEHOLDER = re.compile(
    r"%[0-9]*\$?[-#+0,(<]*[0-9]*(?:\.[0-9]+)?[a-zA-Z]"
    r"|%%"
    r"|\{[A-Za-z0-9_]*\}"
)
#: Minecraft 样式码 §a §l §r
_STYLE = re.compile("\u00a7.")


def _sig(pattern: re.Pattern[str], s: str) -> tuple[str, ...]:
    return tuple(sorted(pattern.findall(s)))


def validate(en: str, zh: str, *, as_literal: bool = False) -> str | None:
    """检查一条译文是否可用。返回 ``None`` 表示通过，否则返回拒绝原因。

    这几条不是吹毛求疵——它们对应的都是「构建全绿、进游戏才炸」的故障：
    占位符少一个，``String.format`` 会抛异常或把参数吞掉；样式码丢了，
    整段文字会变成默认颜色；译文为空则玩家看到空字符串。
    """
    if as_literal:
        # 字面量对照表是行式的（一行一条、制表符分隔），条目里带换行会把它
        # 劈成两行并错位到下一条上。母版那 118364 行里一条断行都没有，
        # 说明上游作者也守着这个约束。这类字面量只能走语言文件或字节码补丁。
        for _label, _s in (("原文", en), ("译文", zh)):
            if chr(10) in _s or chr(13) in _s:
                return _label + "含换行，行式对照表无法承载"
            if chr(9) in _s:
                return _label + "含制表符，行式对照表无法承载"
    if not zh.strip():
        return "空译文"
    if _sig(_PLACEHOLDER, en) != _sig(_PLACEHOLDER, zh):
        return (f"占位符不一致：en={_sig(_PLACEHOLDER, en)} "
                f"zh={_sig(_PLACEHOLDER, zh)}")
    if len(_STYLE.findall(en)) != len(_STYLE.findall(zh)):
        return "样式码 §x 数量不一致"
    # 原文没有字母（纯符号/数字/颜色码）时允许译文也是纯符号
    if re.search(r"[A-Za-z]", en) and not has_cjk(zh) and zh.strip() != en.strip():
        return "译文不含中文"
    return None


# --------------------------------------------------------------------------- #
# 译料层
# --------------------------------------------------------------------------- #
def _read_tsv(path: Path, min_cols: int) -> list[list[str]]:
    """读 TSV，跳过表头/空行/``#`` 注释行，列数不足的行丢弃。"""
    if not path.is_file():
        return []
    rows: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < min_cols:
            continue
        if parts[0].strip() in _HEADER_FIRST_COLS and not rows:
            continue  # 表头
        rows.append(parts)
    return rows


@dataclass
class Corpus:
    """三通道译料。缺文件即为空，不报错——首次构建时本来就没有。"""

    root: Path = Path(DEFAULT_ROOT)
    #: 命名空间 → 键 → 中文
    lang: dict[str, dict[str, str]] = field(default_factory=dict)
    #: 英文（已 normalize_literal）→ 中文
    literal: dict[str, str] = field(default_factory=dict)
    #: 目标路径 → JSON 指针 → 中文
    config: dict[str, dict[str, str]] = field(default_factory=dict)
    #: 第三方模组命名空间 → 键 → 中文（vendor 通道）
    vendor: dict[str, dict[str, str]] = field(default_factory=dict)
    #: 「新增配置键」片段：目标路径 → 任意 JSON 片段
    extra_config: dict[str, object] = field(default_factory=dict)

    # ---------------- 读 ----------------
    @classmethod
    def load(cls, root: Path | str = DEFAULT_ROOT) -> "Corpus":
        root = Path(root)
        c = cls(root=root)
        for parts in _read_tsv(root / LANG_FILE, 4):
            ns, key = parts[0].strip(), parts[1]
            zh = unescape(parts[3]) if len(parts) > 3 else ""
            if ns and key and zh.strip():
                c.lang.setdefault(ns, {})[unescape(key)] = zh
        for parts in _read_tsv(root / LITERAL_FILE, 2):
            en, zh = unescape(parts[0]), unescape(parts[1])
            if en and zh.strip():
                c.literal[normalize_literal(en)] = zh
        for parts in _read_tsv(root / CONFIG_FILE, 3):
            target, ptr = unescape(parts[0]), parts[1].strip()
            zh = unescape(parts[3]) if len(parts) > 3 else ""
            if target and ptr and zh.strip():
                c.config.setdefault(target, {})[ptr] = zh
        for parts in _read_tsv(root / VENDOR_FILE, 4):
            ns, key = parts[0].strip(), unescape(parts[1])
            zh = unescape(parts[3]) if len(parts) > 3 else ""
            if ns and key and zh.strip():
                c.vendor.setdefault(ns, {})[key] = zh
        extra = root / CONFIG_EXTRA_FILE
        if extra.is_file():
            import json as _json
            try:
                parsed = _json.loads(extra.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                raise ValueError(
                    f"{CONFIG_EXTRA_FILE} 不是合法 JSON：{e}") from e
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"{CONFIG_EXTRA_FILE} 顶层必须是对象（目标路径 → 片段）")
            for t, frag in parsed.items():
                if isinstance(frag, (dict, list)) and frag:
                    c.extra_config[str(t)] = frag
        return c

    # ---------------- 写 ----------------
    def merge_lang(self, ns: str, key: str, zh: str) -> bool:
        """并入一条语言译文，返回是否为新键或内容有变。"""
        slot = self.lang.setdefault(ns, {})
        old = slot.get(key)
        if old == zh:
            return False
        slot[key] = zh
        return True

    def merge_literal(self, en: str, zh: str) -> bool:
        k = normalize_literal(en)
        if self.literal.get(k) == zh:
            return False
        self.literal[k] = zh
        return True

    def merge_config(self, target: str, ptr: str, zh: str) -> bool:
        slot = self.config.setdefault(target, {})
        if slot.get(ptr) == zh:
            return False
        slot[ptr] = zh
        return True

    def merge_vendor(self, ns: str, key: str, zh: str) -> bool:
        slot = self.vendor.setdefault(ns, {})
        if slot.get(key) == zh:
            return False
        slot[key] = zh
        return True

    def save(self) -> dict[str, int]:
        """写回三份 TSV。**排序输出**——否则每次构建都产生巨大且无意义的
        git diff，真正的译文改动会被淹没。"""
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / LANG_FILE).write_text(
            LANG_HEADER + "".join(
                f"{ns}\t{escape(k)}\t\t{escape(v)}\n"
                for ns in sorted(self.lang)
                for k, v in sorted(self.lang[ns].items())
            ),
            encoding="utf-8", newline="\n",
        )
        (self.root / LITERAL_FILE).write_text(
            LITERAL_HEADER + "".join(
                f"{escape(en)}\t{escape(zh)}\n"
                for en, zh in sorted(self.literal.items())
            ),
            encoding="utf-8", newline="\n",
        )
        (self.root / CONFIG_FILE).write_text(
            CONFIG_HEADER + "".join(
                f"{escape(t)}\t{ptr}\t\t{escape(zh)}\n"
                for t in sorted(self.config)
                for ptr, zh in sorted(self.config[t].items())
            ),
            encoding="utf-8", newline="\n",
        )
        (self.root / VENDOR_FILE).write_text(
            VENDOR_HEADER + "".join(
                f"{ns}\t{escape(k)}\t\t{escape(v)}\n"
                for ns in sorted(self.vendor)
                for k, v in sorted(self.vendor[ns].items())
            ),
            encoding="utf-8", newline="\n",
        )
        return self.stats()

    def stats(self) -> dict[str, int]:
        return {
            "lang": sum(len(v) for v in self.lang.values()),
            "literal": len(self.literal),
            "config": sum(len(v) for v in self.config.values()),
            "vendor": sum(len(v) for v in self.vendor.values()),
            "config_extra": len(self.extra_config),
        }

    # ---------------- 叠加到构建侧 ----------------
    def apply_lang(self, ours: dict[str, dict[str, str]]) -> int:
        """把语言译料并入「我方」语言表。返回叠加条目数。"""
        n = 0
        for ns, kv in self.lang.items():
            slot = ours.setdefault(f"{ns}/zh_cn", {})
            for k, v in kv.items():
                if slot.get(k) != v:
                    n += 1
                slot[k] = v
        return n

    def apply_literal(self, pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """把字面量译料并入母版对照表。

        母版已有的键**就地替换**（保持行序 = 运行时加载序稳定），
        新键追加在末尾并按 en 排序（幂等，diff 友好）。
        """
        out: list[tuple[str, str]] = []
        used: set[str] = set()
        for en, zh in pairs:
            k = normalize_literal(en)
            if k in self.literal:
                out.append((en, self.literal[k]))
                used.add(k)
            else:
                out.append((en, zh))
        extra = sorted(k for k in self.literal if k not in used)
        out.extend((k, self.literal[k]) for k in extra)
        return out

    def apply_config_overlay(self, target: str) -> dict[str, str]:
        return self.config.get(target, {})

    def extra_for(self, target: str) -> object | None:
        """该目标要**新增**的 JSON 片段（没有则 ``None``）。"""
        return self.extra_config.get(target)

    def extra_targets(self) -> list[tuple[str, object]]:
        """``config_extra.json`` 里全部 ``(目标, 片段)``，按目标名排序。

        供构建做**兜底叠加**用：主循环是按五份清单枚举 job 的 有些目标
        （如只存在于 ``config_payload/config/`` 一处的语言副本）可能没被
        任何清单枚举到，导致译料层写了译文却没进产物。
        """
        return [(k, self.extra_config[k]) for k in sorted(self.extra_config)]


def write_corpus_readme(root: Path | str = DEFAULT_ROOT) -> Path:
    """给译料目录留一份自述，免得后来者以为这些 TSV 是导出物而随手删掉。"""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    p = root / README_FILE
    p.write_text(
        "# 译料层（不要删）\n"
        "\n"
        "这四份 TSV 是**本项目累积的译文**，是重基底构建的输入之一，不是导出物。\n"
        "删掉它们，等价于把所有 AI 补译的内容丢掉，下一轮构建会重新把它们列为待译。\n"
        "\n"
        "| 文件 | 列 | 对应通道 |\n"
        "|---|---|---|\n"
        "| `lang_zh.tsv` | `namespace` `key` `en` `zh` | 整合包本体语言文件 `assets/<ns>/lang/zh_cn.json` |\n"
        "| `literal_zh_cn.tsv` | `en` `zh` | 硬编码字面量对照表（写入 jar 内 `literal_zh_cn.tsv`） |\n"
        "| `config_zh.tsv` | `target` `pointer` `en` `zh` | 配置文本（按 JSON 指针回填） |\n"
        "| `vendor_lang_zh.tsv` | `namespace` `key` `en` `zh` | **第三方模组**语言文件（以模组自带 zh 为底整份生成） |\n"
        "\n"
        "`lang_zh.tsv` 与 `vendor_lang_zh.tsv` 结构相同，区别只在归属：前者是整合包\n"
        "本体（`the_vault` / `woldsvaults` / `kubejs` …），后者是整合包自带的第三方\n"
        "模组。分开存是为了让两类工作的进度各自可见。\n"
        "\n"
        "`en` 列只作对照，构建时**不使用**——译文与键（或指针）绑定，\n"
        "这样上游改了英文原文时，已有译文不会因为文本不匹配而失效。\n"
        "\n"
        "写入请走 `python -m tools.cnrebase.cli apply-todo`，不要手改：\n"
        "该命令会做占位符/样式码校验，并做转义与排序，手改容易破坏格式。\n"
        "\n"
        "`pointer` 是 JSON 位置，形如 `/o:skills/i:3/o:name`：\n"
        "`o:` 表示对象键、`i:` 表示数组下标，键内的 `/` 与 `~` 转义为 `~1` / `~0`。\n"
        "回填**只覆盖已存在的叶子**，不会凭空新增字段——结构永远以新版 config 为准。\n",
        encoding="utf-8", newline="\n",
    )
    return p
