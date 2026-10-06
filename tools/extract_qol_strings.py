#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 QOL Hunters jar 中提取配置界面相关的英文原文串。

关键点：这是一个 *正确的* Java class 常量池解析器 —— 按 cp_info tag 逐项跳字节，
只在 tag==1 (CONSTANT_Utf8) 时读 "u2 length + length bytes"。
绝不使用 re.finditer(rb"[\\x20-\\x7e]+") 这种粗暴扫字节的做法（会把 length 的高位字节
吃进字符串，导致串头多出一个乱码字符，如 "!Enable Bartering..."）。

只读，不修改任何 jar。
"""
import io
import os
import re
import struct
import zipfile

JAR = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods\QOL Hunters-0.42.12.jar"
OUT_DIR = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\translations\cn-rebase"

# 目标 class 名（不含包前缀 / 不含 .class）匹配规则
CLASS_PATTERNS = [
    r"QOLHuntersClientConfigs",
    r"ConfigBuilder",
    r"SkillAltarConfig",
    r"DehammerizerConfig",
]

# ---- 常量池 tag -> 该项额外字节数（-1 表示变长/特殊）----
# tag 1: Utf8  -> u2 len + len bytes      (1 槽)
# tag 3: Integer  -> 4                    (1 槽)
# tag 4: Float    -> 4                    (1 槽)
# tag 5: Long     -> 8                    (2 槽)
# tag 6: Double   -> 8                    (2 槽)
# tag 7: Class    -> u2                   (1 槽)
# tag 8: String   -> u2                   (1 槽)
# tag 9: Fieldref -> u2+u2                (1 槽)
# tag 10: Methodref -> u2+u2              (1 槽)
# tag 11: InterfaceMethodref -> u2+u2     (1 槽)
# tag 12: NameAndType -> u2+u2            (1 槽)
# tag 15: MethodHandle -> u1+u2           (1 槽)
# tag 16: MethodType -> u2                (1 槽)
# tag 17: Dynamic -> u2+u2                (1 槽)
# tag 18: InvokeDynamic -> u2+u2          (1 槽)
# tag 19: Module -> u2                    (1 槽)
# tag 20: Package -> u2                   (1 槽)
FIXED_EXTRA = {
    3: 4, 4: 4, 5: 8, 6: 8,
    7: 2, 8: 2,
    9: 4, 10: 4, 11: 4, 12: 4,
    15: 3, 16: 2,
    17: 4, 18: 4,
    19: 2, 20: 2,
}
DOUBLE_SLOT_TAGS = {5, 6}


def decode_modified_utf8(raw: bytes) -> str:
    """解码 JVM 修改版 UTF-8（0xC0 0x80 表示 NUL，代理对拆成两段 3 字节编码）。"""
    out = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b == 0:
            raise ValueError("unexpected 0x00 in modified utf8")
        if b < 0x80:
            out.append(b)
            i += 1
        elif b & 0xE0 == 0xC0:
            if i + 1 >= n:
                raise ValueError("truncated 2-byte seq")
            b1 = raw[i + 1]
            if b == 0xC0 and b1 == 0x80:
                out.append(0)  # NUL
            else:
                out.append(((b & 0x1F) << 6) | (b1 & 0x3F))
            i += 2
        elif b & 0xF0 == 0xE0:
            if i + 2 >= n:
                raise ValueError("truncated 3-byte seq")
            b1, b2 = raw[i + 1], raw[i + 2]
            out.append(((b & 0x0F) << 12) | ((b1 & 0x3F) << 6) | (b2 & 0x3F))
            i += 3
        else:
            raise ValueError("bad leading byte 0x%02x" % b)
    # out 里是码元（可能是半个代理对），用 surrogatepass 还原
    try:
        return "".join(chr(c) for c in out).encode("utf-16", "surrogatepass").decode("utf-16", "surrogatepass")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def parse_constant_pool_utf8(data: bytes):
    """返回 [(utf8_string), ...]（只含 CONSTANT_Utf8 项）。"""
    if len(data) < 10 or data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("not a class file (bad magic)")
    (minor, major, cp_count) = struct.unpack_from(">HHH", data, 4)
    if cp_count < 1:
        raise ValueError("bad constant_pool_count")
    pos = 10
    idx = 1
    utf8s = []
    while idx < cp_count:
        if pos >= len(data):
            raise ValueError("constant pool truncated")
        tag = data[pos]
        pos += 1
        if tag == 1:
            if pos + 2 > len(data):
                raise ValueError("utf8 length truncated")
            (length,) = struct.unpack_from(">H", data, pos)
            pos += 2
            if pos + length > len(data):
                raise ValueError("utf8 bytes truncated")
            utf8s.append(decode_modified_utf8(data[pos:pos + length]))
            pos += length
            idx += 1
        elif tag in FIXED_EXTRA:
            pos += FIXED_EXTRA[tag]
            idx += 2 if tag in DOUBLE_SLOT_TAGS else 1
        else:
            raise ValueError("unknown constant pool tag %d at index %d" % (tag, idx))
    return utf8s


# ---------------- 过滤规则 ----------------
RE_SKIP = [
    re.compile(r"^[A-Z][A-Z0-9_]*$"),                              # 全大写枚举常量 CYLINDER / ALWAYS
    re.compile(r"^[a-z][a-zA-Z0-9]*$"),                            # 单个 camelCase 标识符（兜底）
    re.compile(r"^\(.*\)(?:\[*L[^;]*;|\[*[BCDFIJSZV])$"),          # 方法描述符 (III)V / (Ljava/io/File;)V
    re.compile(r"^\["),                                            # 数组描述符 [I / [Ljava/lang/String;
    re.compile(r"^L[^ ]*;$"),                                      # 对象描述符 Ljava/lang/String;
    re.compile(r"^[a-z]+(/[A-Za-z0-9_$]+)+(\.[A-Za-z0-9_$]+)*$"),  # 包/类路径 io/iridium/...
    re.compile(r"^[A-Za-z0-9_$]+(/[A-Za-z0-9_$]+)+$"),             # 内部类名路径 a/b/C
    re.compile(r"^[A-Za-z0-9_$]+(\.[A-Za-z0-9_$]+)+$"),            # 全限定名 a.b.C（无空格）
    re.compile(r"^QOLHunters: "),                                  # 日志输出，不是界面文本
]
RE_MUST_HAVE = re.compile(r"[A-Za-z]")
RE_NONPRINT = re.compile(r"[\x00-\x1f\x7f]")


def is_config_text(s: str) -> bool:
    """判断是否为配置界面的 label / description / comment 类自然语言串。
    s 中的换行必须已经是两字符转义 \\n（真实控制字符在候选生成阶段已处理）。"""
    if not (6 <= len(s) <= 200):
        return False
    if " " not in s:
        return False
    if not RE_MUST_HAVE.search(s):
        return False
    if RE_NONPRINT.search(s):
        return False
    for rx in RE_SKIP:
        if rx.match(s):
            return False
    # 排除明显是路径 / 键名 / 扩展名的串
    if s.endswith((".png", ".json", ".lang", ".class", ".jar", ".ogg")):
        return False
    if s.startswith("/") or s.startswith("assets/") or s.startswith("net/") or s.startswith("java/"):
        return False
    if "()V" in s or ";)" in s or "()L" in s:
        return False
    if s.isupper():
        return False
    return True


def candidates_from(s: str):
    """把一条 UTF8 常量展开成候选串列表。
    含真实换行的（Forge 多行 comment）同时给出：
      - 整串形式（换行转成两字符转义 \\n，与 literal_zh_cn.tsv 的既有写法一致）
      - 逐行拆开的形式（界面上一行一行渲染出来的真实文本）"""
    if "\n" not in s and "\r" not in s:
        return [s]
    norm = s.replace("\r\n", "\n").replace("\r", "\n")
    escaped = norm.replace("\n", "\\n")
    out = [escaped]
    for seg in norm.split("\n"):
        seg = seg.strip()
        if seg:
            out.append(seg)
    return out


def main():
    zf = zipfile.ZipFile(JAR)
    names = zf.namelist()
    cls_names = [n for n in names if n.endswith(".class")]
    print("jar classes total: %d" % len(cls_names))

    selected = []
    for n in cls_names:
        base = n.rsplit("/", 1)[-1][:-6]      # 去掉 .class，取最后一段
        inner = base.split("$")[-1]
        for p in CLASS_PATTERNS:
            if p in base or p in inner:
                selected.append(n)
                break
    print("selected classes: %d" % len(selected))
    for n in selected:
        print("  ", n)

    pairs = []      # (string, class_simple_name)
    all_dump = []
    for n in selected:
        raw = zf.read(n)
        try:
            utf8s = parse_constant_pool_utf8(raw)
        except Exception as e:
            print("!! parse fail %s: %s" % (n, e))
            continue
        simple = n.rsplit("/", 1)[-1][:-6]
        for s in utf8s:
            all_dump.append((simple, s))
            for cand in candidates_from(s):
                if is_config_text(cand):
                    pairs.append((cand, simple))

    # 去重：同串多来源时合并来源类名
    agg = {}
    order = []
    for s, c in pairs:
        if s not in agg:
            agg[s] = set()
            order.append(s)
        agg[s].add(c)
    print("candidate strings (dedup): %d" % len(agg))

    os.makedirs(OUT_DIR, exist_ok=True)

    # 调试用全量 dump（便于人工核对过滤是否漏/误）
    dbg = os.path.join(OUT_DIR, "_qol_all_utf8_dump.txt")
    with io.open(dbg, "w", encoding="utf-8", newline="\n") as f:
        for c, s in all_dump:
            f.write("%s\t%s\n" % (c, s.replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r")))
    print("dump -> %s (%d lines)" % (dbg, len(all_dump)))

    raw_path = os.path.join(OUT_DIR, "qol_strings_raw.txt")
    src_path = os.path.join(OUT_DIR, "qol_strings_src.txt")
    with io.open(raw_path, "w", encoding="utf-8", newline="\n") as f:
        for s in sorted(agg):
            f.write(s + "\n")
    with io.open(src_path, "w", encoding="utf-8", newline="\n") as f:
        for s in sorted(agg):
            f.write("%s\t%s\n" % (s, ",".join(sorted(agg[s]))))
    print("raw -> %s (%d lines)" % (raw_path, len(agg)))
    print("src -> %s" % src_path)

    # ---- 交叉核对：全量扫 140 个 class，确认没有漏掉别处的配置串 ----
    others = {}
    for n in cls_names:
        if n in selected:
            continue
        try:
            utf8s = parse_constant_pool_utf8(zf.read(n))
        except Exception:
            continue
        simple = n.rsplit("/", 1)[-1][:-6]
        for s in utf8s:
            for cand in candidates_from(s):
                if is_config_text(cand):
                    others.setdefault(cand, set()).add(simple)
    xp = os.path.join(OUT_DIR, "_qol_other_classes_candidates.txt")
    with io.open(xp, "w", encoding="utf-8", newline="\n") as f:
        for s in sorted(others):
            f.write("%s\t%s\n" % (s, ",".join(sorted(others[s]))))
    print("[cross-check] other classes candidates: %d -> %s" % (len(others), xp))


if __name__ == "__main__":
    main()
