# -*- coding: utf-8 -*-
"""1006n: javap Screen.renderTooltipInternal + CN jar FormattedCharSequenceMixin"""
import os, zipfile, subprocess

GRADLE = r"C:\Users\ASUS\.gradle\caches\forge_gradle"
MOJMAP = os.path.join(GRADLE, r"minecraft_user_repo\net\minecraftforge\forge\1.18.2-40.3.11_mapped_official_1.18.2",
                      "forge-1.18.2-40.3.11_mapped_official_1.18.2-recomp.jar")
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"
MODS = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
CN = os.path.join(MODS, "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
HERE = os.path.dirname(os.path.abspath(__file__))

r = subprocess.run([JAVAP, "-c", "-p", "-classpath", MOJMAP,
                    "net.minecraft.client.gui.screens.Screen"],
                   capture_output=True)
txt = r.stdout.decode("utf-8", "replace")
if not txt:
    print("javap err:", r.stderr.decode("utf-8", "replace")[:400])
lines = txt.splitlines()
# 找 renderTooltip* 方法体
cur = None
buf = []
blocks = {}
for ln in lines:
    if ln.startswith("  ") and "(" in ln and ";" in ln and not ln.strip().startswith(("invoke", "aload", "getfield", "ldc", "if", "areturn", "return", "iconst", "biput", "new", "dup", "astore", "checkcast", "goto", "pop")):
        cur = ln.strip()[:100]
        blocks[cur] = []
    elif cur is not None:
        s = ln.strip()
        if s.startswith(("invoke", "ldc")):
            blocks[cur].append(s)
for name, body in blocks.items():
    if "ooltip" in name:
        print("###", name)
        for b in body:
            if "Font" in b or "split" in b or "VisualOrder" in b or "m_92923_" in b or "String" in b:
                print("   ", b[:150])

print()
print("=== FormattedCharSequenceMixin（死代码）钩的目标 ===")
with zipfile.ZipFile(CN) as z:
    blob = z.read("com/woldsvaults/cn/mixin/client/FormattedCharSequenceMixin.class")
d = os.path.join(HERE, "_fcs")
os.makedirs(os.path.join(d, "com/woldsvaults/cn/mixin/client"), exist_ok=True)
open(os.path.join(d, "com/woldsvaults/cn/mixin/client/FormattedCharSequenceMixin.class"), "wb").write(blob)
r = subprocess.run([JAVAP, "-c", "-p", "-classpath", d, "com.woldsvaults.cn.mixin.client.FormattedCharSequenceMixin"],
                   capture_output=True)
print(r.stdout.decode("utf-8", "replace")[:2500])
