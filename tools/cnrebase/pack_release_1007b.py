# -*- coding: utf-8 -*-
"""1007b: 发布打包 —— 两端换 skyblockfix 1.1.2 + 修 README 乱码文件名 + 输出 sha256"""
import os, sys, zipfile, hashlib, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401
import nt

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "..", "..", "dist")
CLIENT = os.path.join(DIST, "WoldsVaults-0.34.1-CN-Client-PCL.zip")
SERVER = os.path.join(DIST, "WoldsVaults-0.34.1-CN-Server.zip")
FIX = os.path.join(HERE, "skyblockfix", "woldsvaults-skyblock-fix-1.1.2.jar")
VERIFY = os.path.join(HERE, "..", "..", "build", "cn", "work", "sbfx", "skyblock-fix-verify.jar")
CN_JAR = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版"
          r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")

NEW_NAME = "woldsvaults-skyblock-fix-1.1.2.jar"
OLD_NAME = "woldsvaults-skyblock-fix-1.1.1.jar"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def entry_bytes_equal(a, b):
    """只比对 class/json/toml 内容，忽略 zip 时间戳"""
    za, zb = zipfile.ZipFile(a), zipfile.ZipFile(b)
    na = sorted(n for n in za.namelist() if n.endswith((".class", ".json", ".toml")))
    nb = sorted(n for n in zb.namelist() if n.endswith((".class", ".json", ".toml")))
    if na != nb:
        return False, "条目不同: %s" % (set(na) ^ set(nb))
    for n in na:
        if za.read(n) != zb.read(n):
            return False, "内容不同: %s" % n
    return True, "一致(%d 条目)" % len(na)


def rewrite_zip(path, mutator):
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    items = mutator(items)
    tmp = path + ".tmp%d" % os.getpid()
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, b in items:
            zo.writestr(info, b)
    os.chmod(path, 0o666)
    nt.remove(path)
    os.rename(tmp, path)


def main():
    # 0) 校验 1.1.2 与源码重编译一致
    ok, msg = entry_bytes_equal(FIX, VERIFY)
    print("[0] 重编译校验:", ok, msg)
    assert ok, "1.1.2 与源码不一致，停止打包"
    fix_blob = open(FIX, "rb").read()

    # 1) 客户端包：1.1.1 -> 1.1.2
    def mut_client(items):
        out, n = [], 0
        for info, b in items:
            if info.filename.endswith("mods/" + OLD_NAME):
                info.filename = info.filename.replace(OLD_NAME, NEW_NAME)
                b = fix_blob
                n += 1
            out.append((info, b))
        print("[1] 客户端替换 %d 处 -> %s" % (n, NEW_NAME))
        return out
    rewrite_zip(CLIENT, mut_client)

    # 2) 服务端包：换 fix + README 乱码文件名改 ASCII
    def mut_server(items):
        out, n, rn = [], 0, 0
        for info, b in items:
            fn = info.filename
            if fn.endswith("mods/" + OLD_NAME):
                info.filename = fn.replace(OLD_NAME, NEW_NAME)
                b = fix_blob
                n += 1
            elif "README" in fn.upper() or any(ord(c) > 127 for c in fn):
                base = fn.rsplit("/", 1)[0]
                info.filename = base + "/README-CN.txt"
                rn += 1
            out.append((info, b))
        print("[2] 服务端替换 %d 处 fix；README 改名 %d 处" % (n, rn))
        return out
    rewrite_zip(SERVER, mut_server)

    # 3) 确认包内 CN jar 与实例一致
    cn_blob = open(CN_JAR, "rb").read()
    for zp, entry in [(CLIENT, "overrides/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar"),
                      (SERVER, "WoldsVaults-0.34.1-CN-Server/cn-overlay/mods/woldsvaults_cn-1.0.17-0.34.1-universal.jar")]:
        with zipfile.ZipFile(zp) as z:
            same = z.read(entry) == cn_blob
        print("[3] %s 内 CN jar 与实例一致: %s" % (os.path.basename(zp), same))
        assert same, "CN jar 不一致"

    # 4) sha256
    print()
    print("=== 发布文件 sha256 ===")
    for p in [CLIENT, SERVER, CN_JAR]:
        print("  %-46s %s  %d B" % (os.path.basename(p), sha(p), os.path.getsize(p)))


if __name__ == "__main__":
    main()
