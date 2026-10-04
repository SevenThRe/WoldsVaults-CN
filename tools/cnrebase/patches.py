"""字节码补丁：移除母版里原作者留下的署名 / 推广提示。

背景
----
母版 ``woldsvaults_cn`` 是 0.30.0 时代的作品，其 ``WelcomeMessages`` 类会在
**mod 加载 / 服务端启动 / 玩家登录** 三个时机，向控制台与玩家聊天栏输出带
原作者署名与 QQ 群号的提示。版本重基底会原样继承这些编译产物（class 代码
与整合包版本解耦，正是重基底成立的前提），所以提示会一直跟着走。

用户诉求是「这条提示不要了」，而**玩家看到的那条**是登录时发进聊天栏的
（``onPlayerLoggedIn``）。这里做两步处理，都在 class 字节码层面完成：

1. 把目标方法的 ``Code`` 属性整体替换为单条 ``return``
   —— 逻辑上不再发任何消息，也不会在聊天栏闪出空行（若只把字符串换成
   空串，``text("") + send`` 仍会投递一条空消息）。
2. 把该类常量池里的展示性 ``Utf8`` 常量（含中日韩字符的，以及署名 /
   群号这类纯 ASCII 片段）**等长覆盖为空格**
   —— 常量池不会被 GC，死字符串留在 jar 里仍可能被字节级扫描到；
   等长覆盖保证 class 内部所有偏移不变，零风险。

两步都幂等：重复执行结果一致。只动这一个类，不触碰任何翻译逻辑与载荷。
"""

from __future__ import annotations

import re
import struct
import zipfile
from dataclasses import dataclass
from pathlib import Path

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class SilenceSpec:
    """一个 class 的静默规格。

    ``methods`` —— 要掏空成 ``return`` 的方法；
    ``marks``   —— 常量池里需要额外抹除的 ASCII 片段（署名、群号等，
                   不含中文所以躲得过 CJK 规则）。
    """

    methods: tuple[str, ...]
    marks: tuple[str, ...] = ()


#: 需要静默的 class → 规格
SILENCE_TARGETS: dict[str, SilenceSpec] = {
    "com/woldsvaults/cn/WelcomeMessages.class": SilenceSpec(
        methods=(
            "logModLoaded",      # mod 加载时打控制台日志
            "onServerStarted",   # 服务端启动时打控制台日志
            "onPlayerLoggedIn",  # ★ 玩家登录时发聊天消息（用户看到的那条）
            "sendWelcome",       # 上面调用的辅助方法
        ),
        marks=("MAAAABG", "906309435"),
    ),
}

_RETURN = b"\xb1"


# --------------------------------------------------------------------------- #
# class 文件只读解析
# --------------------------------------------------------------------------- #
def _u2(raw: bytes, off: int) -> int:
    return struct.unpack_from(">H", raw, off)[0]


def _u4(raw: bytes, off: int) -> int:
    return struct.unpack_from(">I", raw, off)[0]


def _parse_cp(raw: bytes) -> tuple[list, int]:
    """解析常量池。

    返回 ``(pool, end)``，``pool[i]`` 为 ``(tag, payload, decoded|None)``，
    索引从 1 开始（与 class 文件一致）。Long / Double 占两个槽位，
    ``pool`` 对应位置放 ``None`` 占位。
    """
    (count,) = struct.unpack_from(">H", raw, 8)
    pos = 10
    pool: list = [None]
    while len(pool) < count:
        tag = raw[pos]
        pos += 1
        if tag == 1:  # Utf8
            (ln,) = struct.unpack_from(">H", raw, pos)
            pos += 2
            payload = raw[pos:pos + ln]
            pos += ln
            pool.append((tag, payload, payload.decode("utf-8", "replace")))
        elif tag in (3, 4):  # Integer / Float
            pool.append((tag, raw[pos:pos + 4], None))
            pos += 4
        elif tag in (5, 6):  # Long / Double
            pool.append((tag, raw[pos:pos + 8], None))
            pos += 8
            pool.append(None)
        elif tag in (7, 8, 16, 19, 20):
            pool.append((tag, raw[pos:pos + 2], None))
            pos += 2
        elif tag in (9, 10, 11, 12, 17, 18):
            pool.append((tag, raw[pos:pos + 4], None))
            pos += 4
        elif tag == 15:  # MethodHandle
            pool.append((tag, raw[pos:pos + 3], None))
            pos += 3
        else:
            raise ValueError(f"未知常量池 tag {tag} @ {pos - 1}")
    return pool, pos


