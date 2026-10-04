"""增量分析：把 0.30.0 的汉化资产对齐到 0.34.1 的语料。

四类策略
--------
语言键（lang json）
    精确键匹配。我方缺的键若上游自带中文则直接取上游；否则进待译清单。

硬编码（literal tsv）
    我方 tsv 是「英文 → 中文」的穷举对照表。新版本 class 里的字面量若不在
    英文列即视为未译。

配置文本（config json）
    **结构感知合并**，不是整文件替换。以新版本 config 为结构基底，把旧版
    中文按「同路径字符串叶子」回填，从而不丢新版本新增的字段——这是重基底
    最关键的一步，直接沿用旧文件会让游戏读到过时的数据定义。

帕秋莉手册 / KubeJS
    按页集合做差集。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CJK = re.compile(r"[\u3400-\u9fff\u3000-\u303f\uff00-\uffef]")


def has_cjk(s: str) -> bool:
    return bool(CJK.search(s))


#: 资源路径里的语言段。用于把「我方 zh_cn 页」与「新版 en_us 页」对齐比较。
LANG_SEG = re.compile(
    r"/(zh_cn|zh_tw|en_us|en_gb|ja_jp|ru_ru|de_de|fr_fr|es_es|pt_br|ko_kr)(?=[/.]|$)"
)


def normalize_page_path(p: str) -> str:
    """把路径中的语言段抹平成 ``<lang>``。

    跨版本比对手册页时，我方存的是 ``patchouli_books/X/zh_cn/...``，
    而新版整合包只有 ``patchouli_books/X/en_us/...``。不做归一化会得到
    「全部页面都缺汉化」的假结论。
    """
    return LANG_SEG.sub("/<lang>", p)


def is_advancement(p: str) -> bool:
    return "/advancements/" in p and p.endswith(".json")


def is_lang_file(p: str) -> bool:
    return "/lang/" in p and p.endswith(".json")


# --------------------------------------------------------------------------- #
# JSON 位置指针
# --------------------------------------------------------------------------- #
#: 段前缀：``o:`` 对象键，``i:`` 数组下标。显式区分是为了消歧——
#: 纯 JSON Pointer 无法区分「键名 "3"」与「下标 3」，而 config 里两者都真实存在。
#: 键内的 ``/`` 与 ``~`` 分别转义为 ``~1`` / ``~0``（RFC 6901 规则）。
def ptr_join(segments: list[str]) -> str:
    return "/" + "/".join(segments) if segments else ""


def ptr_escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def ptr_unescape(key: str) -> str:
    return key.replace("~1", "/").replace("~0", "~")


def ptr_key(key: str) -> str:
    return "o:" + ptr_escape(key)


def ptr_index(i: int) -> str:
    return f"i:{i}"


def ptr_split(ptr: str) -> list[tuple[str, str]]:
    """把指针拆成 ``[(类型, 段名)]``，类型为 ``o`` 或 ``i``。"""
    if not ptr:
        return []
    out: list[tuple[str, str]] = []
    for seg in ptr.lstrip("/").split("/"):
        kind, _, name = seg.partition(":")
        out.append((kind, name if kind == "i" else ptr_unescape(name)))
    return out


def get_at_pointer(root: Any, ptr: str) -> Any:
    """按指针取值；路径不存在返回 ``None``。"""
    node = root
    for kind, name in ptr_split(ptr):
        if kind == "o":
            if not isinstance(node, dict) or name not in node:
                return None
            node = node[name]
        else:
            if not isinstance(node, list) or not (0 <= int(name) < len(node)):
                return None
            node = node[int(name)]
    return node


def set_at_pointer(root: Any, ptr: str, value: Any) -> bool:
    """按指针写值。**只覆盖已存在的叶子**——不新增结构。

    这是刻意的：本函数用于回填译文，而结构必须永远以新版 config 为基底。
    若允许凭空新增键，译料里的笔误就会变成产物里的多余字段。
    """
    parts = ptr_split(ptr)
    if not parts:
        return False
    node = root
    for kind, name in parts[:-1]:
        if kind == "o":
            if not isinstance(node, dict) or name not in node:
                return False
            node = node[name]
        else:
            if not isinstance(node, list) or not (0 <= int(name) < len(node)):
                return False
            node = node[int(name)]
    kind, name = parts[-1]
    if kind == "o":
        if not isinstance(node, dict) or name not in node:
            return False
        node[name] = value
        return True
    if not isinstance(node, list) or not (0 <= int(name) < len(node)):
        return False
    node[int(name)] = value
    return True


def load_json_safe(data: bytes | str) -> Any:
    """容错 JSON 读取：剥 BOM、容忍尾随逗号与 // 注释。"""
    if isinstance(data, bytes):
        text = data.decode("utf-8-sig", "replace")
    else:
        text = data.lstrip("\ufeff")
    try:
        return json.loads(text)
    except Exception:
        pass
    cleaned = re.sub(r"^\s*//.*$", "", text, flags=re.M)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.S)
    cleaned = re.sub(r",(\s*[}\]])", r"\1", cleaned)
    try:
        return json.loads(cleaned)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 语言键
