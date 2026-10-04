"""版本重基底：以既有汉化模组为模板，按新版本语料重建载荷，产出新 jar。

要点
----
* **class 代码基本零改动**。15 个自研 class 只读取三份载荷，与整合包版本
  解耦；唯一例外是 ``patches`` 对母版遗留署名提示做的字节码静默。
* **config 载荷走结构感知合并**。旧版整文件替换在跨版本时会丢字段，
  这里一律以新版 config 为结构基底，只回填中文叶子。
* **mods.toml 版本约束由实测的依赖 jar 元数据推导**，不硬编码。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.cnrebase import assets, delta, mods, patches, vendor
from tools.cnrebase.corpus import Corpus
from tools.cnrebase.packs import ClientPack, ServerPack

# 汉化模组自身的 modId
SELF_MOD_ID = "woldsvaults_cn"

#: 随仓库管理的「补丁后 class」目录。相对路径即模板（=jar）内的路径；
#: 构建时在字节码补丁之后逐个覆盖进模板，见 :func:`_apply_class_overrides`。
CLASS_OVERRIDES_DIR = Path(__file__).resolve().parent / "class_overrides"


# --------------------------------------------------------------------------- #
#: 载荷里 ``name`` / ``value`` 字段是**游戏主键**（而非显示文本）的配置，
#: 以及每个配置里**必须保持英文**的字段集合。其余字段照常走合并回填中文。
#:
#: 0.34.1 事故链（字节码 + 数据双向核实）：
#:
#: * ``researches.json`` —— ``ResearchDialog`` 的 ``researchName`` 来自
#:   ``ResearchesGUIConfig.getStyles()`` 的**键**（英文），随后做
#:   ``ResearchConfig.getByName(name)``。载荷里 94/95 个 ``name`` 被旧版载荷回填
#:   成中文 → 与 91 个英文样式键交集只剩 **1/95** → ``getByName`` 返回 null →
#:   ``getResearchCost(null)`` NPE → ``descriptionComponent``（``update()`` 偏移
#:   199 才赋值）恒为 null → ``render()`` 抛 NPE → **研究界面打不开**。
#: * ``eternal_aura.json`` —— ``EternalAuraConfig.getByName`` 按 ``name`` 匹配
#:   （``getName().equals``），同文件 ``availableAuras[].value`` 又按它引用。
#: * ``vault_chest.json`` —— ``VaultChestConfig.getEffectByName`` 按 ``name`` 解析
#:   ``LEVELS[].pool[].value``；载荷里 name 与 pool.value 一个中文一个英文 →
#:   ``Optional.map`` 链整段跳过 → **该类陷阱被静默丢弃**（不崩，但机制失效）。
#:
#: 母版 ``ResearchDialogMixin`` 本有 ``translateBack`` 兜底，但反查表**一对多、
#: 大小写与空格敏感**（68929 条中文里 46099 条一对多），实测 ``researches.json``
#: 还原错 3 条（``Stack Upgrading``→``Stack Upgrade``、``Backpacks``→``backpack``、
#: ``RFTools Storage``→``RF Tools Storage ``）。主键保持英文则 ``translateBack``
#: 恒为恒等变换，缺陷再也碰不到。
#:
#: **显示层不受影响**：``TextComponentMixin`` 渲染 ``new TextComponent(英文名)``
#: 时按 ``literal_zh_cn.tsv`` 正向译成中文。前提是「每个英文主键在对照表里都有
#: 条目」——门禁【8】逐条校验，缺一条就红（防「修好崩溃、界面反而变英文」）。
#:
#: **不在此名单的「看似同类」**（已核实，别凭直觉加）：
#:
#: * ``talents.json`` / ``expertises.json`` 的 ``name`` 是**纯显示文本** ——
#:   ``TalentsConfig.getTalentById(String)`` 用 ``id`` 取、
#:   ``ExpertisesConfig.getAll()`` 遍历、``SkillGates`` 判前置一律用
#:   ``Skill.getId()``；``*_gui_styles.json`` 的键同样是 ``id``。
#:   回退只会白丢 44 + 25 条正确译文。
#: * ``researches_groups.json`` 唯一差异是 ``title``（13 条）= 显示用组名，
#:   组主键是 JSON 键（``Special``/``Omega``，从未被翻译）。
PROTECTED_FIELDS: dict[str, frozenset[str]] = {
    "config/the_vault/researches.json": frozenset({"name"}),
    "config/the_vault/eternal_aura.json": frozenset({"name", "value"}),
    "config/the_vault/vault_chest.json": frozenset({"name", "value"}),
}

#: 受保护配置的路径集合（= ``PROTECTED_FIELDS`` 的键）。
PROTECTED_CONFIGS = frozenset(PROTECTED_FIELDS)


#: 字面量对照表里**必须剔除**的键：它们与运行时 ``LiteralTranslator.EMBEDDED_TERMS``
#: 的新增条目是同一批短语。运行时翻译链是「整键 TSV → 模式匹配
#: （``translateKnownColonPrefix`` / ``translateNumericStatLine`` / …）→
#: ``EMBEDDED_TERMS`` 子串替换兜底」：TSV 一旦命中就**短路**后面的兜底。
#: 这些短语的译文由 EMBEDDED_TERMS 统一负责（如 ``Rank``→阶、``Requires``→还需），
#: 若留在 TSV 里会被旧译（``Rank``→等级、``Requires``→需要）抢先命中，
#: 使字节码扩容形同虚设。
#:
#: 实测冲突来源（两表各自核对）：
#:   * 母版内嵌 TSV：``Requires``；
#:   * 译料层 overlay：``Rank`` / ``skill points`` / ``Unlocks rank`` /
#:     ``Row unlocked`` / ``more skill points spent in talents`` /
#:     ``skill points spent in talents``。
#: 其余 3 条（``Next rank`` / ``skill point`` / ``group points``）当前两表都没有，
#: 一并列出以防将来回潮——过滤对不存在的键是空操作。
TSV_DENY_KEYS = frozenset({
    "more skill points spent in talents",
    "skill points spent in talents",
    "skill points",
    "skill point",
    "Unlocks rank",
    "Next rank",
    "Row unlocked",
    "group points",
    "Requires",
    "Rank",
})


def _restore_identifier_fields(merged: Any, base: Any,
                               fields: frozenset[str]) -> int:
    """把 ``merged`` 里被翻译的标识符字段值强制回写成 ``base`` 的新版原文。

    按 JSON 结构逐层对齐（两者同源于新旧两份载荷，指针一一对应），只覆盖
    ``fields`` 里的键，返回改动条数。显示文本字段不受影响，
    因此不会造成「界面又变英文」的副作用（门禁【8】正向兜住这一点）。
    """
    n = 0

    def walk(m: Any, b: Any) -> None:
        nonlocal n
        if isinstance(m, dict):
            if not isinstance(b, dict):
                return
            for k, v in m.items():
                if (k in fields and isinstance(v, str)
                        and isinstance(b.get(k), str)):
                    if v != b[k]:
                        m[k] = b[k]
                        n += 1
                    continue
                walk(v, b.get(k))
        elif isinstance(m, list) and isinstance(b, list):
            for i, v in enumerate(m):
                if i < len(b):
                    walk(v, b[i])

    walk(merged, base)
    return n


# --------------------------------------------------------------------------- #
# 结果
# --------------------------------------------------------------------------- #
@dataclass
class RebaseResult:
    jar_path: Path | None = None
    mods_toml: str = ""
    lang_stats: list[dict] = field(default_factory=list)
    literal_stats: dict = field(default_factory=dict)
    config_stats: list[dict] = field(default_factory=list)
    set_stats: list[dict] = field(default_factory=list)
    pruned: int = 0
    patch_stats: dict[str, dict] = field(default_factory=dict)
    todo_lang: dict[str, dict[str, str]] = field(default_factory=dict)
    #: 含换行/制表符、行式对照表结构上承载不了的硬编码字面量条数
    literal_unrepresentable: int = 0
    todo_literal: dict[str, str] = field(default_factory=dict)
    #: 配置文本待译：``(目标路径, JSON 指针, 英文原文)``
    todo_config: list[tuple[str, str, str]] = field(default_factory=list)
    #: 本轮从译料层叠加进产物的条目数（四个通道）
    corpus_applied: dict[str, int] = field(default_factory=dict)
    #: 第三方模组待译：``(命名空间, 键, 英文原文)``
    todo_vendor: list[tuple[str, str, str]] = field(default_factory=list)
    #: 扫描到的第三方模组命名空间统计
    vendor_stats: list[dict] = field(default_factory=list)
    #: 写进产物的第三方语言文件数
    vendor_files: int = 0
    #: 术语反查表「英文原文 → 包内既有中文」与来源 ``"命名空间:键"``
    term_table: dict[str, str] = field(default_factory=dict)
    term_src: dict[str, str] = field(default_factory=dict)
    #: CFPA 汉化资源包作为「底」层的规模：``{命名空间数, 条目数, 命中本包的命名空间数}``
    cfpa_stats: dict = field(default_factory=dict)
    #: 同路径竞争清单：``{jar 文件名: [命名空间, ...]}`` —— 模组自带 zh_cn 会顶掉我方
    vendor_conflicts: dict[str, list[str]] = field(default_factory=dict)
    #: 本轮为第三方命名空间生成的最终语言表 ``{ns: {键: 中文}}``。
    #: 它既写进我方 mod jar，也用来打一个**汉化资源包**走 OpenLoader 通道
    #: （见 :mod:`tools.cnrebase.langpack` 的文档）。
    vendor_langs: dict[str, dict[str, str]] = field(default_factory=dict)
    #: 载荷 ASCII 化统计：``{"files": 处理文件数, "escaped": 转义字符数,
    #: "skipped": [解析失败而跳过的文件]}``
    payload_escape: dict = field(default_factory=dict)
    #: 本轮按「数据标识符保护」回写为英文原文的配置：
    #: ``"<目标路径>#<回写条数>"``（见 :data:`PROTECTED_FIELDS`）
    protected_configs: list[str] = field(default_factory=list)
    #: 本轮通过 :data:`CONFIG_EXTRA_FILE` 新增进载荷的键：
    #: ``"<目标路径>#<新增条数>"``；目标在清单里但片段为空则不出现
    config_extra: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "jar": self.jar_path.name if self.jar_path else None,
            "lang": self.lang_stats,
            "literal": self.literal_stats,
            "config_files": len(self.config_stats),
            "config_filled": sum(c["filled"] for c in self.config_stats),
            "config_kept_en": sum(c["kept_en"] for c in self.config_stats),
            "config_structure_changed": sum(
                1 for c in self.config_stats if c["structure_changed"]
            ),
            "sets": self.set_stats,
            "pruned_stale": self.pruned,
            "patched_classes": {
                k: v.get("methods", []) for k, v in self.patch_stats.items()
                if v.get("methods")
            },
            "todo_lang_keys": sum(len(v) for v in self.todo_lang.values()),
            "literal_unrepresentable": self.literal_unrepresentable,
            "todo_literal": len(self.todo_literal),
            "todo_config": len(self.todo_config),
            "vendor_namespaces": len(self.vendor_stats),
            "vendor_files": self.vendor_files,
            "todo_vendor": len(self.todo_vendor),
            "cfpa": self.cfpa_stats,
            "vendor_conflicts": len(self.vendor_conflicts),
            "corpus_applied": self.corpus_applied,
            "payload_escape": self.payload_escape,
            "protected_configs": sorted(self.protected_configs),
            "config_extra": sorted(self.config_extra),
            "warnings": self.warnings,
        }


# --------------------------------------------------------------------------- #
# mods.toml
# --------------------------------------------------------------------------- #
def read_mods_toml(template: Path) -> str:
    p = template / "META-INF" / "mods.toml"
    return p.read_text(encoding="utf-8")


def _jar_impl_version(reader: mods.JarReader) -> str:
    """从 MANIFEST.MF 取 Implementation-Version（mods.toml 常用 ${file.jarVersion}）。"""
    try:
        mf = reader.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except Exception:
        return ""
    for line in mf.splitlines():
        if line.lower().startswith("implementation-version:"):
            return line.split(":", 1)[1].strip()
    return ""


def rewrite_mods_toml(
    original: str,
    mod_version: str,
    deps: dict[str, str],
) -> str:
    """更新自身 version 与依赖版本范围。

    ``deps`` 形如 ``{"the_vault": "1.18.2-3.21.6.6884", "woldsvaults": "0.34.1"}``；
    只更新 ``versionRange`` 的下界，保留原来的上界写法。
    """
    out = original
    # 自身 version="..."
    out = re.sub(
        r'(?m)^version\s*=\s*"[^"]*"',
        f'version="{mod_version}"',
        out,
        count=1,
    )
    for mod_id, ver in deps.items():
        pat = re.compile(
            r'(modId\s*=\s*"' + re.escape(mod_id) + r'"\s*\n(?:.*\n)*?'
            r'versionRange\s*=\s*")[^"]*(")'
        )
        floor = f"[{ver},)"
        out, n = pat.subn(lambda m: m.group(1) + floor + m.group(2), out)
        if n == 0:
            out = re.sub(
                r'(modId\s*=\s*"' + re.escape(mod_id) + r'"[^\n]*\n(?:[^\n]*\n)*?versionRange\s*=\s*")[^"]*(")',
                lambda m: m.group(1) + floor + m.group(2),
                out,
            )
    return out


# --------------------------------------------------------------------------- #
# class 覆盖：随仓库管理的补丁后 class
# --------------------------------------------------------------------------- #
def _apply_class_overrides(root: Path) -> dict[str, dict]:
    """把 ``class_overrides/`` 里补丁后的 class 覆盖进模板。

    与 ``patches.apply_all`` 的静默补丁走同一条落盘路径：模板由 ``_fresh_copy``
    每轮从母版 jar 重新解出，故覆盖必须每轮重放。成品 class（如字节码扩容过的
    ``LiteralTranslator``）作为资产入库，构建时直接覆盖，无需本机 JDK 即时生成。
    相对路径即覆盖目标。返回值形状与 :func:`patches.apply_all` 一致，便于并入
    ``res.patch_stats``。
    """
    report: dict[str, dict] = {}
    base = CLASS_OVERRIDES_DIR
    if not base.is_dir():
        return report
    for src in sorted(base.rglob("*.class")):
        rel = src.relative_to(base).as_posix()
        dst = root / rel
        data = src.read_bytes()
        written = (not dst.is_file()) or dst.read_bytes() != data
        if written:
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
        report[rel] = {"methods": [], "override": True,
                       "written": written, "bytes": len(data)}
    return report


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def rebase(
    template: Path,
    out_root: Path,
    pack_version: str,
    mod_version: str,
    client_pack: ClientPack | None = None,
    server_pack: ServerPack | None = None,
    lang_ns: tuple[str, ...] = ("the_vault", "woldsvaults"),
    literal_prefixes: dict[str, tuple[str, tuple[str, ...]]] | None = None,
    corpus: Corpus | None = None,
    vendor_enabled: bool = True,
    mods_dir: Path | None = None,
    verbose: bool = False,
) -> RebaseResult:
    """执行重基底，产出新 jar。``out_root`` 为工作目录。

    ``corpus`` 是累积译料层。母版 jar 是**基线**（随上游升级更新），译料层是
    本项目的**增量**；两者叠加后才写进模板。不传则等价于只用母版基线。

    ``mods_dir`` 指向游戏实例的 ``mods/`` 目录，用来补服务端包里没有的
    **纯客户端模组**（JEI、地图、优化类）。不给也能跑，只是覆盖不到它们。
    """
    res = RebaseResult()
    if corpus is None:
        corpus = Corpus(root=Path("translations/cn-rebase"))
    payload = template / assets.PAYLOAD_IN_JAR
    index = assets.load_index(payload)

    if literal_prefixes is None:
        literal_prefixes = {
            "the_vault": ("the_vault", ("iskallia/vault/",)),
            # jar 名是 wolds-vaults-official-mod-*.jar，片段匹配要用带连字符的写法
            "woldsvaults": ("wolds-vaults", ("xyz/iwolfking/woldsvaults/",)),
        }

    # ------------- 1. 语言表（先把各来源的 en/zh 键集按 ns 汇总，再统一算 delta）-------------
    ours_langs = assets.load_langs(template)
    # 译料层先叠加进「我方」：叠加过的键在 delta 里就不再是「缺键」，
    # 因而不会再次出现在待译清单里。这是「翻过的不会再要求翻」的实现点。
    res.corpus_applied["lang"] = corpus.apply_lang(ours_langs)
    dep_versions: dict[str, str] = {}
    agg: dict[str, dict[str, dict[str, str]]] = {}

    def _add_lang(ns: str, en: dict[str, str], zh: dict[str, str]) -> None:
        slot = agg.setdefault(ns, {"en": {}, "zh": {}})
        slot["en"].update(en)
        slot["zh"].update(zh)

    if server_pack is not None:
        for hint, ns in (("the_vault", "the_vault"), ("wolds", "woldsvaults")):
            m = mods.find_mod_jar(server_pack._zf, hint)
            if not m:
                res.warnings.append(f"服务端包未找到 {hint}")
                continue
            r = mods.reader_from_zip(server_pack._zf, m)
            meta = r.meta()
            ver = meta.version
            if ver.startswith("${"):
                ver = _jar_impl_version(r) or ver
            dep_versions[ns] = (
                f"1.18.2-{ver}"
                if ns == "the_vault" and not ver.startswith("1.18.2")
                else ver
            )
            _add_lang(ns, r.lang(ns, "en_us"), r.lang(ns, "zh_cn"))

    # 整合包 kubejs 目录下的语言表（woldsvaults / kubejs / packmenu / ponderjs）
    for ns, en, zh in _kubejs_langs(client_pack):
        _add_lang(ns, en, zh)

    for ns in sorted(agg):
        slot = agg[ns]
        if not slot["en"]:
            continue
        d = delta.lang_delta(ns, ours_langs.get(f"{ns}/zh_cn", {}), slot["en"], slot["zh"])
        res.lang_stats.append(d.stats())
        ours_langs[f"{ns}/zh_cn"] = delta.apply_lang_delta(d)
        if d.missing_todo:
            res.todo_lang[ns] = d.missing_todo

    # ---------------- 2. 硬编码 ----------------
    tsv = assets.load_literal(template / assets.LITERAL_TSV_IN_JAR)
    # 译料层叠加，并**回写进模板**——这一步不能省：产物 jar 里那份
    # literal_zh_cn.tsv 是靠模板文件打的包，只更新内存里的 known 只会让
    # 待译清单变短，而玩家侧仍然查不到新译文。
    merged_pairs = corpus.apply_literal(tsv.pairs)
    # 剔除与 EMBEDDED_TERMS 冲突的键（见 TSV_DENY_KEYS）。过滤放在 apply_literal
    # **之后**，这样译料层也无法把被拒的键重新带回来（否则 overlay 又把它写回
    # TSV，字节码兜底再次被短路）。
    _kept = [(en, zh) for en, zh in merged_pairs if en not in TSV_DENY_KEYS]
    if len(_kept) != len(merged_pairs):
        res.corpus_applied["literal_denied"] = len(merged_pairs) - len(_kept)
    merged_pairs = _kept
    if corpus.literal:
        added = len(merged_pairs) - len(tsv.pairs)
        res.corpus_applied["literal"] = len(corpus.literal)
        if added > 0:
            res.corpus_applied["literal_added"] = added
    if merged_pairs != tsv.pairs:
        assets.save_literal(template, merged_pairs)
        tsv = assets.LiteralTable(pairs=merged_pairs)
    ld = delta.LiteralDelta(known=tsv.mapping)
    if server_pack is not None:
        for label, (hint, prefixes) in literal_prefixes.items():
            m = mods.find_mod_jar(server_pack._zf, hint)
            if not m:
                res.warnings.append(f"服务端包未找到 {label}（硬编码扫描跳过）")
                continue
            r = mods.reader_from_zip(server_pack._zf, m)
            try:
                found = r.hardcoded(prefixes=prefixes, min_length=3)
            except Exception as e:  # pragma: no cover
                res.warnings.append(f"{label} 硬编码扫描失败: {e}")
                continue
            for k, v in found.items():
                ld.scanned.setdefault(k, []).extend(v)
    res.literal_stats = ld.stats()
    _all_todo = {s: "".join(c[:1]) for s, c in sorted(ld.todo.items())}
    # 含换行/制表符的条目留给报告单独说明，不混进「可交付」的待译数里
    res.todo_literal = {s: v for s, v in _all_todo.items()
                        if chr(10) not in s and chr(13) not in s and chr(9) not in s}
    res.literal_unrepresentable = len(_all_todo) - len(res.todo_literal)

    # ---------------- 2.5 第三方模组语言 ----------------
    # 整合包自带 400+ 个模组，绝大多数没有 zh_cn。它们不在语言表通道的 5 个
    # 命名空间里（the_vault / woldsvaults / kubejs / qolhunters / packmenu），
    # 而界面文本走「语言键 → TranslatableComponent → Component 渲染」，
    # 硬编码通道够不着（见 vendor 模块文档），只能靠补语言文件。
    if vendor_enabled:
        vtables: list[dict[str, vendor.ModLang]] = []
        if server_pack is not None:
            vtables.append(vendor.scan_zipfile(server_pack._zf))
        if mods_dir is not None:
            vtables.append(vendor.scan_dir(mods_dir))
        vtable = vendor.merge(*vtables)
        # CFPA 汉化资源包作为「底」层。没有它，那三万多条「整包零中文」只能靠
        # 本项目逐条翻，是清不完的；有了它，缺口一次性降到一万出头。
        # 第二份是「其他 MC 版本的 CFPA 构建里、1.18 缺的那些键」的补齐底。
        cfpa = vendor.load_base(
            vendor.CFPA_PACK, vendor.CFPA_EXTRA_PACK, only=set(vtable)
        )
        res.cfpa_stats = {
            "namespaces": len(cfpa),
            "entries": sum(len(v) for v in cfpa.values()),
            "hit": len(set(cfpa) & set(vtable)),
        }
        res.todo_vendor = vendor.todo(vtable, corpus.vendor, base=cfpa)
        res.corpus_applied["vendor"] = sum(len(v) for v in corpus.vendor.values())
        # 台账必须在算出 ``todo_vendor`` **之后**生成：缺口口径是「扣掉模组自带 zh
        # 与 CFPA 底」之后的**真实残差**。旧版把这行写在上面的 ``load_base`` 之前，
        # 等于没扣 CFPA —— 报告会把 CFPA 已整包覆盖的 ``chipped``（自带底 7468 键）
        # 仍列成「待译 7467」，把派活引向其实已完成的模组。
        res.vendor_stats = _vendor_stats(
            vtable, corpus.vendor, cfpa, res.todo_vendor
        )
        # 术语反查表：顺带产出，给译员统一译名用（不参与产物）。
        res.term_table, res.term_src = vendor.term_table(vtable)
        # 只给「译料或 CFPA 底里有内容」的命名空间生成文件。空表生成出来等于模组
        # 自带那份，徒增体积，还会平白多占一次同路径竞争。
        langs = vendor.effective(vtable, corpus.vendor, base=cfpa)
        res.vendor_langs = langs
        for ns, data in sorted(langs.items()):
            key = f"{ns}/zh_cn"
            if key in ours_langs:
                # 语言表通道已经管着这个命名空间，以它为准，别两条通道打架
                res.warnings.append(f"vendor 命名空间与语言表通道重名，已跳过: {ns}")
                continue
            ours_langs[key] = data
            res.vendor_files += 1
        # 同路径竞争清单：这些命名空间的模组**自带 zh_cn**，会按资源包加载顺序顶掉
        # 我方那份（顺序不由本项目控制）→ 交付时必须另走「并入模组 jar」通道。
        cf: dict[str, list[str]] = {}
        for ns in sorted(langs):
            rec = vtable.get(ns)
            if rec is None or not rec.zh:
                continue
            cf.setdefault(rec.jar, []).append(ns)
        res.vendor_conflicts = cf

    # ---------------- 3. 配置载荷合并 ----------------
    res.config_stats = _merge_config_payload(
        template, payload, index, client_pack, server_pack, res, corpus
    )

    # ---------------- 4. 集合类载荷差集 ----------------
    res.set_stats, prune = _set_deltas(template, payload, index, client_pack, res)
    res.pruned = _prune_manifest(payload, index, prune)

    # ---------------- 5. 落盘：语言表 ----------------
    assets.save_langs(template, ours_langs)

    # ---------------- 6. mods.toml ----------------
    orig = read_mods_toml(template)
    toml = rewrite_mods_toml(
        orig,
        mod_version=f"{mod_version}-{pack_version}-universal",
        deps=dep_versions,
    )
    res.mods_toml = toml
    (template / "META-INF" / "mods.toml").write_text(toml, encoding="utf-8", newline="\n")

    # ---------------- 6.5 字节码补丁：静默母版遗留的署名/推广提示 ----------------
    # 母版的 WelcomeMessages 会在玩家登录时往聊天栏发一条带原作者署名与
    # QQ 群号的横幅。class 代码原样继承意味着它也会跟着走，故在此掏空方法体。
    patch_stats = patches.apply_all(template)
    # 6.5b class 覆盖：字节码扩容等成品类由仓库资产提供。
    # 覆盖在静默补丁之后，避免两者作用于同一类时顺序不定。
    patch_stats.update(_apply_class_overrides(template))
    res.patch_stats = patch_stats
    for rel, info in patch_stats.items():
        if info.get("error"):
            res.warnings.append(f"字节码补丁失败 {rel}: {info['error']}")
        elif info.get("unmatched"):
            # 一个目标方法都没匹配到：母版很可能改过方法名，必须人工确认
            res.warnings.append(
                f"字节码补丁未匹配到方法 {info['unmatched']}（{rel}）"
            )

    # ---------------- 6.9 载荷 ASCII 化：对系统区域设置免疫 ----------------
    # the_vault 的 iskallia.vault.config.Config.readConfig() 用
    # java.io.FileReader 读全部 config JSON —— FileReader 的字符集**跟随
    # 玩家系统区域**（简中 Windows=GBK、繁中=Big5、英文=cp1252）。我们写进
    # 载荷的 UTF-8 中文在这种系统上必然乱码（实测：简中机器出「浣犲彲」系、
    # 繁中机器出「災爐邊」系）。JSON/JS 的 \uXXXX 转义是语法原生支持的，
    # Gson/Rhino 解析结果与原字符完全一致，而转义后文件变成纯 ASCII，
    # 任何默认编码读进来都无损 → 从根上免疫。
    # 范围：config_payload 下全部 .json / .js。lang JSON 走 vanilla 的
    # UTF-8 显式通道、任务书 SNBT 走 FTB 的 UTF-8 显式通道（均已字节码
    # 核实）， literal TSV 由本模组 UTF-8 显式读取 —— 这三类不动。
    res.payload_escape = _ascii_escape_payload(payload)

    # ---------------- 7. 打包 ----------------
    jar_name = f"{SELF_MOD_ID}-{mod_version}-{pack_version}-universal.jar"
    jar_path = out_root / jar_name
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    _pack_jar(template, jar_path)
    res.jar_path = jar_path
    return res


def _vendor_stats(
    table: dict[str, vendor.ModLang],
    ours: dict[str, dict[str, str]],
    base: dict[str, dict[str, str]],
    todo_vendor: list[tuple[str, str, str]],
) -> list[dict]:
    """第三方命名空间统计，**缺口口径已扣掉 CFPA 底**。

    为什么单列一个函数：旧版直接 ``[vtable[ns].stats() ...]``，缺口
    = 「模组英文键 − 模组自带 zh」，**没有扣 CFPA 底**，于是 CFPA 已整包覆盖
    的命名空间（``chipped`` 自带底 7468 键）在报告里仍显示「待译 7467」，把
    派活引向其实已完成的模组。这里以 ``todo_vendor``（**真正的**待译清单）为准
    回填 ``residual``，使台账与清单**永不脱节**（门禁有 ``sum(残差) == 清单条数``
    的对应断言）。

    每个命名空间在 :meth:`vendor.ModLang.stats` 之上补四个字段：

    * ``cfpa``：CFPA 底为该 ns 提供的、**模组实际用到**的键数（限定在 ``en`` 内，
      避免把与该模组无关的键也算进来）；
    * ``ours``：我方译料（``corpus.vendor``）为该 ns 覆盖的键数（同样限定 ``en``）；
    * ``residual``：真实残差 = ``todo_vendor`` 里该 ns 的条数；
    * ``covered``：``en - residual``（已覆盖键数，便于直接算覆盖率）。

    ``residual`` 与 ``covered`` 均以 ``en`` 为上限，故 ``covered >= 0``。
    """
    residual_by_ns: dict[str, int] = {}
    for ns, _key, _en in todo_vendor:
        residual_by_ns[ns] = residual_by_ns.get(ns, 0) + 1

    stats: list[dict] = []
    for ns in sorted(table):
        rec = table[ns]
        st = rec.stats()
        base_ns = base.get(ns, {})
        ours_ns = ours.get(ns, {})
        st["cfpa"] = sum(1 for k in base_ns if k in rec.en)
        st["ours"] = sum(1 for k in ours_ns if k in rec.en)
        st["residual"] = residual_by_ns.get(ns, 0)
        st["covered"] = len(rec.en) - st["residual"]
        stats.append(st)
    return stats


def _kubejs_langs(client_pack: ClientPack | None) -> list[tuple[str, dict[str, str], dict[str, str]]]:
    """产出整合包 kubejs 目录下各命名空间的语言表。

    整合包自带 ``kubejs/assets/<ns>/lang/en_us.json``（KubeJS 把 kubejs/ 当作
    额外资源根加载），内容会随版本增删键。我方 jar 内的
    ``assets/<ns>/lang/zh_cn.json`` 必须跟上，否则新增词条会显示英文。

    注意 ``woldsvaults`` 这个 ns 模组侧也有语言表，调用方需要**按 ns 汇总**
    再算 delta，否则会重复统计（曾导致覆盖率算出 118.8%）。
    """
    out: list[tuple[str, dict[str, str], dict[str, str]]] = []
    if client_pack is None:
        return out
    for rel in (
        "kubejs/assets/kubejs/lang/en_us.json",
        "kubejs/assets/packmenu/lang/en_us.json",
        "kubejs/assets/ponderjs_generated/lang/en_us.json",
        "kubejs/assets/woldsvaults/lang/en_us.json",
    ):
        raw = client_pack.read_override(rel)
        if raw is None:
            continue
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or not data:
            continue
        ns = rel.split("/")[2]
        en = {str(k): str(v) for k, v in data.items()}
        zh: dict[str, str] = {}
        upstream_zh = client_pack.read_override(f"kubejs/assets/{ns}/lang/zh_cn.json")
        if upstream_zh:
            try:
                d0 = json.loads(upstream_zh.decode("utf-8"))
                if isinstance(d0, dict):
                    zh = {str(k): str(v) for k, v in d0.items()}
            except Exception:
                pass
        out.append((ns, en, zh))
    return out


def _merge_config_payload(
    template: Path,
    payload: Path,
    index: assets.PayloadIndex,
    client_pack: ClientPack | None,
    server_pack: ServerPack | None,
    res: RebaseResult,
    corpus: Corpus,
) -> list[dict]:
    """对全部 config 载荷做结构感知合并，原文件备份为 .orig。"""
    stats: list[dict] = []
    # 目标路径 → 载荷源路径 的两套映射
    jobs: list[tuple[str, str, str]] = []  # (target, source, side)
    for e in index.universal:
        jobs.append((e.target, e.source, "client"))
    for e in index.client:
        jobs.append((e.target, e.source, "client"))
    for e in index.server:
        jobs.append((e.target, e.source, "server"))
    for e in index.repair_client:
        jobs.append((e.target, e.source, "client"))
    for e in index.repair_server:
        jobs.append((e.target, e.source, "server"))

    seen: dict[str, bytes] = {}  # target -> 最终载荷内容
    for target, source, side in jobs:
        if not target.startswith("config/"):
            continue
        if not target.endswith(".json"):
            continue
        src_file = payload / source
        if not src_file.is_file():
            continue

        if target in seen:
            # 同一 target 会同时出现在 universal/client_payload 与
            # repair_payload 里。**每一份载荷源都必须写相同内容**——
            # 预置取哪一份是不确定的，只更新第一份会让另一份的
            # 0.30.0 旧结构悄悄混进产物（曾致 21 个 config 结构退化）。
            src_file.write_bytes(seen[target])
            continue

        # 取新版本基底
        base_bytes: bytes | None = None
        if side == "client" and client_pack is not None:
            base_bytes = client_pack.read_override(target)
        if base_bytes is None and server_pack is not None:
            base_bytes = _server_read(server_pack, target)
        if base_bytes is None:
            continue

        ours_bytes = src_file.read_bytes()

        # 译料层叠加：把人工补译的中文按 JSON 指针写进「我方」那一侧，
        # 再走原有的结构感知合并。这样译文与旧版中文享受完全相同的回填
        # 逻辑（同路径字符串叶子），不需要在合并里开特例分支。
        overlay = corpus.apply_config_overlay(target)
        if overlay:
            obj = delta.load_json_safe(ours_bytes)
            if obj is None:
                res.warnings.append(f"译料无法叠加（载荷 JSON 解析失败）: {target}")
            else:
                hit = sum(1 for ptr, zh in overlay.items()
                          if delta.set_at_pointer(obj, ptr, zh))
                res.corpus_applied["config"] = (
                    res.corpus_applied.get("config", 0) + hit
                )
                miss = len(overlay) - hit
                if miss:
                    # 指针指向的位置在新版已不存在（上游删了字段）。不是错误，
                    # 但要说出来，否则译料里会悄悄累积一堆失效条目。
                    res.warnings.append(
                        f"译料有 {miss} 条指针在新版不存在: {target}"
                    )
                ours_bytes = json.dumps(
                    obj, ensure_ascii=False
                ).encode("utf-8")

        merged, st = delta.merge_json_file(base_bytes, ours_bytes, target)
        if merged is not None and target in PROTECTED_FIELDS:
            # 标识符字段（``name`` / ``value``）是游戏主键，**一律回写成新版
            # 英文原文**。旧版载荷把它们翻成中文 → getByName 落空 →
            # ResearchDialog.render 抛 NPE / 金库箱陷阱被静默丢弃（详见
            # PROTECTED_FIELDS 上方注释）。显示层汉化不受影响：
            # TextComponentMixin 渲染时按字面量对照表把英文名正向译成中文，
            # 前提是该英文名在对照表里有条目 —— 门禁【8】逐条校验这个前提。
            _base_obj = delta.load_json_safe(base_bytes)
            if _base_obj is None:
                res.warnings.append(f"保护配置基底解析失败，标识符未校验: {target}")
            else:
                _fixed = _restore_identifier_fields(
                    merged, _base_obj, PROTECTED_FIELDS[target]
                )
                if _fixed:
                    res.protected_configs.append(f"{target}#{_fixed}")
        if merged is None:
            # 基底解析失败：**绝不保留旧版载荷**——那会把 0.30.0 的旧结构
            # 预置进 0.34.1 包里（曾致 the_vault 报「配置无效」）。改用新版原文。
            res.warnings.append(f"基底解析失败，载荷改用新版原文: {target}")
            data = base_bytes
        elif st.filled == 0:
            # 无中文可回填：merged 恒等于 base，直接落**新版原始字节**
            # （格式零改动）。旧逻辑在这里「保留旧版载荷」，导致纯数据
            # 配置（abilities_vignette / skill_gates / talents_gui_styles
            # 等 34 个文件）被旧结构覆盖，新增字段全部丢失。
            data = base_bytes
        else:
            data = (json.dumps(merged, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

        # 「新增配置键」通道：上游压根没写的条目（如研究说明）由译料层的
        # config_extra.json 补上。**必须放在 data 定型之后**——否则
        # st.filled == 0（无可回填）与基底解析失败这两条「直接落新版原始
        # 字节」的分支会把新增键吞掉。默认只增不改（见 _merge_extra_keys），
        # 已存在的译文不会被覆盖；EXTRA_OVERWRITE 白名单里的目标例外，
        # 允许覆盖已存在的键（用于把上游伪翻译的英文说明替换成中文）。
        _extra = corpus.extra_for(target)
        if _extra is not None:
            _obj = delta.load_json_safe(data)
            if _obj is None:
                res.warnings.append(
                    f"config_extra 无法叠加（JSON 解析失败）: {target}")
            else:
                _ovr = target in EXTRA_OVERWRITE
                _add, _skip = _merge_extra_keys(_obj, _extra, overwrite=_ovr)
                if _skip:
                    res.warnings.append(
                        f"config_extra 有 {len(_skip)} 处被跳过（"
                        f"{'结构不符' if _ovr else '键已存在或结构不符'}）"
                        f": {target} 例={_skip[:2]}")
                if _add:
                    data = (json.dumps(
                        _obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                    res.config_extra.append(f"{target}#{_add}")
                    res.corpus_applied["config_extra"] = (
                        res.corpus_applied.get("config_extra", 0) + _add)
        src_file.write_bytes(data)
        seen[target] = data
        stats.append(st.as_dict())
        for ptr, en in st.todo:
            res.todo_config.append((target, ptr, en))
    _apply_extra_sweep(payload, seen, res, corpus)
    return stats


def _apply_extra_sweep(payload: Path, seen: dict[str, bytes],
                       res: RebaseResult, corpus: Corpus) -> None:
    """兜底：把 ``config_extra`` 应用到**载荷目录里存在、但主循环没走到**的目标。

    为什么需要：主循环按五份清单枚举 job，而 ``manifest.txt`` 是**单列**的
    （``parse_manifest`` 令 ``source == target``）。有些目标只存在于
    ``config_payload/config/<target>`` 一处，恰好没被任何一份清单枚举到，
    于是译料层里明明写了译文、产物里却没生效 ——
    2026-10-03 实测 ``config/the_vault/lang/zh_cn/quest/sky_quests.json``
    就是这样漏掉 ``archetypes`` 那条任务的。

    ``config_extra`` 语义上是「最后一层叠加」，那就对**所有落盘的目标**兜底跑一遍，
    幂等（已存在的键/元素会被跳过），不会覆盖主循环的结果。
    """
    for target, extra in corpus.extra_targets():
        if target in seen:
            continue
        src_file = payload / target
        if not src_file.is_file():
            continue
        data = src_file.read_bytes()
        obj = delta.load_json_safe(data)
        if obj is None:
            res.warnings.append(f"config_extra 兜底：JSON 解析失败 {target}")
            continue
        add, skip = _merge_extra_keys(obj, extra,
                                      overwrite=target in EXTRA_OVERWRITE)
        if skip:
            res.warnings.append(
                f"config_extra 兜底有 {len(skip)} 处被跳过: {target} 例={skip[:2]}")
        if add:
            src_file.write_bytes(
                (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
            seen[target] = src_file.read_bytes()
            res.config_extra.append(f"{target}#{add}(兜底)")
            res.corpus_applied["config_extra"] = (
                res.corpus_applied.get("config_extra", 0) + add)


def _server_read(sp: ServerPack, name: str) -> bytes | None:
    return sp.read(name) if sp.exists(name) else None


#: 允许 config_extra **覆盖已存在键**的目标白名单。默认的只增不改语义
#: 是为了保护人工校对过的译文；但该目标里存有上游**伪翻译**的英文
#: （zh_cn 说明表整文件就是英文复制品），必须允许整键替换。
EXTRA_OVERWRITE = frozenset({
    "config/the_vault/lang/zh_cn/skill_descriptions.json",
    # 主文件 config/the_vault/skill_descriptions.json（442 键，含 9 个 null 专精
    # 与 33 条英文回退条目）需要被 config_extra 覆盖，使 zh_cn 与英文回退口径一致。
    "config/the_vault/skill_descriptions.json",
})


def _merge_extra_keys(dst: object, extra: object,
                      path: str = "",
                      overwrite: bool = False) -> tuple[int, list[str]]:
    """把 ``extra`` 深合并进 ``dst``。

    返回 ``(新增/覆盖键数, 被跳过的路径)``。约定：

    * 默认（``overwrite=False``）**只增不改**：目标处**已存在**的键一律
      跳过 —— 译料层/上游的值优先，``config_extra`` 只负责补上游压根
      没写的条目。否则一次手滑就会静默覆盖掉人工校对过的译文。
    * ``overwrite=True``（仅限 :data:`EXTRA_OVERWRITE` 白名单目标）：
      已存在的键允许被替换 —— 用于清洗上游伪翻译的英文内容。
    * 目标处结构对不上（期望 dict 实际是标量/数组）也跳过并上报，
      不硬塞 —— 那说明上游结构变了，需要人工看。
    """
    added = 0
    skipped: list[str] = []
    if isinstance(extra, dict):
        if not isinstance(dst, dict):
            return 0, [path or "/"]
        for k, v in extra.items():
            p = f"{path}/o:{k}"
            if isinstance(v, dict):
                sub = dst.get(k)
                if not isinstance(sub, dict):
                    # 目标没有这一层 → 整段挂上来（这本身就是「新增」）
                    if k not in dst or overwrite:
                        dst[k] = {}
                        added += 1
                    else:
                        skipped.append(p)
                        continue
                a, s = _merge_extra_keys(dst[k], v, p, overwrite)
                added += a
                skipped.extend(s)
            elif isinstance(v, list) and isinstance(dst.get(k), list):
                # 数组：按元素身份追加（见下面的 list 分支），不能整段替换 ——
                # 整段替换会把译文副本里已有的 hundreds 条一并丢掉。
                a, s = _merge_extra_keys(dst[k], v, p, overwrite)
                added += a
                skipped.extend(s)
            else:
                if k in dst and not overwrite:
                    skipped.append(p)
                else:
                    dst[k] = v
                    added += 1
    elif isinstance(extra, list):
        # 数组：只能「按 id 追加缺失元素」，不能按位置合并 —— 上游与译文副本
        # 顺序一致但长度可能不同（上游漏译就少一个元素），按下标比会整段错位。
        # 元素身份：dict 取 ``item``/``id``，否则用整元素的 JSON 指纹。
        if not isinstance(dst, list):
            skipped.append(path or "/")
            return added, skipped
        have = {_elem_id(e) for e in dst}
        for e in extra:
            k = _elem_id(e)
            if k in have:
                skipped.append(f"{path}#{k}")
                continue
            dst.append(e)
            have.add(k)
            added += 1
    return added, skipped


def _elem_id(e: object) -> str:
    """数组元素的身份键：有 ``item``/``id`` 就用它，否则用规范化 JSON。"""
    if isinstance(e, dict):
        for k in ("item", "id"):
            if isinstance(e.get(k), str) and e[k]:
                return f"{k}={e[k]}"
    return "json=" + json.dumps(e, ensure_ascii=False, sort_keys=True)


def _set_deltas(
    template: Path,
    payload: Path,
    index: assets.PayloadIndex,
    client_pack: ClientPack | None,
    res: RebaseResult,
) -> tuple[list[dict], set[str]]:
    """手册页 / 进度文本的集合差集。

    返回 ``(统计列表, 孤儿目标路径集合)``。孤儿路径会被后续从清单里剔除。

    两条容易踩的坑：

    1. 两侧路径的**语言段不同**（我方 ``zh_cn``、新版只有 ``en_us``）。不归一化
       会得出「整本书都没汉化」的假结论。
    2. KubeJS 只比**含文本**的文件（进展 + lang json）。recipes / loot_tables /
       贴图等纯数据无需汉化，纳入比较只会制造几百条噪声。
    """
    out: list[dict] = []
    pruned: set[str] = set()
    if client_pack is None:
        return out, pruned
    ov = {n[len(client_pack.overrides_prefix):] for n in client_pack.overrides_members()}

    # 帕秋莉手册：只比「页」（路径里带语言段的条目）
    ours_pj: dict[str, str] = {
        delta.normalize_page_path(e.target): e.target
        for e in index.universal
        if e.target.startswith("patchouli_books/") and delta.LANG_SEG.search(e.target)
    }
    base_pj = {
        delta.normalize_page_path(n)
        for n in ov
        if n.startswith("patchouli_books/") and "/en_us/" in n
    }
    d_pj = delta.SetDelta("帕秋莉手册", set(ours_pj), base_pj)
    out.append(d_pj.stats())
    pruned |= {ours_pj[k] for k in d_pj.extra}

    # KubeJS：只比进展文件。
    # 语言文件（kubejs/assets/*/lang/*.json）虽然也在 kubejs 目录下，但我方是把它
    # 打进 jar 的 assets/<ns>/lang/zh_cn.json，路径形态不同，且已在第一节目录里
    # 单独对齐过——混进来只会产生「4 个文件缺汉化」这种假缺口。
    def _kj_text(p: str) -> bool:
        return p.startswith("kubejs/") and delta.is_advancement(p)

    ours_kj: dict[str, str] = {
        delta.normalize_page_path(e.target): e.target
        for e in index.universal
        if _kj_text(e.target)
    }
    base_kj = {delta.normalize_page_path(n) for n in ov if _kj_text(n)}
    d_kj = delta.SetDelta("KubeJS 文本", set(ours_kj), base_kj)
    out.append(d_kj.stats())
    pruned |= {ours_kj[k] for k in d_kj.extra}

    if d_pj.missing:
        res.warnings.append(f"帕秋莉手册有 {len(d_pj.missing)} 个新版页面未汉化")
    if d_kj.missing:
        res.warnings.append(f"KubeJS 有 {len(d_kj.missing)} 个新版文本文件未汉化")
    return out, pruned


def _prune_manifest(payload: Path, index: assets.PayloadIndex, prune: set[str]) -> int:
    """从清单中剔除目标路径已失效的条目并回写。

    0.34.1 移除了 ``izzy_vault`` 命名空间，我方 199 个对应进展文件因此成了孤儿。
    留着它们只会在实例里堆无用文件，且清单指向不存在的资源。
    """
    if not prune:
        return 0
    n = 0
    for attr in ("universal", "client", "server", "repair_client", "repair_server"):
        entries = getattr(index, attr)
        if not entries:
            continue
        kept = []
        for e in entries:
            if e.target in prune:
                n += 1
                continue
            kept.append(e)
        setattr(index, attr, kept)
    if n:
        assets.save_index(payload, index)
    return n


def _pack_jar(src_dir: Path, jar_path: Path, compress: bool = True) -> None:
    """把目录打包成 jar。保持稳定顺序，语言/载荷文件优先。"""
    mode = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
    files: list[tuple[str, Path]] = []
    for dp, _dn, fn in os.walk(src_dir):
        for f in fn:
            full = Path(dp) / f
            rel = full.relative_to(src_dir).as_posix()
            files.append((rel, full))

    def sort_key(item: tuple[str, Path]) -> tuple:
        rel = item[0]
        if rel.startswith("META-INF/"):
            return (0, rel)
        if rel.endswith(".class") or rel.startswith("com/"):
            return (1, rel)
        if rel.endswith((".json", ".tsv")):
            return (2, rel)
        return (3, rel)

    files.sort(key=sort_key)
    with zipfile.ZipFile(jar_path, "w", mode, allowZip64=True) as z:
        for rel, full in files:
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = mode
            info.external_attr = 0o644 << 16
            with z.open(info, "w") as fh:
                fh.write(full.read_bytes())


# --------------------------------------------------------------------------- #
# 载荷 ASCII 化
# --------------------------------------------------------------------------- #
_ASCII_ESCAPABLE_SUFFIXES = (".json", ".js")


def _escape_non_ascii(text: str) -> str:
    """把文本里所有码点 > 127 的字符改写成 ``\\uXXXX``（含代理对）。

    只动非 ASCII 字符 —— 原有的 ASCII 内容（包括已经存在的 ``\\uXXXX``
    转义、``\\\\`` 转义）一个字节都不碰，因此：
    * JSON：转义只出现在字符串里（合法 JSON 的非 ASCII 不可能出现在
      结构层），Gson ``parse`` 后得到同一字符串；
    * JS：字符串/正则/注释里的非 ASCII 转成 ``\\u`` 转义语义不变。
    """
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp < 128:
            out.append(ch)
        elif cp <= 0xFFFF:
            out.append(f"\\u{cp:04x}")
        else:
            cp -= 0x10000
            hi = 0xD800 + (cp >> 10)
            lo = 0xDC00 + (cp & 0x3FF)
            out.append(f"\\u{hi:04x}\\u{lo:04x}")
    return "".join(out)


def _ascii_escape_payload(payload: Path) -> dict:
    """把 ``config_payload/`` 下全部 ``.json`` / ``.js`` 转成纯 ASCII。

    为什么必须做：``the_vault`` 用 ``java.io.FileReader`` 读全部 config
    （``iskallia.vault.config.Config.readConfig()``，字节码核实），FileReader
    的字符集跟随玩家系统区域 —— 简中 Windows 是 GBK、繁中是 Big5，我们
    写入的 UTF-8 中文在这类系统上**必然乱码**（玩家实测截图：繁中机器出
    「災爐邊」系乱码）。``\\uXXXX`` 转义是 JSON/JS 语法原生支持的，解析
    结果与原字符完全一致，而文件本身变成纯 ASCII 后，任何默认编码读入
    都无损。lang JSON（vanilla UTF-8 显式）、任务书 SNBT（FTB UTF-8 显式）、
    literal TSV（本模组 UTF-8 显式）三条通道不经过这里。
    """
    files = 0
    escaped = 0
    skipped: list[str] = []
    for dp, _dn, fn in os.walk(payload):
        for name in fn:
            if not name.endswith(_ASCII_ESCAPABLE_SUFFIXES):
                continue
            full = Path(dp) / name
            try:
                text = full.read_bytes().decode("utf-8")
            except UnicodeDecodeError as e:
                skipped.append(f"{full.relative_to(payload)}: {e}")
                continue
            new_text = _escape_non_ascii(text)
            if new_text == text:
                continue
            # 代价检查：转义会膨胀字节（一个中文 3 B → 6 B），但这些都
            # 是 zip 内压缩存储，ASCII 序列压缩率更高，实际体积几乎不变。
            full.write_bytes(new_text.encode("ascii"))
            files += 1
            escaped += sum(1 for c in text if ord(c) > 127)
    return {"files": files, "escaped": escaped, "skipped": skipped}
