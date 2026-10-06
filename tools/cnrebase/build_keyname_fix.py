# -*- coding: utf-8 -*-
"""
1005r: 编译 MixinKeyMappingSanitize（mojmap -> FART reobf -> SRG），
注入 CN jar（新 class + mixins.woldsvaults_cn.client.json 注册），
并同步 dist 双 zip 与本地服务器副本。
"""
import os, sys, zipfile, shutil, json, subprocess, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "cnfix", "src")
WORK = os.path.join(HERE, "build", "cnfix")

JAVAC = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javac.exe"
JAVA17 = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\java.exe"
GRADLE = r"C:\Users\ASUS\.gradle\caches\forge_gradle"
MOJMAP = os.path.join(GRADLE, r"minecraft_user_repo\net\minecraftforge\forge\1.18.2-40.3.11_mapped_official_1.18.2",
                      "forge-1.18.2-40.3.11_mapped_official_1.18.2-recomp.jar")
FART = os.path.join(GRADLE, r"maven_downloader\net\minecraftforge\ForgeAutoRenamingTool\1.0.6",
                    "ForgeAutoRenamingTool-1.0.6-all.jar")
MAP = os.path.join(GRADLE, r"minecraft_user_repo\de\oceanlabs\mcp\mcp_config\1.18.2-20220404.173914",
                   "srg_to_official_1.18.2.tsrg")
MCLIB = r"E:\Game Files (x86)\Minecraft\.minecraft\libraries"
CN_MOD = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
          r"\Wold's Vaults 汉化版 0.34.1\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")

CP = [
    MOJMAP,
    CN_MOD,
    os.path.join(MCLIB, r"org\spongepowered\mixin\0.8.5\mixin-0.8.5.jar"),
    os.path.join(MCLIB, r"com\google\guava\guava\31.0.1-jre\guava-31.0.1-jre.jar"),
    os.path.join(MCLIB, r"com\google\code\gson\gson\2.8.7\gson-2.8.7.jar"),
    os.path.join(MCLIB, r"org\apache\logging\log4j\log4j-api\2.17.0\log4j-api-2.17.0.jar"),
    os.path.join(MCLIB, r"com\mojang\brigadier\1.0.18\brigadier-1.0.18.jar"),
]

CLSID = "com/woldsvaults/cn/mixin/client/MixinKeyMappingSanitize.class"
MIXIN_JSON = "mixins.woldsvaults_cn.client.json"


def sources():
    out = []
    for root, _d, files in os.walk(SRC):
        for f in files:
            if f.endswith(".java"):
                out.append(os.path.join(root, f))
    return out


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    if r.returncode != 0:
        print(out)
        raise SystemExit("命令失败: %s" % " ".join(cmd))
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    # 1) javac
    cp = os.pathsep.join(CP)
    sh([JAVAC, "-encoding", "UTF-8", "-source", "17", "-target", "17", "-proc:none",
        "-cp", cp, "-d", os.path.join(WORK, "raw")] + sources())
    print("[1] javac ok")

    # 2) raw jar
    raw = os.path.join(WORK, "raw.jar")
    with zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _d, files in os.walk(os.path.join(WORK, "raw")):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, os.path.join(WORK, "raw")).replace("\\", "/"))
    # 3) FART reobf
    reob = os.path.join(WORK, "reob.jar")
    sh([JAVA17, "-jar", FART, "--input", raw, "--output", reob,
        "--map", MAP, "--reverse", "--ann-fix", "--ids-fix", "--lib", MOJMAP])
    print("[2] FART reobf ok")

    # 4) 校验：注解 method 保持 SRG、代码引用转 SRG
    with zipfile.ZipFile(reob) as z:
        blob = z.read(CLSID)
    txt = subprocess.run([os.path.join(os.path.dirname(JAVAC), "javap.exe"), "-p", "-v", "-c", reob + "!" + "/" + CLSID.replace("/", ".")[:-6]],
                         capture_output=True).stdout.decode("utf-8", "replace")
    # javap 直接吃 jar!class 在部分版本不可用，改从 reob.jar 提取到文件
    cls_path = os.path.join(WORK, "MixinKeyMappingSanitize.class")
    with open(cls_path, "wb") as f:
        f.write(blob)
    txt = subprocess.run([os.path.join(os.path.dirname(JAVAC), "javap.exe"), "-p", "-c", "-v", cls_path],
                         capture_output=True).stdout.decode("utf-8", "replace")
    assert "m_90863_" in txt, "注解 method= 丢失 SRG 名"
    for marker in ("m_68786_", "m_237113_"):  # getString / Component.literal
        pass  # 名单仅参考，存在性打印
    print("[3] 注解 method=m_90863_ 保留; SRG 调用:",
          {k: (k in txt) for k in ("m_68786_", "m_237113_", "m_76636_", "getString", "literal")})

    # 5) 注入 CN jar
    bak = CN_MOD + ".bak-1005r-0341"
    if not os.path.exists(bak):
        shutil.copyfile(CN_MOD, bak)
    with zipfile.ZipFile(CN_MOD) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    names = set(i.filename for i, _ in items)
    new_json = None
    for info, b in items:
        if info.filename == MIXIN_JSON:
            d = json.loads(b.decode("utf-8"))
            cl = d.setdefault("client", [])
            if "MixinKeyMappingSanitize" not in cl:
                cl.append("MixinKeyMappingSanitize")
            new_json = json.dumps(d, ensure_ascii=False).encode("utf-8")
    assert new_json, "找不到 %s" % MIXIN_JSON
    tmp = CN_MOD + ".tmp%d" % os.getpid()
    import nt
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, b in items:
            if info.filename == MIXIN_JSON:
                b = new_json
            elif info.filename == CLSID:
                b = blob
            zo.writestr(info, b)
        if CLSID not in names:
            zo.writestr(CLSID, blob)
            print("  [NEW] CN jar 新增", CLSID)
    os.chmod(CN_MOD, 0o666)
    nt.remove(CN_MOD)
    os.rename(tmp, CN_MOD)
    print("[4] CN jar 注入完成: %d bytes (备份 %s)" % (os.path.getsize(CN_MOD), os.path.basename(bak)))

    # 6) 同步 dist 双 zip
    DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"
    cn_blob = open(CN_MOD, "rb").read()
    targets = {
        os.path.join(DIST, "WoldsVaults-0.34.1-CN-Client-PCL.zip"):
            ["overrides/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
        os.path.join(DIST, "WoldsVaults-0.34.1-CN-Server.zip"):
            ["WoldsVaults-0.34.1-CN-Server/cn-overlay/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
    }
    for zp, entries in targets.items():
        with zipfile.ZipFile(zp) as z:
            its = [(i, z.read(i.filename)) for i in z.infolist()]
        nm = set(i.filename for i, _ in its)
        tmpz = zp + ".tmp%d" % os.getpid()
        n = 0
        with zipfile.ZipFile(tmpz, "w", zipfile.ZIP_DEFLATED) as zo:
            for info, b in its:
                if info.filename in entries:
                    b = cn_blob
                    n += 1
                zo.writestr(info, b)
            for e in entries:
                if e not in nm:
                    zo.writestr(e, cn_blob)
                    n += 1
        os.chmod(zp, 0o666)
        nt.remove(zp)
        os.rename(tmpz, zp)
        print("[5] %s 更新 %d 处 -> %d bytes" % (os.path.basename(zp), n, os.path.getsize(zp)))


if __name__ == "__main__":
    main()
