# -*- coding: utf-8 -*-
"""扫 CN jar / class_overrides 所有 class 的常量池 UTF8 项，找 0x01 / F1 相关正则"""
import os, io, sys, zipfile, struct, re

sys.stdout.reconfigure(encoding="utf-8")
INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
CN_JAR = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
OVR = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\tools\cnrebase\class_overrides"

def utf8_constants(blob):
    """粗提 class 文件常量池 UTF8 串（按 JVM spec 解析）"""
    out = []
    if blob[:4] != b"\xca\xfe\xba\xbe":
        return out
    n = struct.unpack_from(">H", blob, 8)[0]
    i = 10
    for _ in range(n - 1):
        tag = blob[i]
        if tag == 1:
            ln = struct.unpack_from(">H", blob, i + 1)[0]
            out.append(blob[i + 3:i + 3 + ln])
            i += 3 + ln
        elif tag in (7, 8, 16, 19, 20):
            i += 3
        elif tag in (15,):
            i += 4
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            i += 5
        elif tag in (5, 6):
            i += 9
        else:
            break
    return out

def scan(tag, blob, src):
    for s in utf8_constants(blob):
        try:
            t = s.decode("utf-8")
        except UnicodeDecodeError:
            continue
        if "\x01" in t:
            print("%s [%s] SOH: %r" % (tag, src, t[:160]))
        if re.search(r"\bF\d\b", t) or "keyboard" in t.lower():
            print("%s [%s] F/KB: %r" % (tag, src, t[:160]))

for fn in os.listdir(OVR):
    if fn.endswith(".class"):
        blob = open(os.path.join(OVR, fn), "rb").read()
        scan("OVR", blob, fn)

with zipfile.ZipFile(CN_JAR) as z:
    for n in z.namelist():
        if n.endswith(".class") and "woldsvaults" in n:
            scan("CNJAR", z.read(n), n)