def _skip_member(raw: bytes, pos: int) -> int:
    """跳过 field_info / method_info（access/name/desc + 属性表）。"""
    ac = _u2(raw, pos + 6)
    p = pos + 8
    for _ in range(ac):
        p += 6 + _u4(raw, p + 2)
    return p


# --------------------------------------------------------------------------- #
# 补丁
# --------------------------------------------------------------------------- #
def blank_methods(raw: bytes, names: set[str]) -> tuple[bytes, list[str], list[str]]:
    """把 ``names`` 里的方法体替换为单条 ``return``。

    返回 ``(新字节, 本次掏空的方法, 已经是空 return 的方法)``。
    """
    pool, pos = _parse_cp(raw)
    p = pos + 6                       # access_flags + this_class + super_class
    p += 2 + 2 * _u2(raw, p)          # interfaces
    p += 2                            # fields_count
    for _ in range(_u2(raw, p - 2)):
        p = _skip_member(raw, p)

    mcount = _u2(raw, p)
    p += 2

    edits: list[tuple[int, int, bytes]] = []
    hits: list[str] = []
    already: list[str] = []
    for _ in range(mcount):
        name_idx = _u2(raw, p + 2)
        mname = pool[name_idx][2] if pool[name_idx] else ""
        ac = _u2(raw, p + 6)
        q = p + 8
        for _ in range(ac):
            ab_name = pool[_u2(raw, q)][2]
            alen = _u4(raw, q + 2)
            body = q + 6
            if ab_name == "Code" and mname in names:
                # 已经是空 return（code_length == 1 且 0xB1）→ 幂等跳过
                if _u4(raw, body + 4) == 1 and raw[body + 8:body + 9] == _RETURN:
                    already.append(mname)
                else:
                    max_locals = _u2(raw, body + 2)
                    info = (
                        struct.pack(">HHI", 0, max_locals, 1)   # max_stack / max_locals / code_length
                        + _RETURN
                        + struct.pack(">HH", 0, 0)              # exception_table / attributes
                    )
                    edits.append((
                        q,
                        body + alen,
                        struct.pack(">HI", _u2(raw, q), len(info)) + info,
                    ))
                    hits.append(mname)
            q = body + alen
        p = q

    if not edits:
        return raw, hits, already

    out = bytearray()
    last = 0
    for start, end, rep in edits:
        out += raw[last:start]
        out += rep
        last = end
    out += raw[last:]
    return bytes(out), hits, already


def scrub_constants(raw: bytes, marks: tuple[str, ...] = ()) -> tuple[bytes, int]:
    """抹除常量池里「展示性」的 Utf8 常量。

    命中的两种情形：

    * 含中日韩字符；
    * 含 ``marks`` 里的任意 ASCII 片段（署名 / 群号这类躲得过 CJK 规则的串）。

    一律**等长**覆盖为空格，保证 class 内部任何偏移都不变。
    """
    marks_b = tuple(m.encode("utf-8") for m in marks if m)
    out = bytearray(raw)
    done = 0
    pos = 10
    i = 1
    count = _u2(raw, 8)
    while i < count:
        tag = raw[pos]
        if tag == 1:
            ln = _u2(raw, pos + 1)
            start = pos + 3
            payload = raw[start:start + ln]
            hit = bool(CJK_RE.search(payload.decode("utf-8", "replace")))
            if not hit:
                hit = any(m in payload for m in marks_b)
            if hit:
                out[start:start + ln] = b" " * ln
                done += 1
            pos = start + ln
            i += 1
        elif tag in (3, 4):
            pos += 5
            i += 1
        elif tag in (5, 6):
            pos += 9
            i += 2
        elif tag in (7, 8, 16, 19, 20):
            pos += 3
            i += 1
        elif tag in (9, 10, 11, 12, 17, 18):
            pos += 5
            i += 1
        elif tag == 15:
            pos += 4
            i += 1
        else:
            raise ValueError(f"未知 tag {tag} @ {pos}")
    return bytes(out), done


