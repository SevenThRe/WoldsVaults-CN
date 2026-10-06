# -*- coding: utf-8 -*-
"""1006m2: 修正版取证 — Font.split SRG 名、TalentWidget 常量、LiteralTranslator 签名"""
import os, zipfile, subprocess, io, re, struct

TSRG = r"C:\Users\ASUS\.gradle\caches\forge_gradle\minecraft_user_repo\de\oceanlabs\mcp\mcp_config\1.18.2-20220404.173914\srg_to_official_1.18.2.tsrg"
MODS = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
CN = os.path.join(MODS, "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
TV = os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar")
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"

print("=== net/minecraft/client/gui/Font 里含 split 的成员 ===")
cur = None
with io.open(TSRG, encoding="utf-8") as f:
    for ln in f:
        ln = ln.rstrip("\n")
        if not ln.startswith("\t"):
            cur = ln.split(" ")[0]
            continue
        if cur == "net/minecraft/client/gui/Font" and "split" in ln:
            print("   ", ln.strip())

FIXED_EXTRA = {3: 4, 4: 4, 5: 8, 6: 8, 7: 2, 8: 2, 9: 4, 10: 4, 11: 4, 12: 4,
               15: 3, 16: 2, 17: 4, 18: 4, 19: 2, 20: 2}

def utf8_constants(data):
    out = []
    n = struct.unpack_from(">H", data, 8)[0]
    i = 10
    idx = 1
    while idx < n:
        tag = data[i]
        if tag == 1:
            ln2 = struct.unpack_from(">H", data, i + 1)[0]
            out.append(data[i + 3:i + 3 + ln2].decode("utf-8", "replace"))
            i += 3 + ln2
        else:
            i += 1 + FIXED_EXTRA[tag]
        if tag in (5, 6):
            idx += 1
        idx += 1
    return out

with zipfile.ZipFile(TV) as z:
    data = z.read("iskallia/vault/client/gui/screen/player/legacy/widget/TalentWidget.class")
consts = utf8_constants(data)
print()
print("=== TalentWidget 常量池（rank/point/Keybind/Level 相关）===")
for c in consts:
    if re.search(r"rank|point|keybind|level|Name", c, re.I) and 3 <= len(c) < 90 and not c.startswith("(") and "L" != c[:1]:
        print("   ", repr(c))

with zipfile.ZipFile(CN) as z:
    blob = z.read("com/woldsvaults/cn/LiteralTranslator.class")
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_lt.class")
open(p, "wb").write(blob)
r = subprocess.run([JAVAP, "-p", "-classpath", os.path.dirname(p), "com.woldsvaults.cn.LiteralTranslator"],
                   capture_output=True)
print()
print("=== LiteralTranslator 公开签名 ===")
print(r.stdout.decode("utf-8", "replace")[:3000])
print(r.stderr.decode("utf-8", "replace")[:500])
