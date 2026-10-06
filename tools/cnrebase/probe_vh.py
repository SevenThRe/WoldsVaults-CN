# -*- coding: utf-8 -*-
"""搜所有 mod jar 的 class 常量池 UTF8 里含控制字符(0x01-0x08/0x0B-0x1F)的字符串常量"""
import zipfile, os, struct, sys, glob

sys.stdout.reconfigure(encoding="utf-8")
INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1\mods"

def utf8s(blob):
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
        t = blob[i]
        if t == 1:
            ln = struct.unpack_from(">H", blob, i + 1)[0]
            out.append(blob[i + 3:i + 3 + ln]); i += 3 + ln
        elif t in (7, 8, 16, 19, 20):
            i += 3
        elif t == 15:
            i += 4
        elif t in (3, 4, 9, 10, 11, 12, 17, 18):
            i += 5
        elif t in (5, 6):
            i += 9
        else:
            break
    return out

BAD = set(range(1, 9)) | set(range(0x0B, 0x20)) - {0x09}

jars = sorted(glob.glob(os.path.join(INST, "*.jar")))
skip = ("woldsvaults_cn",)
for j in jars:
    base = os.path.basename(j)
    if any(s in base for s in skip):
        continue
    try:
        z = zipfile.ZipFile(j)
    except Exception:
        continue
    for n in z.namelist():
        if not n.endswith(".class"):
            continue
        try:
            b = z.read(n)
        except Exception:
            continue
        for s in utf8s(b):
            # 只关心像“人话”的串（含可打印字母），且含控制字符
            try:
                t = s.decode("utf-8")
            except UnicodeDecodeError:
                continue
            ctrl = [c for c in t if ord(c) in BAD]
            if ctrl and any(c.isalpha() or "\u4e00" <= c <= "\u9fff" for c in t):
                print("%s | %s | %r" % (base[:40], n.split("/")[-1], t[:120]))
    z.close()
