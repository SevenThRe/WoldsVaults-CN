# -*- coding: utf-8 -*-
"""确认 the_vault 究竟从哪里读 abilities_descriptions：config/the_vault/lang 还是 datapack"""
import zipfile, os, sys, re

INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
MODS = INST + r"\mods"
NEEDLES = [b"abilities_descriptions", b"vault_configs/abilities/descriptions",
           b"abilities/descriptions", b"the_vault/lang", b"skill_descriptions"]

targets = [f for f in os.listdir(MODS) if f.endswith(".jar") and not f.endswith(".bak")]
for fn in targets:
    p = os.path.join(MODS, fn)
    try:
        z = zipfile.ZipFile(p)
    except Exception as e:
        print("skip", fn, e); continue
    found = {}
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        blob = z.read(n)
        for nd in NEEDLES:
            if nd in blob:
                found.setdefault(nd.decode(), []).append(n)
    if found:
        print("=== %s ===" % fn)
        for nd, cls in found.items():
            print("  %-40s -> %s" % (nd, cls[:6] if len(cls) > 6 else cls))
    z.close()