def patch_class(raw: bytes, spec: SilenceSpec) -> tuple[bytes, list[str], list[str], int]:
    """对单个 class 做「掏空方法 + 抹掉展示常量」两步处理。

    返回 ``(新字节, 本次掏空的方法, 已为空的方法, 抹掉的常量数)``。
    """
    raw, hits, already = blank_methods(raw, set(spec.methods))
    raw, stripped = scrub_constants(raw, spec.marks)
    return raw, hits, already, stripped


def apply_all(root: Path) -> dict[str, dict]:
    """在展开的模板目录上应用全部补丁。

    返回 ``{相对路径: {"methods", "already", "constants", "written", "unmatched"}}``。
    """
    report: dict[str, dict] = {}
    for rel, spec in SILENCE_TARGETS.items():
        f = root / rel
        if not f.is_file():
            report[rel] = {"methods": [], "already": [], "constants": 0,
                           "written": False, "unmatched": list(spec.methods),
                           "error": "文件不存在"}
            continue
        raw = f.read_bytes()
        new, hits, already, stripped = patch_class(raw, spec)
        written = new != raw
        if written:
            f.write_bytes(new)
        report[rel] = {
            "methods": hits,
            "already": already,
            "constants": stripped,
            "written": written,
            # 目标方法一个都没匹配到 → 母版可能改过方法名，需要人工确认
            "unmatched": sorted(set(spec.methods) - set(hits) - set(already)),
        }
    return report


# --------------------------------------------------------------------------- #
# 手动复核
# --------------------------------------------------------------------------- #
def _load_member(src: Path, rel: str) -> bytes:
    """从 jar 或目录里取出成员。"""
    if src.is_dir():
        return (src / rel).read_bytes()
    with zipfile.ZipFile(src) as z:
        return z.read(rel)


def _main(argv: list[str]) -> int:
    """``python -m tools.cnrebase.patches <jar 或解压目录> [导出目录]``

    对每个目标 class 打印静默结果，并把**补丁前 / 后**的 class 导出，
    便于本机有 JDK 时用 ``javap -p -c`` 做权威复核：::

        javap -p -c work/_patched/WelcomeMessages.after.class

    （正式门禁在 ``verify.py``，这里只是人工排查的顺手工具。）
    """
    if len(argv) < 1:
        print(__doc__)
        print("用法: python -m tools.cnrebase.patches <jar|目录> [导出目录]")
        return 2

    src = Path(argv[0])
    out_dir = Path(argv[1]) if len(argv) > 1 else Path("work/_patched")
    out_dir.mkdir(parents=True, exist_ok=True)
    ok = True

    for rel, spec in SILENCE_TARGETS.items():
        short = rel.rsplit("/", 1)[-1].replace(".class", "")
        try:
            raw = _load_member(src, rel)
        except Exception as e:
            print(f"[FAIL] {rel} 读取失败: {e}")
            ok = False
            continue
        new, hits, already, stripped = patch_class(raw, spec)
        print(f"=== {rel}")
        print(f"    掏空方法 {hits}")
        print(f"    已为空   {already}")
        print(f"    抹除常量 {stripped} 条")
        print(f"    大小     {len(raw)} -> {len(new)} B")
        left = [m for m in spec.marks if m.encode() in new]
        cjk = len(CJK_RE.findall(new.decode("utf-8", "replace")))
        print(f"    残留     署名/群号 {left or '无'}，中文 {cjk}")
        (out_dir / f"{short}.before.class").write_bytes(raw)
        (out_dir / f"{short}.after.class").write_bytes(new)
        if left or cjk:
            ok = False
        if set(spec.methods) - set(hits) - set(already):
            print(f"    [WARN] 未匹配到方法: {sorted(set(spec.methods) - set(hits) - set(already))}")
            ok = False

    print(f"\n导出目录: {out_dir}")
    print("结果:", "通过 ✓" if ok else "存在问题")
    return 0 if ok else 1


if __name__ == "__main__":
    import sys as _sys

    raise SystemExit(_main(_sys.argv[1:]))
