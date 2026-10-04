"""沙箱写盘兼容层验收探针（用完即弃）。

逐条覆盖流水线真实用到的写入形态，全部在**目标已存在**的前提下执行 ——
这正是宿主会拒绝的场景。任一条失败即说明 fsutil 兜底有洞。
"""
from __future__ import annotations

import io
import os
import pathlib
import shutil
import stat
import sys
import zipfile

sys.path.insert(0, os.getcwd())

from tools.cnrebase import fsutil  # noqa: E402  导入即触发 install()

assert fsutil.is_installed(), "fsutil.install() 未生效"

D = pathlib.Path("build/cn/work/_wprobe")
if D.exists():
    shutil.rmtree(D)
D.mkdir(parents=True)

ok: list[str] = []
bad: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        ok.append(name)
    except Exception as e:  # noqa: BLE001
        bad.append(f"{name}: {type(e).__name__} {e}")


# --- 1. pathlib.write_text 覆盖既存普通文件 -------------------------------
def t1() -> None:
    p = D / "a.txt"
    p.write_text("v1")
    p.write_text("v2")
    assert p.read_text() == "v2"


# --- 2. pathlib.write_bytes 覆盖既存**只读**文件 -------------------------
# 母版从 jar 解出来就是只读的，这条是真实场景
def t2() -> None:
    p = D / "b.bin"
    p.write_bytes(b"v1")
    os.chmod(p, stat.S_IREAD)
    p.write_bytes(b"v2")
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    assert p.read_bytes() == b"v2"


# --- 3. builtins.open(..., "wb") 覆盖既存只读文件 ------------------------
def t3() -> None:
    p = D / "c.bin"
    p.write_bytes(b"v1")
    os.chmod(p, stat.S_IREAD)
    with open(p, "wb") as fh:
        fh.write(b"v2")
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    assert p.read_bytes() == b"v2"


# --- 4. io.open 路径（zipfile / shutil.copyfile 走的就是这条） -----------
def t4() -> None:
    p = D / "d.bin"
    with io.open(p, "wb") as fh:
        fh.write(b"v1")
    with io.open(p, "wb") as fh:
        fh.write(b"v2")
    assert p.read_bytes() == b"v2"


# --- 5. zipfile.ZipFile(path, "w") 覆盖既存 zip（dist/ 出包的真实路径） --
def t5() -> None:
    p = D / "pack.zip"
    for payload in (b"ONE", b"TWO"):
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("x.txt", payload)
        with zipfile.ZipFile(p) as z:
            assert z.read("x.txt") == payload


# --- 6. zipfile.ZipFile(path) 覆盖既存**只读** zip -----------------------
def t6() -> None:
    p = D / "ro.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("x.txt", b"ONE")
    os.chmod(p, stat.S_IREAD)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("x.txt", b"TWO")
    os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
    with zipfile.ZipFile(p) as z:
        assert z.read("x.txt") == b"TWO"


# --- 7. shutil.copyfile 覆盖既存文件（copytree 底层） -------------------
def t7() -> None:
    src = D / "src.txt"
    src.write_text("SRC")
    dst = D / "dst.txt"
    dst.write_text("OLD")
    shutil.copyfile(src, dst)
    assert dst.read_text() == "SRC"


# --- 8. os.replace 到**不存在**的目标（_retire_dir 的改名路径） ----------
def t8() -> None:
    src = D / "m1.txt"
    src.write_text("M")
    os.replace(src, D / "m2.txt")
    assert (D / "m2.txt").read_text() == "M"


# --- 9. 删除后重建：cli._fresh_copy 的整体形态 --------------------------
def t9() -> None:
    sub = D / "tree"
    sub.mkdir()
    (sub / "f.txt").write_text("1")
    os.replace(sub, D / "tree-old")
    sub.mkdir()
    (sub / "f.txt").write_text("2")
    assert (sub / "f.txt").read_text() == "2"


# --- 10. 无残留：兜底路径不应在目录里留 .cnrebase-tmp --------------------
def t10() -> None:
    leftovers = [p.name for p in D.rglob(f"*{fsutil.TMP_SUFFIX}")]
    assert not leftovers, f"残留临时文件: {leftovers}"


for name, fn in [
    ("pathlib.write_text 覆盖", t1),
    ("pathlib.write_bytes 覆盖只读", t2),
    ("builtins.open('wb') 覆盖只读", t3),
    ("io.open('wb') 覆盖", t4),
    ("zipfile('w') 覆盖 zip", t5),
    ("zipfile('w') 覆盖只读 zip", t6),
    ("shutil.copyfile 覆盖", t7),
    ("os.replace -> 新名字", t8),
    ("目录退役+重建", t9),
    ("无 .cnrebase-tmp 残留", t10),
]:
    check(name, fn)

print(f"结果: {len(ok) + len(bad)} 项 通过 {len(ok)} / 失败 {len(bad)}")
for b in bad:
    print("  FAIL", b)
sys.exit(1 if bad else 0)
