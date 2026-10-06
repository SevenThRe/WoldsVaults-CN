# -*- coding: utf-8 -*-
"""搜所有语言数据源里 keyboard/键绑定相关键值"""
import os, io, sys, zipfile, json, re

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57"
INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
LANGZIP = INST + r"\config\openloader\resources\WoldsVaults-CN-Lang.zip"
CN_JAR = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"

def dump_json_lines(tag, blob):
    try:
        d = json.loads(blob.decode("utf-8"))
    except Exception as e:
        print("%s: JSON 解析失败 %s" % (tag, e)); return
    for k, v in d.items():
        if "keyboard" in k.lower() or "key." == k[:4].lower():
            print("%s: %r -> %r" % (tag, k, v))

# 1) 语言资源包
with zipfile.ZipFile(LANGZIP) as z:
    print("== LANGZIP files:", z.namelist())
    for n in z.namelist():
        if n.endswith(".json"):
            dump_json_lines("LANGZIP " + n, z.read(n))

# 2) CN jar 里的 lang
with zipfile.ZipFile(CN_JAR) as z:
    for n in z.namelist():
        if "/lang/" in n and n.endswith(".json"):
            dump_json_lines("CNJAR " + n, z.read(n))

# 3) 译料层 lang_zh.tsv 里 keyboard
tsv = os.path.join(ROOT, r"translations\cn-rebase\lang_zh.tsv")
for ln in io.open(tsv, encoding="utf-8"):
    if "keyboard" in ln.lower():
        print("lang_zh.tsv: %r" % ln[:160])

# 4) 实例 options.txt 里 F1 绑定
opt = INST + r"\options.txt"
for ln in io.open(opt, encoding="utf-8", errors="replace"):
    if "key_key" in ln and ("f1" in ln.lower() or "vein" in ln.lower()):
        print("options.txt: %r" % ln[:200])
