# -*- coding: utf-8 -*-
"""
1006a: 技能/天赋 tooltip 汉化修复
  1) 译料合并：qol_strings_zh.tsv(167条, 术语归一) + 静态条目 → literal_zh_cn.tsv(译料层 + jar)
  2) 编译 MixinFontFcs.java（mojmap→FART reobf→SRG），连同 MixinKeyMappingSanitize 一起注入 CN jar
  3) 注册 mixins.woldsvaults_cn.client.json
  4) 部署：0.34.1 实例 + 无后缀实例 + dist 双 zip + 服务器副本
"""
import os, sys, zipfile, shutil, json, subprocess, re, io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "cnfix", "src")
WORK = os.path.join(HERE, "build", "cnfix1006")
TRD = os.path.join(HERE, "..", "..", "translations", "cn-rebase")

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
CN_NEW = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
          r"\Wold's Vaults 汉化版 0.34.1\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")
CN_OLD = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
          r"\Wold's Vaults 汉化版\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")
SRV = r"E:\WoldsVaults-0.34.1-CN-Server\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"

CP = [
    MOJMAP, CN_NEW,
    os.path.join(MCLIB, r"org\spongepowered\mixin\0.8.5\mixin-0.8.5.jar"),
    os.path.join(MCLIB, r"com\google\guava\guava\31.0.1-jre\guava-31.0.1-jre.jar"),
    os.path.join(MCLIB, r"com\google\code\gson\gson\2.8.7\gson-2.8.7.jar"),
    os.path.join(MCLIB, r"org\apache\logging\log4j\log4j-api\2.17.0\log4j-api-2.17.0.jar"),
    os.path.join(MCLIB, r"com\mojang\brigadier\1.0.18\brigadier-1.0.18.jar"),
]
CLASSES = {
    "com/woldsvaults/cn/mixin/client/MixinFontFcs.class": "MixinFontFcs",
    "com/woldsvaults/cn/mixin/client/MixinKeyMappingSanitize.class": "MixinKeyMappingSanitize",
}
MIXIN_JSON = "mixins.woldsvaults_cn.client.json"
TSV_ENTRY = "assets/woldsvaults_cn/literal_zh_cn.tsv"

STATIC_ADDS = {
    "Max rank learned": "已达最高等级",
    "QOLHunters Config": "QOL猎手 配置",
}
NORMALIZE = [("能量塔", "晶塔"), ("珠宝", "宝石"), ("补给包", "卡包")]


def sh(cmd):
    r = subprocess.run(cmd, capture_output=True)
    out = (r.stdout + r.stderr).decode("utf-8", "replace")
    if r.returncode != 0:
        print(out)
        raise SystemExit("命令失败: %s" % " ".join(cmd))
    return out


def esc(s):
    return s.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def read_tsv_map(blob):
    m = {}
    for line in blob.split("\n"):
        if "\t" in line:
            k, v = line.split("\t", 1)
            m[k] = v
    return m


