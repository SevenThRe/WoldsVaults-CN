# -*- coding: utf-8 -*-
import json, zipfile, io, sys

INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
CN = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
FORK = INST + r"\mods\wolds-vaults-official-mod-0.34.1.jar"
PREFIX = "data/woldsvaults/vault_configs/abilities/descriptions/"

def listing(jar):
    with zipfile.ZipFile(jar) as z:
        return sorted(n for n in z.namelist() if n.startswith(PREFIX) and n.endswith(".json"))

def read(jar, name):
    with zipfile.ZipFile(jar) as z:
        return json.loads(z.read(name).decode("utf-8"))

print("=== CN descriptions files ===")
for n in listing(CN):
    print("  ", n)
print("=== FORK descriptions files ===")
for n in listing(FORK):
    print("  ", n)

fork_ab = read(FORK, PREFIX + "wolds_abilities.json")
cn_ab = read(CN, PREFIX + "wolds_abilities.json")
print("\n=== fork abilities keys ===", sorted(fork_ab.get("data", {}).keys()))
print("=== cn abilities keys ===", sorted(cn_ab.get("data", {}).keys()))
missing = sorted(set(fork_ab["data"]) - set(cn_ab["data"]))
print("=== MISSING in CN ===", missing)

for k in missing:
    print("\n----- FORK %s -----" % k)
    print(json.dumps(fork_ab["data"][k], ensure_ascii=False, indent=1))

print("\n----- CN Expunge_Base (style ref) -----")
print(json.dumps(cn_ab["data"].get("Expunge_Base"), ensure_ascii=False, indent=1))

# fireshot
for n in listing(FORK):
    if "fireshot" in n:
        print("\n----- FORK FILE %s -----" % n)
        d = read(FORK, n)
        print(json.dumps(d, ensure_ascii=False, indent=1))
