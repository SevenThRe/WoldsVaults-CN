# -*- coding: utf-8 -*-
"""1006e: 一次性取证 — QOL 配置界面硬编码串、技能名、天赋名"""
import os, zipfile, re, json, io

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
INST = BASE + r"\Wold's Vaults 汉化版"
MODS = INST + r"\mods"
CN = MODS + r"\woldsvaults_cn-1.0.17-0.34.1-universal.jar"

# ---------- 1. 我方 CN jar 的字面量表 ----------
tsv = None
with zipfile.ZipFile(CN) as z:
    for n in z.namelist():
        if n.endswith("literal_zh_cn.tsv"):
            tsv = z.read(n).decode("utf-8")
            tsvname = n
print("TSV:", tsvname, len(tsv), "bytes")
table = {}
for line in tsv.splitlines():
    if "\t" in line:
        k, v = line.split("\t", 1)
        table[k] = v
print("TSV 条目:", len(table))
for probe in ["Dash", "Hexbreaker", "Colossus", "Ultimate Shield", "Chain Vein Miner"]:
    print(f"  probe {probe!r}: {'-> ' + repr(table[probe]) if probe in table else 'NOT FOUND'}")

# ---------- 2. qolhunters jar 里的界面字符串 ----------
qj = None
for n in os.listdir(MODS):
    if "qolhunters" in n.lower() or "qol" in n.lower():
        print("QOL jar 候选:", n)
        if "qolhunters" in n.lower():
            qj = os.path.join(MODS, n)
print()
if qj:
    with zipfile.ZipFile(qj) as z:
        names = [n for n in z.namelist() if n.endswith(".class")]
        print("qolhunters class 数:", len(names))
        strpool = {}
        for n in names:
            data = z.read(n)
            # 粗提 UTF8 常量池（ approximated ）：直接抓可打印 ASCII 串
            for m in re.finditer(rb"[\x20-\x7e]{4,}", data):
                s = m.group().decode("ascii").strip()
                if len(s) >= 4 and " " in s or (len(s) >= 4 and s[:1].isupper()):
                    strpool.setdefault(s, set()).add(n)
        # 只留「像界面文案」的：含空格、非包名/类名
        cand = {}
        for s, owners in strpool.items():
            if "/" in s or "\\" in s or ".class" in s or s.startswith("net") or s.startswith("org"):
                continue
            if len(s) < 4 or len(s) > 60:
                continue
            if not re.search(r"[A-Za-z]", s):
                continue
            cand[s] = owners
        print("候选界面串数量:", len(cand))
        already = [s for s in cand if s in table or translate_hit(s) if False]
        hit = [s for s in cand if s in table]
        miss = sorted(s for s in cand if s not in table)
        print("已在 TSV 中:", len(hit))
        print("未在 TSV 中:", len(miss))
        for s in miss[:120]:
            print("   MISS:", repr(s))
