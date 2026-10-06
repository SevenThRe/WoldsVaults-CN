# -*- coding: utf-8 -*-
"""1006x: 从崩溃报告抽出模组清单，与本机实例比对（定位朋友环境的差异）"""
import os, re, sys

REPORT = r"F:\Program Files\tx\crash-2026-10-06_23.36.05-client.txt"
BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"

raw = open(REPORT, encoding="utf-8", errors="replace").read()

# 模组清单行形如:  文件名  |显示名|modid|版本|状态|Manifest...
mods = {}
for line in raw.splitlines():
    m = re.match(r"^\s*(\S+\.jar)\s*\|([^|]*)\|([^|]*)\|([^|]*)\|([^|]*)\|", line)
    if m:
        mods[m.group(1).strip()] = (m.group(3).strip(), m.group(4).strip(), m.group(5).strip())
print("朋友崩溃报告里的模组数:", len(mods))
bad = {k: v for k, v in mods.items() if v[2].strip() not in ("DONE",)}
print("状态非 DONE 的模组:", bad if bad else "无")

local = set(f for f in os.listdir(BASE) if f.lower().endswith(".jar"))
remote = set(mods.keys())
print()
print("=== 朋友有、本机没有（多出来的/版本不同）===", len(remote - local))
for k in sorted(remote - local):
    print("   +", k, mods[k])
print()
print("=== 本机有、朋友没有（缺少的）===", len(local - remote))
for k in sorted(local - remote):
    print("   -", k)

# 同名不同版本：按 modid 分组找重复
byid = {}
for f, (mid, ver, st) in mods.items():
    byid.setdefault(mid, []).append((f, ver))
dup = {k: v for k, v in byid.items() if len(v) > 1}
print()
print("=== 同 modid 重复加载 ===", dup if dup else "无")

# 关键汉化/依赖链是否在场
print()
for key in ("kairosvault", "woldsvaults_cn", "the_vault", "vhapi", "wolds-vaults", "qol", "modernfix", "kubejs"):
    hits = [(f, mods[f]) for f in mods if key.lower() in f.lower()]
    print(f"[{key}]", hits if hits else "★不在场★")
