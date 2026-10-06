# -*- coding: utf-8 -*-
"""1006f: QOL Hunters 界面串提取 + the_vault 技能名语言键来源"""
import os, zipfile, re, json

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
INST = BASE + r"\Wold's Vaults 汉化版"
MODS = INST + r"\mods"
CN = MODS + r"\woldsvaults_cn-1.0.17-0.34.1-universal.jar"

tsv = {}
with zipfile.ZipFile(CN) as z:
    for n in z.namelist():
        if n.endswith("literal_zh_cn.tsv"):
            for line in z.read(n).decode("utf-8").splitlines():
                if "\t" in line:
                    k, v = line.split("\t", 1)
                    tsv[k] = v

qj = os.path.join(MODS, "QOL Hunters-0.42.12.jar")
print("=== QOL Hunters 界面串 ===")
print("jar 存在:", os.path.exists(qj))
cand = {}
with zipfile.ZipFile(qj) as z:
    cls = [n for n in z.namelist() if n.endswith(".class")]
    print("class 数:", len(cls))
    for n in cls:
        data = z.read(n)
        for m in re.finditer(rb"[\x20-\x7e]{5,}", data):
            s = m.group().decode("ascii")
            if "/" in s or "\\" in s or ".class" in s:
                continue
            if not re.search(r"[A-Za-z]{3}", s):
                continue
            if 5 <= len(s) <= 60:
                cand.setdefault(s, n)

def looks_like_ui(s):
    # 排除典型噪声：全大写常量、包名、技术 token
    if s.upper() == s and "_" in s:
        return False
    if re.fullmatch(r"[a-z0-9_.]+", s):
        return False
    if re.search(r"[(){}<>=;]", s):
        return False
    words = s.split()
    if not words:
        return False
    has_word = sum(1 for w in words if re.fullmatch(r"[A-Za-z][A-Za-z'’\-]*", w))
    return has_word >= max(1, len(words) - 1)

ui = {s: o for s, o in cand.items() if looks_like_ui(s)}
print("候选 UI 串:", len(ui))
hit = sorted(s for s in ui if s in tsv)
miss = sorted(s for s in ui if s not in tsv)
print("已汉化:", len(hit), " 未汉化:", len(miss))
for s in miss[:150]:
    print("   MISS:", repr(s), "<-", os.path.basename(ui[s]))

print()
print("=== the_vault 技能名语言键来源 ===")
tv = os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar")
with zipfile.ZipFile(tv) as z:
    langs = [n for n in z.namelist() if re.search(r"assets/.+/lang/.+\.json$", n)]
    print("the_vault lang 文件数:", len(langs))
    for n in langs:
        d = json.loads(z.read(n).decode("utf-8"))
        for k, v in d.items():
            if v == "Dash":
                print("   ", n, k, "->", repr(v))
                print("     zh_cn 是否有该键:", k in [kk for kk in json.loads(z.read(n.replace("/en_us.json", "/zh_cn.json")).decode("utf-8"))] if False else "")
