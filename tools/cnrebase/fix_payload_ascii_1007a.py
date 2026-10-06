# -*- coding: utf-8 -*-
"""1007a: 验证载荷编码规矩 + 用 ASCII 转义重修全部 zh_cn 载荷与现行文件"""
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
LIVE = [
    os.path.join(BASE, "Wold's Vaults 汉化版", "config", "the_vault", "lang", "zh_cn", "abilities_descriptions.json"),
    os.path.join(BASE, "Wold's Vaults 汉化版 0.34.1", "config", "the_vault", "lang", "zh_cn", "abilities_descriptions.json"),
]
ZH_PAYLOADS = [
    "assets/woldsvaults_cn/config_payload/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/server_payload/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/client_payload_0291/config/the_vault/lang/zh_cn/abilities_descriptions.json",
    "assets/woldsvaults_cn/config_payload/universal_payload_0291/config/the_vault/lang/zh_cn/abilities_descriptions.json",
]
SKILL_PL = "assets/woldsvaults_cn/config_payload/config/the_vault/lang/zh_cn/skill_descriptions.json"


def has_non_ascii(b):
    return any(x > 127 for x in b[:200000])


def main():
    # 0) 验证规矩：旧的无害载荷是否纯 ASCII
    with zipfile.ZipFile(CN_NEW) as z:
        sk = z.read(SKILL_PL)
        cur = z.read(ZH_PAYLOADS[0])
    print("[0] skill_descriptions 载荷: %dB, 含非ASCII字节: %s" % (len(sk), has_non_ascii(sk)))
    print("[0] 我昨晚注入的 abilities 载荷: %dB, 含非ASCII字节: %s  <- 问题所在" % (len(cur), has_non_ascii(cur)))

    # 1) 造 ASCII 转义版（\uXXXX），内容语义不变
    d = json.loads(cur.decode("utf-8"))
    assert len(d.get("data", {})) == 107 and "UltimateShield_Base" in d["data"]
    ascii_blob = json.dumps(d, ensure_ascii=True, indent=1).encode("ascii")
    chk = json.loads(ascii_blob.decode("ascii"))
    assert len(chk["data"]) == 107 and chk["data"]["UltimateShield_Base"], "转义后校验失败"
    print("[1] ASCII 转义版: %dB (纯ASCII: %s)" % (len(ascii_blob), not has_non_ascii(ascii_blob)))

    # 2) 注入 4 处载荷
    bak = CN_NEW + ".bak-1007a"
    if not os.path.exists(bak):
        shutil.copyfile(CN_NEW, bak)
    with zipfile.ZipFile(CN_NEW) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    tmp = CN_NEW + ".tmp%d" % os.getpid()
    n = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, b in items:
            if info.filename in ZH_PAYLOADS:
                b = ascii_blob
                n += 1
            zo.writestr(info, b)
    os.chmod(CN_NEW, 0o666)
    nt.remove(CN_NEW)
    os.rename(tmp, CN_NEW)
    print("[2] CN jar 替换 %d 处载荷 -> %d B" % (n, os.path.getsize(CN_NEW)))

    # 3) 现行文件也写 ASCII 转义版（无论哪条通道读都不会错）
    for p in LIVE:
        ob = p + ".bak-1007a"
        if not os.path.exists(ob):
            shutil.copyfile(p, ob)
        os.chmod(p, 0o666)
        nt.remove(p)
        with open(p, "wb") as f:
            f.write(ascii_blob)
        print("[3] 现行文件重写(ASCII):", os.path.basename(os.path.dirname(os.path.dirname(p))))

    # 4) 部署 jar + dist
    cn_blob = open(CN_NEW, "rb").read()
    for other in [CN_OLD, SRV]:
        ob = other + ".bak-1007a"
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
        ok = True
        for p in ZH_PAYLOADS:
            b = z.read(p)
            dd = json.loads(b.decode("ascii"))
            ok &= (len(dd["data"]) == 107 and not has_non_ascii(b))
        print("[5] 4 载荷全部 107 键且纯 ASCII:", ok)
    print("[5] 最终 jar sha256:", hashlib.sha256(cn_blob).hexdigest()[:16], "…")
    for p in [CN_OLD, SRV]:
        print("     部署一致:", open(p, "rb").read() == cn_blob)
    for p in LIVE:
        print("     现行文件一致:", open(p, "rb").read() == ascii_blob)


if __name__ == "__main__":
    main()