# --------------------------------------------------------------------------- #
@dataclass
class LangDelta:
    ns: str
    upstream_en: dict[str, str] = field(default_factory=dict)
    upstream_zh: dict[str, str] = field(default_factory=dict)
    ours: dict[str, str] = field(default_factory=dict)

    @property
    def missing(self) -> dict[str, str]:
        """我方缺的键 → 英文原文。"""
        return {k: v for k, v in self.upstream_en.items() if k not in self.ours}

    @property
    def missing_from_upstream_zh(self) -> dict[str, str]:
        """我方缺、但上游自带中文的键 → 直接可用的译文。"""
        return {k: self.upstream_zh[k] for k in self.missing if k in self.upstream_zh}

    @property
    def missing_todo(self) -> dict[str, str]:
        """我方缺且上游也没中文的键 → 需要人工/机器翻译。"""
        return {k: self.upstream_en[k] for k in self.missing if k not in self.upstream_zh}

    @property
    def stale(self) -> list[str]:
        """我方有但上游已删除的键。"""
        return sorted(k for k in self.ours if k not in self.upstream_en)

    def stats(self) -> dict:
        m = self.missing
        return {
            "ns": self.ns,
            "upstream_en": len(self.upstream_en),
            "upstream_zh": len(self.upstream_zh),
            "ours": len(self.ours),
            "missing": len(m),
            "missing_fillable": len(self.missing_from_upstream_zh),
            "missing_todo": len(self.missing_todo),
            "stale": len(self.stale),
        }


def lang_delta(ns: str, ours: dict[str, str], en: dict[str, str], zh: dict[str, str]) -> LangDelta:
    return LangDelta(ns=ns, upstream_en=en, upstream_zh=zh, ours=ours)


def apply_lang_delta(d: LangDelta) -> dict[str, str]:
    """产出合并后的语言表：我方全量 + 上游可补的中文。"""
    out = dict(d.ours)
    for k, v in d.missing_from_upstream_zh.items():
        out[k] = v
    return out


# --------------------------------------------------------------------------- #
# 硬编码字面量
# --------------------------------------------------------------------------- #
_PLACEHOLDER_STRIP = re.compile(r"\x01+")

#: 命名空间资源 ID，如 ``the_vault:gui/skills/lingering_fumes``
NS_ID = re.compile(r"^[a-z0-9_]+:[a-z0-9_/\-.#]+$")
#: 分号分隔的字段名列表，如 ``tick;extraKnockback`` / ``pos;state;distance``
FIELD_LIST = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(;[A-Za-z_][A-Za-z0-9_]*)+$")


def normalize_literal(s: str) -> str:
    """归一化字面量以便与 tsv 比对。

    class 里的模板用 ``\\x01`` 标记插入点，tsv 用 ``%s``。统一成 ``%s`` 再比对。
    连续插入点合并为一个（``\\x01\\x01`` 与 ``%s%s`` 等价于两个参数占位）。
    """
    if "\x01" not in s:
        return s
    out = _PLACEHOLDER_STRIP.sub("%s", s)
    return out


def is_translatable(s: str, min_len: int = 6) -> bool:
    """判断字面量是否值得翻译。

    class 常量池里绝大多数字符串是**内部标识符**——配置键、资源名、贴图名、
    音效 ID（``classic_vault_ice`` / ``luckyHitChance`` / ``deck_station_tile_entity``）。
    它们含字母，长度也不短，但翻译它们没有任何意义。

    另外 ``\\x01`` 开头的是运行时模板的**拼接片段**（前半段在别的常量里），
    单独拿出来也不是完整句子。

    判定为可译需要同时满足：
    1. 不以 ``\\x01`` 开头（排除拼接片段）
    2. 去掉插入点后长度 >= ``min_len``
    3. 含空格或句读标点（排除标识符）
    4. 至少两个 >= 2 字母的单词
    5. 不是纯资源路径
    """
    if s.startswith("\x01"):
        return False
    probe = _PLACEHOLDER_STRIP.sub("", s)
    if len(probe) < min_len:
        return False
    # 命名空间资源 ID 与字段名列表含冒号/分号，会被下面的标点规则误放行
    if NS_ID.match(probe) or FIELD_LIST.match(probe):
        return False
    if " " not in probe and not re.search(r"[.!?:;,'\"()\[\]]", probe):
        return False
    if len(re.findall(r"[A-Za-z]{2,}", probe)) < 2:
        return False
    if re.match(r"^[\w./\\\-]+$", probe):
        return False
    return True


