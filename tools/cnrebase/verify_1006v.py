# -*- coding: utf-8 -*-
"""1006v: 校验最终部署的 MixinFontFcs 注解"""
import zipfile, subprocess, os

P = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"
with zipfile.ZipFile(P) as z:
    open("_chk.class", "wb").write(z.read("com/woldsvaults/cn/mixin/client/MixinFontFcs.class"))
t = subprocess.run([JAVAP, "-v", "-p", "_chk.class"], capture_output=True).stdout.decode("utf-8", "replace")
for m in ("m_92726_", "m_92733_"):
    print(m, "注解中:", m in t)
print("ModifyVariable 数:", t.count("ModifyVariable"))
print("remap false:", "remap" in t)
os.remove("_chk.class")
