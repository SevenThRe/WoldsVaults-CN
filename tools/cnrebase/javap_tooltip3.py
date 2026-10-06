# -*- coding: utf-8 -*-
"""1006p: 全量 dump renderTooltipInternal invokes + fcs mixin javap(含 stderr)"""
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
nxt = txt.find("\n  private", start + 10)
seg = txt[start:nxt if nxt > 0 else start + 80000]
print("段长:", len(seg))
n = 0
for ln in seg.splitlines():
    s = ln.strip()
    if s.startswith(("invoke", "ldc")):
        print("   ", s[:170])
        n += 1
        if n > 60:
            break
print()
with zipfile.ZipFile(CN) as z:
    blob = z.read("com/woldsvaults/cn/mixin/FormattedCharSequenceMixin.class")
d = os.path.join(HERE, "_fcs")
os.makedirs(os.path.join(d, "com/woldsvaults/cn/mixin"), exist_ok=True)
open(os.path.join(d, "com/woldsvaults/cn/mixin/FormattedCharSequenceMixin.class"), "wb").write(blob)
r = subprocess.run([JAVAP, "-c", "-p", "-classpath", d, "com.woldsvaults.cn.mixin.FormattedCharSequenceMixin"],
                   capture_output=True)
print("=== fcs stdout ===")
print(r.stdout.decode("utf-8", "replace")[:2200])
print("=== fcs stderr ===")
print(r.stderr.decode("utf-8", "replace")[:400])
