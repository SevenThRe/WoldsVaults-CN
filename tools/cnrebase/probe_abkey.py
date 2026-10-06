# -*- coding: utf-8 -*-
"""1006i: 找技能名/天赋名的真正语言键通道"""
import os, re, json, zipfile

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
INST = BASE + r"\Wold's Vaults 汉化版"
MODS = INST + r"\mods"
LANGDIR = os.path.join(INST, "config", "the_vault", "lang", "zh_cn")
CN = os.path.join(MODS, "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
TV = os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar")

print("=== config/the_vault/lang/zh_cn/ 内文件 ===")
for n in sorted(os.listdir(LANGDIR)):
    p = os.path.join(LANGDIR, n)
    print("   ", n, os.path.getsize(p) if os.path.isfile(p) else "(dir)")

print()
print("=== CN jar 的 the_vault zh_cn.json 里含 冲刺/破咒/巨像 的键 ===")
with zipfile.ZipFile(CN) as z:
    d = json.loads(z.read("assets/the_vault/lang/zh_cn.json").decode("utf-8"))
    for kw in ["冲刺", "破咒", "巨像"]:
        hits = [k for k, v in d.items() if kw in str(v)]
        print(f"   {kw}: {hits[:12]}")
    # 名字类键前缀统计
    prefixes = {}
    for k in d:
        m = re.match(r"^(ability|talent|skill|research|vault)[._]", k)
        if m:
            prefixes[m.group(1)] = prefixes.get(m.group(1), 0) + 1
    print("   前缀统计:", prefixes)

print()
print("=== the_vault en_us 里值等于 Dash 的键（含任意文件）===")
with zipfile.ZipFile(TV) as z:
    for n in z.namelist():
        if not re.search(r"assets/.+/lang/en_us\.json$", n):
            continue
        try:
            d2 = json.loads(z.read(n).decode("utf-8"))
        except Exception:
            continue
        for k, v in d2.items():
            if v in ("Dash", "Hexbreaker"):
                print("   ", n, k, "->", repr(v))
    # 看看有没有 ability/talent 命名空间的键
    for n in z.namelist():
        if not re.search(r"assets/the_vault/lang/en_us\.json$", n):
            continue
        d3 = json.loads(z.read(n).decode("utf-8"))
        ks = [k for k in d3 if re.search(r"(dash|hexbreaker)", k, re.I)]
        print("   the_vault en_us 含 dash/hexbreaker 的键:", ks)
