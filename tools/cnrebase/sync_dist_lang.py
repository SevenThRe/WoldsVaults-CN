# -*- coding: utf-8 -*-
"""1005q-5: 把修正后的 abilities_descriptions.json 同步进 dist 客户端/服务端发布包"""
import json, os, io, zipfile, sys, nt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
LANG = INST + "\\config\\the_vault\\lang\\zh_cn\\abilities_descriptions.json"
DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"
CLIENT_ZIP = DIST + r"\WoldsVaults-0.34.1-CN-Client-PCL.zip"
SERVER_ZIP = DIST + r"\WoldsVaults-0.34.1-CN-Server.zip"
NAME = "abilities_descriptions.json"

new_blob = io.open(LANG, encoding="utf-8").read().encode("utf-8")
print("新文件 %d bytes, 能力数 %d" % (len(new_blob), len(json.loads(new_blob.decode("utf-8"))["data"])))

# ---- 客户端 ----
with zipfile.ZipFile(CLIENT_ZIP) as z:
    items = [(i, z.read(i.filename)) for i in z.infolist()]
targets = [i.filename for i, _ in items if i.filename.endswith("/" + NAME)]
print("客户端包内匹配条目:", targets)
tmp = CLIENT_ZIP + ".tmp%d" % os.getpid()
n = 0
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
    for info, b in items:
        if info.filename in targets:
            b = new_blob; n += 1
        zo.writestr(info, b)
os.chmod(CLIENT_ZIP, 0o666); nt.remove(CLIENT_ZIP); os.rename(tmp, CLIENT_ZIP)
print("客户端包已更新(替换 %d 处): %d bytes" % (n, os.path.getsize(CLIENT_ZIP)))

# ---- 服务端 ----
entry = "WoldsVaults-0.34.1-CN-Server/cn-overlay/config/the_vault/lang/zh_cn/" + NAME
with zipfile.ZipFile(SERVER_ZIP) as z:
    items = [(i, z.read(i.filename)) for i in z.infolist()]
names = set(i.filename for i, _ in items)
tmp = SERVER_ZIP + ".tmp%d" % os.getpid()
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
    for info, b in items:
        zo.writestr(info, b)
    if entry not in names:
        zo.writestr(entry, new_blob)
        print("服务端包新增:", entry)
os.chmod(SERVER_ZIP, 0o666); nt.remove(SERVER_ZIP); os.rename(tmp, SERVER_ZIP)
print("服务端包已更新: %d bytes" % os.path.getsize(SERVER_ZIP))
with zipfile.ZipFile(SERVER_ZIP) as z:
    print("  服务端 abilities_descriptions:", [n for n in z.namelist() if n.endswith(NAME)])
