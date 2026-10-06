# -*- coding: utf-8 -*-
"""1006h: 对比两实例 config/the_vault 关键表的汉化状态"""
import os, re, json, hashlib

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLD = BASE + r"\Wold's Vaults 汉化版"
NEW = BASE + r"\Wold's Vaults 汉化版 0.34.1"

TARGETS = ["abilities.json", "talents.json"]

def stat(path):
    if not os.path.exists(path):
        return None
    raw = open(path, encoding="utf-8", errors="replace").read()
    names = re.findall(r'"name"\s*:\s*"([^"]*)"', raw)
    zh = sum(1 for n in names if re.search(r"[\u4e00-\u9fff]", n))
    return (os.path.getsize(path), len(names), zh)

for t in TARGETS:
    po = os.path.join(OLD, "config", "the_vault", t)
    pn = os.path.join(NEW, "config", "the_vault", t)
    so, sn = stat(po), stat(pn)
    print(f"--- {t}")
    print("   OLD(用户在用):", so, " (大小, name总数, 含中文数)")
    print("   NEW(我维护的):", sn)
    if so and sn and so[0] == sn[0]:
        print("   → 两实例完全相同")
    else:
        print("   → 不同")

# 抽样：OLD 里 Dash / Hexbreaker 的原文片段
for t, key in [("abilities.json", "Dash"), ("talents.json", "Hexbreaker")]:
    for tag, base in [("OLD", OLD), ("NEW", NEW)]:
        p = os.path.join(base, "config", "the_vault", t)
        if not os.path.exists(p):
            continue
        raw = open(p, encoding="utf-8", errors="replace").read()
        i = raw.find('"name": "%s"' % key)
        print(f"   {tag} {t} 含 name={key!r}: {i >= 0}")
