# -*- coding: utf-8 -*-
"""
1005q-2: 以已验证可用的分发版数据包 WoldsVaults-CN-Data-0.34.1.zip 为唯一真相源：
  1) 装进本机实例 config/openloader/data/
  2) 移除我临时建的目录版 WoldsVaults-CN-AbilityDesc（避免双 pack 争用）
  3) 用同一批文件回灌 CN jar（双保险）
  4) 同步进 dist 服务端包 cn-overlay/config/openloader/data/
"""
import json, os, io, zipfile, shutil, sys, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"
CLIENT_ZIP = DIST + r"\WoldsVaults-0.34.1-CN-Client-PCL.zip"
SERVER_ZIP = DIST + r"\WoldsVaults-0.34.1-CN-Server.zip"
INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
CN_JAR = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
OL_DATA = INST + r"\config\openloader\data"
MY_DIR = OL_DATA + r"\WoldsVaults-CN-AbilityDesc"
ZIP_NAME = "WoldsVaults-CN-Data-0.34.1.zip"
DESC_PREFIX = "data/woldsvaults/vault_configs/abilities/descriptions/"

def main():
    # 1) 取分发版数据包
    with zipfile.ZipFile(CLIENT_ZIP) as f:
        blob = f.read("overrides/config/openloader/data/" + ZIP_NAME)
    print("分发版数据包: %d bytes" % len(blob))
    desc_files = {}
    outer = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as g:
        for n in g.namelist():
            outer[n] = g.read(n)
            if n.startswith(DESC_PREFIX) and n.endswith(".json"):
                desc_files[n] = g.read(n).decode("utf-8")
    print("  内含 descriptions:", list(desc_files))
    assert desc_files, "分发包里没有 descriptions"

    # 校对：全中文 + 9 能力
    ab = json.loads(desc_files[DESC_PREFIX + "wolds_abilities.json"])
    assert "UltimateShield_Base" in ab["data"], "缺 UltimateShield_Base"
    bad = [k for k, v in ab["data"].items()
           if not re.search(r"[\u4e00-\u9fff]", "".join(c.get("text", "") for c in v["description"]))]
    assert not bad, "未汉化: %s" % bad
    print("  wolds_abilities 能力数:", len(ab["data"]), "全部中文 OK")

    # 2) 装进本机实例
    os.makedirs(OL_DATA, exist_ok=True)
    dst = os.path.join(OL_DATA, ZIP_NAME)
    if os.path.exists(dst):
        os.chmod(dst, 0o666)
        import nt; nt.remove(dst)
    with open(dst, "wb") as f:
        f.write(blob)
    assert os.path.getsize(dst) == len(blob), "写入大小不符"
    print("已安装:", dst, os.path.getsize(dst))

    # 3) 移除临时目录版
    if os.path.isdir(MY_DIR):
        shutil.rmtree(MY_DIR)
        print("已移除临时目录版:", MY_DIR)
    print("实例 openloader/data 内容:", sorted(os.listdir(OL_DATA)))

    # 4) CN jar 回灌（与分发版对齐）
    bak = CN_JAR + ".bak-1005q"
    if not os.path.exists(bak):
        shutil.copyfile(CN_JAR, bak)
    tmp = CN_JAR + ".tmp%d" % os.getpid()
    with zipfile.ZipFile(CN_JAR) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    names = set(i.filename for i, _ in items)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, b in items:
            if info.filename in desc_files:
                b = desc_files[info.filename].encode("utf-8")
            zout.writestr(info, b)
        for n, t in desc_files.items():
            if n not in names:
                zout.writestr(n, t.encode("utf-8"))
                print("  [NEW] CN jar 新增", n)
    import nt
    if os.path.exists(CN_JAR):
        os.chmod(CN_JAR, 0o666)
        nt.remove(CN_JAR)
    os.rename(tmp, CN_JAR)
    with zipfile.ZipFile(CN_JAR) as z:
        chk = json.loads(z.read(DESC_PREFIX + "wolds_abilities.json").decode("utf-8"))
    print("CN jar 回灌完成: %d bytes, 能力数 %d, UltimateShield=%s"
          % (os.path.getsize(CN_JAR), len(chk["data"]), "UltimateShield_Base" in chk["data"]))

    # 5) 服务端包同步
    tmpz = SERVER_ZIP + ".tmp%d" % os.getpid()
    entry = "WoldsVaults-0.34.1-CN-Server/cn-overlay/config/openloader/data/" + ZIP_NAME
    adv = "WoldsVaults-0.34.1-CN-Server/cn-overlay/config/openloader/advanced_options.json"
    with zipfile.ZipFile(SERVER_ZIP) as zin:
        items = [(i, zin.read(i.filename)) for i in zin.infolist()]
    names = set(i.filename for i, _ in items)
    with zipfile.ZipFile(tmpz, "w", zipfile.ZIP_DEFLATED) as zout:
        for info, b in items:
            zout.writestr(info, b)
        if entry not in names:
            zout.writestr(entry, blob)
            print("  服务端包新增:", entry)
        if adv not in names:
            zout.writestr(adv, json.dumps(
                {"resourcePacks": {"enabled": True, "additionalFolders": []},
                 "dataPacks": {"enabled": True, "additionalFolders": []}},
                ensure_ascii=False, indent=2).encode("utf-8"))
            print("  服务端包新增:", adv)
    os.chmod(SERVER_ZIP, 0o666)
    nt.remove(SERVER_ZIP)
    os.rename(tmpz, SERVER_ZIP)
    print("服务端包已更新:", os.path.getsize(SERVER_ZIP))

if __name__ == "__main__":
    main()
