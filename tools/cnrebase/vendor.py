"""第三方模组语言通道：把汉化扩展到整合包自带（但未汉化）的模组上。

为什么必须单独开一条通道
------------------------
汉化模组只有两条「硬编码」通道，且都拦不到语言键渲染的文本：

* ``TextComponentMixin`` 只在 ``Component.literal("...")`` 构造时改写；
* ``FontMixin`` 注入了 ``Font`` 的 11 个方法，但**只有 3 个 String 重载真的调用
  ``LiteralTranslator.translate``**，Component / FormattedCharSequence 那 8 个
  处理器是空壳。

而 JEI 页签、物品名、方块名走的是「语言键 → TranslatableComponent → Component 渲染」，
两条通道都够不着。所以第三方模组**只能靠补语言文件**。

覆盖面事实（0.34.1 实测，服务端包 408 个 mod jar）
--------------------------------------------------
* 语言表通道只覆盖 5 个命名空间（``the_vault`` ``woldsvaults`` ``kubejs``
  ``qolhunters`` ``packmenu``）；
* 全量缺口约 **313 个命名空间 / 36297 个键**，其中 178 个命名空间**整包零中文**。

本模块负责把这份缺口导出成待译清单，并把译文写回 ``assets/<ns>/lang/zh_cn.json``。

必须以「模组自带 zh_cn」为底
----------------------------
语言文件是**整文件**语义：我方只提供一个同名文件，它在某一优先级上顶替模组自带
的那份。若只写稀疏的新词条，模组原有的中文会**整片消失**。
（``mekanism`` 自带 1446 键、``occultism`` 自带 801 键，这类必须先取底再做增量。）

同路径优先级
------------
我方 jar 与模组 jar 对同一 ``assets/<ns>/lang/zh_cn.json`` 是「同路径竞争」，
由资源包顺序决定谁生效，而顺序不由本项目控制。因此：

* 模组**没有** zh_cn（占多数）→ 只有我方文件存在，必生效；
* 模组**有** zh_cn 且键缺失 → 两层会累积，我方独有的键生效；
* 模组**有** zh_cn 但值是英文（「伪翻译」）→ 仅在这种情况下存在被顶掉的风险。

第三种正是 ``Compressium`` 的 ``itemGroup.compressium``（en/zh 都是
``Compressium``）；``fake()`` 专门把它捞出来当待译，并在报告里单列。
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: 已由「语言表通道」管理的命名空间。vendor 通道不再接管，否则同一份
#: ``assets/<ns>/lang/zh_cn.json`` 会被两条通道分别写入，后写的覆盖先写的。
LANG_CHANNEL_NS = frozenset({
    "the_vault", "woldsvaults", "kubejs", "qolhunters", "packmenu",
})

_LANG_RE = re.compile(r"^assets/([^/]+)/lang/(en_us|zh_cn)\.json$")
_MOD_TOML = ("META-INF/mods.toml", "META-INF/neoforge.mods.toml")
_MODID_RE = re.compile(r'modId\s*=\s*"([^"]+)"')
# printf 占位符：%s / %1$s / %d / %.2f / %% 等
_PLACEHOLDER_RE = re.compile(r"%(?:\d+\$)?[-#+ 0,(]*\d*(?:\.\d+)?[a-zA-Z%]")


def _has_letter(s: str) -> bool:
    """原文里是否含至少一个**实义**字母 —— 「这条有没有可翻的东西」的判据。

    ``cropTier...1 = "1"``、``tooltip...buff_line = " - %s (%s)"`` 这类条目
    中文原文就该与英文**逐字相同**：既不算伪翻译，也没有可翻的内容。把它们
    收进待译清单只会制造一批永远清不掉的尾巴。

    判据必须**先剥掉 printf 占位符**再找字母 —— 否则 ``" - %s (%s)"`` 里的
    ``s``（``%s`` 的格式符）会被当成实义字母，判据失效（已踩过）。``§`` 样式码
    一并剥掉。
    """
    stripped = _PLACEHOLDER_RE.sub("", s.replace("\u00a7", ""))
    return any("a" <= c.lower() <= "z" for c in stripped)


@dataclass
class ModLang:
    """一个模组命名空间的语言表。``en`` 是全部可译键，``zh`` 是**模组自带**的。"""

    ns: str
    jar: str = ""
    modid: str = ""
    en: dict[str, str] = field(default_factory=dict)
    zh: dict[str, str] = field(default_factory=dict)

    def missing(self) -> list[str]:
        """键存在、自带 zh 里没有 —— 界面显示英文。"""
        return [k for k in self.en if k not in self.zh]

    def fake(self) -> list[str]:
        """自带 zh 里有键、值却**等于英文** —— 界面同样显示英文。

        ``Compressium`` 的 ``itemGroup.compressium`` 就是这种：作者建了 zh_cn
        条目却忘了翻，于是「有中文文件」却仍是英文页签，最容易让人误判成
        「工具没生效」。

        **值里没有字母的不算伪翻译**（见 :func:`_has_letter`）：形如
        ``cropTier...1 = "1"`` 的条目，中文原文本来就该与英文一致，算作
        待译会让「待译数」永远清不到零。
        """
        return [
            k for k in self.zh
            if k in self.en and self.zh[k] == self.en[k] and _has_letter(self.en[k])
        ]

    def todo_keys(self) -> list[str]:
        """待译键 = 缺键 ∪ 伪翻译，且**原文非空、含字母**。"""
        return sorted(
            k for k in (set(self.missing()) | set(self.fake()))
            if self.en.get(k, "").strip() and _has_letter(self.en[k])
        )

    def stats(self) -> dict:
        return {
            "ns": self.ns,
            "jar": self.jar,
            "modid": self.modid,
            "en": len(self.en),
            "self_zh": len(self.zh),
            "missing": len(self.missing()),
            "fake_zh": len(self.fake()),
        }


# --------------------------------------------------------------------------- #
# 扫描
# --------------------------------------------------------------------------- #
def _read_jar(data: bytes, jar_name: str, out: dict[str, ModLang]) -> None:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        return
    modid = ""
    for tp in _MOD_TOML:
        if tp in z.namelist():
            m = _MODID_RE.search(z.read(tp).decode("utf-8", "replace"))
            if m:
                modid = m.group(1)
            break
    for n in z.namelist():
        m = _LANG_RE.match(n)
        if not m:
            continue
        ns, code = m.group(1), m.group(2)
        try:
            d = json.loads(z.read(n).decode("utf-8", "replace"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        rec = out.setdefault(ns, ModLang(ns=ns, jar=jar_name, modid=modid))
        if not rec.modid:
            rec.modid = modid
        # 只收字符串值：语言文件里偶有嵌套结构，直接透传会让后续 JSON 写出
        # 出现非字符串叶子，玩家侧加载时静默丢弃整份文件。
        pairs = {k: v for k, v in d.items() if isinstance(v, str)}
        (rec.en if code == "en_us" else rec.zh).update(pairs)


def scan_zipfile(zf: zipfile.ZipFile, prefix: str = "mods/") -> dict[str, ModLang]:
    """扫描整合包 zip 内 ``mods/*.jar``。``prefix`` 兼容服务端包的平铺结构。"""
    out: dict[str, ModLang] = {}
    for n in zf.namelist():
        if not (n.startswith(prefix) and n.lower().endswith(".jar")):
            continue
        try:
            _read_jar(zf.read(n), n.rsplit("/", 1)[-1], out)
        except Exception:
            continue
    return out


def scan_dir(mods_dir: Path | str) -> dict[str, ModLang]:
    """扫描一个实例的 ``mods/`` 目录（补服务端包缺少的纯客户端模组）。

    部分模组（JEI、地图、优化类）只在客户端出现，服务端包里根本不存在，
    因此把实例目录作为可选扫描源。
    """
    out: dict[str, ModLang] = {}
    d = Path(mods_dir)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jar")):
        try:
            _read_jar(p.read_bytes(), p.name, out)
        except Exception:
            continue
    return out


def merge(*tables: dict[str, ModLang]) -> dict[str, ModLang]:
    """合并多份扫描结果。先到者优先，缺的字段由后者补。"""
    out: dict[str, ModLang] = {}
    for t in tables:
        for ns, rec in t.items():
            cur = out.get(ns)
            if cur is None:
                out[ns] = ModLang(ns, rec.jar, rec.modid, dict(rec.en), dict(rec.zh))
                continue
            # 已有键不覆盖（保持「先到者优先」，让服务端包这份权威来源说话），
            # 只补它没有的。jar 名保留先到的，便于报告里定位来源。
            for k, v in rec.en.items():
                cur.en.setdefault(k, v)
            for k, v in rec.zh.items():
                cur.zh.setdefault(k, v)
            if not cur.modid:
                cur.modid = rec.modid
    return out


# --------------------------------------------------------------------------- #
# 待译 / 生成
# --------------------------------------------------------------------------- #
def todo(
    table: dict[str, ModLang],
    known: dict[str, dict[str, str]],
    exclude: frozenset[str] = LANG_CHANNEL_NS,
    base: dict[str, dict[str, str]] | None = None,
) -> list[tuple[str, str, str]]:
    """导出待译三元组 ``(命名空间, 键, 英文原文)``。

    ``known`` 是译料层已有的译文，``base`` 是 CFPA 底已有的译文；两者其一有的都不再
    列出——这是「翻过的不会再被要求翻」的落点。``exclude`` 里的命名空间归语言表
    通道管，这里跳过。
    """
    base = base or {}
    rows: list[tuple[str, str, str]] = []
    for ns in sorted(table):
        if ns in exclude:
            continue
        rec = table[ns]
        have = known.get(ns, {})
        have_base = base.get(ns, {})
        for k in rec.todo_keys():
            if k in have or k in have_base:
                continue
            rows.append((ns, k, rec.en[k]))
    return rows


def load_lang_source(
    path: Path | str, only: set[str] | None = None
) -> dict[str, dict[str, str]]:
    """读取一份**外部语言表来源**（资源包 zip 或目录），返回 ``{ns: {键: 中文}}``。

    用途是 CFPA 汉化资源包（``Minecraft-Mod-Language-Package`` 的 1.18 构建，
    见 :data:`CFPA_PACK`）。它覆盖 1600+ 个命名空间、18 万条译文，是「整包零
    中文」模组的主要来源 —— 光靠本项目逐条翻，那 3 万多条是清不完的。

    它只当**底**用（层级低于本项目译料、高于模组自带 zh）：拿它的整份文件保底，
    我们自己的译名再盖上去。``only`` 用于只取本包需要的命名空间，省内存。
    """
    out: dict[str, dict[str, str]] = {}
    p = Path(path)
    if not p.exists():
        return out

    def _take(name: str, raw: bytes) -> None:
        m = _LANG_RE.match(name)
        if not m or m.group(2) != "zh_cn":
            return
        ns = m.group(1)
        if only is not None and ns not in only:
            return
        try:
            d = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            return
        if not isinstance(d, dict):
            return
        out.setdefault(ns, {}).update(
            {k: v for k, v in d.items() if isinstance(v, str) and v.strip()}
        )

    if p.is_dir():
        for f in sorted(p.rglob("*.json")):
            try:
                rel = f.relative_to(p).as_posix()
            except ValueError:
                continue
            _take(rel, f.read_bytes())
        return out

    try:
        with zipfile.ZipFile(p) as z:
            for n in z.namelist():
                if n.endswith("/lang/zh_cn.json"):
                    try:
                        _take(n, z.read(n))
                    except Exception:
                        continue
    except Exception:
        return out
    return out


#: CFPA 汉化资源包（1.18 Forge）在本仓库内的固定位置。
#: 它由上游 ``autobuild`` 频道发布，署名 CFPA 团队；入库是为了构建**可复现**
#: 且**离线可用**。来源与协议见同目录 ``cfpa-mods-1.18.zip`` 内的 ``README.txt``。
CFPA_PACK = "translations/cn-rebase/cfpa-mods-1.18.zip"

#: 从 CFPA **其他 Minecraft 版本**（1.16 / 1.19 / 1.20 / 1.21）构建里，只挑
#: 1.18 那份缺的键，合并成的一份「补齐底」。模组换大版本时语言键基本不变，
#: 所以这些真人的译文可以直接补 1.18 的空白（``buildscape`` 这类 1.18 独有的
#: 模组拿不到，但 ``rechiseled`` ``dyenamicsandfriends`` ``occultism`` 拿到了）。
CFPA_EXTRA_PACK = "translations/cn-rebase/cfpa-mods-extra.zip"


def load_base(*paths: Path | str, only: set[str] | None = None) -> dict[str, dict[str, str]]:
    """按顺序叠加多份语言表来源，**先到者优先**（用于构造「底」）。"""
    out: dict[str, dict[str, str]] = {}
    for p in paths:
        for ns, d in load_lang_source(p, only=only).items():
            slot = out.setdefault(ns, {})
            for k, v in d.items():
                slot.setdefault(k, v)
    return out


def build_lang(
    rec: ModLang,
    zh_by_key: dict[str, str],
    base: dict[str, str] | None = None,
) -> dict[str, str]:
    """生成最终语言表：**模组自带 zh → CFPA 底 → 我方译料**，后层覆盖前层。

    顺序不能反——语言文件是整文件语义，只写增量会让模组原有中文整片消失。
    CFPA 放在模组自带 zh **之上**：模组自带的常常只有一半甚至值是英文（伪翻译），
    CFPA 那份更完整；而我们自己的译料又压在 CFPA 之上，因为本项目的译名是按
    整合包术语表统一过的（如 ``Hedge→树篱``、``Manasteel→魔钢``）。
    """
    out = dict(rec.zh)
    if base:
        out.update(base)
    out.update(zh_by_key)
    return out


def effective(
    table: dict[str, ModLang],
    known: dict[str, dict[str, str]],
    exclude: frozenset[str] = LANG_CHANNEL_NS,
    base: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """算出要写进产物的语言表：处理「译料或 CFPA 底里有内容」的命名空间。

    两者都为空的命名空间不必生成文件——生成出来只会等于模组自带那份，
    徒增体积，还会平白多占一次同路径竞争。
    """
    out: dict[str, dict[str, str]] = {}
    base = base or {}
    for ns, rec in table.items():
        if ns in exclude:
            continue
        zh = known.get(ns)
        b = base.get(ns)
        if not zh and not b:
            continue
        out[ns] = build_lang(rec, zh or {}, b)
    return out


# --------------------------------------------------------------------------- #
# 术语反查表
# --------------------------------------------------------------------------- #
#: 反查表收录的原文长度上限 —— 只收「词条」级别，不收整段话。
TERM_MAX_EN = 40


def term_table(table: dict[str, ModLang]) -> tuple[dict[str, str], dict[str, str]]:
    """建「英文原文 → 包内既有中文」反查表，返回 ``(表, 来源)``。

    收录范围：某个命名空间里 ``en_us`` 与自带 ``zh_cn`` **同一键**且译文不同、
    原文不超过 :data:`TERM_MAX_EN` 字符、不含换行的条目。

    用途是**术语一致性**，不是「直接抄」。翻新模组时先来这里查一遍：
    ``Hedge`` 在包里已经有既有译法（``树篱``）、``Flywheel`` 有、``Cobalt`` 有 ——
    沿用它们，全包译名才统一。查不到再自己定。

    ``来源`` 是 ``英文 → "命名空间:键"``，用于回溯源（注释里可以写出处，
    也便于发现某个词条其实来自一个不相关的模组而需要人工判断）。
    """
    out: dict[str, str] = {}
    src: dict[str, str] = {}
    for ns in sorted(table):
        rec = table[ns]
        for k, en in rec.en.items():
            if not isinstance(en, str) or not en.strip() or len(en) > TERM_MAX_EN:
                continue
            if "\n" in en:
                continue
            zh = rec.zh.get(k)
            if not isinstance(zh, str) or not zh.strip() or zh == en:
                continue
            if en in out:
                continue
            out[en] = zh
            src[en] = f"{ns}:{k}"
    return out, src