def main():
    os.makedirs(WORK, exist_ok=True)

    # ---------- 1. 译料合并 ----------
    with zipfile.ZipFile(CN_NEW) as z:
        jar_tsv_blob = z.read(TSV_ENTRY).decode("utf-8")
    table = read_tsv_map(jar_tsv_blob)
    print("[1] jar TSV 现有条目:", len(table))

    qol_path = os.path.join(TRD, "qol_strings_zh.tsv")
    adds = dict(STATIC_ADDS)
    if os.path.exists(qol_path):
        for raw in io.open(qol_path, encoding="utf-8-sig").read().splitlines():
            if "\t" not in raw:
                continue
            k, v = raw.split("\t", 1)
            k, v = esc(k).strip(), esc(v).strip()
            if not k or not v:
                continue
            for a, b in NORMALIZE:
                v = v.replace(a, b)
            adds[k] = v
    n_add = 0
    for k, v in adds.items():
        if k not in table and k != v:
            table[k] = v
            n_add += 1
    print("[1] 待新增条目:", n_add)

    new_tsv_blob = "\n".join("%s\t%s" % (k, v) for k, v in table.items()) + "\n"
    # 译料层同步
    src_tsv = os.path.join(TRD, "literal_zh_cn.tsv")
    if os.path.exists(src_tsv):
        layer = read_tsv_map(io.open(src_tsv, encoding="utf-8-sig").read())
        layer.update({k: v for k, v in table.items() if k not in layer or layer[k] != v})
        with io.open(src_tsv, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join("%s\t%s" % (k, v) for k, v in layer.items()) + "\n")
        print("[1] 译料层同步 ->", len(layer), "条")
    else:
        print("[1] !! 译料层 literal_zh_cn.tsv 不存在，仅改 jar")

    # ---------- 2. 编译 ----------
    cp = os.pathsep.join(CP)
    srcs = []
    for root, _d, files in os.walk(SRC):
        for f in files:
            if f.endswith(".java"):
                srcs.append(os.path.join(root, f))
    print("[2] 源文件:", [os.path.basename(s) for s in srcs])
    sh([JAVAC, "-encoding", "UTF-8", "-source", "17", "-target", "17", "-proc:none",
        "-cp", cp, "-d", os.path.join(WORK, "raw")] + srcs)
    rawjar = os.path.join(WORK, "raw.jar")
    with zipfile.ZipFile(rawjar, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _d, files in os.walk(os.path.join(WORK, "raw")):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, os.path.join(WORK, "raw")).replace("\\", "/"))
    reob = os.path.join(WORK, "reob.jar")
    sh([JAVA17, "-jar", FART, "--input", rawjar, "--output", reob,
        "--map", MAP, "--reverse", "--ann-fix", "--ids-fix", "--lib", MOJMAP])
    print("[2] FART reobf ok")
    blobs = {}
    with zipfile.ZipFile(reob) as z:
        for cls in CLASSES:
            blobs[cls] = z.read(cls)
    chk = os.path.join(WORK, "MixinFontFcs.class")
    open(chk, "wb").write(blobs["com/woldsvaults/cn/mixin/client/MixinFontFcs.class"])
    txt = subprocess.run([os.path.join(os.path.dirname(JAVAC), "javap.exe"), "-p", "-v", "-c", chk],
                         capture_output=True).stdout.decode("utf-8", "replace")
    assert "m_92726_" in txt, "注解 method=m_92726_ 丢失"
    print("[2] 注解 m_92726_ 保留 ✓; translate 调用:",
          {k: (k in txt) for k in ("translate", "LiteralTranslator")})

    # ---------- 3. 注入 jar（0.34.1 实例为基准） ----------
    bak = CN_NEW + ".bak-1006a"
    if not os.path.exists(bak):
        shutil.copyfile(CN_NEW, bak)
    with zipfile.ZipFile(CN_NEW) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    names = set(i.filename for i, _ in items)
    new_json = None
    for info, b in items:
        if info.filename == MIXIN_JSON:
            d = json.loads(b.decode("utf-8"))
            cl = d.setdefault("client", [])
            for m in CLASSES.values():
                if m not in cl:
                    cl.append(m)
            new_json = json.dumps(d, ensure_ascii=False).encode("utf-8")
        elif info.filename == TSV_ENTRY:
            b = new_tsv_blob.encode("utf-8")
        items2 = True
    assert new_json, "找不到 mixin json"
    # 重新组装（TSV blob 已在循环里替换？没有——重写一遍更稳）
    tmp = CN_NEW + ".tmp%d" % os.getpid()
    import nt
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, b in items:
            if info.filename == MIXIN_JSON:
                b = new_json
            elif info.filename == TSV_ENTRY:
                b = new_tsv_blob.encode("utf-8")
            elif info.filename in blobs:
                b = blobs[info.filename]
            zo.writestr(info, b)
        for cls in blobs:
            if cls not in names:
                zo.writestr(cls, blobs[cls])
                print("  [NEW] 注入", cls)
    os.chmod(CN_NEW, 0o666)
    nt.remove(CN_NEW)
    os.rename(tmp, CN_NEW)
    print("[3] 0.34.1 实例 jar 完成:", os.path.getsize(CN_NEW), "B (备份 .bak-1006a)")

    # ---------- 4. 部署 ----------
    cn_blob = open(CN_NEW, "rb").read()
    for other in [CN_OLD, SRV]:
        d = os.path.dirname(other)
        if not os.path.isdir(d):
            print("[4] 跳过(目录不存在):", d)
            continue
        ob = other + ".bak-1006a"
        if not os.path.exists(ob):
            shutil.copyfile(other, ob)
        os.chmod(other, 0o666)
        import nt as _nt
        _nt.remove(other)
        shutil.copyfile(CN_NEW, other)
        print("[4] 部署:", other, os.path.getsize(other), "B")
    for zp, entries in {
        os.path.join(DIST, "WoldsVaults-0.34.1-CN-Client-PCL.zip"):
            ["overrides/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
        os.path.join(DIST, "WoldsVaults-0.34.1-CN-Server.zip"):
            ["WoldsVaults-0.34.1-CN-Server/cn-overlay/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"],
    }.items():
        if not os.path.exists(zp):
            print("[4] 跳过 dist(不存在):", zp)
            continue
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
        print("[4] %s 更新 %d 处 -> %d B" % (os.path.basename(zp), n, os.path.getsize(zp)))

    # ---------- 5. 校验 ----------
    import hashlib
    h = hashlib.sha256(cn_blob).hexdigest()
    ok_old = os.path.exists(CN_OLD) and open(CN_OLD, "rb").read() == cn_blob
    print("[5] jar sha256:", h[:16], "…  旧实例一致:", ok_old)
    with zipfile.ZipFile(CN_NEW) as z:
        d = json.loads(z.read(MIXIN_JSON).decode("utf-8"))
        tsv = z.read(TSV_ENTRY).decode("utf-8")
    print("[5] mixin client 列表:", d["client"])
    t2 = read_tsv_map(tsv)
    for k in ("Dash", "Hexbreaker", "Max rank learned", "QOLHunters Config",
              "Enable Bartering Discount Display", "Show Hunter Particles for Pylons"):
        print("    TSV %r -> %s" % (k, t2.get(k, "<缺>")))


if __name__ == "__main__":
    main()
