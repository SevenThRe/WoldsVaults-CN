# -*- coding: utf-8 -*-
"""1006a: 对比两个实例的 CN jar（哈希+内容差异），检查 QOL 载荷与技能/天赋汉化条目"""
import zipfile, os, sys, json, hashlib

sys.stdout.reconfigure(encoding="utf-8")
BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
OLD = BASE + r"\Wold's Vaults 汉化版\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"          # 用户在用
NEW = BASE + r"\Wold's Vaults 汉化版 0.34.1\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"   # 我维护的

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

h_old, h_new = sha(OLD), sha(NEW)
print("OLD(用户在用) sha16:", h_old[:16], os.path.getsize(OLD))
print("NEW(0.34.1)   sha16:", h_new[:16], os.path.getsize(NEW))
print("相同" if h_old == h_new else "不同！")

zo, zn = zipfile.ZipFile(OLD), zipfile.ZipFile(NEW)
no, nn = set(zo.namelist()), set(zn.namelist())
print("\n仅 OLD 有:", sorted(no - nn)[:10])
print("仅 NEW 有:", sorted(nn - no)[:20])

# 关键内容对比
def ent(z, n):
    try:
        return z.read(n)
    except KeyError:
        return None

checks = [
    "assets/woldsvaults_cn/literal_zh_cn.tsv",
    "data/woldsvaults/vault_configs/abilities/descriptions/wolds_abilities.json",
    "data/woldsvaults/vault_configs/abilities/descriptions/fireshot.json",
    "com/woldsvaults/cn/mixin/client/MixinKeyMappingSanitize.class",
    "mixins.woldsvaults_cn.client.json",
]
print("\n== 关键条目对比 (OLD size / NEW size) ==")
for n in checks:
    a, b = ent(zo, n), ent(zn, n)
    sa = len(a) if a is not None else -1
    sb = len(b) if b is not None else -1
    mark = "SAME" if a == b else "DIFF"
    print("  %-4s %-80s %8d / %8d" % (mark, n, sa, sb))

# QOL Hunters config 载荷
print("\n== CN jar 内 qolhunters 载荷 ==")
for tag, z in (("OLD", zo), ("NEW", zn)):
    qs = sorted(n for n in z.namelist() if "qol" in n.lower())
    print(" %s: %d 个" % (tag, len(qs)), qs[:8])

# TSV 里 Dash / Hexbreaker 条目
for n in ("assets/woldsvaults_cn/literal_zh_cn.tsv",):
    for tag, z in (("OLD", zo), ("NEW", zn)):
        b = ent(z, n)
        if b:
            t = b.decode("utf-8", "replace")
            hits = [ln for ln in t.splitlines() if ln.startswith("Dash\t") or "Hexbreaker" in ln or ln.startswith("Dash ")]
            print("\n%s %s 相关条目 %d:" % (tag, n.split("/")[-1], len(hits)), hits[:6])

zo.close(); zn.close()

# 两个实例 config 树的 qolhunters
for tag, inst in (("OLD", BASE + r"\Wold's Vaults 汉化版"), ("NEW", BASE + r"\Wold's Vaults 汉化版 0.34.1")):
    q = os.path.join(inst, "config", "qolhunters")
    if os.path.isdir(q):
        fs = os.listdir(q)
        print("config/qolhunters (%s): %d 个" % (tag, len(fs)), fs[:10])
    else:
        print("config/qolhunters (%s): 不存在" % tag)
