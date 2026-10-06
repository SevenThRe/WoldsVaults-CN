# -*- coding: utf-8 -*-
"""1006o: dump renderTooltipInternal 的全部 Font/FormattedCharSequence 调用 + 找 fcs class 路径"""
import os, zipfile, subprocess

GRADLE = r"C:\Users\ASUS\.gradle\caches\forge_gradle"
MOJMAP = os.path.join(GRADLE, r"minecraft_user_repo\net\minecraftforge\forge\1.18.2-40.3.11_mapped_official_1.18.2",
                      "forge-1.18.2-40.3.11_mapped_official_1.18.2-recomp.jar")
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"
MODS = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
CN = os.path.join(MODS, "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
HERE = os.path.dirname(os.path.abspath(__file__))

r = subprocess.run([JAVAP, "-c", "-p", "-classpath", MOJMAP,
                    "net.minecraft.client.gui.screens.Screen"], capture_output=True)
txt = r.stdout.decode("utf-8", "replace")
start = txt.find("private void renderTooltipInternal")
seg = txt[start:start + 60000] if start >= 0 else ""
print("renderTooltipInternal 找到:", start >= 0, "长度:", len(seg))
for ln in seg.splitlines():
    s = ln.strip()
    if s.startswith("invoke") and ("Font" in s or "VisualOrder" in s or "Component" in s and "split" in s or "split" in s.lower()):
        print("   ", s[:160])
    elif s.startswith("ldc") and "String" in s:
        pass
print()
with zipfile.ZipFile(CN) as z:
    fcs = [n for n in z.namelist() if "FormattedCharSequence" in n]
    print("fcs 路径:", fcs)
    blob = z.read(fcs[0])
d = os.path.join(HERE, "_fcs", "com", "woldsvaults", "cn", "mixin", "client")
os.makedirs(d, exist_ok=True)
open(os.path.join(d, "FormattedCharSequenceMixin.class"), "wb").write(blob)
pkg = ".".join(fcs[0][:-6].split("/"))
r = subprocess.run([JAVAP, "-c", "-p", "-classpath", os.path.join(HERE, "_fcs"), pkg], capture_output=True)
print("=== FormattedCharSequenceMixin ===")
print(r.stdout.decode("utf-8", "replace")[:2000])
