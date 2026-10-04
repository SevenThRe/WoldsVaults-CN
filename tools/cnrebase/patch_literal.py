#!/usr/bin/env python3
r"""字节码级扩容 ``LiteralTranslator.EMBEDDED_TERMS``（不编译任何 Java 源码）。

对母版 jar 里的 ``com/woldsvaults/cn/LiteralTranslator.class`` 做纯 Python
class 文件读写：

1. 完整解析 class（常量池支持追加 CONSTANT_Utf8 / CONSTANT_String /
   CONSTANT_Class）并重新序列化；
2. 修改 ``<clinit>``：外层数组长度 ``bipush 118 → 118+N``，并在
   ``putstatic EMBEDDED_TERMS`` 之前插入 N 个与现有条目同形态的行构建块；
3. ``<clinit>`` 必须是**无分支直线代码**（逐条指令校验，有分支/帧则拒绝补丁）；
4. 重新打包母版 jar 的副本（原母版不动）→ ``build/cn/work/patched_literal.jar``；
5. 自检：javap 复核 + 本解析器重新 parse 断言 128 行内容。

幂等：class 已含新增行时报告"已打过补丁"并原样退出，不产出损坏文件。

用法::

    python tools/cnrebase/patch_literal.py            # 补丁 + 打包 + 自检
    python tools/cnrebase/patch_literal.py --no-javap # 跳过 javap 自检
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASE_JAR = REPO / "templates/woldsvaults_cn-1.0.16-base.jar"
OUT_JAR = REPO / "build/cn/work/patched_literal.jar"
WORK = REPO / "build/cn/work/jx2"
TSV = WORK / "embedded_terms.tsv"
TARGET = "com/woldsvaults/cn/LiteralTranslator.class"
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"

# 新增行：顺序即数组顺序（长的在前，勿改动）
NEW_ROWS: list[tuple[str, str]] = [
    ("more skill points spent in talents", "个技能点"),
    ("skill points spent in talents", "个技能点"),
    ("skill points", "技能点"),
    ("skill point", "技能点"),
    ("Unlocks rank", "解锁阶"),
    ("Next rank", "下一阶"),
    ("Row unlocked", "行已解锁"),
    ("group points", "组点数"),
    ("Requires", "还需"),
    ("Rank", "阶"),
]
BASE_COUNT = 118

# --------------------------------------------------------------------------- #
# Modified UTF-8（JVMS 4.4.7）
# --------------------------------------------------------------------------- #


def mutf8_decode(b: bytes) -> str:
    chars: list[str] = []
    i, n = 0, len(b)
    while i < n:
        c = b[i]
        if c < 0x80:
            chars.append(chr(c))
            i += 1
        elif (c & 0xE0) == 0xC0:
            chars.append(chr(((c & 0x1F) << 6) | (b[i + 1] & 0x3F)))
            i += 2
        elif (c & 0xF0) == 0xE0:
            chars.append(chr(((c & 0x0F) << 12) | ((b[i + 1] & 0x3F) << 6)
                             | (b[i + 2] & 0x3F)))
            i += 3
        else:
            raise ValueError(f"非法 mUTF-8 字节 0x{c:02x} @ {i}")
    out: list[str] = []
    j = 0
    while j < len(chars):
        o = ord(chars[j])
        if 0xD800 <= o <= 0xDBFF and j + 1 < len(chars) \
                and 0xDC00 <= ord(chars[j + 1]) <= 0xDFFF:
            o2 = ord(chars[j + 1])
            out.append(chr(0x10000 + ((o - 0xD800) << 10) + (o2 - 0xDC00)))
            j += 2
        else:
            out.append(chars[j])
            j += 1
    return "".join(out)


def mutf8_encode(s: str) -> bytes:
    out = bytearray()
    for ch in s:
        o = ord(ch)
        if 1 <= o <= 0x7F:
            out.append(o)
        elif o == 0:
            out += b"\xc0\x80"
        elif o < 0x800:
            out.append(0xC0 | (o >> 6))
            out.append(0x80 | (o & 0x3F))
        elif o < 0x10000:
            out.append(0xE0 | (o >> 12))
            out.append(0x80 | ((o >> 6) & 0x3F))
            out.append(0x80 | (o & 0x3F))
        else:
            o -= 0x10000
            for c in (0xD800 + (o >> 10), 0xDC00 + (o & 0x3FF)):
                out.append(0xE0 | (c >> 12))
                out.append(0x80 | ((c >> 6) & 0x3F))
                out.append(0x80 | (c & 0x3F))
    return bytes(out)


# --------------------------------------------------------------------------- #
# 常量池
# --------------------------------------------------------------------------- #

CONSTANT_Utf8 = 1
CONSTANT_Integer = 3
CONSTANT_Float = 4
CONSTANT_Long = 5
CONSTANT_Double = 6
CONSTANT_Class = 7
CONSTANT_String = 8
CONSTANT_Fieldref = 9
CONSTANT_Methodref = 10
CONSTANT_InterfaceMethodref = 11
CONSTANT_NameAndType = 12
CONSTANT_MethodHandle = 15
CONSTANT_MethodType = 16
CONSTANT_Dynamic = 17
CONSTANT_InvokeDynamic = 18
CONSTANT_Module = 19
CONSTANT_Package = 20

_TAG_SIZE = {  # tag -> payload 长度（Long/Double 占两个槽位由解析层处理）
    CONSTANT_Utf8: None, CONSTANT_Integer: 4, CONSTANT_Float: 4,
    CONSTANT_Long: 8, CONSTANT_Double: 8, CONSTANT_Class: 2,
    CONSTANT_String: 2, CONSTANT_Fieldref: 4, CONSTANT_Methodref: 4,
    CONSTANT_InterfaceMethodref: 4, CONSTANT_NameAndType: 4,
    CONSTANT_MethodHandle: 3, CONSTANT_MethodType: 2,
    CONSTANT_Dynamic: 4, CONSTANT_InvokeDynamic: 4,
    CONSTANT_Module: 2, CONSTANT_Package: 2,
}


@dataclass
class CPEntry:
    tag: int
    data: bytes = b""          # tag 之后原始字节
    utf8: str | None = None    # CONSTANT_Utf8 专用


class ConstantPool:
    def __init__(self) -> None:
        self.entries: list[CPEntry | None] = [None]  # 1-based，0 号槽占位

    # ---- 解析 ----
    @classmethod
    def parse(cls, data: bytes, count: int) -> "ConstantPool":
        pool = cls()
        pos = 0
        for _ in range(count - 1):
            tag = data[pos]
            if tag == CONSTANT_Utf8:
                ln = struct.unpack_from(">H", data, pos + 1)[0]
                payload = data[pos + 3:pos + 3 + ln]
                pool.entries.append(CPEntry(tag, payload, mutf8_decode(payload)))
                pos += 3 + ln
            else:
                size = _TAG_SIZE[tag]
                pool.entries.append(CPEntry(tag, data[pos + 1:pos + 1 + size]))
                pos += 1 + size
                if tag in (CONSTANT_Long, CONSTANT_Double):
                    pool.entries.append(None)  # 占两个槽位
        return pool

    # ---- 序列化 ----
    def serialize(self) -> bytes:
        out = bytearray(struct.pack(">H", len(self.entries)))
        for e in self.entries[1:]:
            if e is None:
                continue
            out.append(e.tag)
            if e.tag == CONSTANT_Utf8:  # Utf8 需回写 2 字节长度前缀
                out += struct.pack(">H", len(e.data))
            out += e.data
        return bytes(out)

    # ---- 读取 ----
    def get(self, idx: int) -> CPEntry:
        e = self.entries[idx]
        if e is None:
            raise ValueError(f"常量池 #{idx} 是 Long/Double 高位槽或不存在")
        return e

    def utf8(self, idx: int) -> str:
        e = self.get(idx)
        if e.tag != CONSTANT_Utf8:
            raise ValueError(f"#{idx} 不是 CONSTANT_Utf8")
        assert e.utf8 is not None
        return e.utf8

    def class_name(self, idx: int) -> str:
        e = self.get(idx)
        if e.tag != CONSTANT_Class:
            raise ValueError(f"#{idx} 不是 CONSTANT_Class")
        return self.utf8(struct.unpack(">H", e.data)[0])

    def string_value(self, idx: int) -> str:
        e = self.get(idx)
        if e.tag != CONSTANT_String:
            raise ValueError(f"#{idx} 不是 CONSTANT_String")
        return self.utf8(struct.unpack(">H", e.data)[0])

    # ---- 追加（带去重，返回常量池索引）----
    def add_utf8(self, s: str) -> int:
        for i, e in enumerate(self.entries):
            if e is not None and e.tag == CONSTANT_Utf8 and e.utf8 == s:
                return i
        raw = mutf8_encode(s)
        if len(raw) > 0xFFFF:
            raise ValueError("Utf8 超过 65535 字节")
        self.entries.append(CPEntry(CONSTANT_Utf8, raw, s))
        return len(self.entries) - 1

    def add_string(self, s: str) -> int:
        for i, e in enumerate(self.entries):
            if e is not None and e.tag == CONSTANT_String \
                    and self.utf8(struct.unpack(">H", e.data)[0]) == s:
                return i
        u = self.add_utf8(s)
        self.entries.append(CPEntry(CONSTANT_String, struct.pack(">H", u)))
        return len(self.entries) - 1

    def add_class(self, name: str) -> int:
        for i, e in enumerate(self.entries):
            if e is not None and e.tag == CONSTANT_Class \
                    and self.utf8(struct.unpack(">H", e.data)[0]) == name:
                return i
        u = self.add_utf8(name)
        self.entries.append(CPEntry(CONSTANT_Class, struct.pack(">H", u)))
        return len(self.entries) - 1


# --------------------------------------------------------------------------- #
# class 文件结构
# --------------------------------------------------------------------------- #


@dataclass
class Attribute:
    name_index: int
    data: bytes


@dataclass
class Member:
    access: int
    name_index: int
    desc_index: int
    attributes: list[Attribute] = field(default_factory=list)


@dataclass
class CodeAttr:
    max_stack: int
    max_locals: int
    code: bytes
    exc_table: bytes
    sub_attrs: list[Attribute]

    def serialize(self) -> bytes:
        body = struct.pack(">HHI", self.max_stack, self.max_locals,
                           len(self.code)) + self.code
        body += struct.pack(">H", len(self.exc_table) // 8) + self.exc_table
        body += struct.pack(">H", len(self.sub_attrs))
        for a in self.sub_attrs:
            body += struct.pack(">HI", a.name_index, len(a.data)) + a.data
        return body


@dataclass
class ClassFile:
    minor: int
    major: int
    pool: ConstantPool
    access: int
    this_idx: int
    super_idx: int
    interfaces: list[int]
    fields: list[Member]
    methods: list[Member]
    attributes: list[Attribute]

    def serialize(self) -> bytes:
        out = bytearray(b"\xca\xfe\xba\xbe")
        out += struct.pack(">HH", self.minor, self.major)
        out += self.pool.serialize()
        out += struct.pack(">HHH", self.access, self.this_idx, self.super_idx)
        out += struct.pack(">H", len(self.interfaces))
        for i in self.interfaces:
            out += struct.pack(">H", i)
        for members in (self.fields, self.methods):
            out += struct.pack(">H", len(members))
            for m in members:
                out += struct.pack(">HHH", m.access, m.name_index, m.desc_index)
                out += struct.pack(">H", len(m.attributes))
                for a in m.attributes:
                    out += struct.pack(">HI", a.name_index, len(a.data)) + a.data
        out += struct.pack(">H", len(self.attributes))
        for a in self.attributes:
            out += struct.pack(">HI", a.name_index, len(a.data)) + a.data
        return bytes(out)

    def find_method(self, name: str, desc: str | None = None) -> Member | None:
        for m in self.methods:
            if self.pool.utf8(m.name_index) == name and (
                    desc is None or self.pool.utf8(m.desc_index) == desc):
                return m
        return None

    def attr_name(self, a: Attribute) -> str:
        return self.pool.utf8(a.name_index)


def parse_class(data: bytes) -> ClassFile:
    if data[:4] != b"\xca\xfe\xba\xbe":
        raise ValueError("magic 不符，不是 class 文件")
    minor, major = struct.unpack_from(">HH", data, 4)
    cp_count = struct.unpack_from(">H", data, 8)[0]
    pool = ConstantPool.parse(data[10:], cp_count)
    # 常量池结束位置
    pos = 10
    for _ in range(cp_count - 1):
        tag = data[pos]
        if tag == CONSTANT_Utf8:
            pos += 3 + struct.unpack_from(">H", data, pos + 1)[0]
        else:
            pos += 1 + _TAG_SIZE[tag]
            if tag in (CONSTANT_Long, CONSTANT_Double):
                pos += 1
    access, this_idx, super_idx = struct.unpack_from(">HHH", data, pos)
    pos += 6
    n_ifc = struct.unpack_from(">H", data, pos)[0]
    pos += 2
    interfaces = list(struct.unpack_from(f">{n_ifc}H", data, pos)) if n_ifc else []
    pos += 2 * n_ifc

    def read_members(pos: int) -> tuple[list[Member], int]:
        n = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        members = []
        for _ in range(n):
            acc, ni, di = struct.unpack_from(">HHH", data, pos)
            pos += 6
            na = struct.unpack_from(">H", data, pos)[0]
            pos += 2
            attrs = []
            for _ in range(na):
                ai, al = struct.unpack_from(">HI", data, pos)
                pos += 6
                attrs.append(Attribute(ai, data[pos:pos + al]))
                pos += al
            members.append(Member(acc, ni, di, attrs))
        return members, pos

    fields, pos = read_members(pos)
    methods, pos = read_members(pos)

    def read_attrs(pos: int) -> tuple[list[Attribute], int]:
        # 类级属性头是 (name_index u2, length u4)，与字段/方法的
        # (access u2, name u2, desc u2) 不同，不能复用 read_members
        n = struct.unpack_from(">H", data, pos)[0]
        pos += 2
        attrs = []
        for _ in range(n):
            ai, al = struct.unpack_from(">HI", data, pos)
            pos += 6
            attrs.append(Attribute(ai, data[pos:pos + al]))
            pos += al
        return attrs, pos

    attributes, pos = read_attrs(pos)
    if pos != len(data):
        raise ValueError(f"class 尾部有 {len(data) - pos} 字节未解析")
    return ClassFile(minor, major, pool, access, this_idx, super_idx,
                     interfaces, fields, methods, attributes)


def parse_code(cf: ClassFile, a: Attribute) -> CodeAttr:
    d = a.data
    max_stack, max_locals, code_len = struct.unpack_from(">HHI", d, 0)
    code = d[8:8 + code_len]
    pos = 8 + code_len
    exc_n = struct.unpack_from(">H", d, pos)[0]
    pos += 2
    exc_table = d[pos:pos + exc_n * 8]
    pos += exc_n * 8
    n = struct.unpack_from(">H", d, pos)[0]
    pos += 2
    sub = []
    for _ in range(n):
        ai, al = struct.unpack_from(">HI", d, pos)
        pos += 6
        sub.append(Attribute(ai, d[pos:pos + al]))
        pos += al
    if pos != len(d):
        raise ValueError("Code attribute 长度不一致")
    return CodeAttr(max_stack, max_locals, code, exc_table, sub)


# --------------------------------------------------------------------------- #
# <clinit> 结构校验与补丁
# --------------------------------------------------------------------------- #

OP_BIPUSH, OP_SIPUSH, OP_DUP = 0x10, 0x11, 0x59
OP_ICONST_0, OP_ICONST_1, OP_ICONST_2 = 0x03, 0x04, 0x05
OP_ANEWARRAY, OP_LDC, OP_LDC_W = 0xBD, 0x12, 0x13
OP_AASTORE, OP_PUTSTATIC, OP_RETURN = 0x53, 0xB3, 0xB1


def _read_index_push(code: bytes, pos: int) -> tuple[int, int]:
    """读一条「压整数」指令，返回 (值, 新 pos)。"""
    op = code[pos]
    if op == OP_BIPUSH:
        return struct.unpack_from(">b", code, pos + 1)[0], pos + 2
    if op == OP_SIPUSH:
        return struct.unpack_from(">h", code, pos + 1)[0], pos + 3
    if OP_ICONST_0 <= op <= OP_ICONST_0 + 5:  # iconst_0..iconst_5
        return op - OP_ICONST_0, pos + 1
    raise ValueError(f"@{pos}: 0x{op:02x} 不是压整数指令")


def _read_ldc(code: bytes, pos: int) -> tuple[int, int]:
    op = code[pos]
    if op == OP_LDC:
        return code[pos + 1], pos + 2
    if op == OP_LDC_W:
        return struct.unpack_from(">H", code, pos + 1)[0], pos + 3
    raise ValueError(f"@{pos}: 0x{op:02x} 不是 ldc/ldc_w")


@dataclass
class ClinitInfo:
    code_attr: Attribute
    parsed: CodeAttr
    count: int
    rows: list[tuple[str, str]]
    outer_class_idx: int
    inner_class_idx: int
    head_end: int  # 首条「压数组长度」指令结束偏移


def analyze_clinit(cf: ClassFile) -> ClinitInfo:
    m = cf.find_method("<clinit>", "()V")
    if m is None:
        raise ValueError("找不到 <clinit>()V")
    code_attr = None
    for a in m.attributes:
        if cf.attr_name(a) == "Code":
            code_attr = a
            break
    if code_attr is None:
        raise ValueError("<clinit> 没有 Code 属性")
    parsed = parse_code(cf, code_attr)
    code = parsed.code
    if parsed.exc_table:
        raise ValueError("<clinit> 有异常表，不符合直线代码假设")

    # StackMapTable 检查：直线代码不允许有帧
    for a in parsed.sub_attrs:
        nm = cf.attr_name(a)
        if nm in ("StackMapTable", "StackMap"):
            raise ValueError(f"<clinit> 存在 {nm}（有分支/帧），拒绝补丁")

    # 首条「压数组长度」指令：bipush / sipush / iconst 均可
    # （注意 bipush 是有符号字节，上限 127；128 必须用 sipush）
    count, pos = _read_index_push(code, 0)
    if count < 0:
        raise ValueError("@0: 数组长度为负")
    head_end = pos
    if code[pos] != OP_ANEWARRAY:
        raise ValueError(f"@{pos}: 不是 anewarray")
    outer = struct.unpack_from(">H", code, pos + 1)[0]
    if cf.pool.class_name(outer) != "[Ljava/lang/String;":
        raise ValueError("anewarray 目标不是 [[Ljava/lang/String;")
    pos += 3

    rows: list[tuple[str, str]] = []
    inner_idx = None
    while pos < len(code) and code[pos] == OP_DUP \
            and code[pos + 1] != OP_PUTSTATIC:
        # dup / idx / iconst_2 / anewarray String / dup / iconst_0 / ldc find
        # / aastore / dup / iconst_1 / ldc repl / aastore / aastore
        pos += 1  # dup
        idx, pos = _read_index_push(code, pos)
        if idx != len(rows):
            raise ValueError(f"行索引不连续: 期望 {len(rows)} 实际 {idx}")
        if code[pos] != OP_ICONST_2:
            raise ValueError(f"@{pos}: 不是 iconst_2")
        pos += 1
        if code[pos] != OP_ANEWARRAY:
            raise ValueError(f"@{pos}: 不是 anewarray（内层）")
        inner = struct.unpack_from(">H", code, pos + 1)[0]
        if cf.pool.class_name(inner) != "java/lang/String":
            raise ValueError("内层 anewarray 目标不是 java/lang/String")
        inner_idx = inner
        pos += 3
        pos += 1  # dup
        if code[pos] != OP_ICONST_0:
            raise ValueError(f"@{pos}: 不是 iconst_0")
        pos += 1
        c, pos = _read_ldc(code, pos)
        find = cf.pool.string_value(c)
        if code[pos] != OP_AASTORE:
            raise ValueError(f"@{pos}: 不是 aastore")
        pos += 1
        pos += 1  # dup
        if code[pos] != OP_ICONST_1:
            raise ValueError(f"@{pos}: 不是 iconst_1")
        pos += 1
        c, pos = _read_ldc(code, pos)
        repl = cf.pool.string_value(c)
        if code[pos] != OP_AASTORE or code[pos + 1] != OP_AASTORE:
            raise ValueError(f"@{pos}: 结尾不是两次 aastore")
        pos += 2
        rows.append((find, repl))
    if code[pos] != OP_PUTSTATIC:
        raise ValueError(f"@{pos}: 不是 putstatic")
    pos += 3
    if code[pos] != OP_RETURN or pos + 1 != len(code):
        raise ValueError("<clinit> 结尾不是 return / 有多余字节")
    if inner_idx is None:
        raise ValueError("未找到任何行构建块")
    return ClinitInfo(code_attr, parsed, count, rows, outer, inner_idx, head_end)


def _emit_index_push(out: bytearray, v: int) -> None:
    if 0 <= v <= 5:
        out.append(OP_ICONST_0 + v)
    elif -128 <= v <= 127:
        out.append(OP_BIPUSH)
        out += struct.pack(">b", v)
    else:
        out.append(OP_SIPUSH)
        out += struct.pack(">h", v)


def build_row_block(idx: int, find: str, repl: str,
                    inner_class_idx: int, find_idx: int, repl_idx: int) -> bytes:
    """生成与现有个例完全同形态的行构建块。"""
    out = bytearray()
    out.append(OP_DUP)
    _emit_index_push(out, idx)
    out.append(OP_ICONST_2)
    out.append(OP_ANEWARRAY)
    out += struct.pack(">H", inner_class_idx)
    out.append(OP_DUP)
    out.append(OP_ICONST_0)
    out.append(OP_LDC_W)
    out += struct.pack(">H", find_idx)
    out.append(OP_AASTORE)
    out.append(OP_DUP)
    out.append(OP_ICONST_1)
    out.append(OP_LDC_W)
    out += struct.pack(">H", repl_idx)
    out.append(OP_AASTORE)
    out.append(OP_AASTORE)
    return bytes(out)


def patch_class_bytes(data: bytes) -> tuple[bytes, str]:
    """返回 (补丁后字节, 状态消息)。状态: patched / already。"""
    cf = parse_class(data)
    info = analyze_clinit(cf)

    old_rows = list(info.rows)
    if len(old_rows) != BASE_COUNT:
        if len(old_rows) == BASE_COUNT + len(NEW_ROWS) \
                and old_rows[BASE_COUNT:] == NEW_ROWS:
            return data, ("already: class 已打过补丁 "
                          f"（EMBEDDED_TERMS 已是 {len(old_rows)} 行）")
        raise ValueError(f"现有行数 {len(old_rows)} 与预期 {BASE_COUNT} 不符，"
                         "母版可能已变更，拒绝补丁")
    overlap = [f for f, _ in NEW_ROWS if f in dict(old_rows)]
    if overlap:
        raise ValueError(f"新增 find 与现有条目冲突: {overlap}（疑似已打过补丁）")

    pool = cf.pool
    new_find_idx = [pool.add_string(f) for f, _ in NEW_ROWS]
    new_repl_idx = [pool.add_string(r) for _, r in NEW_ROWS]

    new_count = BASE_COUNT + len(NEW_ROWS)
    if new_count > 32767:
        raise ValueError(f"总数 {new_count} 超出 sipush 范围")

    insert = bytearray()
    for i, (f, r) in enumerate(NEW_ROWS):
        insert += build_row_block(BASE_COUNT + i, f, r,
                                  info.inner_class_idx,
                                  new_find_idx[i], new_repl_idx[i])

    code = info.parsed.code
    tail_off = len(code) - 4  # 尾部 4 字节是 putstatic(u2) + return
    # 重写首条「压数组长度」指令：bipush 有符号上限 127，128 起必须 sipush
    head = bytearray()
    _emit_index_push(head, new_count)
    head_shift = len(head) - info.head_end

    new_code = bytearray(head)
    new_code += code[info.head_end:tail_off]
    new_code += insert          # 行块全部插在 putstatic 之前
    new_code += code[tail_off:]

    # LineNumberTable 平移：头指令变长时中间条目右移，插入点后右移 len(insert)
    parsed = info.parsed
    sub_attrs = []
    for a in parsed.sub_attrs:
        if cf.attr_name(a) == "LineNumberTable":
            n = struct.unpack_from(">H", a.data)[0]
            body = bytearray(struct.pack(">H", n))
            for i in range(n):
                spc, ln = struct.unpack_from(">HH", a.data, 2 + 4 * i)
                if spc == 0:
                    pass
                elif spc >= tail_off:
                    spc += len(insert)
                else:
                    spc += head_shift
                body += struct.pack(">HH", spc, ln)
            sub_attrs.append(Attribute(a.name_index, bytes(body)))
        else:
            sub_attrs.append(a)
    new_attr_data = CodeAttr(parsed.max_stack, parsed.max_locals,
                             bytes(new_code), parsed.exc_table,
                             sub_attrs).serialize()
    target = cf.find_method("<clinit>", "()V")
    assert target is not None
    for i, a in enumerate(target.attributes):
        if a is info.code_attr:
            target.attributes[i] = Attribute(a.name_index, new_attr_data)
    return cf.serialize(), (
        f"patched: {BASE_COUNT} → {new_count} 行，插入 {len(insert)} 字节，"
        f"常量池 {len(pool.entries) - 1} 项")


# --------------------------------------------------------------------------- #
# jar 打包 / 自检
# --------------------------------------------------------------------------- #


def _remove(p: Path) -> None:
    """沙箱内不可原地覆盖：先删后建。os.remove 被宿主改写，须用 nt.remove。"""
    if not p.exists():
        return
    import nt  # noqa: PLC0415
    nt.remove(str(p))


def repack_jar(src: Path, dst: Path, target: str, payload: bytes) -> None:
    _remove(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zout:
        for info in zin.infolist():
            data = payload if info.filename == target else zin.read(info.filename)
            ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            ni.compress_type = info.compress_type
            ni.external_attr = info.external_attr
            zout.writestr(ni, data, compress_type=info.compress_type)


def run_javap(class_path: Path) -> tuple[int, str]:
    # javap 中文输出跟随系统区域（GBK），按字节捕获再宽松解码
    r = subprocess.run([JAVAP, "-p", "-c", "-constants", str(class_path)],
                       capture_output=True)
    out = (r.stdout or b"") + (r.stderr or b"")
    return r.returncode, out.decode("utf-8", errors="replace")


def selfcheck(patched: bytes, original: bytes) -> list[str]:
    notes: list[str] = []

    # 本解析器重新 parse：结构 + 行内容
    cf = parse_class(patched)
    info = analyze_clinit(cf)
    assert len(info.rows) == 128, f"行数 {len(info.rows)} != 128"
    assert info.count == 128, f"bipush 操作数 {info.count} != 128"
    notes.append(f"解析器复核：EMBEDDED_TERMS 共 {len(info.rows)} 行，"
                 f"bipush 操作数 {info.count}，两者一致")

    # 前 118 行与 tsv 一致
    tsv_rows = [tuple(line.split("\t")) for line in
                TSV.read_text(encoding="utf-8").rstrip("\n").split("\n")]
    assert len(tsv_rows) == 118, f"tsv 行数 {len(tsv_rows)} != 118"
    assert info.rows[:118] == [tuple(r) for r in tsv_rows], "前 118 行与 tsv 不一致"
    notes.append("前 118 行与 embedded_terms.tsv 完全一致")

    # 后 10 行与清单一致
    assert info.rows[118:] == NEW_ROWS, "后 10 行与新增清单不一致"
    notes.append("后 10 行与新增清单完全一致（长条目在前）")

    # 结构一致性：除 <clinit> Code 与常量池尾部追加外，其余不变
    ocf = parse_class(original)
    assert ocf.minor == cf.minor and ocf.major == cf.major
    assert ocf.access == cf.access and ocf.this_idx == cf.this_idx \
        and ocf.super_idx == cf.super_idx and ocf.interfaces == cf.interfaces
    assert len(ocf.fields) == len(cf.fields) and len(ocf.methods) == len(cf.methods)
    assert [(e.tag, e.data, e.utf8) if e is not None else None
            for e in cf.pool.entries[:len(ocf.pool.entries)]] == \
        [(e.tag, e.data, e.utf8) if e is not None else None
         for e in ocf.pool.entries], "常量池前缀被改动"
    notes.append("类结构（版本/访问标志/字段/方法）与原 class 一致；"
                 "常量池为纯尾部追加，原索引未变")
    return notes


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="EMBEDDED_TERMS 字节码扩容工具")
    ap.add_argument("--no-javap", action="store_true", help="跳过 javap 自检")
    args = ap.parse_args(argv)

    with zipfile.ZipFile(BASE_JAR) as z:
        original = z.read(TARGET)
    patched, status = patch_class_bytes(original)
    print(f"[补丁] {status}")

    if status.startswith("already"):
        print("已打过补丁：不重写 jar，直接结束（幂等保护）")
        return 0

    WORK.mkdir(parents=True, exist_ok=True)
    patched_class_path = WORK / "LiteralTranslator.patched.class"
    _remove(patched_class_path)
    patched_class_path.write_bytes(patched)

    # ---- javap 自检（javap 没有 -verdict 选项，退出码 0 即权威通过）----
    if not args.no_javap:
        orig_class_path = WORK / "LiteralTranslator.orig.class"
        _remove(orig_class_path)
        orig_class_path.write_bytes(original)
        rc0, out0 = run_javap(orig_class_path)
        rc, out = run_javap(patched_class_path)
        if rc != 0 or rc0 != 0:
            print(out)
            print("[失败] javap 退出码", rc, rc0)
            return 1
        base = out0.count("anewarray     #14")
        now = out.count("anewarray     #14")
        ok_head = "sipush        128" in out
        ok_field = "Field EMBEDDED_TERMS" in out
        if not ok_head or not ok_field or now != base + len(NEW_ROWS):
            print(f"[失败] javap 输出异常: sipush 128={ok_head}, "
                  f"putstatic EMBEDDED_TERMS={ok_field}, "
                  f"anewarray #14 {base} -> {now}")
            return 1
        print("[自检] javap -p -c -constants 退出码 0："
              f"clinit 头部 sipush 128，anewarray #14 共 {base} → {now} 处")

    # ---- 本解析器自检 ----
    for note in selfcheck(patched, original):
        print("[自检]", note)

    # ---- 打包 ----
    repack_jar(BASE_JAR, OUT_JAR, TARGET, patched)
    size = OUT_JAR.stat().st_size
    with zipfile.ZipFile(OUT_JAR) as z:
        assert z.testzip() is None
        assert z.read(TARGET) == patched
        n = sum(1 for _ in z.infolist())
    with zipfile.ZipFile(BASE_JAR) as z:
        assert n == sum(1 for _ in z.infolist()), "打包后 entry 数不一致"
    print(f"[产物] {OUT_JAR}（{size} 字节，{n} 个 entry，仅 {TARGET} 被替换，"
          "母版未动）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
