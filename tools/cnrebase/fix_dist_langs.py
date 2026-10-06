# -*- coding: utf-8 -*-
"""
1005q-6: 修正上一脚本的误伤——把 de_de/es_es/fr_fr/pt_br/ru_ru/sv_se 还原为各自语言原文，
只让 zh_cn（以及 config/the_vault 根级）使用新的中文版。
"""
import json, os, io, zipfile, sys, nt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

INST = "E:\\Game Files (x86)\\Minecraft\\.minecraft\\versions\\Wold's Vaults 汉化版 0.34.1"
LANGDIR = INST + "\\config\\the_vault\\lang"
ROOTFILE = INST + "\\config\\the_vault\\abilities_descriptions.json"
DIST = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\dist"
CLIENT_ZIP = DIST + r"\WoldsVaults-0.34.1-CN-Client-PCL.zip"
NAME = "abilities_descriptions.json"

zh_blob = io.open(LANGDIR + "\\zh_cn\\" + NAME, encoding="utf-8").read().encode("utf-8")
print("zh_cn 新版 %d bytes" % len(zh_blob))

blobs = {}
for d in ("de_de", "es_es", "fr_fr", "pt_br", "ru_ru", "sv_se"):
    p = os.path.join(LANGDIR, d, NAME)
    blobs["overrides/config/the_vault/lang/%s/%s" % (d, NAME)] = io.open(p, "rb").read()
    print("  还原 %s <- %d bytes" % (d, os.path.getsize(p)))

# 根级：若实例根级是中文则用新版中文，否则保留实例内容
root = io.open(ROOTFILE, "rb").read()
root_txt = root.decode("utf-8")
is_zh = any("\u4e00" <= ch <= "\u9fff" for ch in root_txt[:4000])
blobs["overrides/config/the_vault/" + NAME] = zh_blob if is_zh else root
print("根级 abilities_descriptions.json 实例为%s -> %s" % ("中文" if is_zh else "非中文",
      "新版中文" if is_zh else "保留原文"))
blobs["overrides/config/the_vault/lang/zh_cn/" + NAME] = zh_blob

with zipfile.ZipFile(CLIENT_ZIP) as z:
    items = [(i, z.read(i.filename)) for i in z.infolist()]
targets = set(blobs)
found = [i.filename for i, _ in items if i.filename in targets]
print("命中条目 %d/%d:" % (len(found), len(targets)))
for f in found:
    print("   ", f)

tmp = CLIENT_ZIP + ".tmp%d" % os.getpid()
with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
    for info, b in items:
        if info.filename in targets:
            b = blobs[info.filename]
        zo.writestr(info, b)
os.chmod(CLIENT_ZIP, 0o666); nt.remove(CLIENT_ZIP); os.rename(tmp, CLIENT_ZIP)
print("客户端包已修正: %d bytes" % os.path.getsize(CLIENT_ZIP))

# 复核
with zipfile.ZipFile(CLIENT_ZIP) as z:
    for d in ("de_de", "zh_cn"):
        b = z.read("overrides/config/the_vault/lang/%s/%s" % (d, NAME))
        txt = b.decode("utf-8")
        print("  复核 %s: %d bytes, 含中文=%s" % (d, len(b),
              any("\u4e00" <= ch <= "\u9fff" for ch in txt[:4000])))
