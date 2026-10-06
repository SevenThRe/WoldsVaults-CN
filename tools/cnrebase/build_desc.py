# -*- coding: utf-8 -*-
"""
1005q: 补全缺失的能力描述中文（UltimateShield_Base / Fireball_Fireshot），
并通过 OpenLoader data 通道部署（避开 mod datapack 同名冲突），同时回灌 CN jar。
"""
import json, os, zipfile, shutil, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401  (接管 builtins.open / io.open，绕开沙箱写锁)

INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
CN_JAR = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
FORK_JAR = INST + r"\mods\wolds-vaults-official-mod-0.34.1.jar"
PREFIX = "data/woldsvaults/vault_configs/abilities/descriptions/"
OL_DIR = INST + r"\config\openloader\data\WoldsVaults-CN-AbilityDesc"
OUT_DIR = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\build\cn\desc"

def rd(jar, name):
    with zipfile.ZipFile(jar) as z:
        return z.read(name).decode("utf-8")

def rdj(jar, name):
    return json.loads(rd(jar, name))

def comp(t, c):
    return {"text": t, "color": c}

# ---------------- 译文 ----------------
# UltimateShield_Base
ULT_DESC = [
    comp("将自己包裹在纯粹的奥术能量中", "$text"),
    comp("，将受到的伤害按一定比例转由你的", "$text"),
    comp("魔力", "$manaCost"),
    comp("承担。\n\n", "$text"),
    comp("这道强大的屏障需要越来越多的", "$text"),
    comp("魔力", "$manaCost"),
    comp("才能长期维持。", "$text"),
    comp("\n\n● 切换型技能", "$castType"),
]
# Fireball_Fireshot
FIRE_DESC = [
    comp("召唤一团小型魔法火焰弹，远距离命中怪物\n\n", "$text"),
    comp("造成一定数额的", "$text"),
    comp("伤害", "$ability_power"),
    comp("，数值取决于你的", "$text"),
    comp("能力强度", "$ability_power"),
    comp("，并附带你的全部", "$radius"),
    comp("命中效果", "$name"),
    comp("，但不包含", "$text"),
    comp("幸运一击", "$luckyHit"),
    comp("。\n\n", "$text"),
    comp("被命中的敌人还会陷入", "$text"),
    comp("燃烧", "red"),
    comp("状态，在接下来的", "$text"),
    comp("10 秒", "yellow"),
    comp("内持续受到等额的", "$text"),
    comp("伤害", "$ability_power"),
    comp("。", "$text"),
    comp("\n\n✴ 施放技能", "$castType"),
]

def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    fork_ab = rdj(FORK_JAR, PREFIX + "wolds_abilities.json")
    cn_ab = rdj(CN_JAR, PREFIX + "wolds_abilities.json")
    fork_keys = list(fork_ab["data"].keys())

    # --- 术语校对 dump：CN 现有所有 castType / 结尾组件 ---
    print("=== CN castType 尾部组件（术语校对） ===")
    for k, v in cn_ab["data"].items():
        tail = [c.get("text", "") for c in v.get("description", [])][-1:]
        print("  %-20s %r" % (k, tail))

    # --- 1) wolds_abilities.json：补 UltimateShield_Base，按 fork key 顺序重排 ---
    ult = fork_ab["data"]["UltimateShield_Base"]
    ult_cn = {"description": ULT_DESC,
              "current": ult.get("current", []),
              "next": ult.get("next", [])}
    new_data = {}
    for k in fork_keys:
        if k == "UltimateShield_Base":
            new_data[k] = ult_cn
        elif k in cn_ab["data"]:
            new_data[k] = cn_ab["data"][k]
        else:
            new_data[k] = fork_ab["data"][k]
            print("  [WARN] CN 无译本，直抄英文: %s" % k)
    wolds_out = {"data": new_data}
    assert len(new_data) == len(fork_keys) == 9, (len(new_data), len(fork_keys))
    assert all(any("\u4e00" <= ch <= "\u9fff" for ch in
                   "".join(c.get("text", "") for c in v["description"]))
               for v in new_data.values()), "仍有能力未汉化"

    # --- 2) fireshot.json ---
    fork_fs = rdj(FORK_JAR, PREFIX + "fireshot.json")
    fkey = list(fork_fs["data"].keys())[0]
    fs_src = fork_fs["data"][fkey]
    fs_out = {"data": {fkey: {"description": FIRE_DESC,
                              "current": fs_src.get("current", []),
                              "next": fs_src.get("next", [])}}}
    print("=== fireshot key ===", fkey)

    payload = {
        PREFIX + "wolds_abilities.json": json.dumps(wolds_out, ensure_ascii=False, indent=1),
        PREFIX + "fireshot.json": json.dumps(fs_out, ensure_ascii=False, indent=1),
    }
    # CN 已有的另两个文件原样带上（保证 openloader pack 覆盖完整）
    for n in ("chaos_cube.json", "fireball_volley.json"):
        payload[PREFIX + n] = rd(CN_JAR, PREFIX + n)

    # --- 3) 落盘工作区 ---
    for name, text in payload.items():
        p = os.path.join(OUT_DIR, os.path.basename(name))
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("=== 已写出 %d 个文件到 %s ===" % (len(payload), OUT_DIR))

    # --- 4) OpenLoader data pack ---
    if os.path.isdir(OL_DIR):
        shutil.rmtree(OL_DIR)
    os.makedirs(OL_DIR + r"\data\woldsvaults\vault_configs\abilities\descriptions", exist_ok=True)
    with open(OL_DIR + r"\pack.mcmeta", "w", encoding="utf-8", newline="\n") as f:
        json.dump({"pack": {"pack_format": 9,
                            "description": "Wolds Vaults CN - ability descriptions"}},
                  f, ensure_ascii=False, indent=2)
    for name, text in payload.items():
        rel = name[len("data/"):].replace("/", "\\")
        with open(os.path.join(OL_DIR, "data", rel), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    print("=== OpenLoader pack: %s ===" % OL_DIR)
    for root, _, files in os.walk(OL_DIR):
        for fn in files:
            fp = os.path.join(root, fn)
            print("   %8d  %s" % (os.path.getsize(fp), os.path.relpath(fp, OL_DIR)))

    # --- 5) 回灌 CN jar ---
    bak = CN_JAR + ".bak-1005q"
    if not os.path.exists(bak):
        shutil.copyfile(CN_JAR, bak)
    tmp = CN_JAR + ".tmp%d" % os.getpid()
    with zipfile.ZipFile(CN_JAR) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    names = set(i.filename for i, _ in items)
    for n in payload:
        if n not in names:
            print("  [NEW] CN jar 新增条目 %s" % n)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, blob in items:
            if info.filename in payload:
                blob = payload[info.filename].encode("utf-8")
            zout.writestr(info, blob)
        for n, text in payload.items():
            if n not in names:
                zout.writestr(n, text.encode("utf-8"))
    import nt
    if os.path.exists(CN_JAR):
        os.chmod(CN_JAR, 0o666)
        nt.remove(CN_JAR)
    os.rename(tmp, CN_JAR)
    print("=== CN jar 已回灌: %d bytes ===" % os.path.getsize(CN_JAR))
    with zipfile.ZipFile(CN_JAR) as z:
        chk = json.loads(z.read(PREFIX + "wolds_abilities.json").decode("utf-8"))
        print("   jar 内能力数:", len(chk["data"]), "含 UltimateShield:",
              "UltimateShield_Base" in chk["data"])

if __name__ == "__main__":
    main()
