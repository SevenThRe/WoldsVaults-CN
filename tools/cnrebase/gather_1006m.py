# -*- coding: utf-8 -*-
"""1006m: 取 SRG 名、TalentWidget 常量、LiteralTranslator 签名"""
import os, zipfile, re, subprocess, sys

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版"
MODS = os.path.join(BASE, "mods")
CN = os.path.join(MODS, "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
TV = os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar")
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"
WORK = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\build\cn\work\1006m"
os.makedirs(WORK, exist_ok=True)

# 1. tsrg 里 Font.split 的 SRG 名
print("=== 找 tsrg ===")
tsrg = None
for root, dirs, fs in os.walk(r"E:\Game Files (x86)\Minecraft\.minecraft\libraries\net\minecraft"):
    for f in fs:
        if f.endswith(".tsrg") or f == "srg_to_official_1.18.2.tsrg":
            print("   ", os.path.join(root, f))
            if "srg_to_official" in f:
                tsrg = os.path.join(root, f)
if tsrg is None:
    for cand in [r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\build\out-final8\asmtool",
                 r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\tools"]:
        for root, dirs, fs in os.walk(cand):
            for f in fs:
                if "tsrg" in f:
                    print("   (alt)", os.path.join(root, f))
                    tsrg = os.path.join(root, f)
if tsrg:
    infont = False
    with open(tsrg, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.startswith("\t") or line.startswith("\t\t"):
                infont = line.startswith("net/minecraft/client/gui/Font")
                if not line.startswith("\t"):
                    infont = line.strip() == "net.minecraft.client.gui.Font" or line.strip() == "net/minecraft/client/gui/Font"
                continue
            if infont and ("split" in line or "getSplitter" in line):
                print("   TSRG:", line.rstrip())

# 2. TalentWidget 常量池 UTF8（正确解析器）
def utf8_constants(data):
    out = []
    if data[0:4] != b"\xca\xfe\xba\xbe":
        return out
    n = int.from_bytes(data[8:10], "big")
    i = 10
    idx = 1
    while idx < n:
        tag = data[i]
        if tag == 1:
            ln = int.from_bytes(data[i+1:i+3], "big")
            out.append(data[i+3:i+3+ln].decode("utf-8", "replace"))
            i += 3 + ln
        elif tag in (5, 6):
            i += 9; idx += 1
        elif tag == 7:
            i += 3
        elif tag == 8:
            i += 3
        elif tag == 9 or tag == 10 or tag == 11 or tag == 12:
            i += 5
        elif tag == 3 or tag == 4:
            i += 5
        elif tag == 15:
            i += 5
        elif tag == 16:
            i += 3
        elif tag == 17 or tag == 18:
            i += 5
        else:
            break
        idx += 1
    return out

with zipfile.ZipFile(TV) as z:
    data = z.read("iskallia/vault/client/gui/screen/player/legacy/widget/TalentWidget.class")
consts = utf8_constants(data)
print()
print("=== TalentWidget 常量（含 rank/point/skill）===")
for c in consts:
    if re.search(r"rank|point|skill|Keybind|Name", c, re.I) and len(c) < 90:
        print("   ", repr(c))

# 3. LiteralTranslator 签名
with zipfile.ZipFile(CN) as z:
    cl = [n for n in z.namelist() if "LiteralTranslator" in n or "translate" in n.lower()]
    print()
    print("CN jar translate 相关 class:", cl)
    for n in cl:
        p = os.path.join(WORK, os.path.basename(n))
        open(p, "wb").write(z.read(n))
        r = subprocess.run([JAVAP, "-p", "-c", p], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            if "translate" in line or "class " in line or "static" in line and "(" in line:
                print("   ", line.strip()[:150])
