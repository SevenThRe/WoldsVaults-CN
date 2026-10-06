# -*- coding: utf-8 -*-
"""
1005q-3: 真正生效的通道是 config/the_vault/lang/zh_cn/abilities_descriptions.json
（the_vault 的语言覆盖，键 = 能力 ID）。把 fork(woldsvaults) 的能力描述补进去。
源 = 已有的中文数据包 WoldsVaults-CN-Data-0.34.1.zip。
"""
import json, os, io, zipfile, shutil, sys, re, nt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
LANG = INST + r"\config\the_vault\lang\zh_cn\abilities_descriptions.json"
OL_ZIP = INST + r"\config\openloader\data\WoldsVaults-CN-Data-0.34.1.zip"
DESC_PREFIX = "data/woldsvaults/vault_configs/abilities/descriptions/"

def zh(v):
    return bool(re.search(r"[\u4e00-\u9fff]", "".join(c.get("text", "") for c in v["description"])))

def main():
    # 源：中文数据包
    src = {}
    with zipfile.ZipFile(OL_ZIP) as g:
        for n in g.namelist():
            if n.startswith(DESC_PREFIX) and n.endswith(".json"):
                d = json.loads(g.read(n).decode("utf-8"))
                for k, v in d.get("data", {}).items():
                    src[k] = v
    print("源数据包能力数:", len(src), "全中文:", all(zh(v) for v in src.values()))
    print("  ", sorted(src))

    # 目标：lang 覆盖文件
    bak = LANG + ".bak-1005q"
    if not os.path.exists(bak):
        shutil.copyfile(LANG, bak)
    with open(LANG, "rb") as f:
        raw = f.read()
    lang = json.loads(raw.decode("utf-8"))
    data = lang["data"]
    before = len(data)

    added, overwrote = [], []
    for k, v in src.items():
        if k not in data:
            data[k] = v
            added.append(k)
        else:
            if not zh(data[k]) and zh(v):
                data[k] = v
                overwrote.append(k)
    print("lang 原有:", before, "→ 现有:", len(data))
    print("新增:", added)
    print("覆盖(原为英文):", overwrote)

    assert "UltimateShield_Base" in data and "Expunge_Base" in data
    bad = [k for k, v in data.items() if not zh(v)]
    print("仍未汉化的键(%d):" % len(bad), bad[:20])

    out = json.dumps(lang, ensure_ascii=False, indent=1)
    os.chmod(LANG, 0o666)
    nt.remove(LANG)
    with open(LANG, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("已写出:", LANG, os.path.getsize(LANG))

    # 复核
    chk = json.loads(io.open(LANG, encoding="utf-8").read().encode("utf-8").decode("utf-8"))
    for k in ("UltimateShield_Base", "Expunge_Base"):
        print("  %s -> %s" % (k, "".join(c["text"] for c in chk["data"][k]["description"]).replace("\n", "\\n")))

if __name__ == "__main__":
    main()
