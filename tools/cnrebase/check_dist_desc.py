# -*- coding: utf-8 -*-
"""1006y: 检查 dist 分发包里的 abilities_descriptions.json 是否为 1005q 修复后的 107 键版"""
import os, zipfile, json, io, shutil

DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"
GOOD = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版"
        r"\config\the_vault\lang\zh_cn\abilities_descriptions.json")

def count_keys(blob):
    try:
        d = json.loads(blob.decode("utf-8"))
        return len(d.get("data", d)), ("UltimateShield_Base" in d.get("data", d))
    except Exception as e:
        return ("解析失败:%s" % e, False)

print("本机已修复版:", os.path.getsize(GOOD), "B,", count_keys(open(GOOD, "rb").read()))
print()
for zp in sorted(os.listdir(DIST)):
    if not zp.endswith(".zip"):
        continue
    p = os.path.join(DIST, zp)
    with zipfile.ZipFile(p) as z:
        hits = [n for n in z.namelist() if n.endswith("abilities_descriptions.json")]
        print(f"--- {zp} ({len(hits)} 处)")
        for n in hits:
            k, us = count_keys(z.read(n))
            print("   ", n, "->", k, "键, 含UltimateShield:", us)