@dataclass
class LiteralDelta:
    """硬编码层增量。"""

    known: dict[str, str] = field(default_factory=dict)  # 已有 英文→中文
    scanned: dict[str, list[str]] = field(default_factory=dict)  # 新版扫描到的字面量

    @property
    def candidates(self) -> dict[str, list[str]]:
        return {s: c for s, c in self.scanned.items() if is_translatable(s)}

    @property
    def covered(self) -> dict[str, str]:
        """能在我方 tsv 命中的（含归一化命中）。"""
        nk = {normalize_literal(k): k for k in self.known}
        out: dict[str, str] = {}
        for s in self.candidates:
            if s in self.known:
                out[s] = self.known[s]
            else:
                key = nk.get(normalize_literal(s))
                if key is not None:
                    out[s] = self.known[key]
        return out

    @property
    def todo(self) -> dict[str, list[str]]:
        cov = self.covered
        return {s: c for s, c in self.candidates.items() if s not in cov}

    def stats(self) -> dict:
        return {
            "known_pairs": len(self.known),
            "scanned_raw": len(self.scanned),
            "candidates": len(self.candidates),
            "covered": len(self.covered),
            "todo": len(self.todo),
        }


# --------------------------------------------------------------------------- #
# 配置文本（结构感知合并）
# --------------------------------------------------------------------------- #
@dataclass
class MergeStat:
    path: str
    filled: int = 0  # 回填的中文叶子
    kept_en: int = 0  # 保留的英文叶子（新版本新增或未译）
    kept_en_text: int = 0  # 其中「疑似可读文本」的
    kept_en_other: int = 0  # 其中 ID / 数值 / 路径等无需翻译的
    stale_zh: int = 0  # 我方有、新版本已无对应位置的译文
    structure_changed: bool = False
    base_ok: bool = True
    ours_ok: bool = True
    #: 待译文本叶子：``(JSON 指针, 英文原文)``。指针用于回填译文（见 set_at_pointer）。
    todo: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict:
        """给报告用的扁平字典。**不含 todo 明细**——它可能有上万条，
        写进 review-config-structure.json 会把那个文件撑成几 MB。"""
        out = {k: v for k, v in self.__dict__.items() if k != "todo"}
        out["todo_count"] = len(self.todo)
        return out


#: 疑似可读文本：有一定长度、含空格、不是资源 ID 形态。
_TEXT_HINT = re.compile(r"^[A-Za-z][A-Za-z0-9 ,.'!?()\[\]{}%:;\-_/&+]{9,}$")


def looks_textlike(v: str) -> bool:
    """区分「玩家看得见的文本」与「资源 ID / 数值」。

    the_vault 的 config 里有海量字符串叶子其实是 ID
    （``idona_altar``、``minecraft:stone``、``NORMAL``）。不区分的话，
    「保留英文叶子 390,399」这种数字会让人误以为汉化率只有 7%。
    """
    if len(v) < 6:
        return False
    if not re.search(r"[A-Za-z]{3,}", v):
        return False
    if NS_ID.match(v) or FIELD_LIST.match(v):
        return False
    if " " in v:
        return len(re.findall(r"[A-Za-z]{2,}", v)) >= 1
    # 无空格：只接受较长且非全大写下划线风格的值
    if v.isupper() or "_" in v:
        return False
    return bool(_TEXT_HINT.match(v)) and len(v) >= 10


