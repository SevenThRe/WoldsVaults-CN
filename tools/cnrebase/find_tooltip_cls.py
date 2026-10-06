# -*- coding: utf-8 -*-
"""1006k: 在 the_vault/fork jar 里定位画技能 tooltip 的类与串"""
import os, zipfile, re

MODS = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
JARS = [
    os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar"),
    os.path.join(MODS, "wolds-vaults-official-mod-0.34.1.jar"),
    os.path.join(MODS, "QOL Hunters-0.42.12.jar"),
]
NEEDLES = [b"Unlocks rank", b"Next Rank: ", b" skill points", b"Rank ", b"QOLHunters Config"]
for jp in JARS:
    if not os.path.exists(jp):
        print("不存在:", jp)
        continue
    print("===", os.path.basename(jp))
    with zipfile.ZipFile(jp) as z:
        for n in z.namelist():
            if not n.endswith(".class"):
                continue
            data = z.read(n)
            hits = [k.decode() for k in NEEDLES if k in data]
            if hits:
                print("   ", n, "->", hits)
