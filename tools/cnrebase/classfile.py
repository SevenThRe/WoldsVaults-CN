"""Java .class 解析：常量池读取 + 方法体内 LDC 字符串定位。

为什么不用反编译：
  * 反编译(CFR)对 450 个 jar 太慢，且会引入反编译噪声；
  * 硬编码汉化只需要「哪些字符串常量被真的当成文本压栈」，即 LDC/LDC_W 指令；
  * 直接走常量池 + 字节码遍历，纯 Python，毫秒级，且天然排除掉
    类名/字段描述符/资源路径（它们不经由 CONSTANT_String，不会被误报）。

关键点：只有 ldc -> CONSTANT_String -> CONSTANT_Utf8 这条链上的字符串
才是「代码里写死的文本」，其余 Utf8 一律不动。这保证了改写安全性。
"""

from __future__ import annotations

import struct
from typing import Iterator

MAGIC = b"\xca\xfe\xba\xbe"

# ---- 常量池 tag ----
UTF8 = 1
INTEGER = 3
FLOAT = 4
LONG = 5
DOUBLE = 6
CLASS = 7
STRING = 8
FIELDREF = 9
METHODREF = 10
INTERFACE_METHODREF = 11
NAME_AND_TYPE = 12
METHOD_HANDLE = 15
METHOD_TYPE = 16
DYNAMIC = 17
INVOKE_DYNAMIC = 18
MODULE = 19
PACKAGE = 20

_TWO_BYTE = {CLASS, STRING, METHOD_TYPE, MODULE, PACKAGE}
_FOUR_BYTE = {INTEGER, FLOAT, FIELDREF, METHODREF, INTERFACE_METHODREF,
              NAME_AND_TYPE, DYNAMIC, INVOKE_DYNAMIC}
_EIGHT_BYTE = {LONG, DOUBLE}
_THREE_BYTE = {METHOD_HANDLE}

# ---------------------------------------------------------------------------
# 指令长度表（JVM spec §6）。默认 1 字节；变长指令单独处理。
# ---------------------------------------------------------------------------
OPLEN = [1] * 0x100

for _op in (0x10, 0x12, 0x15, 0x16, 0x17, 0x18, 0x19,
            0x36, 0x37, 0x38, 0x39, 0x3A, 0xA9, 0xBC):
    OPLEN[_op] = 2

for _op in list(range(0x99, 0xA9)) + [0x11, 0x13, 0x14, 0x84,
                                      0xB2, 0xB3, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8,
                                      0xBB, 0xBD, 0xC0, 0xC1, 0xC6, 0xC7]:
    OPLEN[_op] = 3

OPLEN[0xC5] = 4            # multianewarray
OPLEN[0xB9] = 5            # invokeinterface
OPLEN[0xBA] = 5            # invokedynamic
OPLEN[0xC8] = 5            # goto_w
OPLEN[0xC9] = 5            # jsr_w

LDC = 0x12
LDC_W = 0x13
LDC2_W = 0x14
TABLESWITCH = 0xAA
LOOKUPSWITCH = 0xAB
WIDE = 0xC4


class ClassFormatError(ValueError):
    """class 文件无法解析（新版本格式 / 混淆 / 截断）。"""


# ---------------------------------------------------------------------------
# 常量池
# ---------------------------------------------------------------------------
class ClassFile:
    """最小可用的 class 解析结果：常量池 + 常量池结束偏移。"""

    __slots__ = ("major", "minor", "cp", "cp_end")

    def __init__(self, major: int, minor: int,
                 cp: dict[int, tuple[int, object]], cp_end: int):
        self.major = major
        self.minor = minor
        self.cp = cp
        self.cp_end = cp_end

    def utf8(self, index: int) -> str | None:
        ent = self.cp.get(index)
        if not ent or ent[0] != UTF8:
            return None
        return ent[1]  # type: ignore[return-value]

    def class_name(self, index: int) -> str | None:
        ent = self.cp.get(index)
        if not ent or ent[0] != CLASS:
            return None
        return self.utf8(ent[1])  # type: ignore[arg-type]

    def string_const(self, index: int) -> str | None:
        """CONSTANT_String -> 文本字面量。

        与类名/描述符严格区分：只有 tag=8 才可能是文本。
        """
        ent = self.cp.get(index)
        if not ent or ent[0] != STRING:
            return None
        return self.utf8(ent[1])  # type: ignore[arg-type]

    def all_strings(self) -> set[str]:
        """常量池里全部 CONSTANT_String（不区分是否被 LDC 引用，供兜底统计）。"""
        out: set[str] = set()
        for tag, payload in self.cp.values():
            if tag == STRING:
                s = self.utf8(payload)  # type: ignore[arg-type]
                if s:
                    out.add(s)
        return out


