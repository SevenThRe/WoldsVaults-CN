# -*- coding: utf-8 -*-
"""1006b: QOL 缺键清单 + Dash/Hexbreaker 名字来源 + OLD 实例数据包状态"""
import zipfile, os, sys, json

sys.stdout.reconfigure(encoding="utf-8")
BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLDI = BASE + r"\Wold's Vaults 汉化版"
NEWI = BASE + r"\Wold's Vaults 汉化版 0.34.1"
QOL_JAR = OLDI + r"\mods\QOL Hunters-0.42.12.jar"

# 1) qolhunters en_us vs 我方 zh_cn
zq = zipfile.ZipFile(QOL_JAR)
enus = None
for n in zq.namelist():
    if n.endswith("lang/en_us.json"):
        enus = json.loads(zq.read(n).decode("utf-8"))
        print("qolhunters en_us:", n, len(enus), "键")
cn = zipfile.ZipFile(OLDI + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")
ours = json.loads(cn.read("assets/qolhunters/lang/zh_cn.json").decode("utf-8"))
print("我方 qolhunters zh_cn:", len(ours), "键")
missing = {k: v for k, v in enus.items() if k not in ours}
print("缺失键数:", len(missing))
for k, v in list(missing.items())[:25]:
    print("   %r -> %r" % (k, v))

# 2) Dash 能力名 / Hexbreaker 天赋名的语言键
print("\n== en_us 里 dash/hexbreaker 相关键 ==")
for tag, jar in (("tv", NEWI + r"\mods\the_vault-1.18.2-3.21.6.6884.jar"),
                 ("wolds", NEWI + r"\mods\wolds-vaults-official-mod-0.34.1.jar")):
    z = zipfile.ZipFile(jar)
    for n in z.namelist():
        if n.endswith("lang/en_us.json"):
            d = json.loads(z.read(n).decode("utf-8"))
            for k, v in d.items():
                kl = k.lower()
                if ("dash" in kl or "hexbreaker" in kl) and len(k) < 80:
                    print("  %s %s: %r -> %r" % (tag, n.split("/")[-2], k, v))
    z.close()

# 3) OLD 实例 openloader data 与 lang 覆盖状态
print("\n== OLD 实例状态 ==")
od = os.path.join(OLDI, "config", "openloader", "data")
print("openloader/data:", sorted(os.listdir(od)) if os.path.isdir(od) else "无")
ab = os.path.join(OLDI, r"config\the_vault\lang\zh_cn\abilities_descriptions.json")
if os.path.exists(ab):
    d = json.loads(open(ab, encoding="utf-8").read())
    ks = list(d.get("data", {}))
    print("abilities_descriptions 键数:", len(ks), "含 UltimateShield:", "UltimateShield_Base" in ks)
else:
    print("abilities_descriptions: 不存在")
# skill_descriptions / talents
sd = os.path.join(OLDI, r"config\the_vault\lang\zh_cn\skill_descriptions.json")
if os.path.exists(sd):
    d = json.loads(open(sd, encoding="utf-8").read())
    print("skill_descriptions 顶层键:", list(d.keys())[:5], "data 键数:", len(d.get("data", d)) if isinstance(d, dict) else "?")
