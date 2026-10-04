"""译料库：从既有汉化模组 jar 中提取/回写三份载荷，并解析安装清单。

术语
----
模板（template）
    已解开的汉化模组 jar 目录，如 ``templates/woldsvaults_cn-1.0.16``。
    其中 ``com/`` ``META-INF/`` ``mixins.*.json`` ``pack.mcmeta`` 是**静态**部分，
    跨版本继承；其余为**载荷**，需要按新版本语料重建。

载荷（payload）
    ``config_payload/`` 下的目录树 + 5 份清单文件。安装行为完全由清单决定，
    因此重建载荷不需要重新编译任何 Java 代码。

清单格式（四种，靠列数区分）
    manifest.txt                  单列  ``目标路径``，源 = config_payload/目标路径
    manifest_client.txt           两列  目标 \t 源
    manifest_server.txt           两列  目标 \t 源
    repair_manifest_client.txt    三列  目标 \t 源 \t 摘要
    repair_manifest_server.txt    单列
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# jar 内固定路径
LITERAL_TSV_IN_JAR = "assets/woldsvaults_cn/literal_zh_cn.tsv"
PAYLOAD_IN_JAR = "assets/woldsvaults_cn/config_payload"
LANG_RE = re.compile(r"^assets/([^/]+)/lang/([a-z_A-Z]+)\.json$")

#: 静态（跨版本继承）的顶层条目
STATIC_PREFIXES = ("com/", "META-INF/", "mixin")
STATIC_FILES = ("pack.mcmeta",)

MANIFEST_NAMES = (
    "manifest.txt",
    "manifest_client.txt",
    "manifest_server.txt",
    "repair_manifest_client.txt",
    "repair_manifest_server.txt",
)


# --------------------------------------------------------------------------- #
# 清单
# --------------------------------------------------------------------------- #
@dataclass
class ManifestEntry:
    """一条载荷安装指令。"""

    target: str  # 相对游戏目录的安装目标
    source: str  # 相对 config_payload/ 的源路径
    digest: str = ""  # repair 清单第三列

    def line(self) -> str:
        parts = [self.target, self.source]
        if self.digest:
            parts.append(self.digest)
        return "\t".join(parts)


@dataclass
class PayloadIndex:
    """五份清单的集合。"""

    universal: list[ManifestEntry] = field(default_factory=list)
    client: list[ManifestEntry] = field(default_factory=list)
    server: list[ManifestEntry] = field(default_factory=list)
    repair_client: list[ManifestEntry] = field(default_factory=list)
    repair_server: list[ManifestEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, list[ManifestEntry]]:
        return {
            "manifest.txt": self.universal,
            "manifest_client.txt": self.client,
            "manifest_server.txt": self.server,
            "repair_manifest_client.txt": self.repair_client,
            "repair_manifest_server.txt": self.repair_server,
        }

    def counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.as_dict().items()}


def parse_manifest(text: str) -> list[ManifestEntry]:
    """解析一份清单。列数自适应：1 列源=目标，2 列源=第二列，3 列再带摘要。"""
    out: list[ManifestEntry] = []
    for raw in text.splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        target = parts[0].strip()
        if not target:
            continue
        if len(parts) >= 3:
            out.append(ManifestEntry(target, parts[1].strip(), parts[2].strip()))
        elif len(parts) == 2:
            out.append(ManifestEntry(target, parts[1].strip()))
        else:
            out.append(ManifestEntry(target, target))
    return out


def load_index(payload_root: Path | str) -> PayloadIndex:
    """读取 config_payload/ 下的全部清单。"""
    root = Path(payload_root)
    idx = PayloadIndex()
    mapping = {
        "manifest.txt": "universal",
        "manifest_client.txt": "client",
        "manifest_server.txt": "server",
        "repair_manifest_client.txt": "repair_client",
        "repair_manifest_server.txt": "repair_server",
    }
    for fname, attr in mapping.items():
        p = root / fname
        if p.is_file():
            setattr(idx, attr, parse_manifest(p.read_text(encoding="utf-8", errors="replace")))
    return idx


def save_index(payload_root: Path | str, idx: PayloadIndex) -> dict[str, int]:
    """回写全部清单，返回各文件行数。"""
    root = Path(payload_root)
    root.mkdir(parents=True, exist_ok=True)
    counts = {}
    for fname, entries in idx.as_dict().items():
        body = "".join(e.line() + "\n" for e in entries)
        (root / fname).write_text(body, encoding="utf-8", newline="\n")
        counts[fname] = len(entries)
    return counts


# --------------------------------------------------------------------------- #
# 硬编码字面量表
# --------------------------------------------------------------------------- #
@dataclass
class LiteralTable:
    """literal_zh_cn.tsv：``英文原文 <TAB> 中文译文``，行序即加载序。"""

    pairs: list[tuple[str, str]] = field(default_factory=list)
    conflicts: dict[str, set[str]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.pairs)

    @property
    def mapping(self) -> dict[str, str]:
        """英文 → 中文。同名多译时取**首次出现**（保持原文件优先级）。"""
        out: dict[str, str] = {}
        for en, zh in self.pairs:
            out.setdefault(en, zh)
        return out

    def render(self) -> str:
        return "".join(f"{en}\t{zh}\n" for en, zh in self.pairs)


def load_literal(path: Path | str) -> LiteralTable:
    """解析 tsv。容忍 CRLF、空行、缺列行。"""
    tbl = LiteralTable()
    seen: dict[str, set[str]] = {}
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        if not raw.strip():
            continue
        if "\t" not in raw:
            continue
        en, zh = raw.split("\t", 1)
        if not en:
            continue
        tbl.pairs.append((en, zh))
        seen.setdefault(en, set()).add(zh)
    tbl.conflicts = {k: v for k, v in seen.items() if len(v) > 1}
    return tbl


# --------------------------------------------------------------------------- #
# 语言文件
# --------------------------------------------------------------------------- #
def save_literal(template_root: Path | str, pairs: list[tuple[str, str]]) -> Path:
    """把（叠加译料后的）对照表写回模板，返回写入路径。

    必须回写：产物 jar 里的 ``literal_zh_cn.tsv`` 是打包时从模板目录取的，
    运行期 ``LiteralTranslator`` 也只读 jar 内这一份。只更新内存中的映射
    会让待译清单变短，玩家侧却查不到新译文。
    """
    p = Path(template_root) / LITERAL_TSV_IN_JAR
    p.parent.mkdir(parents=True, exist_ok=True)
    # 兜底：行式格式承载不了换行/制表符，这里再过滤一次。语料层已在校验
    # 阶段拦下这类条目，但 tsv 一旦被劈断，运行期会把下一条译文错配到
    # 别的原文上——后果比丢一条译文严重得多。
    kept = [(en, zh) for en, zh in pairs
            if chr(10) not in en + zh and chr(13) not in en
            and chr(9) not in en]
    p.write_text(
        "".join(en + chr(9) + zh + chr(10) for en, zh in kept),
        encoding="utf-8", newline=chr(10),
    )
    return p


def load_langs(template_root: Path | str) -> dict[str, dict[str, str]]:
    """收集模板里全部 ``assets/<ns>/lang/<code>.json``。键为 ``ns/lang``。"""
    root = Path(template_root) / "assets"
    out: dict[str, dict[str, str]] = {}
    if not root.is_dir():
        return out
    for ns_dir in sorted(root.iterdir()):
        lang_dir = ns_dir / "lang"
        if not lang_dir.is_dir():
            continue
        for f in sorted(lang_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                out[f"{ns_dir.name}/{f.stem}"] = data
    return out


def save_langs(template_root: Path | str, langs: dict[str, dict[str, str]]) -> int:
    """回写语言文件，返回写入文件数。

    ``langs`` 的键必须是 ``"<命名空间>/<语言码>"``（如 ``compressium/zh_cn``），
    值是该语言文件的**完整内容**——写出去是整文件覆盖语义，不是增量合并。
    因此第三方模组必须以「模组自带 ``zh_cn`` 为底」再叠加我方译文
    （见 :func:`tools.cnrebase.vendor.build_lang`），否则模组原有中文会整片消失
    （``mekanism`` 自带 1446 键、``occultism`` 自带 801 键）。

    键格式非法时直接抛 :class:`ValueError`：历史上传入裸命名空间会让
    ``partition("/")`` 得到空语言码，静默产出名为 ``.json`` 的文件——文件名缺失、
    玩家侧加载不到，而构建全程不报错。
    """
    root = Path(template_root) / "assets"
    n = 0
    for key, data in langs.items():
        ns, sep, code = key.partition("/")
        if not sep or not ns or not code:
            raise ValueError(
                f"语言表键格式非法（应为 ns/lang，如 compressium/zh_cn）: {key!r}"
            )
        d = root / ns / "lang"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{code}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        n += 1
    return n


# --------------------------------------------------------------------------- #
# 静态 / 载荷 判定
# --------------------------------------------------------------------------- #
def is_static_member(rel: str) -> bool:
    """判断模板内某相对路径是否属于可跨版本继承的静态部分。"""
    if rel in STATIC_FILES:
        return True
    if rel.startswith(STATIC_PREFIXES):
        return True
    # 编译产物与 mixin 配置
    if rel.endswith(".class"):
        return True
    base = os.path.basename(rel)
    return base.startswith("mixins.") and base.endswith(".json")


def walk_template(template_root: Path | str) -> dict[str, list[str]]:
    """把模板文件分为 static / payload / other 三类（相对 POSIX 路径）。"""
    root = Path(template_root)
    buckets: dict[str, list[str]] = {"static": [], "payload": [], "other": []}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            full = Path(dp) / f
            rel = full.relative_to(root).as_posix()
            if rel.startswith(PAYLOAD_IN_JAR + "/"):
                buckets["payload"].append(rel)
            elif is_static_member(rel):
                buckets["static"].append(rel)
            elif rel == LITERAL_TSV_IN_JAR:
                buckets["payload"].append(rel)
            elif LANG_RE.match(rel):
                buckets["payload"].append(rel)
            else:
                buckets["other"].append(rel)
    for k in buckets:
        buckets[k].sort()
    return buckets
