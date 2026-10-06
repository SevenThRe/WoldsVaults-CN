# -*- coding: utf-8 -*-
"""1006z: 谁回写了 abilities_descriptions.json？查 CN jar 载荷 + 文件时间线"""
import os, zipfile, time, json

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版"
CN = os.path.join(BASE, "mods", "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
LANG = os.path.join(BASE, "config", "the_vault", "lang", "zh_cn", "abilities_descriptions.json")

def ts(p):
    return time.strftime("%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p)))

print("=== 文件时间线（用户实例）===")
d = os.path.dirname(LANG)
for n in sorted(os.listdir(d)):
    p = os.path.join(d, n)
    if os.path.isfile(p):
        print("   %s  %8d  %s" % (ts(p), os.path.getsize(p), n))

print()
print("=== CN jar 里是否带 abilities_descriptions / config 载荷 ===")
with zipfile.ZipFile(CN) as z:
    hits = [n for n in z.namelist() if "abilities_descriptions" in n]
    print("abilities_descriptions 相关条目:", hits)
    for n in hits:
        b = z.read(n)
        try:
            dd = json.loads(b.decode("utf-8"))
            k = len(dd.get("data", dd))
            us = "UltimateShield_Base" in dd.get("data", dd)
        except Exception as e:
            k, us = "err:%s" % e, "?"
        print("   ", n, len(b), "B ->", k, "键, UltimateShield:", us)
    cfg = [n for n in z.namelist() if n.startswith("config/")][:20]
    print("config/ 前缀条目:", cfg if cfg else "无")
    other = [n for n in z.namelist() if n.endswith(".json") and "mixin" not in n and "mods" not in n][:30]
    print("其他 json(前30):", other)
