# -*- coding: utf-8 -*-
"""全 mod 扫 mixin json：目标类含 KeyMapping / Language / Component / Font 的 mixin"""
import zipfile, os, sys, json, glob, re

sys.stdout.reconfigure(encoding="utf-8")
INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1\mods"
PAT = re.compile(r"KeyMapping|Language|Translatable|Font|MutableComponent|Component", re.I)

for j in sorted(glob.glob(os.path.join(INST, "*.jar"))):
    try:
        z = zipfile.ZipFile(j)
    except Exception:
        continue
    for n in z.namelist():
        if not (n.endswith("mixins.json") or n.endswith("-mixins.json") or "mixin" in n.lower() and n.endswith(".json")):
            continue
        try:
            d = json.loads(z.read(n).decode("utf-8"))
        except Exception:
            continue
        ms = list(d.get("mixins", [])) + list(d.get("client", []))
        for m in ms:
            tgt = d.get("mixins", []) and ""
            if isinstance(m, str) and PAT.search(m):
                print("%s | %s | %s" % (os.path.basename(j)[:36], n, m))
    z.close()
