"""产物门禁：把「可交付」变成可执行的断言。

设计原则
--------
1. **以模板为参照系**，不写死数字。class 集合、语言键数、清单行数都跟母版比，
   母版升级时门禁自动跟随，不会因为一个魔法数字过期而误报。
2. **以源包为参照系**，不写死 445/409。模组数、成员集合从原始整合包里现算。
3. 需要「不存在」的断言一律走**精确文件名 / 集合差**，禁止子串匹配——
   ``0.5.1.f`` 会命中同为 create 生态的 ``create_enchantment_industry-...-0.5.1.f-...jar``，
   这类误伤会让门禁变成噪声源。
4. 重复 modid 不靠名单核对，而是**对产物重新跑一遍检测**，这才是真正的验收。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from tools.cnrebase import assets, classfile, delta, inject, packs, patches
from tools.cnrebase.build import (
    PROTECTED_FIELDS,
    SELF_MOD_ID,
    TSV_DENY_KEYS,
)
from tools.cnrebase.corpus import Corpus

TEXT_README = "汉化说明.txt"
META_NAME = "CN-BUILD.json"

#: 抄自 delta 的 CJK 判定，用于确认预置文件真的是中文
CJK = re.compile(r"[\u4e00-\u9fff]")


def _cu2(raw: bytes, o: int) -> int:
    return struct.unpack_from(">H", raw, o)[0]


def _cu4(raw: bytes, o: int) -> int:
    return struct.unpack_from(">I", raw, o)[0]


def _read_cp(raw: bytes) -> tuple[dict[int, str], int]:
    """跳过常量池，返回 ``(Utf8 索引 → 字符串, 常量池结束偏移)``。

    刻意**不复用** ``patches`` 的解析器——门禁若与被验实现共用解析代码，
    解析器自身的 bug 就永远查不出来。
    """
    count = _cu2(raw, 8)
    pos, i, utf8 = 10, 1, {}
    while i < count:
        tag = raw[pos]
        if tag == 1:
            ln = _cu2(raw, pos + 1)
            utf8[i] = raw[pos + 3:pos + 3 + ln].decode("utf-8", "replace")
            pos += 3 + ln
        elif tag in (3, 4):
            pos += 5
        elif tag in (5, 6):
            pos += 9
            i += 1
        elif tag in (7, 8, 16, 19, 20):
            pos += 3
        elif tag in (9, 10, 11, 12, 17, 18):
            pos += 5
        elif tag == 15:
            pos += 4
        else:
            raise ValueError(f"未知常量池 tag {tag} @ {pos}")
        i += 1
    return utf8, pos


def _skip_members(raw: bytes, pos: int) -> int:
    """跳过 ``pos`` 处的成员表（字段或方法），返回表末偏移。"""
    n = _cu2(raw, pos)
    pos += 2
    for _ in range(n):
        q = pos + 8
        for _ in range(_cu2(raw, pos + 6)):
            q += 6 + _cu4(raw, q + 2)
        pos = q
    return pos


def _walk_class(raw: bytes) -> str:
    """完整遍历 class 文件；返回空串表示结构自洽。

    逐段按长度推进（常量池 → 字段 → 方法 → 类属性），最后必须**恰好**
    落在文件末尾。这是 JVM 加载前的第一道格式校验，能独立发现
    字节码补丁把某处长度算错、导致后续整体错位的情况。
    """
    try:
        _utf8, pos = _read_cp(raw)
        pos += 6                                    # access / this / super
        pos += 2 + 2 * _cu2(raw, pos)               # interfaces
        pos = _skip_members(raw, pos)               # fields
        pos = _skip_members(raw, pos)               # methods
        n = _cu2(raw, pos)                          # class_attributes_count
        pos += 2
        for _ in range(n):
            pos += 6 + _cu4(raw, pos + 2)
    except (struct.error, IndexError) as e:
        return f"{type(e).__name__}: {e}"
    if pos != len(raw):
        return f"遍历结束于 {pos}，文件长度 {len(raw)}"
    return ""


def _method_codes(raw: bytes, wanted: set[str]) -> dict[str, bytes]:
    """取指定方法的 ``Code`` 字节码（用独立实现的解析器）。"""
    utf8, pos = _read_cp(raw)
    p = pos + 6                       # access_flags / this_class / super_class
    p += 2 + 2 * _cu2(raw, p)         # interfaces
    p += 2                            # fields_count
    for _ in range(_cu2(raw, p - 2)):
        q = p + 8
        for _ in range(_cu2(raw, p + 6)):
            q += 6 + _cu4(raw, q + 2)
        p = q

    mcount = _cu2(raw, p)
    p += 2
    out: dict[str, bytes] = {}
    for _ in range(mcount):
        name = utf8.get(_cu2(raw, p + 2), "")
        q = p + 8
        for _ in range(_cu2(raw, p + 6)):
            an = utf8.get(_cu2(raw, q), "")
            alen = _cu4(raw, q + 2)
            body = q + 6
            if an == "Code" and name in wanted:
                clen = _cu4(raw, body + 4)
                out[name] = raw[body + 8:body + 8 + clen]
            q = body + alen
        p = q
    return out


def _embedded_terms_rows(raw: bytes) -> int | None:
    """数 ``LiteralTranslator.EMBEDDED_TERMS`` 的行数。

    每行构建块形如 ``… iconst_2; anewarray java/lang/String; …``，一行恰好一次。
    这里用 ``classfile`` 的常量池与指令长度表，配合本模块**自有**的
    ``_method_codes``（独立于 patches 的解析器）遍历 ``<clinit>``，按
    「``anewarray`` 的目标类名为 ``java/lang/String``」精确计数——既不受
    javac 生成的具体常量池索引影响，也不会被 ``ldc`` 操作数里恰好等于某
    索引的字节误导。返回 ``None`` 表示 class 结构不符 / 无法解析。
    """
    try:
        cf = classfile.parse(raw)
    except Exception:
        return None
    code = _method_codes(raw, {"<clinit>"}).get("<clinit>")
    if not code:
        return None
    n, i = 0, 0
    while i < len(code):
        op = code[i]
        if op in (0xAA, 0xAB):                      # tableswitch / lookupswitch
            pad = (4 - ((i + 1) % 4)) % 4
            p = i + 1 + pad
            if op == 0xAA:
                lo, hi = struct.unpack_from(">ii", code, p + 4)
                i = p + 12 + 4 * (hi - lo + 1)
            else:
                i = p + 8 + 8 * struct.unpack_from(">i", code, p + 4)[0]
            continue
        if op == 0xC4:                              # wide
            i += 6 if code[i + 1] == 0x84 else 4
            continue
        if op == 0xBD:                              # anewarray
            idx = struct.unpack_from(">H", code, i + 1)[0]
            if cf.class_name(idx) == "java/lang/String":
                n += 1
        i += classfile.OPLEN[op]
    return n


def _extras_dir(rel: str) -> Path:
    """仓库 ``extras/`` 下某个产物目录（门禁与注入侧共用同一处定义）。"""
    return Path(__file__).resolve().parents[2] / rel


def _has_cjk(b: bytes) -> bool:
    return bool(CJK.search(b.decode("utf-8", errors="replace")))


def _has_cjk_text(b: bytes) -> bool:
    """判定「文件里有没有中文」，对 JSON 先解码再查。

    载荷里的 JSON 大量使用 ``\\uXXXX`` 转义（``"\\u6e38\\u620f\\u673a\\u5236"``
    就是「游戏机制」），直接在字节流上跑 CJK 正则会得出「没有中文」的假结论。
    """
    if _has_cjk(b):
        return True
    text = b.decode("utf-8", errors="replace")
    if "\\u" not in text:
        return False
    try:
        data = json.loads(text)
    except Exception:
        return False
    return _has_cjk(json.dumps(data, ensure_ascii=False).encode("utf-8"))


def _duplicate_names(zf: zipfile.ZipFile) -> list[str]:
    """zip 内重复条目名。

    必须查：``rewrite_zip`` 的 add 对已存在的名字会静默跳过，
    一旦分流写错就会出现「磁盘上是英文、zip 里却有两份」这类隐蔽故障。
    """
    seen: set[str] = set()
    dup: list[str] = []
    for n in zf.namelist():
        if n in seen:
            dup.append(n)
        else:
            seen.add(n)
    return dup


@dataclass
class VerifyReport:
    """分段收集断言，最后统一渲染。

    每个 section 自行登记标题，checks 按加入顺序归属到最近登记的 section。
    """

    items: list[tuple[str | None, bool, str, str]] = field(default_factory=list)
    skipped: list[tuple[str | None, str, str]] = field(default_factory=list)
    _current: str | None = None

    def section(self, title: str) -> None:
        self._current = title

    def check(self, cond: bool, label: str, detail: str = "") -> bool:
        self.items.append((self._current, bool(cond), label, detail))
        return bool(cond)

    def skip(self, label: str, why: str) -> None:
        """登记一项**没跑成**的断言。

        必须显式登记：``--client/--server`` 未给时，十几项「与源包逐条
        对照」的断言会整段消失，报告仍是「全部通过」——绿灯会被误读成
        「全量校验通过」。宁可把跳过项摊在报告里，也不留这个盲区。
        """
        self.skipped.append((self._current, label, why))

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def failed(self) -> list[str]:
        return [lbl for _, ok, lbl, _ in self.items if not ok]

    def render(self) -> str:
        out: list[str] = []
        seen: str | None = None
        for sec, ok, lbl, det in self.items:
            if sec != seen:
                out.append("=" * 74)
                out.append(sec or "")
                seen = sec
            out.append(("  OK   " if ok else "  FAIL ") + lbl + (f"  {det}" if det else ""))
        if self.skipped:
            out.append("=" * 74)
            out.append("【跳过】未提供源包对照，以下断言本轮未执行")
            for sec, lbl, why in self.skipped:
                out.append(f"  SKIP  {lbl}  {why}")
        out.append("=" * 74)
        tail = f"（另有 {len(self.skipped)} 项跳过）" if self.skipped else ""
        if self.failed:
            out.append(f"结果: {len(self.failed)} / {self.total} 项失败: "
                       f"{self.failed}{tail}")
        else:
            out.append(f"结果: {self.total} 项全部通过 ✓{tail}")
        return "\n".join(out)


# --------------------------------------------------------------------------- #
# 参照系
# --------------------------------------------------------------------------- #
def _zip_classes(path: Path) -> set[str]:
    if path.is_dir():
        return {p.relative_to(path).as_posix() for p in path.rglob("*.class")}
    with zipfile.ZipFile(path) as z:
        return {n for n in z.namelist() if n.endswith(".class")}


def _zip_json_len(path: Path, member: str) -> int:
    import json

    if path.is_dir():
        f = path / member
        if not f.is_file():
            return -1
        return len(json.loads(f.read_text(encoding="utf-8")))
    with zipfile.ZipFile(path) as z:
        if member not in z.namelist():
            return -1
        return len(json.loads(z.read(member).decode("utf-8")))


def _zip_line_count(path: Path, member: str) -> int:
    if path.is_dir():
        f = path / member
        if not f.is_file():
            return -1
        text = f.read_text(encoding="utf-8", errors="replace")
    else:
        with zipfile.ZipFile(path) as z:
            if member not in z.namelist():
                return -1
            text = z.read(member).decode("utf-8", errors="replace")
    return len([l for l in text.splitlines() if l.strip()])


def _mod_toml(path: Path) -> str:
    if path.is_dir():
        return (path / "META-INF" / "mods.toml").read_text(encoding="utf-8")
    with zipfile.ZipFile(path) as z:
        return z.read("META-INF/mods.toml").decode("utf-8")


def _decoded_cjk(b: bytes) -> int:
    """JSON 解码后的中文字符数；非 JSON 退化为字节级计数。

    载荷里的 JSON 大量使用 ``\\uXXXX`` 转义，直接在字节流上数 CJK 会得到
    「没有中文」的假结论，比较中文多寡必须走解码后的值。
    """
    try:
        data = json.loads(b.decode("utf-8"))
    except Exception:
        return len(CJK.findall(b.decode("utf-8", errors="replace")))
    return len(CJK.findall(json.dumps(data, ensure_ascii=False)))


# --------------------------------------------------------------------------- #
# 【1】汉化模组 jar
# --------------------------------------------------------------------------- #
def verify_jar(r: VerifyReport, jar: Path, template: Path, pack_version: str, mod_version: str) -> None:
    r.section("【1】汉化模组 jar")
    if not r.check(jar.is_file(), "产物存在", jar.name if jar.is_file() else "缺失"):
        return

    toml = _mod_toml(jar)
    want_ver = f"{mod_version}-{pack_version}"
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', toml)
    # 实际版本形如 1.0.17-0.34.1-universal，故用前缀判定
    r.check(m is not None and m.group(1).startswith(want_ver), "mods.toml 版本号已更新",
            m.group(1) if m else "-")

    # 版本约束：整合包依赖必须锁到本次版本
    r.check(re.search(r'modId\s*=\s*"woldsvaults"', toml) is not None
            and f"[{pack_version}" in toml.replace(" ", ""),
            f"woldsvaults 依赖已锁到 >={pack_version}")

    # class 集合与母版完全相等——这是「不重新编译」路线的核心不变量
    tpl_cls = _zip_classes(template)
    jar_cls = _zip_classes(jar)
    r.check(jar_cls == tpl_cls, "自研 class 与母版集合完全一致",
            f"{len(jar_cls)} 个（母版 {len(tpl_cls)}）")
    if jar_cls != tpl_cls:
        r.check(False, "  ├ 缺失", str(sorted(tpl_cls - jar_cls)))
        r.check(False, "  └ 多出", str(sorted(jar_cls - tpl_cls)))
    else:
        n_mixin = len([n for n in jar_cls if "/mixin/" in n])
        r.check(n_mixin == 6, "Mixin 类齐全", f"{n_mixin} 个")

    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        r.check("META-INF/MANIFEST.MF" in names, "MANIFEST 存在")
        mf = z.read("META-INF/MANIFEST.MF").decode("utf-8") if "META-INF/MANIFEST.MF" in names else ""
        r.check("MixinConfigs" in mf, "Mixin 配置已声明")
        for mj in ("mixins.woldsvaults_cn.json", "mixins.woldsvaults_cn.client.json"):
            r.check(mj in names, f"{mj} 存在")

        # 母版遗留的署名 / 推广提示必须已被静默（patches.SILENCE_TARGETS）。
        # 三重口径：字节级（署名/群号）、常量级（中文残留）、语义级（方法体已空）。
        for rel, spec in patches.SILENCE_TARGETS.items():
            short = rel.rsplit("/", 1)[-1]
            if rel not in names:
                r.check(False, f"{short} 存在")
                continue
            raw = z.read(rel)
            left = [m for m in spec.marks if m.encode("utf-8") in raw]
            r.check(not left, f"{short} 无署名 / 群号残留",
                    str(left) if left else "已抹净")
            r.check(not CJK.search(raw.decode("utf-8", "replace")),
                    f"{short} 无中文提示残留")
            codes = _method_codes(raw, set(spec.methods))
            silent = [m for m in spec.methods if codes.get(m) == b"\xb1"]
            r.check(len(silent) == len(spec.methods),
                    f"{short} 提示方法已静默",
                    f"{len(silent)}/{len(spec.methods)}")
            # 字节码补丁改了长度，必须确认整个 class 仍然结构自洽
            err = _walk_class(raw)
            r.check(not err, f"{short} 结构自洽（遍历至文件末尾）", err or "已校验")

        r.check(z.testzip() is None, "jar CRC 校验")

        # LiteralTranslator.EMBEDDED_TERMS 必须已扩容到 128 行（class_overrides
        # 覆盖生效）——天赋界面短语兜底的核心不变量，成品类随仓库资产入库。
        lt_rel = "com/woldsvaults/cn/LiteralTranslator.class"
        if lt_rel in names:
            _rows = _embedded_terms_rows(z.read(lt_rel))
            r.check(_rows == 128, "LiteralTranslator EMBEDDED_TERMS 共 128 行",
                    f"实际 {_rows}" if _rows is not None else "结构不符/无法解析")
        else:
            r.check(False, "LiteralTranslator.class 存在")

        # 硬编码对照表：不得比母版缩水
        tpl_tsv = _zip_line_count(template, assets.LITERAL_TSV_IN_JAR)
        jar_tsv = _zip_line_count(jar, assets.LITERAL_TSV_IN_JAR)
        r.check(jar_tsv >= tpl_tsv > 0, "硬编码对照表未缩水",
                f"{jar_tsv} 行（母版 {tpl_tsv}）")

        # 载荷清单：行数 ≤ 母版（只应剪枝），且无孤儿
        tpl_mf = _zip_line_count(template, f"{assets.PAYLOAD_IN_JAR}/manifest.txt")
        jar_mf = _zip_line_count(jar, f"{assets.PAYLOAD_IN_JAR}/manifest.txt")
        r.check(0 < jar_mf <= tpl_mf, "载荷清单只减不增",
                f"{jar_mf} 行（母版 {tpl_mf}，剪枝 {tpl_mf - jar_mf}）")

        payload_members = {n for n in names
                           if n.startswith(f"{assets.PAYLOAD_IN_JAR}/")
                           and not n.endswith("/")}
        r.check(len(payload_members) > 0, "载荷文件已写入", f"{len(payload_members)} 个")

        # 清单完整性：五份清单里每一条的 source 都必须有实体文件，
        # 且每条 target 都不应再指向已被剪枝的失效命名空间
        total_entries = 0
        dangling: list[str] = []
        for mname in assets.MANIFEST_NAMES:
            member = f"{assets.PAYLOAD_IN_JAR}/{mname}"
            if member not in names:
                continue
            entries = assets.parse_manifest(z.read(member).decode("utf-8", errors="replace"))
            total_entries += len(entries)
            for e in entries:
                src = e.source.lstrip("/")
                if f"{assets.PAYLOAD_IN_JAR}/{src}" not in payload_members:
                    dangling.append(f"{mname}:{e.source}")
        r.check(not dangling, "五份清单条目全部有实体文件",
                f"悬空 {len(dangling)} 条 {dangling[:3]}" if dangling else f"{total_entries} 条命中")

        # 语言表：逐 ns 与母版比对，只增不减
        for ns, code in _lang_targets(template):
            member = f"assets/{ns}/lang/{code}.json"
            if member not in names:
                r.check(False, f"{member} 缺失")
                continue
            have = _zip_json_len(jar, member)
            base = _zip_json_len(template, member)
            r.check(have >= base, f"{ns} 语言表未缩水", f"{have} 键（母版 {base}）")

        # 净化：失效命名空间不应再出现在任何清单里
        stale = [mname for mname in assets.MANIFEST_NAMES
                 if f"{assets.PAYLOAD_IN_JAR}/{mname}" in names
                 and "izzy_vault" in z.read(
                     f"{assets.PAYLOAD_IN_JAR}/{mname}").decode("utf-8", errors="replace")]
        r.check(not stale, "清单中不含已失效的 izzy_vault", f"残留于 {stale}" if stale else "")


def _lang_targets(template: Path) -> list[tuple[str, str]]:
    """母版里出现过中文语言表的 (命名空间, 语言码)。"""
    members: list[str] = []
    if template.is_dir():
        members = [p.relative_to(template).as_posix() for p in template.rglob("assets/*/lang/*.json")]
    else:
        with zipfile.ZipFile(template) as z:
            members = [n for n in z.namelist() if assets.LANG_RE.match(n)]
    out = set()
    for m in members:
        mm = assets.LANG_RE.match(m)
        if mm and mm.group(2) == "zh_cn":
            out.add((mm.group(1), mm.group(2)))
    return sorted(out)


# --------------------------------------------------------------------------- #
# 【2】客户端拖拽包
# --------------------------------------------------------------------------- #
def verify_client(r: VerifyReport, client: Path, src: Path | None, jar: Path | None,
                  pack_version: str, mod_version: str) -> None:
    r.section("【2】客户端拖拽包（PCL 用）")
    if not r.check(client.is_file(), "产物存在", client.name if client.is_file() else "缺失"):
        return
    import json

    with zipfile.ZipFile(client) as z:
        names = z.namelist()
        nset = set(names)
        dup = _duplicate_names(z)
        r.check(not dup, "无重复 zip 条目", f"{len(dup)} 个 {dup[:3]}" if dup else "")
        if not r.check("manifest.json" in nset, "manifest.json 存在"):
            return
        m = json.loads(z.read("manifest.json").decode("utf-8"))
        r.check(m.get("version") == pack_version, "版本号保留", m.get("version"))

        if src is not None:
            with zipfile.ZipFile(src) as zs:
                sm = json.loads(zs.read("manifest.json").decode("utf-8"))
                r.check(len(m.get("files") or []) == len(sm.get("files") or []),
                        "模组清单条目数与源包一致",
                        f"{len(m.get('files') or [])} / {len(sm.get('files') or [])}")
                r.check(m.get("manifestType") == sm.get("manifestType"), "manifestType 未改")
                r.check(m.get("overrides") == sm.get("overrides"), "overrides 字段未改")
                r.check(m.get("minecraft") == sm.get("minecraft"), "minecraft 版本段未改")
                # 逐条 projectID/fileID 保真（PCL 靠它决定下载什么）
                f1 = [(f.get("projectID"), f.get("fileID")) for f in (m.get("files") or [])]
                f2 = [(f.get("projectID"), f.get("fileID")) for f in (sm.get("files") or [])]
                r.check(f1 == f2, "projectID/fileID 逐条保真")
                # 原 overrides 成员一条不丢
                src_ov = {n for n in zs.namelist() if n.startswith("overrides/") or n.startswith("config/")}
                out_ov = {n for n in nset if n.startswith("overrides/") or n.startswith("config/")}
                missing = sorted(src_ov - out_ov)
                r.check(not missing, "原 overrides 成员未丢失",
                        f"丢失 {len(missing)} 条 {missing[:3]}" if missing else f"{len(out_ov)} 条保留")
        else:
            r.skip("与源客户端包逐条对照",
                   "未提供 --client（条目数 / manifestType / overrides / minecraft / "
                   "projectID·fileID / overrides 成员，共 6 项）")

        _nm = str(m.get("name", ""))
        r.check("汉化版" in _nm and pack_version in _nm,
                "展示名已标注汉化版并带整合包版本号", _nm)
        jar_in = [n for n in names if n.startswith("overrides/mods/") and n.endswith(".jar")]
        cn_jars = [n for n in jar_in if mod_version in n]
        r.check(len(cn_jars) == 1,
                "汉化 jar 已注入 overrides/mods/", cn_jars[0] if cn_jars else "-")
        # 随包汉化扩展模组（**客户端专属**，如 JECh 拼音搜索）：允许 overrides/mods/
        # 下存在汉化 jar 之外的额外 jar，但必须逐一对应仓库 extras/mods/（防错配/夹带）。
        extras_dir = _extras_dir("extras/mods")
        extra_expected = {j.name for j in extras_dir.glob("*.jar")} if extras_dir.is_dir() else set()
        extra_in = sorted(n.rsplit("/", 1)[-1] for n in jar_in if n not in cn_jars)
        r.check(set(extra_in) == extra_expected,
                "随包汉化扩展模组已注入（extras/mods）",
                f"{len(extra_in)} 个 {extra_in[:3]}" if extra_in else "无")
        # 反向门禁：**服务端专属**模组绝不能混进客户端包。SkyblockAddon 这类模组
        # 只装服务端，客户端加载会直接失败（引用服务端不存在的类/注册项）。
        # 必须在客户端侧断言——只查服务端包「有」是不够的，那管不住手滑把
        # extras/mods-server/ 也塞进 overrides.update(...) 的情况。
        srv_only_dir = _extras_dir("extras/mods-server")
        srv_only = {j.name for j in srv_only_dir.glob("*.jar")} if srv_only_dir.is_dir() else set()
        leaked = sorted(n.rsplit("/", 1)[-1] for n in jar_in
                        if n.rsplit("/", 1)[-1] in srv_only)
        r.check(not leaked,
                "客户端包未混入服务端专属模组（extras/mods-server）",
                f"混入 {len(leaked)} 个 {leaked[:3]}" if leaked
                else f"已排除 {len(srv_only)} 个")
        # 注入的汉化 jar 必须就是本次构建产物本身（防将来重构 inject 时错配）
        if cn_jars and jar is not None and jar.is_file():
            same = (hashlib.sha256(z.read(cn_jars[0])).digest()
                    == hashlib.sha256(jar.read_bytes()).digest())
            r.check(same, "注入的 jar 与构建产物字节一致")
        r.check("overrides/" + META_NAME in nset, "构建元数据已写入")
        r.check("overrides/" + TEXT_README in nset, "安装说明已写入")

        # —— 载荷预置：中文必须物理存在于包内，而不是只躺在 jar 里等运行期安装 ——
        if jar is not None and jar.is_file():
            targets = inject.payload_targets(jar, "client")
            absent = sorted(t for t in targets if f"overrides/{t}" not in nset)
            r.check(not absent, "载荷全部预置到 overrides/",
                    f"缺 {len(absent)}/{len(targets)} {absent[:2]}" if absent
                    else f"{len(targets)} 个目标")
            # 抽样确认预置内容真的是中文
            snbt = "overrides/config/ftbquests/quests/chapters/2_gaining_a_foothold.snbt"
            if snbt in nset:
                r.check(_has_cjk_text(z.read(snbt)), "FTB 任务书预置内容为中文")
            pb = [n for n in names if "patchouli_books" in n and "/zh_cn/" in n
                  and n.endswith(".json")]
            r.check(bool(pb), "帕秋莉 zh_cn 手册已预置", f"{len(pb)} 个")
            if pb:
                r.check(_has_cjk_text(z.read(pb[0])), "帕秋莉手册预置内容为中文",
                        pb[0].rsplit("/", 3)[-3] if pb[0].count("/") >= 3 else "")

            # 原版自带的中文不得被预置覆盖掉（the_vault 的 config 语言表是官方译文）
            if src is not None and src.is_file():
                with zipfile.ZipFile(src) as zs:
                    src_names = set(zs.namelist())
                    worse, checked = [], 0
                    for t in targets:
                        ko = f"overrides/{t}"
                        if ko not in nset or ko not in src_names:
                            continue
                        checked += 1
                        before = _decoded_cjk(zs.read(ko))
                        after = _decoded_cjk(z.read(ko))
                        if before > after:
                            worse.append(f"{t}（{before}→{after}）")
                r.check(not worse, "预置未削弱原版自带中文",
                        f"{len(worse)} 处 {worse[:2]}" if worse else f"复核 {checked} 处")
            else:
                r.skip("预置未削弱原版自带中文", "未提供 --client，无法与源包比对")
        _check_structure(r, jar, src, client, "overrides/", "overrides/", "客户端")
        r.check(z.testzip() is None, "zip CRC 校验")


# --------------------------------------------------------------------------- #
# 【3】服务端包
# --------------------------------------------------------------------------- #
def verify_server(r: VerifyReport, server: Path, src: Path | None, jar: Path | None,
                  pack_version: str, mod_version: str) -> None:
    r.section("【3】服务端包")
    if not r.check(server.is_file(), "产物存在", server.name if server.is_file() else "缺失"):
        return

    with zipfile.ZipFile(server) as z:
        names = z.namelist()
        nset = set(names)
        dup = _duplicate_names(z)
        r.check(not dup, "无重复 zip 条目", f"{len(dup)} 个 {dup[:3]}" if dup else "")
        jars = [n for n in names if n.startswith("mods/") and n.endswith(".jar")]
        # 本次注入的汉化 jar
        injected = [n for n in jars if SELF_MOD_ID in n]
        r.check(len(injected) == 1, "汉化 jar 已注入 mods/",
                injected[0].rsplit("/", 1)[-1] if injected else "-")
        # 注入的 jar 必须就是本次构建产物本身（防将来重构 inject 时错配）
        if injected and jar is not None and jar.is_file():
            same = (hashlib.sha256(z.read(injected[0])).digest()
                    == hashlib.sha256(jar.read_bytes()).digest())
            r.check(same, "注入的 jar 与构建产物字节一致")

        # 服务端专属模组的声明集合（extras/mods-server/*.jar）。先算出来，
        # 后面「模组数恒等式」与 extras 断言共用同一份口径。
        srv_mods_dir = _extras_dir("extras/mods-server")
        srv_expected = {j.name for j in srv_mods_dir.glob("*.jar")} if srv_mods_dir.is_dir() else set()

        if src is not None:
            with zipfile.ZipFile(src) as zs:
                src_all = set(zs.namelist())
                src_jars = [n for n in src_all
                            if n.startswith("mods/") and n.endswith(".jar")]
                dropped = sorted(set(src_jars) - set(jars))
                # 产物 = 源包 − 剔除 + 注入（汉化 jar + extras/mods-server 的服务端专属模组）
                n_srv_extra = len(srv_expected)
                r.check(len(jars) == len(src_jars) - len(dropped) + len(injected) + n_srv_extra,
                        "模组数 = 源包 − 去重数 + 注入 + 服务端专属模组",
                        f"{len(jars)} = {len(src_jars)} − {len(dropped)} + {len(injected)}"
                        f" + {n_srv_extra}（源包 {len(src_jars)}）")
                # 被剔除的必须是同 modid 的旧版本，而不是别的模组
                sp = packs.ServerPack.open(src)
                try:
                    dups = sp.duplicate_mods()
                finally:
                    sp.close()
                dropped_names = {d.rsplit("/", 1)[-1] for d in dropped}
                expected_drop = {d.rsplit("/", 1)[-1] for info in dups.values()
                                 for d in info["drop"]}
                r.check(dropped_names == expected_drop,
                        "剔除集合 = 同 modid 旧版本集合",
                        f"剔除 {len(dropped_names)}，预期 {len(expected_drop)}")
                expect_keep = {info["keep"].rsplit("/", 1)[-1] for info in dups.values()}
                have = {j.rsplit("/", 1)[-1] for j in jars}
                r.check(expect_keep <= have, "应保留的新版本确实在产物内",
                        f"{len(expect_keep)} 个")
                # 除主动剔除的旧 jar 外，其余成员一条不丢
                missing = sorted(src_all - nset - set(dropped))
                r.check(not missing, "其余成员未丢失",
                        f"丢失 {len(missing)} 条 {missing[:3]}" if missing
                        else f"保留 {len(src_all - set(dropped))} 条")
        else:
            r.skip("与源服务端包逐条对照",
                   "未提供 --server（模组数恒等式 / 剔除集合 / 保留集 / 其余成员，共 4 项）")

        # —— 服务端专属扩展模组 + 开服预设（extras/）——
        # 查的是「该进的进了」；防错配/夹带靠**集合相等**而不是「至少有一个」
        # ——后者在 jar 放错名字时照样绿灯。
        have_base = {j.rsplit("/", 1)[-1] for j in jars}
        if src is None or not src.is_file():
            r.skip("服务端专属模组已注入（extras/mods-server）",
                   "未提供 --server，无法区分源包原有 jar 与本轮注入项")
            r.skip("服务端额外 jar 集合 = extras/mods-server 声明集合",
                   "未提供 --server，无法区分源包原有 jar 与本轮注入项")
            r.skip("服务端包未混入客户端专属模组（extras/mods）",
                   "未提供 --server，无法比对 mods/ 成员")
        else:
            with zipfile.ZipFile(src) as _zs:
                src_jar_names = {n.rsplit("/", 1)[-1] for n in _zs.namelist()
                                 if n.startswith("mods/") and n.endswith(".jar")}
            # 产物独有的 jar = 产物 − 源包 − 本轮汉化 jar（去重只会让源包 jar 变少，
            # 不会造出源包里没有的名字，所以这个差集恰好是「本轮新增的额外 jar」）
            added_names = have_base - src_jar_names - {
                j.rsplit("/", 1)[-1] for j in injected
            }
            r.check(len(added_names) == 1 and added_names <= srv_expected,
                    "服务端专属模组已注入（extras/mods-server）",
                    f"{len(added_names)} 个 {sorted(added_names)}" if added_names else "0 个")
            r.check(added_names == srv_expected,
                    "服务端额外 jar 集合 = extras/mods-server 声明集合",
                    f"注入 {sorted(added_names)} / 声明 {sorted(srv_expected)}")
            # 客户端专属模组（JECh）同样不能混进服务端包
            cli_dir = _extras_dir("extras/mods")
            cli_only = {j.name for j in cli_dir.glob("*.jar")} if cli_dir.is_dir() else set()
            bad = sorted(cli_only & have_base)
            r.check(not bad, "服务端包未混入客户端专属模组（extras/mods）",
                    f"混入 {bad}" if bad else f"已排除 {len(cli_only)} 个")

        # 开服预设：逐个断言存在，且**逐字节**等于仓库里的那份。
        # 官方包根本来就有 install.bat / install.sh（各 61 B），而 rewrite_zip 的
        # add 对源包同名条目静默跳过 —— 只断言「存在」会放过「增强脚本没替换」
        # 这个已经踩过的坑，所以这里比字节。
        preset_dir = _extras_dir("extras/server")
        preset_files = sorted((p for p in preset_dir.iterdir() if p.is_file()),
                              key=lambda p: p.name) if preset_dir.is_dir() else []
        if not preset_files:
            r.skip("开服预设已随包分发（extras/server）", "extras/server/ 为空")
        else:
            for p in preset_files:
                if p.name not in nset:
                    r.check(False, f"服务端包根含预设 {p.name}", "缺失")
                    continue
                r.check(z.read(p.name) == p.read_bytes(),
                        f"服务端包根含预设 {p.name}",
                        f"{p.stat().st_size} B 字节一致")
            # 天空宝库预设必须真的改了 level-type（复制普通那份也算「存在」）
            sky = preset_dir / "server.properties.skyblock"
            if sky.is_file() and "server.properties.skyblock" in nset:
                want = [l for l in sky.read_text(encoding="utf-8", errors="replace").splitlines()
                        if l.startswith("level-type=")]
                got = [l for l in z.read("server.properties.skyblock")
                       .decode("utf-8", "replace").splitlines()
                       if l.startswith("level-type=")]
                r.check(bool(want) and want == got,
                        "天空宝库预设 level-type 与仓库一致",
                        got[0] if got else "无 level-type 行")

        # 真正的验收：对产物重新跑一遍重复检测
        sp2 = packs.ServerPack.open(server)
        try:
            dups2 = sp2.duplicate_mods()
        finally:
            sp2.close()
        r.check(not dups2, "产物内无重复 modid",
                f"残留 {sorted(dups2)}" if dups2 else "0 组")

        tv = [n for n in jars if "the_vault" in n.lower()]
        r.check(len(tv) == 1, "the_vault 唯一", f"{len(tv)} 个")
        r.check(META_NAME in nset, "构建元数据已写入")
        r.check(TEXT_README in nset, "安装说明已写入")
        r.check(any(n.startswith("kubejs/") for n in names), "kubejs 保留")
        r.check(any(n.startswith("forge-") and n.endswith("-installer.jar") for n in names),
                "Forge 安装器保留")
        r.check("server.properties" in nset, "server.properties 保留")

        # —— 载荷预置：服务端目标路径直接落在包根目录 ——
        if jar is not None and jar.is_file():
            targets = inject.payload_targets(jar, "server")
            absent = sorted(t for t in targets if t not in nset)
            r.check(not absent, "载荷全部预置到包根",
                    f"缺 {len(absent)}/{len(targets)} {absent[:2]}" if absent
                    else f"{len(targets)} 个目标")
            snbt = "config/ftbquests/quests/chapters/2_gaining_a_foothold.snbt"
            if snbt in nset:
                r.check(_has_cjk_text(z.read(snbt)), "FTB 任务书预置内容为中文")
        _check_structure(r, jar, src, server, "", "", "服务端")
        r.check(z.testzip() is None, "zip CRC 校验")


# --------------------------------------------------------------------------- #
# 预置 JSON 全量结构断言
# --------------------------------------------------------------------------- #
def _manifest_targets(jar: Path) -> set[str]:
    """jar 内五份清单指向的全部 target。"""
    out: set[str] = set()
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        for mf in assets.MANIFEST_NAMES:
            k = f"{assets.PAYLOAD_IN_JAR}/{mf}"
            if k not in names:
                continue
            for e in assets.parse_manifest(z.read(k).decode("utf-8", errors="replace")):
                out.add(e.target)
    return out


def _json_leaves(b: bytes) -> set[str] | None:
    """JSON 的叶子路径集合；解析失败返回 None。

    list 只记 ``<路径>[]`` 不记长度——合并时 list 以 base 长度为准，
    长度差异不是结构退化；叶子集合缩水才是。
    """
    try:
        data = json.loads(b.decode("utf-8"))
    except Exception:
        return None

    out: set[str] = set()

    def walk(node: object, pre: str) -> None:
        if isinstance(node, dict):
            if not node:
                out.add(pre + "{}")
            for k, v in node.items():
                walk(v, f"{pre}.{k}" if pre else str(k))
        elif isinstance(node, list):
            out.add(f"{pre}[]")
            for v in node:
                walk(v, pre)
        else:
            out.add(pre)

    walk(data, "")
    return out


def _check_structure(r: VerifyReport, jar: Path, src: Path | None, out_zip: Path,
                     prefix_src: str, prefix_out: str, label: str) -> None:
    """产物里每个预置 JSON 的叶子集合必须 ⊇ 原版同路径文件。

    背景：``build._merge_config_payload`` 曾在「无中文可回填」时保留旧版
    载荷，导致 34 个文件被 0.30.0 旧结构覆盖（the_vault 报
    「配置无效 / Some configs are invalid」）。这条断言保证这类退化
    永远到不了用户手里。
    """
    if src is None or not src.is_file() or not out_zip.is_file() or not jar.is_file():
        r.skip(f"{label}：预置 JSON 结构无退化",
               "未提供源包或产物缺失，无法比对叶子集合")
        return
    targets = _manifest_targets(jar)
    checked = skipped = 0
    degraded: list[str] = []
    with zipfile.ZipFile(src) as zs, zipfile.ZipFile(out_zip) as zo:
        src_names = set(zs.namelist())
        for t in sorted(targets):
            if not t.endswith(".json"):
                continue
            ks, ko = prefix_src + t, prefix_out + t
            if ks not in src_names or ko not in set(zo.namelist()):
                skipped += 1          # 新版没有该文件（新文件）或产物未预置
                continue
            raw = zs.read(ks)
            if len(raw) > 12_000_000:
                skipped += 1
                continue
            ls, lo = _json_leaves(raw), _json_leaves(zo.read(ko))
            if ls is None or lo is None:
                skipped += 1          # 解析失败（如带注释的 json），另行人工审
                continue
            checked += 1
            gone = ls - lo
            if gone:
                degraded.append(f"{t}（丢 {len(gone)}/{len(ls)} 叶子）")
    r.check(not degraded, f"{label}：预置 JSON 结构无退化",
            f"{checked} 个核对、{skipped} 个跳过" if not degraded
            else f"{len(degraded)} 个退化，如 {degraded[:4]}")


# --------------------------------------------------------------------------- #
# 【4】Mixin 目标类：版本重基底最脆弱的一环
# --------------------------------------------------------------------------- #
_OWNER_REF = re.compile(rb"L([A-Za-z0-9_/$]+);")
_MIXIN_CFGS = ("mixins.woldsvaults_cn.json", "mixins.woldsvaults_cn.client.json")
_MOD_PREFIX = ("iskallia/", "xyz/iwolfking/")
_MOD_HINT = ("the_vault", "wolds-vaults", "official-mod")


def _collect_mod_jars(pack: Path, prefix: str, out: dict[str, set[str]]) -> None:
    """把包内与汉化相关的模组 jar 成员清单收进 out。"""
    if not pack.is_file():
        return
    tag = pack.name.rsplit(".", 1)[0][:16]
    with zipfile.ZipFile(pack) as z:
        for n in z.namelist():
            if not (n.startswith(prefix) and n.endswith(".jar")):
                continue
            base = n.rsplit("/", 1)[-1]
            if not any(k in base.lower() for k in _MOD_HINT):
                continue
            key = f"{tag}:{base}"
            if key in out:
                continue
            try:
                with zipfile.ZipFile(io.BytesIO(z.read(n))) as mz:
                    out[key] = set(mz.namelist())
            except Exception:
                continue


def verify_mixin(r: VerifyReport, jar: Path, server: Path | None,
                 client: Path | None) -> None:
    """Mixin 配置与目标类的双重核对。

    这是重基底**最容易崩**的一环，必须独立成节：

    * 配置写的是 ``required: true`` + ``defaultRequire: 1`` ——
      目标类被改名或移除时**不是降级，而是启动直接崩溃**；
    * 母版基于 0.30.0，重基底到 0.34.1 时，``iskallia/vault/...`` 这类
      模组侧路径随时可能随上游重构而变（``ResearchDialog`` 的包就有
      7 层深）。
    * 反过来，``net/minecraft/client/**`` 是客户端专属，必须待在
      ``.client.json`` 的 ``client`` 分组里，否则服务端会去注入一个
      它没有的类。
    """
    r.section("【4】Mixin 目标类（跨版本最易崩的一环）")
    if not jar.is_file():
        return

    mod_targets: dict[str, str] = {}
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        for cfg in _MIXIN_CFGS:
            if cfg not in names:
                r.check(False, f"{cfg} 存在")
                continue
            try:
                d = json.loads(z.read(cfg).decode("utf-8"))
            except Exception as exc:
                r.check(False, f"{cfg} 可解析", str(exc))
                continue
            pkg = d["package"].replace(".", "/")
            for group in ("mixins", "client", "server"):
                for c in d.get(group, []):
                    r.check(f"{pkg}/{c}.class" in names,
                            f"[{group}] {c} 的 class 在 jar 内")
            if cfg.endswith(".client.json"):
                r.check(not d.get("mixins") and not d.get("server"),
                        "客户端专属配置未混入双端 Mixin")

        for n in sorted(x for x in names if x.endswith(".class") and "/mixin/" in x):
            refs = {m.group(1).decode() for m in _OWNER_REF.finditer(z.read(n))}
            hits = sorted(x for x in refs if x.startswith(_MOD_PREFIX))
            base = n.rsplit("/", 1)[-1][:-len(".class")]
            if len(hits) == 1:
                mod_targets[base] = hits[0]
            elif hits:
                r.check(False, f"{base} 的模组侧目标不唯一", str(hits))

    r.check(bool(mod_targets), "已识别模组侧 Mixin 目标",
            ", ".join(f"{k}→{v.rsplit('/', 1)[-1]}" for k, v in sorted(mod_targets.items()))
            or "无")

    pool: dict[str, set[str]] = {}
    if server is not None:
        _collect_mod_jars(server, "mods/", pool)
    if client is not None:
        _collect_mod_jars(client, "overrides/mods/", pool)
    if not pool:
        for cls, tgt in sorted(mod_targets.items()):
            r.skip(f"{cls} 的目标类在新版仍存在",
                   f"--server/--client 未给，无法核对 {tgt.rsplit('/', 1)[-1]}")
        return
    for cls, tgt in sorted(mod_targets.items()):
        hit = sorted(k for k, v in pool.items() if f"{tgt}.class" in v)
        r.check(bool(hit), f"{cls} 的目标类在新版仍存在",
                f"{tgt.rsplit('/', 1)[-1]} @ {hit[0].rsplit(':', 1)[-1]}" if hit
                else f"缺失 {tgt}（required:true → 启动崩溃）")


# --------------------------------------------------------------------------- #
# 【5】报告与清单
# --------------------------------------------------------------------------- #
def verify_docs(r: VerifyReport, out: Path) -> None:
    r.section("【5】报告与待译清单")
    want = ["CN-REPORT.md", "cn-build-summary.json", "todo/todo-lang.tsv",
            "todo/todo-literal.tsv", "todo/review-config-structure.json"]
    for rel in want:
        p = out / rel
        r.check(p.is_file() and p.stat().st_size > 0, f"build/cn/{rel}",
                f"{p.stat().st_size} B" if p.is_file() else "缺失")
    rep = out / "CN-REPORT.md"
    if rep.is_file():
        txt = rep.read_text(encoding="utf-8")
        for sec in ("覆盖", "硬编码", "配置", "待译"):
            r.check(sec in txt, f"CN-REPORT.md 含「{sec}」章节")


# --------------------------------------------------------------------------- #
# 【7】第三方缺口台账口径自证
# --------------------------------------------------------------------------- #
def verify_vendor(r: VerifyReport, out: Path) -> None:
    """第三方缺口台账的**口径自证**：``sum(residual) == 待译清单条数``。

    防的是一类「数字好看但误导派活」的缺陷：台账曾把缺口算成
    「模组英文键 − 模组自带 zh」，**没扣 CFPA 底**，于是 CFPA 已整包覆盖的
    命名空间（``chipped`` 自带底 7468 键）在报告里仍显示「待译 7467」，把下一批
    翻译引向其实已完成的模组。

    这里从两份**落盘产物**核对口径（不依赖内存、也不写死任何数字，随语料浮动）：

    * ``todo/vendor-scan.json`` —— 台账，每条含 ``residual`` 等口径字段；
    * ``cn-build-summary.json`` —— ``rebase.todo_vendor`` 即真实待译条数。

    任一缺字段 / 缺文件都会暴露；缺文件时按 SKIP 处理（未启用 vendor 通道）。
    """
    r.section("【7】第三方缺口台账口径")
    scan = out / "todo" / "vendor-scan.json"
    summary = out / "cn-build-summary.json"
    if not scan.is_file() or not summary.is_file():
        r.skip("第三方缺口台账口径自证", "缺 todo/vendor-scan.json 或 cn-build-summary.json")
        return
    try:
        stats = json.loads(scan.read_text(encoding="utf-8"))
        sm = json.loads(summary.read_text(encoding="utf-8"))
    except Exception as e:  # pragma: no cover
        r.check(False, "台账文件可解析", str(e))
        return
    if not isinstance(stats, list):
        r.check(False, "todo/vendor-scan.json 为列表", type(stats).__name__)
        return

    need = {"residual", "cfpa", "ours", "covered"}
    have = set().union(*(set(s) for s in stats)) if stats else set()
    miss = sorted(need - have)
    r.check(not miss, "台账含残差口径字段（residual/cfpa/ours/covered）",
            "缺: " + ", ".join(miss) if miss else "四字段齐备")

    todo = (sm.get("rebase") or {}).get("todo_vendor")
    if todo is None:
        r.skip("sum(残差) == 待译清单条数", "cn-build-summary.json 无 todo_vendor")
        return
    total = sum(int(s.get("residual", 0)) for s in stats)
    r.check(total == int(todo), "sum(残差) == 第三方待译清单条数（口径自证）",
            f"残差和={total} 清单={int(todo)}")

    # 派活台账本身也要在，且表头口径清晰（列顺序即语义）。
    resid = out / "todo" / "vendor-residual.tsv"
    head = ["ns", "residual", "en", "self_zh", "cfpa", "ours"]
    if resid.is_file():
        lines = [ln for ln in resid.read_text(encoding="utf-8").splitlines() if ln]
        got = lines[0].split("\t") if lines else []
        r.check(got[: len(head)] == head, "todo/vendor-residual.tsv 表头正确",
                str(got[: len(head)]) if got else "空文件")
    else:
        r.check(False, "todo/vendor-residual.tsv 存在")


# --------------------------------------------------------------------------- #
# 【6】译料层是否真的进了产物
# --------------------------------------------------------------------------- #
def _manifest_target_sources(z: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    """jar 内五份清单的 ``目标路径 → 载荷源路径``。"""
    out: dict[str, str] = {}
    for mf in assets.MANIFEST_NAMES:
        k = f"{assets.PAYLOAD_IN_JAR}/{mf}"
        if k not in names:
            continue
        for e in assets.parse_manifest(z.read(k).decode("utf-8", "replace")):
            out.setdefault(e.target, e.source)
    return out


def verify_corpus(r: VerifyReport, jar: Path, corpus_root: str | None) -> None:
    """译料层的每一条译文都必须能在产物里找回来。

    这一节防的是一类**静默失效**：译料只更新了内存里的映射（于是待译清单变短、
    报告变好看），却没有回写进模板载荷——玩家侧根本查不到译文，门禁却全绿。
    报告里的数字好看不等于译文进了包，只有从产物里捞回来才算数。
    """
    r.section("【6】译料层已消费")
    if corpus_root is None:
        r.skip("译料层条目进入产物", "未指定 --corpus")
        return
    corpus = Corpus.load(corpus_root)
    st = corpus.stats()
    total = st["lang"] + st["literal"] + st["config"] + st["vendor"]
    if total == 0:
        r.check(True, "译料层为空（尚未补译）", "无需核对")
        return
    if not jar.is_file():
        r.skip("译料层条目进入产物", "汉化 jar 缺失")
        return

    tab = chr(9)
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())

        # —— 语言键 ——
        bad_lang: list[str] = []
        parsed: dict[str, dict] = {}
        for ns, kv in corpus.lang.items():
            m = f"assets/{ns}/lang/zh_cn.json"
            if m not in names:
                bad_lang.append(f"{ns}（产物无该语言表）")
                continue
            if ns not in parsed:
                parsed[ns] = json.loads(z.read(m).decode("utf-8"))
            for k, v in kv.items():
                if parsed[ns].get(k) != v:
                    bad_lang.append(f"{ns}:{k}")
        r.check(not bad_lang, "语言键译料已写入产物",
                f"缺 {len(bad_lang)} 条 {bad_lang[:3]}" if bad_lang
                else f"复核 {st['lang']} 键")

        # —— 硬编码字面量 ——
        if st["literal"]:
            keys: set[str] = set()
            if assets.LITERAL_TSV_IN_JAR in names:
                text = z.read(assets.LITERAL_TSV_IN_JAR).decode("utf-8", "replace")
                for line in text.splitlines():
                    if tab in line:
                        keys.add(line.split(tab, 1)[0])
            # TSV_DENY_KEYS 里的键是**故意**不写进对照表的：它们由运行时
            # EMBEDDED_TERMS 子串兜底负责，留在 TSV 里反而会短路它。故这些
            # 译料条目「产物里查不到」是预期结果，不计入缺键。
            denied = [k for k in corpus.literal if k in TSV_DENY_KEYS]
            miss = sorted(k for k in corpus.literal
                          if k not in keys and k not in TSV_DENY_KEYS)
            r.check(not miss, "硬编码译料已写入产物对照表",
                    f"缺 {len(miss)} 条 {miss[:2]}" if miss
                    else f"复核 {st['literal']} 条"
                         + (f"（{len(denied)} 条转入 EMBEDDED_TERMS 兜底）"
                            if denied else ""))

        # —— 第三方模组语言 ——
        # 与语言键同源但不同表：vendor 通道是「以模组自带 zh 为底整份生成」的，
        # 只更新内存映射同样会让产物缺译文。这里逐键回捞。
        if st["vendor"]:
            bad_v: list[str] = []
            vparsed: dict[str, dict] = {}
            for ns, kv in corpus.vendor.items():
                m = f"assets/{ns}/lang/zh_cn.json"
                if m not in names:
                    bad_v.append(f"{ns}（产物无该语言表）")
                    continue
                if ns not in vparsed:
                    vparsed[ns] = json.loads(z.read(m).decode("utf-8"))
                for k, v in kv.items():
                    if vparsed[ns].get(k) != v:
                        bad_v.append(f"{ns}:{k}")
            r.check(not bad_v, "第三方模组译料已写入产物语言表",
                    f"缺 {len(bad_v)} 条 {bad_v[:3]}" if bad_v
                    else f"复核 {st['vendor']} 键 / {len(corpus.vendor)} 个命名空间")

        # —— 配置文本 ——
        if st["config"]:
            tmap = _manifest_target_sources(z, names)
            bad_cfg: list[str] = []
            checked = 0
            for target, kv in corpus.config.items():
                src = tmap.get(target)
                if src is None:
                    bad_cfg.append(f"{target}（清单无此目标）")
                    continue
                member = f"{assets.PAYLOAD_IN_JAR}/{src}"
                if member not in names:
                    bad_cfg.append(f"{target}（载荷缺失）")
                    continue
                data = delta.load_json_safe(z.read(member))
                if data is None:
                    bad_cfg.append(f"{target}（载荷无法解析）")
                    continue
                for ptr, zh in kv.items():
                    checked += 1
                    if delta.get_at_pointer(data, ptr) != zh:
                        bad_cfg.append(f"{target}{ptr}")
            r.check(not bad_cfg, "配置文本译料已写入产物载荷",
                    f"缺 {len(bad_cfg)} 条 {bad_cfg[:2]}" if bad_cfg
                    else f"复核 {checked} 处")


# --------------------------------------------------------------------------- #
# 【8】配置数据标识符：主键必须保持英文，且显示层仍有中文兜底
# --------------------------------------------------------------------------- #
def _field_values(obj: object, field: str) -> list[str]:
    """递归收集全部 ``field`` 字段的字符串值。"""
    out: list[str] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            v = node.get(field)
            if isinstance(v, str):
                out.append(v)
            for x in node.values():
                walk(x)
        elif isinstance(node, list):
            for x in node:
                walk(x)

    walk(obj)
    return out


def _literal_pairs(z: zipfile.ZipFile, names: set[str]) -> dict[str, str]:
    """jar 内字面量对照表 ``en -> zh``。"""
    if assets.LITERAL_TSV_IN_JAR not in names:
        return {}
    out: dict[str, str] = {}
    for line in z.read(assets.LITERAL_TSV_IN_JAR).decode("utf-8", "replace").splitlines():
        if chr(9) in line:
            en, zh = line.split(chr(9), 1)
            out.setdefault(en, zh)
    return out


def verify_identifiers(r: VerifyReport, jar: Path) -> None:
    """守三条不变量（0.34.1「研究界面打不开」事故的回归防线）。

    背景：``researches.json`` 的 ``name`` 是 ``ResearchConfig.getByName`` 的主键，
    与 ``researches_gui_styles.json`` 的**键**（英文）必须一致。旧版载荷把它翻成
    中文后交集只剩 1/95 → ``getByName`` 返回 null → ``ResearchDialog.render()``
    抛 NPE。修复是「主键一律回写成新版英文原文」，中文交给字面量通道渲染。

    所以这里要同时守住**两个方向**：

    * 主键不能再被翻（否则崩溃复现）；
    * 回写成英文后界面不能反而变英文（否则「修好崩溃、汉化退化」）。

    载荷是 ASCII 转义过的（``\\uXXXX``），**必须先用 json 解一层再判中文**，
    直接在字节流上跑 CJK 正则会得到「没有中文」的假绿灯 —— 本项目已踩过同类坑。
    """
    r.section("【8】配置数据标识符")
    if not jar.is_file():
        r.skip("保护配置的标识符字段保持英文", "汉化 jar 缺失")
        return
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        tmap = _manifest_target_sources(z, names)

        def load(target: str):
            src = tmap.get(target)
            if src is None:
                return None
            member = f"{assets.PAYLOAD_IN_JAR}/{src}"
            if member not in names:
                return None
            return delta.load_json_safe(z.read(member))

        # —— 1. 主键保持英文 ——
        bad: list[str] = []
        display: list[str] = []
        for target in sorted(PROTECTED_FIELDS):
            obj = load(target)
            if obj is None:
                bad.append(f"{target}（清单无此目标或载荷缺失）")
                continue
            for field in sorted(PROTECTED_FIELDS[target]):
                got = _field_values(obj, field)
                hit = [v for v in got if CJK.search(v)]
                if hit:
                    bad.append(
                        f"{target}:{field} 仍有中文 {len(hit)}/{len(got)} 例={hit[:2]}"
                    )
            # ``name`` 是显示名（值字段如 pool.value 只是引用，不要求有译文）
            if "name" in PROTECTED_FIELDS[target]:
                display.extend(_field_values(obj, "name"))
        r.check(not bad, "保护配置的标识符字段保持英文",
                f"核对 {len(PROTECTED_FIELDS)} 个配置" if not bad
                else "; ".join(bad[:2]))

        # —— 2. 受保护配置的样式键必须能被它的 name/id 覆盖 ——
        # 只查**受保护配置自己的**同名样式表：这一条正是崩掉的那个不变量
        # （``researches_gui_styles.json`` 的键 = 研究主键）。
        # 不去横扫全部 ``*_gui_styles.json``：同目录另有配对关系不同的样式表
        # （``greed/greed_gui_styles.json`` 的键属于 ``greed_nodes.json`` 的
        # ``tree.skills[].id``），按文件名硬配对会误报，把门禁变成噪声源。
        unpaired: list[str] = []
        pairs_checked = 0
        for target in sorted(PROTECTED_FIELDS):
            stem = target[:-len(".json")] if target.endswith(".json") else target
            sty = f"{stem}_gui_styles.json"
            if sty not in tmap:
                continue
            sobj, cobj = load(sty), load(target)
            if sobj is None or cobj is None:
                continue
            styles = sobj.get("styles") if isinstance(sobj, dict) else None
            if not isinstance(styles, dict):
                continue
            pairs_checked += 1
            known = set(_field_values(cobj, "name")) | set(_field_values(cobj, "id"))
            miss = sorted(set(styles) - known)
            if miss:
                unpaired.append(
                    f"{sty.rsplit('/', 1)[-1]} 有 {len(miss)}/{len(styles)} 个键在"
                    f" {target} 里找不到（例 {miss[:2]}）"
                )
        r.check(not unpaired, "受保护配置的样式键能被其 name/id 覆盖",
                f"{pairs_checked} 组配对全部对齐" if not unpaired
                else "; ".join(unpaired[:2]))

        # —— 3. 显示名有中文兜底，且不会被中文反查表改写 ——
        pairs = _literal_pairs(z, names)
        reverse: dict[str, str] = {}
        for en, zh in pairs.items():
            reverse.setdefault(zh, en)
        no_disp: list[str] = []
        mangled: list[str] = []
        total = 0
        for v in sorted(set(display)):
            total += 1
            zh = pairs.get(v)
            if not zh or not CJK.search(zh):
                no_disp.append(v)
            elif reverse.get(v, v) != v:
                mangled.append(f"{v}→{reverse[v]}")
        r.check(not no_disp, "回写为英文的主键在字面量对照表里有中文",
                f"复核 {total} 个显示名" if not no_disp
                else f"缺 {len(no_disp)} 条（界面会露英文）{no_disp[:3]}")
        r.check(not mangled, "英文主键不会被中文反查表改写",
                f"复核 {total} 个显示名" if not mangled
                else f"{len(mangled)} 条会被改写 {mangled[:3]}")


# --------------------------------------------------------------------------- #
def verify_research_descriptions(r: VerifyReport, jar: Path) -> None:
    """【9】研究说明覆盖：91 个界面研究键必须 91/91 有中文。

    背景（0.34.1 用户反馈「点开研究只看到英文占位」）：
    ``SkillDescriptionsConfig`` 维护**两张独立的 map** —— 主表
    ``config/the_vault/skill_descriptions.json`` 与 locale 表
    ``config/the_vault/lang/<locale>/skill_descriptions.json``，
    ``getDescriptionFor`` **查询期**先查 locale、miss 再查主表、再 miss
    才回退到硬编码 ``No description for X, yet``。查表是 ``HashMap.get``
    **精确 equals**（大小写/空格敏感）。

    所以下面三条都是在守这个语义：

    * locale 表缺 ``descriptions`` 包裹 → ``loadLocaleVariants`` 会
      **静默跳过整个文件**（不崩、不报错、中文全没了）—— 最阴的一坑；
    * 键名必须与 ``researches_gui_styles.json`` 的键**逐字节一致**
      （主表里 ``Laser IO`` vs 研究键 ``LaserIO`` 就因此永不命中）；
    * 覆盖必须 91/91，少一个就是玩家可见的英文占位；
    * **同一张表还供技能树（SkillDialog）与贪婪天赋（GreedDialog）用**
      —— ``getDescriptionFor`` 的调用方是这一整族 dialog，所以除 91 个
      研究键外，还要查全表「非空条目是否含中文」（断言 5）。
    """
    r.section("【9】研究说明覆盖")
    if not jar.is_file():
        r.skip("界面研究键的说明 91/91 有中文", "汉化 jar 缺失")
        return
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        tmap = _manifest_target_sources(z, names)
        P = assets.PAYLOAD_IN_JAR

        def load(target: str):
            src = tmap.get(target)
            if src is None:
                return None
            member = f"{P}/{src}"
            return (delta.load_json_safe(z.read(member))
                    if member in names else None)

        styles = load("config/the_vault/researches_gui_styles.json")
        zhloc = load(
            "config/the_vault/lang/zh_cn/skill_descriptions.json")
        main = load("config/the_vault/skill_descriptions.json")
        if styles is None or zhloc is None:
            r.check(False, "研究说明两文件都在载荷清单里",
                    f"styles={styles is not None} zh_cn={zhloc is not None}")
            return
        skeys = sorted(styles.get("styles", {}))
        zd = zhloc.get("descriptions")

        # 1) locale 表必须有 descriptions 包裹（缺了 = 整文件静默失效）
        r.check(isinstance(zd, dict),
                "zh_cn 说明表带 descriptions 包裹（缺了会静默失效）",
                f"实际类型 {type(zd).__name__}" if not isinstance(zd, dict)
                else "")
        if not isinstance(zd, dict):
            return

        def zh_text(v: object) -> str:
            # Component 有三种合法形态：纯字符串 / 单对象 {text,...} / 对象数组。
            # 早期只处理 str 与 list，**对象形态被当成空串** → 整类条目对
            # 「是否含中文」的检查隐形（上游 zh_cn 表里就有 32 条是对象形态）。
            if isinstance(v, str):
                return v
            if isinstance(v, dict):
                return str(v.get("text", ""))
            if isinstance(v, list):
                return "".join(p.get("text", "") for p in v
                               if isinstance(p, dict))
            return ""

        # 2) 覆盖 91/91 且值含中文
        no_key = [k for k in skeys if k not in zd]
        no_cjk = [k for k in skeys
                  if k in zd and not CJK.search(zh_text(zd[k]))]
        r.check(not no_key,
                f"界面研究键的说明 {len(skeys)}/{len(skeys)} 有条目",
                f"缺 {len(no_key)} 条 {no_key[:4]}")
        r.check(not no_cjk,
                "界面研究键的说明全部含中文",
                f"{len(no_cjk)} 条仍是英文 {no_cjk[:4]}")

        # 3) 键名体检：locale 表里不应有「几乎等于某研究键却又不相等」的键
        #    （正是 Laser IO / LaserIO 那类拼写漂移 —— 精确 equals 下永不命中）
        import re as _re

        def norm(s: str) -> str:
            return _re.sub(r"[^a-z0-9]", "", s.lower())

        sk = {norm(k): k for k in skeys}
        drift = []
        for k in zd:
            n = norm(k)
            # 只在「正确拼写的键在 zh_cn 里不存在」时报——若正确键已有
            # 中文条目，多余变体（如 'Backpacks!' 空值垃圾键）游戏永不
            # 查它，属无害噪声，报出来只会淹没真问题。
            if n in sk and k != sk[n] and sk[n] not in zd:
                drift.append(f"{k!r} 应为 {sk[n]!r}")
        r.check(not drift,
                "说明键名与研究键无拼写漂移",
                f"{len(drift)} 处 {drift[:3]}")

        # 4) 值不允许是空数组（Component 解析会抛
        #    JsonParseException("Unexpected empty array of components")）
        empty = [k for k, v in zd.items()
                 if isinstance(v, list) and not v]
        r.check(not empty,
                "说明值无空数组（空数组会让游戏解析抛异常）",
                f"{len(empty)} 条 {empty[:3]}")

        # 5) 全表体检：**非空**说明必须含中文。
        #    依据：getDescriptionFor 的调用方不止研究面板 ——
        #    SkillDialog（技能树）、GreedDialog（贪婪天赋）、ArchetypeDialog、
        #    AbilityDescriptionFactory 读的是同名家族表。上游 zh_cn 说明表
        #    是「英文复制品」，漏翻就在面板里露英文；空字符串是上游占位
        #    （不给中文正文，也不会显示英文），所以只查非空条目。
        def _dm(o: object) -> dict:
            if not isinstance(o, dict):
                return {}
            d = o.get("descriptions")
            return d if isinstance(d, dict) else o

        fam = {
            "skill_descriptions": zd,
            "abilities_descriptions": _dm(
                load("config/the_vault/lang/zh_cn/abilities_descriptions.json")),
            "archetype_descriptions": _dm(
                load("config/the_vault/archetype_descriptions.json")),
        }
        resid: dict[str, list[str]] = {}
        for label, dd in fam.items():
            bad = [k for k, v in dd.items()
                   if zh_text(v).strip() and not CJK.search(zh_text(v))]
            if bad:
                resid[label] = bad
        r.check(not resid,
                "说明表（技能/天赋/原型）非空条目全部含中文",
                "; ".join(f"{k} {len(v)} 条 {v[:2]}"
                          for k, v in resid.items()))


# --------------------------------------------------------------------------- #
# 【12】汉化数据包通道：OpenLoader 只把 data/ 当数据包加载
# --------------------------------------------------------------------------- #
#: 汉化数据包在包内的落点（客户端再叠一层 ``overrides/``）。
DATA_PACK_DIR = "config/openloader/data"

#: 数据包里必须出现的 abilities 描述覆盖文件（汉化数据覆盖的核心目标之一）。
DATA_PACK_KEY_FILE = (
    "data/woldsvaults/vault_configs/abilities/descriptions/wolds_abilities.json"
)


def _find_data_packs(namelist: list[str], dir_prefix: str) -> list[str]:
    """在包内 ``dir_prefix/`` 下找汉化数据包 zip。

    按「名字以 ``WoldsVaults-CN-Data`` 开头且以 ``.zip`` 结尾」匹配，既能命中包内
    约定的 ``WoldsVaults-CN-Data.zip``（不带版本号，与 ``WoldsVaults-CN-Lang.zip``
    一致），也不会因将来加版本号后缀而漏判。
    """
    d = dir_prefix.rstrip("/") + "/"
    return sorted(
        n for n in namelist
        if n.startswith(d)
        and n.endswith(".zip")
        and n.rsplit("/", 1)[-1].startswith("WoldsVaults-CN-Data")
    )


def verify_data_pack(
    r: VerifyReport, dist: Path, client: Path | None, server: Path | None,
) -> None:
    """【12】汉化数据包：``data/`` 必须走数据包通道，且资源包里不得再混入 ``data/``。

    背景（本轮修复的 bug）：``data/`` 覆盖曾被打进 ``WoldsVaults-CN-Lang.zip``
    资源包，而 **OpenLoader 的 ``resources/`` 只当资源包加载（仅 ``assets/``
    生效）**——``data/`` 放那里根本不生效，装备属性说明 / 技能描述 / 物品提示
    全部漏翻。正确落点是 ``config/openloader/data/``（上游整合包同目录里就有
    4 个 zip）。

    本节守四件事：

    1. 客户端 PCL 包内含数据包（``overrides/config/openloader/data/``）；
    2. 服务端包内含同一个数据包（``config/openloader/data/``）；
    3. 数据包自身内容完整：``pack.mcmeta`` + ``data/woldsvaults/...`` 覆盖，
       且 ``pack_format == 8``（1.18.2）；
    4. **回归守卫**：``dist/WoldsVaults-CN-Lang-*.zip`` 里不得再有任何 ``data/``
       条目——这正是本轮修复的 bug，必须锁死。
    """
    r.section("【12】汉化数据包（OpenLoader data 通道）")

    payloads: dict[str, bytes] = {}
    for label, zip_path, prefix in (
        ("客户端", client, "overrides/"),
        ("服务端", server, ""),
    ):
        if zip_path is None or not zip_path.is_file():
            r.skip(f"{label}包内含汉化数据包", f"{label}产物缺失")
            continue
        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            hits = _find_data_packs(names, prefix + DATA_PACK_DIR)
            ok = r.check(
                len(hits) == 1,
                f"{label}包内含汉化数据包（{prefix}{DATA_PACK_DIR}/）",
                hits[0] if len(hits) == 1 else f"命中 {len(hits)} 个 {hits[:2]}",
            )
            if ok:
                payloads[label] = z.read(hits[0])

    payload = payloads.get("客户端") or payloads.get("服务端")
    if payload is None:
        r.skip("数据包含 pack.mcmeta 与 data/woldsvaults 覆盖",
               "两侧产物都没有可检的数据包")
    else:
        with zipfile.ZipFile(io.BytesIO(payload)) as dz:
            dn = dz.namelist()
            r.check("pack.mcmeta" in dn, "数据包含 pack.mcmeta")
            r.check(DATA_PACK_KEY_FILE in dn, "数据包含 abilities 描述覆盖",
                    DATA_PACK_KEY_FILE.rsplit("/", 1)[-1])
            n_data = sum(1 for n in dn if n.startswith("data/"))
            r.check(n_data > 0, "数据包含 data/ 覆盖文件", f"{n_data} 个")
            fmt = None
            if "pack.mcmeta" in dn:
                try:
                    meta = json.loads(dz.read("pack.mcmeta").decode("utf-8"))
                    fmt = (meta.get("pack") or {}).get("pack_format")
                except Exception:
                    fmt = None
            r.check(fmt == 8, "数据包 pack_format == 8（1.18.2）", f"实际 {fmt}")

    # —— 回归守卫：资源包（应为纯 assets/）里不得混入任何 data/ 条目 ——
    lang_zips = sorted(dist.glob("WoldsVaults-CN-Lang-*.zip"))
    if not lang_zips:
        r.skip("汉化资源包内无 data/ 条目（回归守卫）",
               "缺 dist/WoldsVaults-CN-Lang-*.zip")
    else:
        for lz_path in lang_zips:
            with zipfile.ZipFile(lz_path) as lz:
                bad = sorted(n for n in lz.namelist() if n.startswith("data/"))
            r.check(not bad, f"{lz_path.name} 内无 data/ 条目（回归守卫）",
                    f"误入 {len(bad)} 条 {bad[:2]}" if bad else "0 条")


def run(out: Path, template: Path, pack_version: str, mod_version: str,
        client_src: Path | None = None, server_src: Path | None = None,
        corpus_root: str | None = None) -> VerifyReport:
    """对 ``out/dist`` 下的三件产物跑完整门禁。"""
    dist = out / "dist"
    jar = dist / f"{SELF_MOD_ID}-{mod_version}-{pack_version}-universal.jar"
    r = VerifyReport()
    verify_jar(r, jar, template, pack_version, mod_version)
    verify_client(r, dist / f"WoldsVaults-{pack_version}-CN-Client-PCL.zip",
                  client_src, jar, pack_version, mod_version)
    verify_server(r, dist / f"WoldsVaults-{pack_version}-CN-Server.zip",
                  server_src, jar, pack_version, mod_version)
    verify_mixin(r, jar, dist / f"WoldsVaults-{pack_version}-CN-Server.zip",
                 dist / f"WoldsVaults-{pack_version}-CN-Client-PCL.zip")
    verify_corpus(r, jar, corpus_root)
    verify_identifiers(r, jar)
    verify_research_descriptions(r, jar)
    verify_no_literal_collapse(r, jar)
    verify_locale_copies(r, dist / f"WoldsVaults-{pack_version}-CN-Client-PCL.zip")
    verify_docs(r, out)
    verify_vendor(r, out)
    verify_data_pack(r, dist, dist / f"WoldsVaults-{pack_version}-CN-Client-PCL.zip",
                     dist / f"WoldsVaults-{pack_version}-CN-Server.zip")
    return r


#: 同一个中文被多少个**互不相同**的英文共用即视为「塌缩误译」。
#:
#: 现实里存在合理的复用（``Level``/``Lv.``/``Rank`` → 等级；``Unlock ``/
#: ``Unlocks the `` → 解锁 ；``Bleed I``/``Bleed II`` → 流血 I/II），
#: 实测合法组最大 7 个（``Buffed``/``Empower``/``Empowered``/``Powerup``/
#: ``REINFORCED`` → 强化）。阈值取 10：既能放过合法同义合并，又能拦住
#: 2026-10-03 发现的那种崩坏——母版把 **64 条**互不相关的英文
#: （难度档位标签、``&5…`` 提示行、``&6/gamerule …`` 命令行…）统统
#: 译成了同一个「宝库指南」，玩家实机看到界面上一片「宝库指南」。
COLLAPSE_THRESHOLD = 10

#: **已知「上游 zh_cn 语言副本本身就漏译」的键**（白名单之外的任何缺键都判失败）。
#:
#: 2026-10-03：这个白名单曾有 11 条 —— ``tooltip.json`` 里 9 条物品说明，以及
#: ``archetypes``（原型/构筑指南）任务在两个任务书副本里各缺一条。它们当时补不进去，
#: 因为 ``_merge_extra_keys`` 对数组直接 skip；现已给 :func:`build._merge_extra_keys`
#: 加了「按 ``item``/``id`` 追加数组元素」的能力（并有单测覆盖幂等与结构不符），
#: 全部经 ``config_extra.json`` 补齐 → **白名单现为空**。
#:
#: 保留这个常量而不是删掉：将来上游再漏译时，正好把新缺口登记到这里，
#: 避免「反反复复报同一个已知问题」。**门禁只拦白名单之外的新缺口。**
KNOWN_LOCALE_GAPS = frozenset({
    # （暂无已知缺口）
})

#: 判定「值还是英文」的启发式：≥4 个连续拉丁字母、无 CJK、且不是纯色码/占位符。
_UNTRANSLATED = re.compile(r"[A-Za-z]{4}")
_NOT_TEXT = re.compile(r"^(§.|<[^>]*>|#|\$|[a-z_]+:[a-z_/#]+$|[\d\s.,%+-]*$)")
#: 真正的**显示文字**几乎总带空格或句读；单个驼峰/下划线 token（``additionalResistance``、
#: ``manaCost``、``cooldown``）是**字段标识符**，两侧本来就一样，比它们会产出上百条假缺口。
_PROSE = re.compile(r"\s|[.!?,;:，。、…]")


def _leaf_keys(o: object, prefix: str = "") -> set[str]:
    """摊平 JSON 的叶子键路径；数组里带 ``item``/``id`` 的元素按该字段做键。

    数组不能按下标比——上游与译文副本的**顺序一致但长度可能不同**（上游漏译就会
    少一个元素，按下标比会全盘错位、报出一堆假缺口）。按 ``item``/``id`` 比才准确。
    """
    out: set[str] = set()
    if isinstance(o, dict):
        for k, v in o.items():
            out |= _leaf_keys(v, f"{prefix}/{k}")
    elif isinstance(o, list):
        for e in o:
            if isinstance(e, dict) and ("item" in e or "id" in e):
                out.add(f"{prefix}#{e.get('item') or e.get('id')}")
            else:
                out |= _leaf_keys(e, prefix + "#")
    else:
        out.add(prefix)
    return out


def _flat_values(o: object, prefix: str = "") -> dict[str, object]:
    """摊平成 ``路径 -> 叶子值``；数组里带 ``item``/``id`` 的元素用该字段做路径段。

    数组**不能按下标比**：上游与译文副本顺序一致但长度可能不同（上游漏译就少一个
    元素，按下标比会整段错位、报出一堆假缺口）。
    """
    if isinstance(o, dict):
        out: dict[str, object] = {}
        for k, v in o.items():
            out |= _flat_values(v, f"{prefix}/{k}")
        return out
    if isinstance(o, list):
        out = {}
        for e in o:
            if isinstance(e, dict) and ("item" in e or "id" in e):
                tag = e.get("item") or e.get("id")
                out |= _flat_values(
                    {k: v for k, v in e.items() if k not in ("item", "id")},
                    f"{prefix}#{tag}")
            else:
                out |= _flat_values(e, prefix + "#")
        return out
    return {prefix: o}


def _is_display_text(v: object) -> bool:
    """判断英文值是不是「玩家会看到的文字」（而非色码 / 占位符 / ID / 数字）。

    只有这类值才**必须**有中文对应；结构性的空串、``color``、``$ref``、``#RRGGBB``
    两岸本来就一样，比它们会产出上百条假缺口。
    """
    if not isinstance(v, str):
        return False
    s = v.strip()
    if not s or CJK.search(s):
        return False                      # 上游自己已翻 / 非文字
    if not _UNTRANSLATED.search(s):
        return False                      # 纯数字、符号
    if not _PROSE.search(s):
        return False                      # 单 token：字段标识符 / 枚举名
    return not _NOT_TEXT.match(s)         # 色码 / $ref / 注册名 / 十六进制


def verify_locale_copies(r: VerifyReport, client_zip: Path | None,
                         locale: str = "zh_cn") -> None:
    """逐个 locale 语言副本与**英文默认**比键集，把「漏译/丢描述」一次性挖出来。

    这类缺陷玩家只能靠实机截图反馈（2026-10-03 的一批「描述丢失 / 有效生命英文」
    就是这么来的），而根因往往只是**上游的 zh_cn 副本少了一个键**。
    本门禁把「找出来」这一步自动化：任何**新增**缺键直接判失败。

    判据只认「英文默认里是显示文字、而译文侧没有对应中文」——这样才能把真正的
    漏译与「两边都是色码/占位符」的结构差异区分开。
    """
    r.section("【11】locale 语言副本键覆盖自检")
    if client_zip is None or not client_zip.is_file():
        r.skip("locale 语言副本无缺键", "未提供客户端包")
        return
    tag = f"lang/{locale}/"
    gaps: list[str] = []
    untranslated: list[str] = []
    pairs = 0
    with zipfile.ZipFile(client_zip) as z:
        names = set(z.namelist())
        for n in sorted(names):
            if not n.startswith("overrides/config/") or not n.endswith(".json"):
                continue
            i = n.find(tag)
            if i < 0:
                continue
            default = n[:i] + n[i + len(tag):]
            if default not in names:
                continue
            try:
                loc = json.loads(z.read(n).decode("utf-8"))
                en = json.loads(z.read(default).decode("utf-8"))
            except Exception:
                continue
            pairs += 1
            tgt = n.replace("overrides/", "")
            lv, ev = _flat_values(loc), _flat_values(en)
            for k, v in ev.items():
                if not _is_display_text(v):
                    continue
                got = lv.get(k)
                if got is None:
                    gaps.append(f"{tgt}|{k.lstrip('/')}")
                elif isinstance(got, str) and _is_display_text(got):
                    untranslated.append(f"{tgt}|{k.lstrip('/')}")
    known = [g for g in gaps if g in KNOWN_LOCALE_GAPS]
    new = [g for g in gaps if g not in KNOWN_LOCALE_GAPS]
    r.check(not new, "locale 语言副本无缺键（英文显示文字逐条对照）",
            f"比对 {pairs} 对文件；缺 {len(gaps)} 条"
            f"（已知上游漏译白名单 {len(known)} 条）"
            if not new else
            f"新增缺键 {len(new)} 条：{new[:4]}")
    # 值级只作报告：专有名词/品牌名无法可靠区分，判失败会淹没真问题。
    r.check(True, "locale 语言副本译文覆盖率（值级，仅报告）",
            f"{pairs} 对文件里还有 {len(untranslated)} 条未译："
            + (f"例 {untranslated[:3]}" if untranslated else "无"))




def verify_no_literal_collapse(r: VerifyReport, jar: Path) -> None:
    """字面量表不得出现「多个不同英文 → 同一个中文」的塌缩误译。"""
    r.section("【10】字面量表塌缩误译自检")
    entry = "assets/woldsvaults_cn/literal_zh_cn.tsv"
    if not jar.is_file():
        r.skip("字面量表无塌缩误译", "汉化 jar 缺失")
        return
    with zipfile.ZipFile(jar) as z:
        if entry not in z.namelist():
            r.skip("字面量表无塌缩误译", f"jar 内无 {entry}")
            return
        raw = z.read(entry).decode("utf-8")
    zh2en: dict[str, set[str]] = {}
    for line in raw.splitlines():
        if "\t" not in line:
            continue
        p = line.split("\t")
        if p[0] == "en" or len(p) < 2 or not p[1].strip():
            continue
        if not re.search(r"[\u4e00-\u9fff]", p[1]):
            continue
        zh2en.setdefault(p[1], set()).add(p[0])
    bad = sorted(((len(v), k, sorted(v)) for k, v in zh2en.items()
                  if len(v) >= COLLAPSE_THRESHOLD), reverse=True)
    if bad:
        detail = "、".join(f"{k}({n} 个英文)" for n, k, _ in bad[:5])
        samples = "；样例 " + " / ".join(ens[0] for _, _, ens in bad[:3])
        r.check(False, "字面量表无塌缩误译（同一中文未被 ≥10 个不同英文共用）",
                f"塌缩 {len(bad)} 组：{detail}{samples}")
    else:
        top = max((len(v) for v in zh2en.values()), default=0)
        r.check(True, "字面量表无塌缩误译（同一中文未被 ≥10 个不同英文共用）",
                f"最大合法组 {top} 个（阈值 {COLLAPSE_THRESHOLD}）")