def parse(raw: bytes) -> ClassFile:
    """解析 class 头 + 常量池，并记录常量池结束偏移。"""
    if len(raw) < 10 or raw[:4] != MAGIC:
        raise ClassFormatError("not a java class file")

    n = len(raw)
    try:
        minor, major, count = struct.unpack_from(">HHH", raw, 4)
    except struct.error as exc:  # pragma: no cover
        raise ClassFormatError("truncated header") from exc
    if count == 0:
        raise ClassFormatError("empty constant pool")

    cp: dict[int, tuple[int, object]] = {}
    off = 10
    i = 1
    while i < count:
        if off >= n:
            raise ClassFormatError("truncated constant pool")
        tag = raw[off]
        off += 1

        if tag == UTF8:
            if off + 2 > n:
                raise ClassFormatError("truncated utf8 length")
            ln = struct.unpack_from(">H", raw, off)[0]
            off += 2
            if off + ln > n:
                raise ClassFormatError("truncated utf8 payload")
            cp[i] = (UTF8, raw[off:off + ln].decode("utf-8", "replace"))
            off += ln
        elif tag in _TWO_BYTE:
            if off + 2 > n:
                raise ClassFormatError("truncated constant")
            cp[i] = (tag, struct.unpack_from(">H", raw, off)[0])
            off += 2
        elif tag in _FOUR_BYTE:
            if off + 4 > n:
                raise ClassFormatError("truncated constant")
            cp[i] = (tag, struct.unpack_from(">I", raw, off)[0])
            off += 4
        elif tag in _THREE_BYTE:
            if off + 3 > n:
                raise ClassFormatError("truncated constant")
            cp[i] = (tag, (raw[off], struct.unpack_from(">H", raw, off + 1)[0]))
            off += 3
        elif tag in _EIGHT_BYTE:
            if off + 8 > n:
                raise ClassFormatError("truncated constant")
            cp[i] = (tag, struct.unpack_from(">Q", raw, off)[0])
            off += 8
            i += 1                      # Long/Double 占两个常量池槽位
        else:
            raise ClassFormatError(f"unknown constant tag {tag}")
        i += 1

    return ClassFile(major, minor, cp, off)


# ---------------------------------------------------------------------------
# 字节码遍历
# ---------------------------------------------------------------------------
def _iter_ldc(code: bytes) -> Iterator[tuple[int, int]]:
    """遍历字节码，产出 (字节偏移, 常量池索引) 的 LDC 引用。"""
    i = 0
    n = len(code)
    while i < n:
        op = code[i]

        if op in (TABLESWITCH, LOOKUPSWITCH):
            pad = (4 - ((i + 1) % 4)) % 4
            p = i + 1 + pad
            if p + 4 > n:
                return
            if op == TABLESWITCH:
                if p + 12 > n:
                    return
                _, low, high = struct.unpack_from(">iii", code, p)
                i = p + 12 + 4 * max(0, high - low + 1)
            else:
                if p + 8 > n:
                    return
                npairs = struct.unpack_from(">i", code, p + 4)[0]
                i = p + 8 + 8 * max(0, npairs)
            continue

        if op == WIDE:
            if i + 1 >= n:
                return
            i += 6 if code[i + 1] == 0x84 else 4
            continue

        if op == LDC:
            if i + 1 < n:
                yield i, code[i + 1]
        elif op == LDC_W:
            if i + 2 < n:
                yield i, struct.unpack_from(">H", code, i + 1)[0]
        elif op == LDC2_W:
            pass                        # long/double 常量，不是文本

        i += OPLEN[op]


# ---------------------------------------------------------------------------
# 方法表
# ---------------------------------------------------------------------------
def _iter_code(raw: bytes, cf: ClassFile) -> Iterator[tuple[str, str, bytes]]:
    """产出 (方法名, 描述符, Code 字节码)。"""
    n = len(raw)
    try:
        off = cf.cp_end + 6                     # access_flags u2 + this u2 + super u2
        if off + 2 > n:
            return
        interfaces = struct.unpack_from(">H", raw, off)[0]
        off += 2 + 2 * interfaces

        # 字段表
        if off + 2 > n:
            return
        fcount = struct.unpack_from(">H", raw, off)[0]
        off += 2
        for _ in range(fcount):
            if off + 6 > n:
                return
            acount = struct.unpack_from(">H", raw, off + 4)[0]
            off += 6
            for _a in range(acount):
                if off + 6 > n:
                    return
                alen = struct.unpack_from(">I", raw, off + 2)[0]
                off += 6 + alen
            if off > n:
                return

        # 方法表
        if off + 2 > n:
            return
        mcount = struct.unpack_from(">H", raw, off)[0]
        off += 2
        for _ in range(mcount):
            if off + 8 > n:
                return
            _, name_i, desc_i, acount = struct.unpack_from(">HHHH", raw, off)
            off += 8
            name = cf.utf8(name_i) or ""
            desc = cf.utf8(desc_i) or ""
            for _a in range(acount):
                if off + 6 > n:
                    return
                aname_i, alen = struct.unpack_from(">HI", raw, off)
                off += 6
                if off + alen > n:
                    return
                if cf.utf8(aname_i) == "Code" and alen >= 8:
                    code_len = struct.unpack_from(">I", raw, off + 4)[0]
                    if code_len <= alen - 8:
                        yield name, desc, raw[off + 8: off + 8 + code_len]
                off += alen
    except struct.error:  # pragma: no cover
        return


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------
class LdcHit:
    """一条硬编码字符串的定位信息。"""

    __slots__ = ("method", "descriptor", "value", "offset")

    def __init__(self, method: str, descriptor: str, value: str, offset: int):
        self.method = method
        self.descriptor = descriptor
        self.value = value
        self.offset = offset

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Ldc @{self.method} {self.value!r}>"


def ldc_strings(raw: bytes, cf: ClassFile | None = None) -> list[LdcHit]:
    """提取所有被 LDC 引用、且经 CONSTANT_String 的文本字面量。"""
    if cf is None:
        cf = parse(raw)
    hits: list[LdcHit] = []
    for mname, mdesc, code in _iter_code(raw, cf):
        if not code:
            continue
        for pos, idx in _iter_ldc(code):
            s = cf.string_const(idx)
            if s:
                hits.append(LdcHit(mname, mdesc, s, pos))
    return hits


def class_internal_name(raw: bytes, cf: ClassFile | None = None) -> str | None:
    """取 class 的内部名（用于 VP 的 target_class 字段）。"""
    if cf is None:
        cf = parse(raw)
    off = cf.cp_end + 2                     # 跳过 access_flags
    if off + 2 > len(raw):
        return None
    this_index = struct.unpack_from(">H", raw, off)[0]
    return cf.class_name(this_index)
