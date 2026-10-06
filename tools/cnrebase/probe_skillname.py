# -*- coding: utf-8 -*-
"""1006g: 查 the_vault 技能名的语言键通道 + CN jar 自带的 the_vault 语言覆盖"""
import os, zipfile, re, json

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
INST = BASE + r"\Wold's Vaults 汉化版"
MODS = INST + r"\mods"
CN = MODS + r"\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
TV = os.path.join(MODS, "the_vault-1.18.2-3.21.6.6884.jar")

print("=== CN jar 自带的 zh_cn 语言资源（前 60 条路径）===")
with zipfile.ZipFile(CN) as z:
    zl = z.namelist()
    langres = [n for n in zl if re.search(r"assets/.+/lang/zh_cn\.(json|tsv)$", n)]
    for n in sorted(langres):
        print("   ", n, z.getinfo(n).file_size)
    print("CN jar 条目总数:", len(zl))
    # CN jar 是否自带 the_vault lang
    tvz = [n for n in langres if "the_vault" in n]
    print("CN jar 自带 the_vault zh_cn:", tvz)
    for n in tvz:
        d = json.loads(z.read(n).decode("utf-8"))
        print("   键数:", len(d))
        for k in ["ability.the_vault.dash", "talent.the_vault.hexbreaker"]:
            print("     ", k, "->", d.get(k, "<无>"))

print()
print("=== the_vault 里等于 Dash / Hexbreaker 的语言键 ===")
targets = {"Dash", "Hexbreaker", "Colossus"}
with zipfile.ZipFile(TV) as z:
    langs = [n for n in z.namelist() if re.search(r"assets/.+/lang/[a-z_]+\.json$", n)]
    for n in langs:
        try:
            d = json.loads(z.read(n).decode("utf-8"))
        except Exception:
            continue
        for k, v in d.items():
            if v in targets:
                print(f"   {n}  {k} -> {v!r}")
