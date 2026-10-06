# -*- coding: utf-8 -*-
"""
1006z2: 根治 —— CN jar 内 config_payload 里的 abilities_descriptions.json 全部是旧版，
游戏每次启动回写实例配置，把 1005q/1006a 的修复打回 98/89 键。
本脚本：用 dist 包里的 107 键中文版，替换 CN jar 内全部 lang/zh_cn 载荷，
重写两实例的现行文件，部署五处，并核对其余三个 lang 文件的载荷是否与现行一致。
"""
import os, sys, zipfile, shutil, json, hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401
import nt

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "..", "dist")
CLIENT_ZIP = os.path.join(DIST, "WoldsVaults-0.34.1-CN-Client-PCL.zip")
SERVER_ZIP = os.path.join(DIST, "WoldsVaults-0.34.1-CN-Server.zip")

BASE = r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
CN_NEW = os.path.join(BASE, "Wold's Vaults 汉化版 0.34.1", "mods", "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
CN_OLD = os.path.join(BASE, "Wold's Vaults 汉化版", "mods", "woldsvaults_cn-1.0.17-0.34.1-universal.jar")
SRV = r"E:\WoldsVaults-0.34.1-CN-Server\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
LIVE = {
    "OLD": os.path.join(BASE, "Wold's Vaults 汉化版", "config", "the_vault", "lang", "zh_cn", "abilities_descriptions.json"),
    "NEW": os.path.join(BASE, "Wold's Vaults 汉化版 0.34.1", "config", "the_vault", "lang", "zh_cn", "abilities_descriptions.json"),
}
ZH_PAYLOADS = [
    "assets/woldsvaults_cn/config_payload/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/server_payload/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/client_payload_0291/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/universal_payload_0291/config/the_vault/lang/zh_cn/abilities_descriptions.json",
]
OTHER_LANG = ["skill_descriptions.json", "tooltip.json", "menu_player_stat_description.json"]


def keys_of(blob):
    d = json.loads(blob.decode("utf-8"))
    return len(d.get("data", d)), "UltimateShield_Base" in d.get("data", d), "Fangs_Base" in d.get("data", d)


def main():
    # 1) 取 107 键权威内容
    with zipfile.ZipFile(CLIENT_ZIP) as z:
        good = z.read("overrides/config/the_vault/lang/zh_cn/abilities_descriptions.json")
    print("[1] 权威内容:", len(good), "B ->", keys_of(good))
    assert keys_of(good)[0] == 107 and keys_of(good)[1] and keys_of(good)[2], "权威内容不对"

    # 2) 替换 CN jar 内 4 个 zh_cn 载荷
    bak = CN_NEW + ".bak-1006z"
    if not os.path.exists(bak):
        shutil.copyfile(CN_NEW, bak)
    with zipfile.ZipFile(CN_NEW) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    n = 0
    tmp = CN_NEW + ".tmp%d" % os.getpid()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, b in items:
            if info.filename in ZH_PAYLOADS:
                b = good
                n += 1
            zo.writestr(info, b)
    os.chmod(CN_NEW, 0o666)
    nt.remove(CN_NEW)
    os.rename(tmp, CN_NEW)
    print("[2] CN jar 替换 %d 处 zh_cn 载荷 -> %d B" % (n, os.path.getsize(CN_NEW)))

    # 3) 重写两实例现行文件
    for tag, p in LIVE.items():
        cur = open(p, "rb").read()
        if cur != good:
            ob = p + ".bak-1006z"
            if not os.path.exists(ob):
                shutil.copyfile(p, ob)
            os.chmod(p, 0o666)
            nt.remove(p)
            with open(p, "wb") as f:
                f.write(good)
            print("[3] %s 现行文件重写: %d -> 107键" % (tag, len(cur)))
        else:
            print("[3] %s 已是 107 键，无需改" % tag)

    # 4) 部署 jar 到其余位置 + dist
    cn_blob = open(CN_NEW, "rb").read()
    for other in [CN_OLD, SRV]:
        d = os.path.dirname(other)
        if not os.path.isdir(d):
            print("[4] 跳过:", d)
            continue
        ob = other + ".bak-1006z"
        if not os.path.exists(ob):
            shutil.copyfile(other, ob)
        os.chmod(other, 0o666)
        nt.remove(other)
        shutil.copyfile(CN_NEW, other)
        print("[4] 部署:", other)
    for zp, entries in {
        CLIENT_ZIP: ["overrides/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
        SERVER_ZIP: ["WoldsVaults-0.34.1-CN-Server/cn-overlay/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
    }.items():
        with zipfile.ZipFile(zp) as z:
            its = [(i, z.read(i.filename)) for i in z.infolist()]
        tmpz = zp + ".tmp%d" % os.getpid()
        m = 0
        with zipfile.ZipFile(tmpz, "w", zipfile.ZIP_DEFLATED) as zo:
            for info, b in its:
                if info.filename in entries:
                    b = cn_blob
                    m += 1
                zo.writestr(info, b)
        os.chmod(zp, 0o666)
        nt.remove(zp)
        os.rename(tmpz, zp)
        print("[4] %s 更新 %d 处" % (os.path.basename(zp), m))

    # 5) 终验
    with zipfile.ZipFile(CN_NEW) as z:
        ok = all(keys_of(z.read(p))[:2] == (107, True) for p in ZH_PAYLOADS)
        print("[5] jar 内 4 载荷全部 107 键:", ok)
        # 其余三个 lang 文件：载荷 vs 现行
        for f in OTHER_LANG:
            pl = "assets/woldsvaults_cn/config_payload/config/the_vault/lang/zh_cn/" + f
            try:
                pb = z.read(pl)
            except KeyError:
                print("    载荷无", f)
                continue
            for tag, p in LIVE.items():
                lp = os.path.join(os.path.dirname(p), f)
                same = open(lp, "rb").read() == pb
                print("    %s 载荷(%dB) vs %s 现行: %s" % (f, len(pb), tag, "一致" if same else "★不同★"))
    h = hashlib.sha256(cn_blob).hexdigest()
    print("[5] 最终 jar sha256:", h[:16], "…")
    for p in [CN_OLD, SRV]:
        print("    ", os.path.basename(os.path.dirname(p)), open(p, "rb").read() == cn_blob)


if __name__ == "__main__":
    main()
