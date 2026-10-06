# -*- coding: utf-8 -*-
import zipfile, os, sys, re, subprocess

INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1\\mods"
JAR = INST + "\\the_vault-1.18.2-3.21.6.6884.jar"
CLS = "iskallia/vault/config/AbilitiesDescriptionsConfig.class"
OUT = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\build\tv"
JAVAP = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javap.exe"
os.makedirs(OUT, exist_ok=True)
with zipfile.ZipFile(JAR) as z:
    blob = z.read(CLS)
dst = os.path.join(OUT, "AbilitiesDescriptionsConfig.class")
open(dst, "wb").write(blob)
r = subprocess.run([JAVAP, "-p", "-c", "-constants", dst], capture_output=True)
txt = (r.stdout + r.stderr).decode("utf-8", "replace")
open(os.path.join(OUT, "AbilitiesDescriptionsConfig.txt"), "w", encoding="utf-8").write(txt)
print("javap rc=%d lines=%d" % (r.returncode, len(txt.splitlines())))
for line in txt.splitlines():
    if re.search(r'String .*(lang|abilities_descriptions|the_vault|%s|\.json|\.json5)', line):
        print("  ", line.strip())
