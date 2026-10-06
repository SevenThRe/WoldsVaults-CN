# -*- coding: utf-8 -*-
"""tsrg2 (left=srg right=official) 精确解析：查成员的 SRG 名"""
import sys, io

TSRG = r"C:\Users\ASUS\.gradle\caches\forge_gradle\minecraft_user_repo\de\oceanlabs\mcp\mcp_config\1.18.2-20220404.173914\srg_to_official_1.18.2.tsrg"
targets = {
    ("net/minecraft/network/chat/Component", "getString"),
    ("net/minecraft/client/KeyMapping", "getTranslatedKeyMessage"),
    ("net/minecraft/network/chat/TranslatableComponent", "getKey"),
    ("net/minecraft/network/chat/TranslatableComponent", "getArgs"),
}
cur = None
res = {}
with io.open(TSRG, encoding="utf-8") as f:
    for ln in f:
        ln = ln.rstrip("\n")
        if not ln.startswith("\t") and not ln.startswith("\t\t"):
            cur = ln.split(" ")[0] if ln.strip() else None
        elif ln.startswith("\t") and not ln.startswith("\t\t"):
            parts = ln.strip().split(" ")
            if len(parts) == 3 and (cur, parts[2]) in targets and parts[1] == "()Ljava/lang/String;":
                res[(cur, parts[2])] = parts[0]
for cls, meth in sorted(targets):
    print("%-55s %-26s -> %s" % (cls, meth, res.get((cls, meth), "未找到")))
