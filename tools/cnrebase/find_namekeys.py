# -*- coding: utf-8 -*-
"""1006l: 全 mod 找语言键值 = Dash / Hexbreaker 的键（L1 语言键通道）"""
import os, zipfile, re, json

MODS = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
TARGETS = {"Dash", "Hexbreaker"}
for n in sorted(os.listdir(MODS)):
    if not n.lower().endswith(".jar"):
        continue
    p = os.path.join(MODS, n)
    try:
        zf = zipfile.ZipFile(p)
    except Exception:
        continue
    try:
        for m in zf.namelist():
            if not re.search(r"assets/.+/lang/[a-z_]+\.json$", m):
                continue
            try:
                d = json.loads(zf.read(m).decode("utf-8"))
            except Exception:
                continue
            for k, v in d.items():
                if isinstance(v, str) and v in TARGETS:
                    print(f"{n}  {m}  {k} -> {v!r}")
    finally:
        zf.close()
print("done")
