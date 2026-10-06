# -*- coding: utf-8 -*-
"""1006w: 定位崩溃真因 —— kairosvault 类完整性 + 我方 mixin 是否报错"""
import os, zipfile, hashlib, re

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLD = BASE + r"\Wold's Vaults 汉化版"
NEW = BASE + r"\Wold's Vaults 汉化版 0.34.1"
NEED = ["com/kairos/ui/EntitySelectorScreen$1.class",
        "com/kairos/render/Render2D.class",
        "com/kairos/client/hud/ArrayListHud$1.class",
        "com/kairos/ui/EntitySelectorScreen.class"]

def info(inst):
    p = os.path.join(inst, "mods", "kairosvault.jar")
    if not os.path.exists(p):
        return None
    b = open(p, "rb").read()
    z = zipfile.ZipFile(p)
    names = set(z.namelist())
    return (len(b), hashlib.sha256(b).hexdigest()[:16], len(names),
            {n: (n in names) for n in NEED})

for tag, inst in [("OLD(用户在用)", OLD), ("NEW(我维护)", NEW)]:
    r = info(inst)
    print(tag, r if r is None else "大小=%d sha16=%s 条目=%d" % (r[0], r[1], r[2]))
    if r:
        for k, v in r[3].items():
            print("    ", k, "存在" if v else "★缺失★")

print()
print("=== 我方 mixin 是否在最新日志里报错 ===")
for tag, inst in [("OLD", OLD), ("NEW", NEW)]:
    for ln in ["logs/latest.log", "logs/debug.log"]:
        p = os.path.join(inst, ln)
        if not os.path.exists(p):
            continue
        hits = []
        with open(p, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if re.search(r"woldsvaults_cn|MixinFontFcs|MixinKeyMapping", line) and \
                   re.search(r"(ERROR|Exception|failed|FATAL)", line):
                    hits.append((i + 1, line.strip()[:200]))
        print(f"[{tag}/{ln}] 命中 {len(hits)} 条")
        for n, h in hits[:8]:
            print("    L%d: %s" % (n, h))
