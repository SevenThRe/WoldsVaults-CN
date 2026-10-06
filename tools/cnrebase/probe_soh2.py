# -*- coding: utf-8 -*-
"""1005r-2: 全实例 config 树搜 0x01 / 字面SOH / F1"""
import os, sys

sys.stdout.reconfigure(encoding="utf-8")
CONF = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1\\config"

for dirpath, _, files in os.walk(CONF):
    for fn in files:
        p = os.path.join(dirpath, fn)
        try:
            b = open(p, "rb").read()
        except OSError:
            continue
        if b"\x01" in b:
            n = b.count(b"\x01")
            print("SOH 0x01 x%d : %s" % (n, p))
            txt = b.decode("utf-8", "replace")
            for i, ln in enumerate(txt.splitlines()):
                if "\x01" in ln:
                    print("    L%d %r" % (i + 1, ln[:160]))
        if b"SOH" in b:
            print("LITERAL 'SOH' : %s" % p)
            txt = b.decode("utf-8", "replace")
            for i, ln in enumerate(txt.splitlines()):
                if "SOH" in ln:
                    print("    L%d %r" % (i + 1, ln[:160]))
# abilities.json 的 keybind 字段
ab = os.path.join(CONF, "the_vault", "abilities.json")
if os.path.exists(ab):
    txt = open(ab, encoding="utf-8").read()
    import re
    print("\n=== abilities.json keybind 字段 ===")
    for m in re.finditer(r'"keybind"\s*:\s*"([^"]*)"', txt):
        print("   %r" % m.group(1))
