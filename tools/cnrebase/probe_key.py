# -*- coding: utf-8 -*-
"""找「按键 : 」模板来源：fork/tv jar 常量 + 语言文件"""
import zipfile, sys, struct, re, io, json

sys.stdout.reconfigure(encoding="utf-8")
INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1\\mods"
FORK = INST + r"\wolds-vaults-official-mod-0.34.1.jar"
TV = INST + r"\the_vault-1.18.2-3.21.6.6884.jar"

NEEDLES = ["Key: ", "Keybind", "Bind: ", "按键"]

def utf8_constants(blob):
    out = []
    if blob[:4] != b"\xca\xfe\xba\xbe":
        return out
    try:
        n = struct.unpack_from(">H", blob, 8)[0]
    except struct.error:
        return out
    i = 10
    for _ in range(n - 1):
        if i >= len(blob):
            break
        tag = blob[i]
        if tag == 1:
            ln = struct.unpack_from(">H", blob, i + 1)[0]
            out.append(blob[i + 3:i + 3 + ln])
            i += 3 + ln
        elif tag in (7, 8, 16, 19, 20):
            i += 3
        elif tag == 15:
            i += 4
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            i += 5
        elif tag in (5, 6):
            i += 9
        else:
            break
    return out

for jar, name in ((FORK, "FORK"), (TV, "TV")):
    with zipfile.ZipFile(jar) as z:
        for n in z.namelist():
            if n.endswith(".class"):
                for s in utf8_constants(z.read(n)):
                    try:
                        t = s.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    for nd in NEEDLES:
                        if nd in t and len(t) < 120:
                            print("%s [%s] %r" % (name, n.split("/")[-1], t))
                            break
        # 语言文件
        for n in z.namelist():
            if "/lang/" in n and n.endswith(".json") and "zh_cn" in n:
                try:
                    d = json.loads(z.read(n).decode("utf-8"))
                except Exception:
                    continue
                for k, v in d.items():
                    if any(nd in str(v) for nd in NEEDLES):
                        print("%s LANG %s %r -> %r" % (name, n, k, v))