def _collect_todo(node: Any, segs: list[str], stat: MergeStat) -> None:
    """整块新增（ours 无对应）的子树：把里面的可见文本登记为待译。

    之前这里只做 ``kept_en += _count_leaves(v)`` 不递归，于是**新版新增的整个
    配置段落**（如新加的一类装饰件）内部文本既没进 kept_en_text，也永远不出现在
    待译清单里——译员根本看不到它们。既然译文要靠人工，就必须让它可见。
    """
    if isinstance(node, str):
        if not has_cjk(node) and looks_textlike(node):
            stat.kept_en_text += 1
            stat.todo.append((ptr_join(segs), node))
        else:
            stat.kept_en_other += 1
        return
    if isinstance(node, dict):
        for k, v in node.items():
            _collect_todo(v, segs + [ptr_key(k)], stat)
        return
    if isinstance(node, list):
        for i, v in enumerate(node):
            _collect_todo(v, segs + [ptr_index(i)], stat)


def merge_json_text(base: Any, ours: Any, stat: MergeStat, _depth: int = 0,
                    _segs: list[str] | None = None) -> Any:
    """以 ``base``（新版结构）为准，用 ``ours``（旧版中文）回填字符串叶子。

    规则
    ----
    * ``dict``：键集合以 base 为准；base 有而 ours 无 → 保留 base（新增字段）
    * ``list``：长度以 base 为准，逐位递归
    * ``str``：ours 同位置也有字符串时取 ours（视为已译）；否则保留 base
    * 其他类型：一律取 base

    这样保证**结构永不退化**，最多是某些叶子仍是英文。

    保留英文的可见文本会连同它的 JSON 指针记进 ``stat.todo``，供人工翻译后
    用 ``set_at_pointer`` 原路回填。
    """
    segs = _segs or []

    if isinstance(base, dict):
        if not isinstance(ours, dict):
            stat.structure_changed = True
            _collect_todo(base, segs, stat)
            return base
        out = {}
        for k, v in base.items():
            if k in ours:
                out[k] = merge_json_text(v, ours[k], stat, _depth + 1,
                                         segs + [ptr_key(k)])
            else:
                out[k] = v
                stat.kept_en += _count_leaves(v)
                _collect_todo(v, segs + [ptr_key(k)], stat)
        for k in ours:
            if k not in base:
                stat.stale_zh += _count_leaves(ours[k])
        return out

    if isinstance(base, list):
        if not isinstance(ours, list):
            stat.structure_changed = True
            _collect_todo(base, segs, stat)
            return base
        out = []
        for i, v in enumerate(base):
            if i < len(ours):
                out.append(merge_json_text(v, ours[i], stat, _depth + 1,
                                           segs + [ptr_index(i)]))
            else:
                out.append(v)
                stat.kept_en += _count_leaves(v)
                _collect_todo(v, segs + [ptr_index(i)], stat)
        if len(ours) > len(base):
            stat.stale_zh += sum(_count_leaves(x) for x in ours[len(base):])
        return out

    if isinstance(base, str):
        # 旧中文回填；base 已是中文（上游自带）则不被覆盖
        if isinstance(ours, str) and ours != base and has_cjk(ours) and not has_cjk(base):
            stat.filled += 1
            return ours
        stat.kept_en += 1
        if looks_textlike(base):
            stat.kept_en_text += 1
            if not has_cjk(base):
                stat.todo.append((ptr_join(segs), base))
        else:
            stat.kept_en_other += 1
        return base

    return base


def _count_leaves(node: Any) -> int:
    if isinstance(node, dict):
        return sum(_count_leaves(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_leaves(v) for v in node)
    return 1


def merge_json_file(base_bytes: bytes, ours_bytes: bytes, path: str) -> tuple[Any, MergeStat]:
    """合并一个 config json，返回 (结果对象, 统计)。"""
    stat = MergeStat(path=path)
    base = load_json_safe(base_bytes)
    ours = load_json_safe(ours_bytes)
    if base is None:
        stat.base_ok = False
        stat.ours_ok = ours is not None
        return None, stat
    if ours is None:
        stat.ours_ok = False
        return base, stat
    return merge_json_text(base, ours, stat), stat


# --------------------------------------------------------------------------- #
# 文件集合（帕秋莉 / KubeJS）
# --------------------------------------------------------------------------- #
@dataclass
class SetDelta:
    label: str
    ours: set[str] = field(default_factory=set)
    base_en: set[str] = field(default_factory=set)

    @property
    def missing(self) -> list[str]:
        return sorted(self.base_en - self.ours)

    @property
    def extra(self) -> list[str]:
        return sorted(self.ours - self.base_en)

    def stats(self) -> dict:
        return {
            "label": self.label,
            "ours": len(self.ours),
            "base_en": len(self.base_en),
            "missing": len(self.missing),
            "extra": len(self.extra),
        }
