# -*- coding: utf-8 -*-
"""1006c: 对旧实例(无后缀)补 abilities_descriptions（1005q 同款修复）"""
import json, os, io, zipfile, shutil, sys, re, nt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLDI = BASE + r"\Wold's Vaults 汉化版"
LANG = OLDI + r"\config\the_vault\lang\zh_cn\abilities_descriptions.json"
OL_ZIP = OLDI + r"\config\openloader\data\WoldsVaults-CN-Data-0.34.1.zip"
DESC_PREFIX = "data/woldsvaults/vault_configs/abilities/descriptions/"

def zh(v):
    return bool(re.search(r"[\u4e00-\u9fff]", "".join(c.get("text", "") for c in v["description"])))

src = {}
with zipfile.ZipFile(OL_ZIP) as g:
    for n in g.namelist():
        if n.startswith(DESC_PREFIX) and n.endswith(".json"):
            d = json.loads(g.read(n).decode("utf-8"))
            for k, v in d.get("data", {}).items():
                src[k] = v
print("源能力数:", len(src))

bak = LANG + ".bak-1006a"
if not os.path.exists(bak):
    shutil.copyfile(LANG, bak)
lang = json.loads(open(LANG, encoding="utf-8").read())
data = lang["data"]
added = []
for k, v in src.items():
    if k not in data:
        data[k] = v
        added.append(k)
    elif not zh(data[k]) and zh(v):
        data[k] = v
        added.append(k + "(覆盖)")
print("原有", len(data) - len(added), "→ 现有", len(data), "新增:", added)

# 残留英文组件清理（1005q-4 同款）
MAP = {"Cast Ability": "施放技能", "Toggle Ability": "切换技能", "Hold Ability": "长按技能"}
n_fix = 0
for v in data.values():
    for c in v["description"]:
        t = c.get("text", "")
        if re.search(r"[A-Za-z]", t) and not re.search(r"[\u4e00-\u9fff]", t):
            t2 = t
            for en, zhcn in MAP.items():
                t2 = t2.replace(en, zhcn)
            if t2 != t:
                c["text"] = t2
                n_fix += 1
print("残留英文修复:", n_fix)

out = json.dumps(lang, ensure_ascii=False, indent=1)
os.chmod(LANG, 0o666)
nt.remove(LANG)
with open(LANG, "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
chk = json.loads(open(LANG, encoding="utf-8").read())
print("写回:", os.path.getsize(LANG), "键数:", len(chk["data"]),
      "UltimateShield:", "UltimateShield_Base" in chk["data"])
