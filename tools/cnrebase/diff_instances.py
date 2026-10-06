# -*- coding: utf-8 -*-
"""1006d: 比较两个实例实例的 mods jar / openloader / resourcepacks 差异"""
import os, hashlib, zipfile, json, re

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLD = BASE + r"\Wold's Vaults 汉化版"        # 用户在用（无后缀）
NEW = BASE + r"\Wold's Vaults 汉化版 0.34.1"  # 我一直维护

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def list_jars(d):
    r = {}
    if not os.path.isdir(d):
        return r
    for n in os.listdir(d):
        if n.lower().endswith(".jar"):
            p = os.path.join(d, n)
            r[n] = (os.path.getsize(p), sha(p))
    return r

o = list_jars(OLD + r"\mods")
n = list_jars(NEW + r"\mods")
print("=== MODS JAR 差异 ===")
print("OLD 数量:", len(o), " NEW 数量:", len(n))
for k in sorted(set(o) | set(n)):
    if k not in o:
        print("  仅 NEW 有:", k)
    elif k not in n:
        print("  仅 OLD 有:", k)
    elif o[k] != n[k]:
        print("  内容不同:", k, o[k][0], "vs", n[k][0], "sha16", o[k][1][:16], n[k][1][:16])

print()
print("=== openloader / resourcepacks 目录差异 ===")
for sub in [r"\config\openloader\resources", r"\config\openloader\data", r"\resourcepacks",
            r"\config\the_vault\lang\zh_cn"]:
    od, nd = OLD + sub, NEW + sub
    def walk(d):
        r = {}
        if not os.path.isdir(d):
            return None
        for root, _, fs in os.walk(d):
            for f in fs:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, d)
                try:
                    r[rel] = os.path.getsize(p)
                except OSError:
                    r[rel] = -1
        return r
    a, b = walk(od), walk(nd)
    if a is None and b is None:
        print(f"[{sub}] 两边都不存在")
        continue
    print(f"[{sub}] OLD={len(a) if a is not None else 'NONE'} NEW={len(b) if b is not None else 'NONE'}")
    if a is None or b is None:
        continue
    for k in sorted(set(a) | set(b)):
        if k not in a:
            print("   仅 NEW:", k)
        elif k not in b:
            print("   仅 OLD:", k)
        elif a[k] != b[k]:
            print("   大小不同:", k, a[k], "vs", b[k])
