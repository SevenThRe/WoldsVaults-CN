# -*- coding: utf-8 -*-
"""1005r: 搜 F1/SOH(0x01) 污染源 —— 译料层 TSV、语言资源包、CN jar、实例 config 树"""
import os, io, sys, zipfile, re

sys.stdout.reconfigure(encoding="utf-8")
ROOT = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57"
INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
CN_JAR = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
LANGZIP = INST + r"\config\openloader\resources\WoldsVaults-CN-Lang.zip"

def scan_bytes(tag, blob):
    hits = []
    for i, b in enumerate(blob):
        if b == 1:  # SOH
            seg = blob[max(0, i-40):i+40]
            hits.append((i, seg))
    return hits

def show(tag, blob):
    hs = scan_bytes(tag, blob)
    if hs:
        print("=== %s : %d 个 SOH ===" % (tag, len(hs)))
        for i, seg in hs[:10]:
            print("   @%d %r" % (i, seg))

# 1) 译料层 TSV
tsv = os.path.join(ROOT, r"translations\cn-rebase\literal_zh_cn.tsv")
blob = open(tsv, "rb").read()
show("literal_zh_cn.tsv", blob)
print("TSV 中含 F1 的行:")
for line in blob.decode("utf-8", "replace").splitlines():
    if "F1" in line or "\x01" in line:
        print("   %r" % line)

# 2) 语言资源包 zip
with zipfile.ZipFile(LANGZIP) as z:
    for n in z.namelist():
        b = z.read(n)
        hs = scan_bytes(n, b)
        if hs:
            print("=== LANGZIP %s : %d SOH ===" % (n, len(hs)))
            for i, seg in hs[:5]:
                print("   @%d %r" % (i, seg))
        if b"\xf1" in b or b"F1" in b:
            txt = b.decode("utf-8", "replace")
            for ln in txt.splitlines():
                if "F1" in ln and "keyboard" in ln.lower():
                    print("   F1-line:", ln[:200])

# 3) CN jar 内 tsv/json
with zipfile.ZipFile(CN_JAR) as z:
    for n in z.namelist():
        if n.endswith((".tsv", ".json")):
            b = z.read(n)
            if b"\x01" in b:
                txt = b.decode("utf-8", "replace")
                print("=== CNJAR %s : SOH x%d ===" % (n, b.count(b"\x01")))
                for ln in txt.splitlines():
                    if "\x01" in ln:
                        print("   %r" % ln[:200])
