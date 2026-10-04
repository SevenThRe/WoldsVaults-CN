# -*- coding: utf-8 -*-
"""组合法批量生成「变体方块」模组的译文（buildscape 等）。

背景
----
``buildscape`` 有 4068 条待译，形态几乎全是 ``<材质> <构件>``，例如::

    Acacia Log Slab          金合欢原木台阶
    Acacia Log Vertical Slab 金合欢原木竖直台阶
    Ashpen Fence Gate        （Ashpen 为模组自造词，无法组合，应拒绝）

材质与构件都是有限词表：只要把这两张表学出来，缺口就能组合填补，而且
术语与包内既有译法保持一致。

算法（见 ``learn`` / ``build`` 子命令）
---------------------------------------
1. **自举词典 ``terms``**：原版中英对照（权威）∪ ``term-table.json`` 反查表。
   原版优先。
2. **构件后缀 ``shapes``**：对目标命名空间的全部英文穷举 1–3 个词的后缀片段
   S（频次 ≥ 5），用投票法求中文：遍历 ``terms`` 中以 S 结尾的对照
   ``(en, zh)``，令 ``M = en`` 去掉尾部 S，若 ``terms[M]`` 存在且是 ``zh``
   的前缀，则给 ``zh`` 去掉该前缀后的尾段投一票。票数 ≥ 3 且唯一最高才采信。
3. **材质词 ``materials``**：对目标英文穷举 1–4 个词的前缀片段 P，用已学到的
   ``shapes``（以及 ``terms`` 自身）去切分 ``terms`` 里的对照：若
   ``en = P + " " + T`` 且 ``terms`` 中 T 有译名、``zh`` 以该译名结尾，则给
   ``zh`` 去掉该译名后的头段投一票。同样 ≥ 3 票且唯一最高才采信。
4. **生成**：按词边界切 ``left + " " + right``，命中即得分，优先取 ``left``
   最长者（先试「原子」材质，再试可拼合的材质），``right`` 允许是 1–2 个构件
   的多级拼接，拼接处不加空格。
5. **质量闸门**：拒绝含 ASCII 字母残留、含 ``%s``/``%d`` 占位符、或与英文
   逐字相同的结果（``ME`` / ``TNT`` 一类全大写缩写白名单放行）。
6. **产出**：``<ns>.tsv``（采纳）、``rejected.tsv``（拒绝，附原因）、
   ``report.md``（覆盖率 + 两张全表 + 按置信度升序的 300 条抽样）。

与原任务书的偏差（有意为之，均在报告里注明）
--------------------------------------------
* 任务书 §2 的字面投票是「``mz = zh`` 去掉尾部 ``len(S)`` 个字符」——中英
  字符数并不对齐（``Slab`` 4 字符 vs ``台阶`` 2 字），实测该式得票恒为 0。
  本模块改用「以已知材质译名为前缀去切」的同构投票，才有票可投。
* §3 的材质学习把「切分用的尾部 T」放宽到 ``terms ∪ shapes``，否则
  ``Polished``/``Chiseled``/``Stripped`` 一类修饰词学不到。
* §4 生成额外允许把 ``left`` 由已知词素拼合（如 ``Black Sandstone`` =
  ``Black`` + ``Sandstone``），否则 ``Black Sandstone Slab`` 这类会整片漏掉。

词表优先级（高 → 低）
----------------------
``corrections（人工地面真值） > 组合 > term-table 整条 > 学到材质 > 原版``

* **corrections** 是人工地面真值：整条命中即定稿（``translate`` 第一步）。
* **组合优先于 term-table 整条**：当短语含有 corrections 词素时，禁用
  ``_atom`` 里的整串捷径，改由 ``compose`` 以**权威词素表** ``_tok_auth``
  （corrections > 构件 > 材质 > 原版，**不含 term-table**）组合；词边界判定见
  ``_has_correction_token``。这是通用规则——否则 ``term-table`` 自带的整条
  译名会顶掉人工校正的组合（如 ``Mangrove Door`` 被 term-table 译成「红木门」
  而非按 ``Mangrove=红树`` 组合出「红树门」）。开关：
  ``Translator(enforce_corrections_compose=...)``，默认开。
* 无 corrections 词素的短语仍沿用 ``_atom``（原版 > 学到材质 > term-table）
  的整串优先，保持既有行为不变。

零第三方依赖；纯函数 + 可重复（所有字典遍历均排序）；Windows 路径安全
（不拼 shell 字符串）。

命令行::

    python -m tools.cnrebase.ruletrans build --ns buildscape
    python -m tools.cnrebase.ruletrans learn --ns buildscape
    python -m tools.cnrebase.ruletrans selftest
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

DEFAULT_RESIDUAL: Path = PROJECT_ROOT / "build" / "cn" / "work" / "residual2.json"
DEFAULT_TERM_TABLE: Path = PROJECT_ROOT / "build" / "cn" / "todo" / "term-table.json"
DEFAULT_OUT_DIR: Path = PROJECT_ROOT / "build" / "cn" / "work" / "ruletrans"
# 人工校正表（en\tzh，两列）。程序只读，不生成。
DEFAULT_CORRECTIONS: Path = DEFAULT_OUT_DIR / "corrections.tsv"
# 目标键集首选来源：post-CFPA 残差清单（namespace\tkey\ten\tzh）。用它而非
# 原始英文键，可避免用机器组合译文覆盖 CFPA 已有人工译文的键（防退化）。
DEFAULT_TODO_VENDOR: Path = PROJECT_ROOT / "build" / "cn" / "todo" / "todo-vendor.tsv"
# CFPA 资源包（用于批报里「目标键与 CFPA 键集无交集」的断言）。程序只读。
DEFAULT_CFPA_PACKS: Tuple[Path, ...] = (
    PROJECT_ROOT / "translations" / "cn-rebase" / "cfpa-mods-1.18.zip",
    PROJECT_ROOT / "translations" / "cn-rebase" / "cfpa-mods-extra.zip",
)

_MC = Path("E:/Game Files (x86)/Minecraft/.minecraft")
DEFAULT_INDEX: Path = _MC / "assets" / "indexes" / "1.18.json"
DEFAULT_OBJECTS: Path = _MC / "assets" / "objects"
DEFAULT_VERSIONS: Path = _MC / "versions"

# 构件后缀候选：最多几个词的片段
MAX_SHAPE_WORDS: int = 3
# 材质前缀候选：最多几个词的片段
MAX_MATERIAL_WORDS: int = 4
# 构件候选的最低出现频次
MIN_SHAPE_FREQ: int = 5
# 材质候选的最低出现频次
MIN_MATERIAL_FREQ: int = 2
# 采信所需最低票数
MIN_VOTES: int = 3

# 质量闸门放行的全大写专有缩写
ASCII_WHITELIST: frozenset = frozenset({"ME", "TNT"})

# G2：显式登记的构件后缀（压过原版查表）。原版把独立词 Brick 译「红砖」，
# 但本模组里它一律是后缀，应译「砖」。
SHAPE_SEEDS: Dict[str, str] = {"Brick": "砖", "Bricks": "砖"}

# 只做「词素覆盖」、**不**触发「含校正词素即绕行 term-table」的校正。
# 适用于「材质修饰位」的单字词素：整条短语在 term-table 里往往是对的
# （``Cut Copper Vertical Slab``=切制铜竖直台阶），只是单字词素取错了义项
# （``Cut``=剪切）；在词素层把它改对即可，不必绕行，免得误伤整条。
TOKEN_ONLY_CORRECTIONS: frozenset = frozenset({"Cut"})

# C：纯 UI 语境词，混进材质表只会误导 → 剔除（Frost/Glow 保留）。
UI_MATERIAL_DENYLIST: frozenset = frozenset({
    "Add", "Delete", "Edit", "No", "Search", "Select", "Remove",
    "World", "Creative", "Large", "Stone",
})

_ASCII = re.compile(r"[A-Za-z]")
_NON_ASCII = re.compile(r"[^\x00-\x7f]")
_PLACEHOLDER = re.compile(r"%[a-zA-Z0-9%]")

# G5：输出禁用标记符号。方括号只在 en 原文本就带方括号时才允许保留。
_G5_BRACKETS: str = "[]"
# G6：长度为 1 的 ASCII 字母 token（A–Z / a–z），必须在 zh 中原样出现。
_SINGLE_LETTER = re.compile(r"^[A-Za-z]$")
# G7：相邻重复词素（同一连续片段重复出现，片段长 >= 2 字，如「相机相机」）。
_DUP_MORPHEME = re.compile(r"(.{2,})\1")
# G8：尺寸 / 状态修饰词 → 前置形容词（须走前缀路径，禁括号 / 标记兜底）。
MODIFIER_ADJ: Dict[str, str] = {
    "Small": "小", "Empty": "空的", "Large": "大", "Tiny": "微小",
}
MODIFIER_WORDS: frozenset = frozenset(MODIFIER_ADJ)

# G9 弱词材质守卫（vanilla 回退层兜底）。vanilla 词典把裸词 Light 泄漏成
# 「光源方块」（Light 本是「淡 / 浅」明暗修饰词）。规则：**仅当弱词后紧跟
# 颜色词**时，把它当作「淡 / 浅」前缀（Light Green -> 淡绿色）；否则裸弱词
# 不得作为独立材质 token，一律从查表里删掉（Light Cabinet 不再拼出「光源方块柜」）。
WEAK_MATERIAL_WORDS: Dict[str, str] = {"Light": "淡"}
COLOR_WORDS: frozenset = frozenset({
    "Black", "Blue", "Brown", "Cyan", "Gray", "Grey", "Green", "Lime",
    "Magenta", "Orange", "Pink", "Purple", "Red", "White", "Yellow",
})

_LANG_ZH = "minecraft/lang/zh_cn.json"
_LANG_EN = "minecraft/lang/en_us.json"
_JAR_LANG_EN = "assets/minecraft/lang/en_us.json"


# --------------------------------------------------------------------------- #
# 基础 IO
# --------------------------------------------------------------------------- #

def read_json(path: Path) -> object:
    """读一个 UTF-8 JSON 文件。"""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_asset_object(objects_dir: Path, digest: str) -> Optional[object]:
    """按 sha1 摘要从 assets/objects 里读一个 JSON 对象。"""
    p = Path(objects_dir) / digest[:2] / digest
    if not p.is_file():
        return None
    try:
        return read_json(p)
    except (OSError, ValueError):
        return None


def _find_en_us_in_jars(versions_dir: Path) -> Tuple[Optional[dict], Optional[Path]]:
    """从实例的客户端 jar 里找 ``assets/minecraft/lang/en_us.json``。

    1.18 的 assets 索引里没有 ``en_us``（英语走客户端 jar 内置），因此需要
    这一步兜底。按目录名排序遍历，取第一个命中的 jar，保证可重复。
    """
    vd = Path(versions_dir)
    if not vd.is_dir():
        return None, None
    for sub in sorted(vd.iterdir(), key=lambda q: q.name):
        jar = sub / f"{sub.name}.jar"
        if not sub.is_dir() or not jar.is_file():
            continue
        try:
            with zipfile.ZipFile(jar) as zf:
                if _JAR_LANG_EN in zf.namelist():
                    data = json.loads(zf.read(_JAR_LANG_EN).decode("utf-8"))
                    if isinstance(data, dict):
                        return data, jar
        except (OSError, ValueError, zipfile.BadZipFile):
            continue
    return None, None


def _usable(en: str, zh: object) -> bool:
    """一条对照是否可用于学习 / 生成：中文侧非空、非纯 ASCII（未翻译）、无占位符。"""
    if not isinstance(zh, str) or not zh or not en:
        return False
    if "%" in en or "%" in zh:
        return False
    if not _NON_ASCII.search(zh):
        return False  # 值全是 ASCII，说明其实没翻（如 vanilla 的 End -> End）
    return True


def _vanilla_key_priority(key: str) -> int:
    """同一英文串可能来自多个键（block / item / UI），块名优先。

    返回越小越先处理，后处理的覆盖先前的。
    """
    if key.startswith("block."):
        return 3
    if key.startswith("item."):
        return 2
    if key.startswith(("entity.", "effect.", "biome.", "enchantment.")):
        return 1
    return 0


def load_vanilla_pairs(
    index_path: Path = DEFAULT_INDEX,
    objects_dir: Path = DEFAULT_OBJECTS,
    versions_dir: Path = DEFAULT_VERSIONS,
) -> Tuple[Dict[str, str], List[str]]:
    """读原版中英对照 ``{英文: 中文}``。

    中文来自 assets 索引指向的对象文件；英文优先取索引（若含），否则回退到
    客户端 jar。返回 ``(pairs, notes)``，``notes`` 说明用了哪些来源 / 缺了什么。
    """
    notes: List[str] = []
    en: Dict[str, str] = {}
    zh: Dict[str, str] = {}

    index_path = Path(index_path)
    if index_path.is_file():
        try:
            idx = read_json(index_path)
        except (OSError, ValueError) as exc:
            idx = None
            notes.append(f"索引不可解析：{index_path}（{exc}）")
        if isinstance(idx, dict):
            objs = idx.get("objects") if isinstance(idx.get("objects"), dict) else {}
            for name, sink, label in ((_LANG_EN, "en", "英文"),
                                      (_LANG_ZH, "zh", "中文")):
                rec = objs.get(name)
                if not isinstance(rec, dict) or not rec.get("hash"):
                    notes.append(f"索引中无 {name}（{label}）")
                    continue
                obj = _read_asset_object(objects_dir, str(rec["hash"]))
                if isinstance(obj, dict):
                    if sink == "en":
                        en = {k: v for k, v in obj.items() if isinstance(v, str)}
                    else:
                        zh = {k: v for k, v in obj.items() if isinstance(v, str)}
                    notes.append(f"索引 {index_path.name} 提供 {label} {len(obj)} 条")
                else:
                    notes.append(f"{name} 对象文件缺失：{rec['hash']}")
    else:
        notes.append(f"索引文件不存在：{index_path}")

    if not en:
        jar_en, jar = _find_en_us_in_jars(Path(versions_dir))
        if isinstance(jar_en, dict):
            en = {k: v for k, v in jar_en.items() if isinstance(v, str)}
            notes.append(f"英文回退自客户端 jar：{jar.name}（{len(en)} 条）")
        else:
            notes.append(f"未能从 {versions_dir} 找到客户端 jar 的 en_us.json")

    if not zh:
        notes.append("无原版中文对照，仅使用 term-table.json 兜底")

    pairs: Dict[str, str] = {}
    for k in sorted(en, key=lambda kk: (_vanilla_key_priority(kk), kk)):
        e = en[k]
        z = zh.get(k)
        if _usable(e, z):
            pairs[e] = z
    return pairs, notes


def load_terms(
    term_table_path: Path = DEFAULT_TERM_TABLE,
    vanilla: Optional[Dict[str, str]] = None,
    stats: Optional[Dict[str, int]] = None,
) -> Dict[str, str]:
    """自举词典：``term-table.json`` 反查表 ∪ 原版对照（原版优先）。

    含 ``%`` 的键 / 值一律丢弃（占位符不应参与组合）。
    **G6 根因**：长度为 1 的 ASCII 字母 key（``A``/``C``/``D``…）是 term-table 的
    噪声（把变体后缀当实义词），一律在装载阶段过滤；``stats["single_letter"]``
    记过滤条数。
    """
    terms: Dict[str, str] = {}
    filtered = 0
    tt_path = Path(term_table_path)
    if tt_path.is_file():
        data = read_json(tt_path)
        table = data.get("table") if isinstance(data, dict) else None
        if isinstance(table, dict):
            for k, v in table.items():
                if isinstance(k, str) and _SINGLE_LETTER.match(k):
                    filtered += 1
                    continue
                if _usable(k, v):
                    terms[k] = v
    if vanilla:
        for en, zh in sorted(vanilla.items()):
            if _usable(en, zh):
                terms[en] = zh  # 原版优先
    if stats is not None:
        stats["single_letter"] = filtered
    return terms


def load_targets(residual_path: Path, namespace: str) -> List[Tuple[str, str]]:
    """读目标命名空间的待译 ``[(key, en)]``（按原顺序）。"""
    data = read_json(Path(residual_path))
    out: List[Tuple[str, str]] = []
    if not isinstance(data, list):
        return out
    for rec in data:
        if not isinstance(rec, dict):
            continue
        if rec.get("namespace") != namespace:
            continue
        key = rec.get("key")
        en = rec.get("en")
        if isinstance(key, str) and isinstance(en, str) and en.strip():
            out.append((key, en.strip()))
    return out


def load_corrections(path: Path = DEFAULT_CORRECTIONS) -> Dict[str, str]:
    """读人工校正表 ``en\\tzh``（两列；``#`` 开头与空行忽略）。

    这些条目是**人工权威**：既做短语级整条覆盖，也并入查表供其它短语组合，
    但不参与投票学习（避免被「派生成新条目」）。
    """
    corr: Dict[str, str] = {}
    p = Path(path)
    if not p.is_file():
        return corr
    # utf-8-sig：容忍 BOM（编辑器常见），首行注释不会被误读成数据行。
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        en, zh = parts[0].strip(), parts[1].strip()
        if en and zh:
            corr[en] = zh
    return corr


# --------------------------------------------------------------------------- #
# 目标键集：post-CFPA 残差清单（todo-vendor.tsv）
# --------------------------------------------------------------------------- #

def _unescape_todo(text: str) -> str:
    """还原 ``todo-vendor.tsv`` 的转义：``\\n`` -> 换行、``\\t`` -> 制表符。

    ``\\x01`` 占位符标记保持原样（不参与组合，仅作为不可译的一部分）。
    """
    return text.replace("\\n", "\n").replace("\\t", "\t").replace("\\r", "\r")


def load_targets_todo_vendor(path: Path, namespace: str) -> List[Tuple[str, str]]:
    """读 ``todo-vendor.tsv`` 中某命名空间的 ``[(key, en)]``。

    文件格式：``#`` 注释行 + 表头 ``namespace\\tkey\\ten\\tzh`` + 数据行。列以
    真实制表符分隔（字段内的换行 / 制表符已转义为 ``\\n`` / ``\\t``），故按行读取、
    按 ``\\t`` 切分即可。``en`` 还原转义后返回。
    """
    out: List[Tuple[str, str]] = []
    p = Path(path)
    if not p.is_file():
        return out
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4 or parts[0] == "namespace":
            continue
        ns, key, en = parts[0], parts[1], parts[2]
        if ns == namespace and key:
            out.append((key, _unescape_todo(en)))
    return out


def count_todo_vendor_rows(path: Path, namespace: str) -> int:
    """数 ``todo-vendor.tsv`` 中某命名空间的数据行数（用于「键集条数」断言）。"""
    n = 0
    p = Path(path)
    if not p.is_file():
        return 0
    for raw in p.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 4 or parts[0] == "namespace":
            continue
        if parts[0] == namespace:
            n += 1
    return n


def load_cfpa_keys(pack_paths: Sequence[Path], namespace: str) -> "set[str]":
    """从 CFPA 资源包里取某命名空间已人工翻译的键集（``assets/<ns>/lang/zh_cn.json``）。"""
    keys: "set[str]" = set()
    prefix = f"assets/{namespace}/lang/zh_cn.json"
    for pack in pack_paths:
        pp = Path(pack)
        if not pp.is_file():
            continue
        with zipfile.ZipFile(pp) as zf:
            for name in zf.namelist():
                if name != prefix:
                    continue
                data = json.loads(zf.read(name).decode("utf-8"))
                if isinstance(data, dict):
                    keys.update(data.keys())
    return keys


# --------------------------------------------------------------------------- #
# 片段穷举
# --------------------------------------------------------------------------- #

def _suffix_fragments(en: str, max_words: int = MAX_SHAPE_WORDS) -> Iterable[str]:
    words = en.split()
    for k in range(1, min(max_words, len(words)) + 1):
        yield " ".join(words[-k:])


def _prefix_fragments(en: str, max_words: int = MAX_MATERIAL_WORDS) -> Iterable[str]:
    words = en.split()
    for k in range(1, min(max_words, len(words)) + 1):
        yield " ".join(words[:k])


def _head_index(dic: Dict[str, str]) -> Dict[str, List[Tuple[str, str]]]:
    """按「首个词」分组，供前缀匹配剪枝。"""
    idx: Dict[str, List[Tuple[str, str]]] = collections.defaultdict(list)
    for en, zh in dic.items():
        if not en:
            continue
        idx[en.split()[0]].append((en, zh))
    for v in idx.values():
        v.sort(key=lambda kv: kv[0])
    return dict(idx)


def _tail_index(dic: Dict[str, str]) -> Dict[str, List[Tuple[str, str]]]:
    """按「末个词」分组，供后缀匹配剪枝。"""
    idx: Dict[str, List[Tuple[str, str]]] = collections.defaultdict(list)
    for en, zh in dic.items():
        if not en:
            continue
        idx[en.split()[-1]].append((en, zh))
    for v in idx.values():
        v.sort(key=lambda kv: kv[0])
    return dict(idx)


def _pick(votes: "collections.Counter[str]", min_votes: int) -> Tuple[Optional[str], int, int]:
    """从票箱里挑唯一最高票。返回 ``(值|None, 最高票, 总票)``。"""
    if not votes:
        return None, 0, 0
    ordered = sorted(votes.items(), key=lambda kv: (-kv[1], kv[0]))
    top_val, top_n = ordered[0]
    total = sum(votes.values())
    if top_n < min_votes:
        return None, top_n, total
    if len(ordered) > 1 and ordered[1][1] == top_n:
        return None, top_n, total  # 并列，不采信
    return top_val, top_n, total


# --------------------------------------------------------------------------- #
# 学习
# --------------------------------------------------------------------------- #

def learn_shapes(
    target_ens: Sequence[str],
    terms: Dict[str, str],
    min_freq: int = MIN_SHAPE_FREQ,
    min_votes: int = MIN_VOTES,
) -> Tuple[Dict[str, str], Dict[str, Tuple[int, int]]]:
    """学「构件」后缀。返回 ``(shapes, detail)``，``detail[S] = (得票, 总票)``。

    投票法见模块 docstring §2：以已知材质译名为前缀去切 ``terms`` 的对照。
    """
    cand: "collections.Counter[str]" = collections.Counter()
    for en in target_ens:
        for s in set(_suffix_fragments(en)):
            cand[s] += 1

    tail_idx = _tail_index(terms)
    shapes: Dict[str, str] = {}
    detail: Dict[str, Tuple[int, int]] = {}
    for S, freq in sorted(cand.items()):
        if freq < min_freq:
            continue
        votes: "collections.Counter[str]" = collections.Counter()
        for en, zh in tail_idx.get(S.split()[-1], ()):  # 按末词剪枝
            if not en.endswith(" " + S):
                continue
            M = en[: -(len(S) + 1)]
            if not M:
                continue
            tm = terms.get(M)
            if not tm or not zh.startswith(tm) or len(zh) <= len(tm):
                continue
            votes[zh[len(tm):]] += 1
        val, top_n, total = _pick(votes, min_votes)
        if val is not None:
            shapes[S] = val
            detail[S] = (top_n, total)
    return shapes, detail


def learn_materials(
    target_ens: Sequence[str],
    terms: Dict[str, str],
    shapes: Dict[str, str],
    min_freq: int = MIN_MATERIAL_FREQ,
    min_votes: int = MIN_VOTES,
) -> Tuple[Dict[str, str], Dict[str, Tuple[int, int]]]:
    """学「材质」词。返回 ``(materials, detail)``。

    尾部 T 取自 ``terms ∪ shapes``（见模块 docstring 的偏差说明 §3）。
    """
    cand: "collections.Counter[str]" = collections.Counter()
    for en in target_ens:
        for p in set(_prefix_fragments(en)):
            cand[p] += 1

    cut: Dict[str, str] = dict(terms)
    cut.update(shapes)
    head_idx = _head_index(cut)

    materials: Dict[str, str] = {}
    detail: Dict[str, Tuple[int, int]] = {}
    for P, freq in sorted(cand.items()):
        if freq < min_freq:
            continue
        votes: "collections.Counter[str]" = collections.Counter()
        for en, zh in head_idx.get(P.split()[0], ()):
            if not en.startswith(P + " "):
                continue
            tv = cut.get(en[len(P) + 1:])
            if not tv or not zh.endswith(tv) or len(zh) <= len(tv):
                continue
            votes[zh[: -len(tv)]] += 1
        val, top_n, total = _pick(votes, min_votes)
        if val is not None:
            materials[P] = val
            detail[P] = (top_n, total)
    return materials, detail


def prune_weak_materials(materials: Dict[str, str]) -> Tuple[Dict[str, str], List[str]]:
    """丢掉「单字、且只是更长材质译名前缀」的材质词。

    典型是颜色明暗词 ``Light``（``淡`` 是 ``淡蓝色`` 的前缀）——单独拼进去会
    产出生硬结果（如 ``String Light``）；长词表已能覆盖它的正式用法。
    """
    dropped: List[str] = []
    kept: Dict[str, str] = {}
    for P, pz in sorted(materials.items()):
        weak = len(pz) == 1 and any(
            K != P and K.startswith(P + " ") and materials[K].startswith(pz)
            for K in materials
        )
        if weak:
            dropped.append(P)
        else:
            kept[P] = pz
    return kept, dropped


def apply_guards(
    materials: Dict[str, str],
    terms: Dict[str, str],
    shapes: Dict[str, str],
    authoritative: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], List[Tuple[str, str]]]:
    """G1 / G3 / G5 / G7 通用守卫（在生成之前作用于学到的材质表）。

    G1「块」守卫：材质英文不以 ``Block``/``Blocks`` 结尾时，中文不得以「块」
        结尾——干掉 ``Exposed Copper``→「斑驳的铜块」这类把 Block 的「块」带进来
        的错误复合。
    G3 复合可导出：含空格的复合材质，必须能由其原子词按同序拼出、且与学到的
        译法一致；否则丢弃。权威来源（原版 / term-table 命中的整条对照）豁免。
    G5 括号材质：材质中文含方括号标记（如 ``Small``→「[小型]」）→ 丢弃（这类
        标记在游戏里会原样显示）。
    G7 材质吸收构件词素：材质**值**以某构件译名结尾、而英文并不以对应构件键
        结尾 → 丢弃（如 ``Polaroid``→「宝丽来相机」吸了构件「相机」，拼
        ``Polaroid Camera`` 会变成「宝丽来相机相机」）。``Stone Block``→「石头块」
        结尾的「块」与英文 ``Block`` 一致，属合法复合，不丢。

    返回 ``(保留的材质, [(被丢的英文, 原因)])``。原因取值 ``"G1-block"`` /
    ``"G3-not-composable"`` / ``"G5-material-bracket"`` / ``"G7-material-shape"``。
    """
    auth = dict(authoritative or {})
    dropped: List[Tuple[str, str]] = []
    # 构件「值 -> 键」反查（用于判断材质是否把某个构件词素吸进了自身）
    shape_keys: Dict[str, List[str]] = {}
    for K, V in shapes.items():
        if V:
            shape_keys.setdefault(V, []).append(K)

    def _absorbs_shape(P: str, pz: str) -> bool:
        """材质值是否「吸收了构件词素」。

        判据（精确）：``pz`` 以某构件译名 ``V`` 结尾，且英文 ``P`` **并不**以该
        构件对应的英文键结尾——说明这个构件词素是被整条吸进来的（如
        ``Polaroid``→「宝丽来相机」吸了 ``相机``），拼接时会重复。反之
        ``Stone Block``→「石头块」结尾的「块」与英文 ``Block`` 一致，属合法复合。
        """
        for V, keys in shape_keys.items():
            if pz.endswith(V) and not any(
                    P == K or P.endswith(" " + K) for K in keys):
                return True
        return False

    # 原子词表：terms ∪ 单字材质 ∪ shapes（只用于判断复合可导出）
    atom: Dict[str, str] = dict(terms)
    atom.update(shapes)
    atom.update({k: v for k, v in materials.items() if " " not in k})

    def composable(text: str) -> Optional[str]:
        words = text.split()
        out: List[str] = []
        i = 0
        while i < len(words):
            hit: Optional[str] = None
            for k in range(min(MAX_MATERIAL_WORDS, len(words) - i), 0, -1):
                val = atom.get(" ".join(words[i:i + k]))
                if val is not None:
                    hit = val
                    i += k
                    break
            if hit is None:
                return None
            out.append(hit)
        return "".join(out)

    kept: Dict[str, str] = {}
    for P, pz in sorted(materials.items()):
        # G1
        if pz.endswith("块") and not _ends_with_block(P):
            dropped.append((P, "G1-block"))
            continue
        # G5：材质值带方括号标记 → 丢弃
        if any(c in pz for c in _G5_BRACKETS):
            dropped.append((P, "G5-material-bracket"))
            continue
        # G7：材质值吸收了构件词素（英文未以对应构件结尾）→ 丢弃
        if _absorbs_shape(P, pz):
            dropped.append((P, "G7-material-shape"))
            continue
        # G3：仅约束复合词，且权威来源豁免
        if " " in P and P not in auth:
            if composable(P) != pz:
                dropped.append((P, "G3-not-composable"))
                continue
        kept[P] = pz
    return kept, dropped


def _ends_with_block(en: str) -> bool:
    """英文是否以 ``Block`` / ``Blocks`` 结尾（G1 的豁免条件）。"""
    words = en.split()
    return bool(words) and words[-1] in ("Block", "Blocks")


# --------------------------------------------------------------------------- #
# 生成
# --------------------------------------------------------------------------- #

class Translator:
    """把 ``<材质> <构件>`` 的英文组合成中文。"""

    def __init__(
        self,
        terms: Dict[str, str],
        shapes: Dict[str, str],
        materials: Dict[str, str],
        shapes_votes: Optional[Dict[str, Tuple[int, int]]] = None,
        materials_votes: Optional[Dict[str, Tuple[int, int]]] = None,
        vanilla: Optional[Dict[str, str]] = None,
        corrections: Optional[Dict[str, str]] = None,
        enforce_corrections_compose: bool = True,
    ) -> None:
        self.corrections = dict(corrections or {})
        # 通用规则开关：短语含 corrections 词素时，禁止走 term-table 整条捷径，
        # 改走组合路径（见 _has_correction_token / translate）。默认开启。
        self.enforce_corrections_compose = bool(enforce_corrections_compose)
        # 构件表并入 G2 显式种子（Brick→砖…），压过原版查表。
        self.shapes = dict(shapes)
        self.shapes_votes = dict(shapes_votes or {})
        for seed, sz in SHAPE_SEEDS.items():
            self.shapes[seed] = sz
            self.shapes_votes.setdefault(seed, (MIN_VOTES, MIN_VOTES))
        self.materials = dict(materials)
        self.materials_votes = dict(materials_votes or {})
        self.vanilla = dict(vanilla or {})
        # 「可触发整条绕行」的 corrections 词素：排除与 shapes 同值的冗余项
        # （如 Brick/Bricks=砖 已由构件表表达）。否则会误伤 term-table 的合法
        # 复合词条——如「Stone Brick Vertical Slab=石砖竖直台阶」被拆成
        # 「石头砖竖直台阶」（Stone=石头 + Brick=砖）。
        # 排除「仅词素覆盖」的校正（如 Cut=切制）：它们只改词素，不参与绕行，
        # 否则会误伤 term-table 里正确的整条（Cut Copper Vertical Slab）。
        self._corr_tokens: Dict[str, str] = {
            k: v for k, v in self.corrections.items()
            if self.shapes.get(k) != v and k not in TOKEN_ONLY_CORRECTIONS
        }
        # 原子查表优先级（高→低）：corrections > 原版 > 学到材质 > term-table。
        # 原版是权威块名（Deepslate=深板岩）；学到的材质贴合方块语境
        # （Cut=切制、Vertical=竖直）；term-table 单字最杂（Block=阻挡）兜底。
        self._atom: Dict[str, str] = dict(terms)
        self._atom.update(self.materials)
        self._atom.update(self.vanilla)
        self._atom.update(self.corrections)
        # 拼接用词素表（高→低）：corrections > 构件 > 原版 > 材质 > term-table。
        # G2：构件（Block=块、Brick=砖）必须压过原版（Brick 独立义=红砖）。
        self._tok: Dict[str, str] = dict(terms)
        self._tok.update(self.materials)
        self._tok.update(self.vanilla)
        self._tok.update(self.shapes)
        self._tok.update(self.corrections)
        # 「权威词素」表：**不含 term-table**（高→低）：corrections > 构件 >
        # 材质 > 原版。命中 corrections 词素的短语改用它做组合，从而绕开
        # term-table 自带的整条译名（否则贪婪最长匹配仍会选中整条）。
        self._tok_auth: Dict[str, str] = dict(self.vanilla)
        self._tok_auth.update(self.materials)
        self._tok_auth.update(self.shapes)
        self._tok_auth.update(self.corrections)

        # G9 弱词材质守卫：记录命中（裸弱词被删 / 颜色对派生），供报告。
        self.weak_drops: List[str] = []
        self.weak_derived: Dict[str, str] = {}
        self._apply_weak_material_guard()

    # -- 弱词材质守卫（G9） ------------------------------------------------- #

    def _apply_weak_material_guard(self) -> None:
        """G9 弱词材质守卫（vanilla 回退层兜底）。

        vanilla 词典把裸词 ``Light`` 泄漏成「光源方块」（``Light`` 本是
        「淡 / 浅」明暗修饰词）。规则：

        * 弱词后**紧跟颜色词** -> 派生 ``"<弱词> <颜色>"`` 词素
          （``Light Green`` -> 淡绿色）；已存在的官方条目（如 ``Light Gray``
          / ``Light Blue``）不覆盖，保持既有译法一致。
        * 裸弱词 -> 从 ``_atom`` / ``_tok`` / ``_tok_auth`` 中删除，禁止其作为
          独立材质 token（``Light Cabinet`` 不再拼出「光源方块柜」，改为未命中）。

        ``self.weak_drops`` 记「被拉黑的裸弱词」，``self.weak_derived`` 记
        「派生出的颜色对」。
        """
        for w, adj in sorted(WEAK_MATERIAL_WORDS.items()):
            for color in sorted(COLOR_WORDS):
                cz = self._tok.get(color)          # 颜色词的权威中文
                if not cz:
                    continue
                frag = f"{w} {color}"
                if frag in self._tok or frag in self._atom:
                    continue                        # 已有官方条目，不覆盖
                val = adj + cz
                self._atom[frag] = val
                self._tok[frag] = val
                self._tok_auth[frag] = val
                self.weak_derived[frag] = val
            hit = False
            for table in (self._atom, self._tok, self._tok_auth):
                if w in table:
                    del table[w]
                    hit = True
            if hit:
                self.weak_drops.append(w)

    # -- 查表助手 ---------------------------------------------------------- #

    def _suffix_val(self, tok: str) -> Optional[str]:
        """取一个后缀（构件）的中文：corrections 优先于学到的 shapes。"""
        if tok in self.corrections:
            return self.corrections[tok]
        return self.shapes.get(tok)

    def _has_correction_token(self, en: str) -> bool:
        """``en`` 是否含任一「可触发整条绕行」的 corrections 词素。

        **按词边界**判定：把 ``en`` 切成词，枚举连续词片段（n-gram），任一片段
        恰为一条 corrections 键即命中。这样 ``Mangrove`` 命中 ``Mangrove Door``、
        但**不会**命中 ``Mangrovexyz``（子串不算）。与 shapes 同值的冗余校正
        （Brick/Bricks=砖）不计入，避免拆散 term-table 合法复合词条。
        """
        toks = getattr(self, "_corr_tokens", self.corrections)
        if not toks:
            return False
        words = en.split()
        n = len(words)
        for i in range(n):
            for j in range(i + 1, n + 1):
                if " ".join(words[i:j]) in toks:
                    return True
        return False

    # -- 词素拼合 ---------------------------------------------------------- #

    def compose(self, text: str,
                table: Optional[Dict[str, str]] = None) -> Optional[str]:
        """把 ``text`` 逐词用最长已知词素拼成中文；有任一未知词素则返回 None。

        ``table`` 缺省用 ``self._tok``（含 term-table）；传 ``self._tok_auth``
        可只用权威词素拼合（绕开 term-table 整条，供 corrections 规则使用）。
        """
        tok = self._tok if table is None else table
        words = text.split()
        out: List[str] = []
        i = 0
        while i < len(words):
            hit: Optional[Tuple[int, str]] = None
            for k in range(min(MAX_MATERIAL_WORDS, len(words) - i), 0, -1):
                frag = " ".join(words[i:i + k])
                val = tok.get(frag)
                if val is not None:
                    hit = (k, val)
                    break
            if hit is None:
                return None
            out.append(hit[1])
            i += hit[0]
        return "".join(out) if out else None

    def _votes_for(self, *components: str) -> List[int]:
        """收集参与部件的得票（供质量闸门复核）。"""
        votes: List[int] = []
        for c in components:
            if c in self.shapes_votes:
                votes.append(self.shapes_votes[c][0])
            elif c in self.materials_votes:
                votes.append(self.materials_votes[c][0])
        return votes

    # -- 主生成 ------------------------------------------------------------ #

    def translate(self, en: str) -> Tuple[Optional[str], Optional[str], List[int]]:
        """返回 ``(中文|None, 方法|None, 参与部件得票)``。

        切分顺序：整串 → 原子材质 + 最长构件后缀 → 原子材质 + 两级构件 →
        可拼合材质 + 构件 → 整串即材质。``right`` 优先取最长构件后缀。
        """
        en = en.strip()
        if not en:
            return None, None, []
        words = en.split()

        if en in self.corrections:
            return self.corrections[en], "correction", []
        # G8：尺寸 / 状态修饰词走「前置形容词 + 剩余部分」路径（Small=小、
        # Empty=空的…），避免把 term-table 的 [小型] 一类标记带出来。
        if words and words[0] in MODIFIER_ADJ:
            sub, _sm, _sv = self.translate(" ".join(words[1:]))
            if sub and _DUP_MORPHEME.search(MODIFIER_ADJ[words[0]] + sub) is None:
                return MODIFIER_ADJ[words[0]] + sub, "modifier", []
        # 校正表后缀（最长优先）压过 term-table 整条，保证同一构件译法一致
        # （如 Acacia Leaf Hedge 不被旧词条「树叶篱」拉偏成「树叶篱笆」以外的写法）。
        for i in range(1, len(words)):
            R = " ".join(words[i:])
            if R in self.corrections:
                L = " ".join(words[:i])
                # 左侧若含 corrections 词素，同样禁用 term-table 整条捷径，改走
                # 权威词素表组合：否则 ``Polished Cut`` 会被 term-table 的
                # ``Cut=剪切`` 顶掉，得不到 ``Cut=切制``（team-lead §五.2）。
                if self.enforce_corrections_compose and self._has_correction_token(L):
                    lz = self.compose(L, self._tok_auth)
                else:
                    lz = self._atom.get(L) or self.compose(L)
                if lz:
                    return lz + self.corrections[R], "correction", []

        if en in self.shapes:
            return self.shapes[en], "shape", self._votes_for(en)
        if en in self._atom:
            # 通用规则：短语含任一 corrections 词素时，禁止走 term-table 整条
            # 捷径（`_atom` 里的整串条目），改走组合路径。否则人工校正会被
            # term-table 自带的整条译名「顶掉」（Mangrove Door=红木门 即此类）。
            if self.enforce_corrections_compose and self._has_correction_token(en):
                c = self.compose(en, self._tok_auth)
                if c is not None:
                    return c, "compose-corr", []
            return self._atom[en], "atom", self._votes_for(en)

        # 1) 原子材质前缀 + 最长构件后缀
        for i in range(1, len(words)):
            R = " ".join(words[i:])
            L = " ".join(words[:i])
            rz = self._suffix_val(R)
            if rz and L in self._atom:
                return self._atom[L] + rz, "l1-atomic", \
                    self._votes_for(R) + self._votes_for(L)

        # 2) 原子材质前缀 + 两级构件（如 Vertical Slab 未被整体学到时）
        for i in range(1, len(words)):
            L = " ".join(words[:i])
            if L not in self._atom:
                continue
            right = words[i:]
            for j in range(1, len(right)):
                r1 = " ".join(right[:j])
                r2 = " ".join(right[j:])
                a = self._suffix_val(r1)
                b = self._suffix_val(r2)
                if a and b:
                    return self._atom[L] + a + b, "l2", \
                        self._votes_for(r1, r2) + self._votes_for(L)

        # 3) 可拼合的材质前缀 + 最长构件后缀
        for i in range(1, len(words)):
            R = " ".join(words[i:])
            rz = self._suffix_val(R)
            if not rz:
                continue
            lz = self.compose(" ".join(words[:i]))
            if lz:
                return lz + rz, "l1-compose", self._votes_for(R)

        # 4) 整串就是一个材质
        c = self.compose(en)
        if c:
            return c, "whole-compose", []

        return None, None, []


def check_quality(
    en: str,
    zh: Optional[str],
    used_votes: Optional[Sequence[int]] = None,
    whitelist: Iterable[str] = ASCII_WHITELIST,
) -> Optional[str]:
    """质量闸门。返回拒绝原因；通过返回 ``None``。

    顺序：G6（单字母透传） → ASCII 残留 → G5（括号禁令） → G7（相邻重复词素）
    → G8（修饰词前置形容词） → 占位符 / 逐字相同 / 票数。
    """
    if not zh:
        return "empty"
    if zh in set(whitelist):
        return None
    # G6：en 里长度为 1 的 ASCII 字母 token 必须在 zh 里原样出现，否则整条拒绝
    # （并进 unknown.tsv）。en 自带的这几个字母在后续 ASCII 检查中豁免。
    letters = [w for w in en.split() if _SINGLE_LETTER.match(w)]
    for w in letters:
        if w not in zh:
            return "single-letter"
    zh_checked = zh
    for w in letters:
        zh_checked = zh_checked.replace(w, "", 1)
    if _ASCII.search(zh_checked):
        return "ascii"
    # G5：输出 zh 不得含方括号，除非 en 原文本就带方括号（带则按原样保留）。
    if any(c in zh for c in _G5_BRACKETS) and not any(c in en for c in _G5_BRACKETS):
        return "bracket"
    # G7：拼接结果不得出现相邻的重复词素（相机相机、台阶台阶…）。
    if _DUP_MORPHEME.search(zh):
        return "dup-morpheme"
    # G8：尺寸 / 状态修饰词必须落实为前置形容词（Small=小、Empty=空的…）。
    toks = set(en.split())
    for w, adj in MODIFIER_ADJ.items():
        if w in toks and adj not in zh:
            return "G8-modifier"
    if _PLACEHOLDER.search(en):
        return "placeholder"
    if zh == en:
        return "same"
    if used_votes and min(used_votes) < MIN_VOTES:
        return "low-votes"
    return None


# 方法 -> 置信度（越大越可靠）
_CONFIDENCE: Dict[str, int] = {
    "correction": 6,
    "modifier": 5,
    "shape": 5,
    "atom": 5,
    "l1-atomic": 5,
    "compose-corr": 5,
    "l2": 3,
    "l1-compose": 3,
    "whole-compose": 2,
}


# --------------------------------------------------------------------------- #
# 一次性构建某一命名空间的结果
# --------------------------------------------------------------------------- #

class BuildResult:
    """一个命名空间的构建结果（纯数据）。"""

    def __init__(self, namespace: str) -> None:
        self.namespace = namespace
        self.total = 0
        self.accepted: List[Tuple[str, str, str, str]] = []   # key, en, zh, method
        self.rejected: List[Tuple[str, str, str, str]] = []   # key, en, zh, reason
        self.shapes: Dict[str, str] = {}
        self.shapes_detail: Dict[str, Tuple[int, int]] = {}
        self.materials: Dict[str, str] = {}
        self.materials_detail: Dict[str, Tuple[int, int]] = {}
        self.dropped_materials: List[str] = []
        self.guard_drops: List[Tuple[str, str]] = []          # (英文, 守卫原因)
        self.conflicts: Dict[str, List[str]] = {}             # 短语 -> 独立译法
        self.notes: List[str] = []


def _detect_conflicts(
    accepted: Sequence[Tuple[str, str, str, str]],
    trans: Translator,
    targets: Sequence[str],
) -> Dict[str, List[str]]:
    """G4 自一致守卫：同一英文短语「独立成条」与「嵌在更长的短语里」译法须一致。

    判据（精确、低误伤）：对每条采纳结果，枚举 2 词及以上的词边界前缀 p；只考察
    **本身也是一条待译英文** 的 p。若 ``translate(p)`` 不是该结果中文的前缀，说明
    同一短语在两处被译成了不同写法——记为矛盾。返回 ``{英文片段: [独立译法]}``。

    为什么要求 p 本身是待译条目：否则 ``Black`` 会命中 ``Black Sandstone`` 这类
    「假前缀」，把『黑色沙子』与『黑色砂岩』误判为矛盾（其实是不同词）。

    为什么跳过「整条已被人工校正」的 en：``corrections.tsv`` 是人工权威，整条
    校正即该英文的定稿译法，不该再被更短前缀下的组合结果「反推成矛盾」。典型
    如 ``Mangrove Boat``（红树船）与 ``Mangrove Boat with Chest``（红树运输船）：
    后者带 ``with Chest`` 本就与前者不同义，属误报，故对已整条校正者一律豁免。
    """
    tset = set(targets)
    corr_keys = set(getattr(trans, "corrections", {}) or {})
    mism: Dict[str, set] = collections.defaultdict(set)
    for _key, en, zh, _m in accepted:
        if en in corr_keys:
            continue
        words = en.split()
        for i in range(2, len(words)):
            p = " ".join(words[:i])
            if p not in tset:
                continue
            pz, _pm, _pv = trans.translate(p)
            if pz and check_quality(p, pz) is None and not zh.startswith(pz):
                mism[p].add(pz)
    return {p: sorted(v) for p, v in mism.items()}


def learn_tables(
    target_ens: Sequence[str],
    terms: Dict[str, str],
    vanilla: Optional[Dict[str, str]] = None,
) -> "Tuple[Dict[str, str], Dict[str, Tuple[int, int]], Dict[str, str], Dict[str, Tuple[int, int]], List[str], List[Tuple[str, str]]]":
    """学习 + 守卫的完整词表层，供 ``learn`` 与 ``build`` 共用。

    返回 ``(shapes, shapes_detail, materials, materials_detail, 剔除词, 守卫丢弃)``。
    """
    shapes, shapes_detail = learn_shapes(target_ens, terms)
    materials, materials_detail = learn_materials(target_ens, terms, shapes)

    dropped: List[str] = []
    dropped += _check_denylist(materials, materials_detail)
    auth: Dict[str, str] = dict(terms)
    if vanilla:
        auth.update(vanilla)
    materials, gdrops = apply_guards(materials, terms, shapes, auth)
    for d, _reason in gdrops:
        materials_detail.pop(d, None)
    materials, weak = prune_weak_materials(materials)
    for d in weak:
        materials_detail.pop(d, None)
    dropped += weak
    return shapes, shapes_detail, materials, materials_detail, sorted(set(dropped)), sorted(gdrops)


def build_namespace(
    namespace: str,
    targets: Sequence[Tuple[str, str]],
    terms: Dict[str, str],
    notes: Optional[Sequence[str]] = None,
    vanilla: Optional[Dict[str, str]] = None,
    corrections: Optional[Dict[str, str]] = None,
) -> Tuple[BuildResult, Translator]:
    """对单个命名空间跑完整流程，返回 ``(结果, 翻译器)``。"""
    res = BuildResult(namespace)
    res.notes = list(notes or [])
    res.total = len(targets)
    ens = [en for _k, en in targets]

    shapes, shapes_detail, materials, materials_detail, dropped, gdrops = \
        learn_tables(ens, terms, vanilla)

    res.shapes = shapes
    res.shapes_detail = shapes_detail
    res.materials = materials
    res.materials_detail = materials_detail
    res.dropped_materials = dropped
    res.guard_drops = gdrops

    trans = Translator(terms, shapes, materials, shapes_detail,
                       materials_detail, vanilla, corrections)

    for key, en in targets:
        zh, method, votes = trans.translate(en)
        if zh is None:
            res.rejected.append((key, en, "", "no-hit"))
            continue
        reason = check_quality(en, zh, votes)
        if reason is None:
            res.accepted.append((key, en, zh, method or ""))
        else:
            res.rejected.append((key, en, zh, reason))

    # G4：自一致守卫（整组丢弃「统一短语两处译法不同」的条目）
    res.conflicts = _detect_conflicts(res.accepted, trans, ens)
    if res.conflicts:
        bad = set(res.conflicts)
        kept: List[Tuple[str, str, str, str]] = []
        for row in res.accepted:
            key, en, zh, _m = row
            hit = next((p for p in bad
                        if en == p or en.startswith(p + " ")), None)
            if hit is not None:
                res.rejected.append((key, en, zh, f"inconsistent:{hit}"))
            else:
                kept.append(row)
        res.accepted = kept

    res.accepted.sort(key=lambda r: r[0])
    res.rejected.sort(key=lambda r: r[0])
    # 输出前按 key 去重并断言唯一：合并进 vendor_lang_zh.tsv 时，同一 key
    # 出现两次会产生歧义。residual2.json 里同 EN 不同 key（block./item.）是
    # 正常的、必须各自保留，故只按 key 去重、绝不按 en 去重。
    res.accepted = _dedupe_by_key(res.accepted)
    res.rejected = _dedupe_by_key(res.rejected)
    _assert_unique_keys(res.accepted, f"{namespace}/accepted")
    _assert_unique_keys(res.rejected, f"{namespace}/rejected")
    return res, trans


def _dedupe_by_key(
    rows: Sequence[Tuple[str, str, str, str]],
) -> List[Tuple[str, str, str, str]]:
    """按第 0 列（key）去重，保留首见；不改变其余顺序。"""
    seen: "set[str]" = set()
    out: List[Tuple[str, str, str, str]] = []
    for row in rows:
        if row[0] in seen:
            continue
        seen.add(row[0])
        out.append(row)
    return out


def _assert_unique_keys(
    rows: Sequence[Tuple[str, str, str, str]],
    label: str,
) -> None:
    """断言输出行的 key 唯一；发现重复即抛出（宁停不脏）。"""
    seen: "set[str]" = set()
    dups: List[str] = []
    for row in rows:
        if row[0] in seen and row[0] not in dups:
            dups.append(row[0])
        seen.add(row[0])
    if dups:
        raise ValueError(f"{label}: 输出存在重复 key（前 10 个）：{sorted(dups)[:10]}")


def _check_denylist(
    materials: Dict[str, str],
    detail: Dict[str, Tuple[int, int]],
) -> List[str]:
    """C：把纯 UI 语境材质词从表里剔掉（就地修改 detail），返回被剔的英文。"""
    dropped: List[str] = []
    for P in sorted(materials):
        if P in UI_MATERIAL_DENYLIST:
            dropped.append(P)
            detail.pop(P, None)
            del materials[P]
    return dropped


# --------------------------------------------------------------------------- #
# 产出
# --------------------------------------------------------------------------- #

def _tsv_escape(cell: str) -> str:
    """TSV 单元格：制表符 / 换行都替换掉，避免破坏列结构。"""
    return cell.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def write_tsv(path: Path, rows: Iterable[Sequence[str]], header: Sequence[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(_tsv_escape(str(c)) for c in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _table_md(title: str, table: Dict[str, str],
              detail: Dict[str, Tuple[int, int]]) -> List[str]:
    lines = [f"### {title}（{len(table)} 条）", ""]
    if not table:
        lines.append("（空）")
        lines.append("")
        return lines
    lines.append("| 英文 | 中文 | 票数 | 总票 |")
    lines.append("| --- | --- | --- | --- |")
    for en in sorted(table):
        top_n, total = detail.get(en, (0, 0))
        lines.append(f"| {en} | {table[en]} | {top_n} | {total} |")
    lines.append("")
    return lines


def report_markdown(res: BuildResult, sample_limit: int = 300) -> str:
    accepted = len(res.accepted)
    rejected = sum(1 for r in res.rejected if r[3] != "no-hit")
    no_hit = sum(1 for r in res.rejected if r[3] == "no-hit")
    total = res.total or 1

    lines: List[str] = []
    lines.append(f"# ruletrans 报告 —— {res.namespace}")
    lines.append("")
    lines.append("## 覆盖率")
    lines.append("")
    lines.append(f"- 待译总数：{res.total}")
    lines.append(f"- 采纳（生成）：{accepted}（{accepted / total:.1%}）")
    lines.append(f"- 生成后被闸门拒绝：{rejected}（{rejected / total:.1%}）")
    lines.append(f"- 未命中：{no_hit}（{no_hit / total:.1%}）")
    lines.append("")
    reason_count: "collections.Counter[str]" = collections.Counter(
        r[3] for r in res.rejected)
    if reason_count:
        lines.append("拒绝原因分布：")
        lines.append("")
        for reason, n in sorted(reason_count.items()):
            lines.append(f"- `{reason}`：{n}")
        lines.append("")
    if res.notes:
        lines.append("### 数据来源与说明")
        lines.append("")
        for note in res.notes:
            lines.append(f"- {note}")
        if res.dropped_materials:
            lines.append(f"- 剔除的材质词（UI 语境 / 弱词）："
                         f"{'、'.join(sorted(res.dropped_materials))}")
        if res.guard_drops:
            g1 = [e for e, why in res.guard_drops if why == "G1-block"]
            g3 = [e for e, why in res.guard_drops if why == "G3-not-composable"]
            if g1:
                lines.append(f"- G1「块」守卫丢弃：{'、'.join(sorted(g1))}")
            if g3:
                lines.append(f"- G3 复合不可导出丢弃：{'、'.join(sorted(g3))}")
        lines.append("")

    # G4 自相矛盾清单
    n_conf = len(res.conflicts)
    lines.append(f"## 自相矛盾清单（G4，须为 0）—— 共 {n_conf} 组")
    lines.append("")
    if n_conf:
        lines.append("| 英文短语 | 独立成条的译法 |")
        lines.append("| --- | --- |")
        for pfx in sorted(res.conflicts):
            lines.append(f"| {pfx} | {' / '.join(res.conflicts[pfx])} |")
    else:
        lines.append("无（0）：同一英文短语独立成条与嵌入更长短语时译法一致。")
    lines.append("")

    lines.append("## 学到的词表（人工审阅重点）")
    lines.append("")
    lines.extend(_table_md("构件 shapes", res.shapes, res.shapes_detail))
    lines.extend(_table_md("材质 materials", res.materials, res.materials_detail))

    # 抽样：置信度升序（最可疑的排最前）
    ranked = sorted(
        res.accepted,
        key=lambda r: (_CONFIDENCE.get(r[3], 0), r[0], r[1]),
    )
    sample = ranked[:max(0, sample_limit)]
    lines.append(f"## 按置信度升序抽样（共 {len(sample)} 条，最可疑在前）")
    lines.append("")
    lines.append("| 英文 | 中文 | 方法 | 置信度 |")
    lines.append("| --- | --- | --- | --- |")
    for _key, en, zh, method in sample:
        lines.append(f"| {en} | {zh} | `{method}` | {_CONFIDENCE.get(method, 0)} |")
    lines.append("")
    return "\n".join(lines)


def _unknown_units(
    miss_ens: Sequence[str],
    trans: Translator,
    shapes: Dict[str, str],
) -> "Tuple[collections.Counter, Dict[str, List[str]]]":
    """统计未命中英文里的「未知片段」，供人工造词。

    两类粒度合并：
    * 单个未知词（Ashpen / Stained / Wallpaper …）：不在任何查表里；
    * 未学到的构件候选（``Leaf Layers`` / ``Factory Mesh`` …）：作为 1–3 词后缀
      片段出现 ≥3 次，却既不在查表里、也没被学成构件。

    返回 ``(计数, 片段 -> ≤3 条样例英文)``。
    """
    known = set(trans._atom) | set(trans._tok)
    shape_keys = set(shapes) | set(trans.shapes)
    count: "collections.Counter[str]" = collections.Counter()
    samples: Dict[str, List[str]] = collections.defaultdict(list)

    def add(unit: str, en: str) -> None:
        count[unit] += 1
        if len(samples[unit]) < 3 and en not in samples[unit]:
            samples[unit].append(en)

    for en in miss_ens:
        for w in en.split():
            if w not in known:
                add(w, en)

    frag: "collections.Counter[str]" = collections.Counter()
    frag_en: Dict[str, List[str]] = collections.defaultdict(list)
    for en in miss_ens:
        for s in set(_suffix_fragments(en)):
            frag[s] += 1
            if len(frag_en[s]) < 3 and en not in frag_en[s]:
                frag_en[s].append(en)
    for s in sorted(frag):
        if frag[s] < 3 or s in known or s in shape_keys or s in count:
            continue
        count[s] = frag[s]
        samples[s] = list(frag_en[s])
    return count, samples


def write_unknown_tsv(
    path: Path,
    miss_ens: Sequence[str],
    trans: Translator,
    shapes: Dict[str, str],
) -> int:
    """D：导出未知词清单 ``unit\\tcount\\t3 条样例英文``（次数降序）。"""
    count, samples = _unknown_units(miss_ens, trans, shapes)
    rows: List[Tuple[str, str, str]] = []
    for unit in sorted(count, key=lambda u: (-count[u], u)):
        rows.append((unit, str(count[unit]), " ⏐ ".join(samples.get(unit, []))))
    write_tsv(path, rows, ("unit", "count", "samples"))
    return len(rows)


def _representative_samples(
    res: BuildResult,
    count: int = 15,
) -> List[Tuple[str, str, str, str]]:
    """抽代表样本：最短 / 最长 en + 其间等距若干（确定性，去重保序）。"""
    rows = sorted(res.accepted, key=lambda r: (len(r[1]), r[1]))
    if len(rows) <= count:
        return rows
    n = len(rows)
    picks = {0, n - 1}
    for t in range(1, count - 1):
        picks.add(round(t * (n - 1) / (count - 1)))
    return [rows[i] for i in sorted(picks)][:count]


_GUARD_LABELS: Dict[str, str] = {
    "bracket": "G5 括号",
    "single-letter": "G6 单字母",
    "dup-morpheme": "G7 相邻重复",
    "G8-modifier": "G8 修饰词",
    "G5-material-bracket": "G5 括号材质",
    "G7-material-shape": "G7 材质含构件",
}


def guard_counts(res: BuildResult) -> Dict[str, int]:
    """统计一处构建里 G5–G8 各守卫的实际拦截条数（输出级 + 材质级）。"""
    c = collections.Counter(r[3] for r in res.rejected)
    md = collections.Counter(why for _e, why in res.guard_drops)
    out: Dict[str, int] = {}
    for key in _GUARD_LABELS:
        out[key] = c.get(key, 0) + md.get(key, 0)
    return out


def write_batch_report(
    results: Dict[str, BuildResult],
    path: Path,
    samples_per_ns: int = 15,
) -> None:
    """写合并批报：各 ns 覆盖率 / 拒绝 / 未命中 / G4 矛盾 + G5–G8 拦截 + 代表样本。"""
    lines: List[str] = ["# ruletrans 批报（batch2）", ""]
    lines.append("| 命名空间 | target | 采纳 | 拒绝 | 未命中 | 覆盖率 | G4矛盾 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    tot: "collections.Counter[str]" = collections.Counter()
    for ns in sorted(results):
        res = results[ns]
        acc = len(res.accepted)
        rej = sum(1 for r in res.rejected if r[3] != "no-hit")
        miss = res.total - acc - rej
        cov = acc / res.total if res.total else 0.0
        lines.append(f"| {ns} | {res.total} | {acc} | {rej} | {miss} "
                     f"| {cov:.1%} | {len(res.conflicts)} |")
        for k, v in guard_counts(res).items():
            tot[k] += v
    lines.append("")
    lines.append("### G5–G8 守卫拦截合计")
    lines.append("")
    lines.append("| 守卫 | 拦截条数 |")
    lines.append("| --- | --- |")
    for key in _GUARD_LABELS:
        lines.append(f"| {_GUARD_LABELS[key]} | {tot.get(key, 0)} |")
    lines.append("")
    for ns in sorted(results):
        res = results[ns]
        acc = len(res.accepted)
        rej = sum(1 for r in res.rejected if r[3] != "no-hit")
        miss = res.total - acc - rej
        cov = acc / res.total if res.total else 0.0
        gc = guard_counts(res)
        lines.append(f"## {ns}")
        lines.append("")
        lines.append(f"- target {res.total} / 采纳 {acc} / 拒绝 {rej} / 未命中 {miss}"
                     f" / 覆盖率 {cov:.1%} / G4矛盾 {len(res.conflicts)}（须为 0）")
        lines.append("- 与 CFPA 键集无交集：是（构建期已断言）")
        lines.append("- 守卫拦截：" + "、".join(
            f"{_GUARD_LABELS[k]} {gc[k]}" for k in _GUARD_LABELS if gc[k]))
        if cov < 0.25:
            lines.append("- ⚠ 覆盖率 < 25%：复用词表明显不足，建议先补词表再跑，勿硬凑。")
        lines.append("")
        lines.append(f"### {ns} 代表样本（{samples_per_ns} 条，含最长/最短 en）")
        lines.append("")
        lines.append("| en | zh |")
        lines.append("| --- | --- |")
        for _k, en, zh, _m in _representative_samples(res, samples_per_ns):
            lines.append(f"| {en} | {zh} |")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def build_namespaces(
    namespaces: Sequence[str],
    residual_path: Path = DEFAULT_RESIDUAL,
    term_table_path: Path = DEFAULT_TERM_TABLE,
    index_path: Path = DEFAULT_INDEX,
    objects_dir: Path = DEFAULT_OBJECTS,
    versions_dir: Path = DEFAULT_VERSIONS,
    out_dir: Path = DEFAULT_OUT_DIR,
    corrections_path: Path = DEFAULT_CORRECTIONS,
    source: str = "todo-vendor",
    todo_vendor_path: Path = DEFAULT_TODO_VENDOR,
    cfpa_packs: Sequence[Path] = DEFAULT_CFPA_PACKS,
    batch_report_path: Optional[Path] = None,
) -> Dict[str, BuildResult]:
    """对一批命名空间跑构建并写出成果，返回各命名空间结果。

    ``source`` 默认 ``"todo-vendor"``：目标键集取 post-CFPA 残差清单，并断言
    「目标键数 == 该 ns 在清单中的行数」；``"residual"`` 时退回旧行为。
    ``batch_report_path`` 非空时额外写一份合并批报（含 CFPA 无交集断言）。
    """
    ns_list = [n.strip() for n in namespaces if n and n.strip()]
    vanilla, vnotes = load_vanilla_pairs(index_path, objects_dir, versions_dir)
    tstats: Dict[str, int] = {}
    terms = load_terms(term_table_path, vanilla, tstats)
    corrections = load_corrections(corrections_path)
    notes = list(vnotes)
    notes.append(f"自举词典 terms 共 {len(terms)} 条")
    notes.append(f"G6 过滤 term-table 单字符 key：{tstats.get('single_letter', 0)} 条")
    notes.append(f"人工校正表共 {len(corrections)} 条（{corrections_path.name}）")
    notes.append(f"目标键集来源：{'todo-vendor 残差' if source == 'todo-vendor' else 'residual'}")

    out = Path(out_dir)
    single = len(ns_list) == 1
    results: Dict[str, BuildResult] = {}
    for ns in ns_list:
        if source == "todo-vendor":
            targets = load_targets_todo_vendor(todo_vendor_path, ns)
            n_rows = count_todo_vendor_rows(todo_vendor_path, ns)
            ok = len(targets) == n_rows
            print(f"[{ns}] 输入键集：todo-vendor {len(targets)} 行"
                  f"（清单内 {n_rows} 行）{'OK' if ok else 'MISMATCH'}")
            if not ok:
                raise SystemExit(
                    f"{ns}: 目标键数 {len(targets)} != {todo_vendor_path.name} 行数 {n_rows}")
        else:
            targets = load_targets(residual_path, ns)
        if not targets:
            raise SystemExit(f"命名空间 {ns!r} 没有待译条目")
        res, trans = build_namespace(ns, targets, terms, notes, vanilla, corrections)
        cfpa_keys = load_cfpa_keys(cfpa_packs, ns)
        overlap = {k for k, _en in targets} & cfpa_keys
        if overlap:
            raise SystemExit(
                f"{ns}: 目标键与 CFPA 键集有交集（{len(overlap)} 条），疑似用了非残差输入")
        res.notes.append(f"与 CFPA 键集无交集：是（CFPA 已译 {len(cfpa_keys)} 键）")
        results[ns] = res

        prefix = "" if single else f"{ns}."
        write_tsv(out / f"{ns}.tsv",
                  [(ns, key, en, zh) for key, en, zh, _m in res.accepted],
                  ("namespace", "key", "en", "zh"))
        write_tsv(out / f"{prefix}rejected.tsv",
                  [(ns, key, en, zh, reason) for key, en, zh, reason in res.rejected],
                  ("namespace", "key", "en", "zh", "reason"))
        miss_ens = [en for _k, en, _zh, reason in res.rejected
                    if reason in ("no-hit", "single-letter")]
        write_unknown_tsv(out / f"{prefix}unknown.tsv", miss_ens, trans, res.shapes)
        report_path = out / f"{prefix}report.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown(res), encoding="utf-8")

    if batch_report_path is not None:
        write_batch_report(results, Path(batch_report_path), samples_per_ns=15)
    return results


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _print_tables(res: BuildResult) -> None:
    print(f"# {res.namespace}：待译 {res.total} 条")
    print()
    print(f"## 构件 shapes（{len(res.shapes)} 条，含 G2 种子 Brick/Bricks）")
    for S in sorted(res.shapes):
        top_n, total = res.shapes_detail.get(S, (0, 0))
        print(f"  {S!r:28} -> {res.shapes[S]!r}   票 {top_n}/{total}")
    print()
    print(f"## 材质 materials（{len(res.materials)} 条）"
          f"（剔除：{'、'.join(sorted(res.dropped_materials)) or '无'}）")
    for P in sorted(res.materials):
        top_n, total = res.materials_detail.get(P, (0, 0))
        print(f"  {P!r:28} -> {res.materials[P]!r}   票 {top_n}/{total}")
    if res.guard_drops:
        print()
        print("## 守卫丢弃（G1/G3）")
        for en, why in res.guard_drops:
            print(f"  {en!r:28} 原因 {why}")


def _split_ns(arg: str) -> List[str]:
    return [n.strip() for n in arg.split(",") if n.strip()]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tools.cnrebase.ruletrans",
        description="组合法生成变体方块模组译文（buildscape 等）。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--ns", default="buildscape", help="命名空间，逗号分隔可多个")
        p.add_argument("--residual", type=Path, default=DEFAULT_RESIDUAL)
        p.add_argument("--todo-vendor", type=Path, default=DEFAULT_TODO_VENDOR,
                       help="post-CFPA 残差清单（目标键集首选来源）")
        p.add_argument("--source", choices=("todo-vendor", "residual"),
                       default="todo-vendor", help="目标键集来源，默认 todo-vendor")
        p.add_argument("--term-table", type=Path, default=DEFAULT_TERM_TABLE)
        p.add_argument("--corrections", type=Path, default=DEFAULT_CORRECTIONS)
        p.add_argument("--index", type=Path, default=DEFAULT_INDEX)
        p.add_argument("--objects", type=Path, default=DEFAULT_OBJECTS)
        p.add_argument("--versions", type=Path, default=DEFAULT_VERSIONS)
        p.add_argument("--out", type=Path, default=DEFAULT_OUT_DIR)

    p_build = sub.add_parser("build", help="生成译文并落盘到 build/cn/work/ruletrans/")
    add_common(p_build)
    p_build.add_argument("--batch-report", type=Path, default=None,
                         help="多 ns 时额外写一份合并批报")

    p_learn = sub.add_parser("learn", help="只学习并打印 shapes / materials")
    add_common(p_learn)

    sub.add_parser("selftest", help="跑纯逻辑自检")

    args = parser.parse_args(argv)

    if args.command == "selftest":
        from tools.cnrebase import ruletrans_selftest
        return ruletrans_selftest.run()

    ns_list = _split_ns(args.ns)
    if args.command == "learn":
        vanilla, vnotes = load_vanilla_pairs(args.index, args.objects, args.versions)
        tstats: Dict[str, int] = {}
        terms = load_terms(args.term_table, vanilla, tstats)
        corrections = load_corrections(args.corrections)
        for note in vnotes:
            print(f"# {note}")
        print(f"# G6 过滤 term-table 单字符 key：{tstats.get('single_letter', 0)} 条")
        print(f"# terms 共 {len(terms)} 条")
        print(f"# 人工校正表共 {len(corrections)} 条")
        print()
        for ns in ns_list:
            if args.source == "todo-vendor":
                targets = load_targets_todo_vendor(args.todo_vendor, ns)
                n_rows = count_todo_vendor_rows(args.todo_vendor, ns)
                print(f"# [{ns}] todo-vendor {len(targets)} 行（清单内 {n_rows} 行）"
                      f"{'OK' if len(targets) == n_rows else 'MISMATCH'}")
                if len(targets) != n_rows:
                    raise SystemExit(
                        f"{ns}: 目标键数 {len(targets)} != 行数 {n_rows}")
            else:
                targets = load_targets(args.residual, ns)
            ens = [en for _k, en in targets]
            shapes, sdetail, materials, mdetail, dropped, gdrops = \
                learn_tables(ens, terms, vanilla)
            tmp = BuildResult(ns)
            tmp.total = len(targets)
            tmp.shapes, tmp.shapes_detail = shapes, sdetail
            tmp.materials, tmp.materials_detail = materials, mdetail
            tmp.dropped_materials = dropped
            tmp.guard_drops = gdrops
            _print_tables(tmp)
        return 0

    # build
    results = build_namespaces(
        ns_list, residual_path=args.residual, term_table_path=args.term_table,
        index_path=args.index, objects_dir=args.objects,
        versions_dir=args.versions, out_dir=args.out,
        corrections_path=args.corrections,
        source=args.source, todo_vendor_path=args.todo_vendor,
        batch_report_path=args.batch_report,
    )
    for ns, res in results.items():
        acc = len(res.accepted)
        rej = sum(1 for r in res.rejected if r[3] != "no-hit")
        miss = res.total - acc - rej
        gc = guard_counts(res)
        print(f"[{ns}] 采纳 {acc} / 拒绝 {rej} / 未命中 {miss} / 共 {res.total}"
              f"（shapes {len(res.shapes)}，materials {len(res.materials)}，"
              f"矛盾 {len(res.conflicts)}）")
        print("         守卫：G5 {} / G6 {} / G7 {} / G8 {}".format(
            gc["bracket"], gc["single-letter"], gc["dup-morpheme"], gc["G8-modifier"]))
    print(f"        产出：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
