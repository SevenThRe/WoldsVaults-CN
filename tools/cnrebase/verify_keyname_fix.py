# -*- coding: utf-8 -*-
"""1005r 收尾验证：0.34.1 实例 CN jar 的 mixin 注册 + 同步服务器副本"""
import zipfile, os, sys, json, shutil

sys.stdout.reconfigure(encoding="utf-8")
CLSID = "com/woldsvaults/cn/mixin/client/MixinKeyMappingSanitize.class"
MJ = "mixins.woldsvaults_cn.client.json"

def check(jar, tag):
    z = zipfile.ZipFile(jar)
    d = json.loads(z.read(MJ).decode("utf-8"))
    ok1 = "MixinKeyMappingSanitize" in d.get("client", [])
    ok2 = CLSID in z.namelist()
    print("%s: json=%s class=%s" % (tag, ok1, ok2))
    z.close()
    return ok1 and ok2

INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
CN = INST + r"\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
check(CN, "客户端实例")

SRV = r"E:\WoldsVaults-0.34.1-CN-Server\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar"
if os.path.exists(SRV):
    bak = SRV + ".bak-1005r"
    if not os.path.exists(bak):
        shutil.copyfile(SRV, bak)
    shutil.copyfile(CN, SRV)
    print("服务器副本已同步:", os.path.getsize(SRV), "bytes")
    check(SRV, "服务器副本")
else:
    print("服务器副本不存在:", SRV)
