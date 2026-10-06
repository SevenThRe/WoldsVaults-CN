# -*- coding: utf-8 -*-
"""1005q-4: 扫描 abilities_descriptions.json 里残留的英文组件并翻译（先扫描后修复，幂等）"""
import json, os, io, re, sys, nt, shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fsutil  # noqa: F401

INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版 0.34.1"
LANG = INST + r"\config\the_vault\lang\zh_cn\abilities_descriptions.json"

MAP = {
    "Cast Ability": "施放技能",
    "Toggle Ability": "切换技能",
    "Hold Ability": "长按技能",
    "Passive Ability": "被动技能",
    "Instant Ability": "瞬发技能",
}

def is_en(t):
    return re.search(r"[A-Za-z]", t) and not re.search(r"[\u4e00-\u9fff]", t)

def main():
    lang = json.loads(io.open(LANG, encoding="utf-8").read())
    data = lang["data"]
    hits = {}
    for k, v in data.items():
        for c in v["description"]:
            t = c.get("text", "")
            if is_en(t):
                hits.setdefault(t.strip(), []).append(k)
    print("=== 残留英文组件（去重视图） ===")
    for t, ks in sorted(hits.items(), key=lambda x: -len(x[1])):
        print("  %-40r  x%d  e.g. %s" % (t, len(ks), ks[:3]))

    changed = 0
    for v in data.values():
        for c in v["description"]:
            t = c.get("text", "")
            if not is_en(t):
                continue
            nt_text = t
            for en, zh in MAP.items():
                nt_text = nt_text.replace(en, zh)
            if nt_text != t:
                c["text"] = nt_text
                changed += 1
    print("已修复组件数:", changed)

    if changed:
        bak = LANG + ".bak-1005q-enfix"
        if not os.path.exists(bak):
            shutil.copyfile(LANG, bak)
        out = json.dumps(lang, ensure_ascii=False, indent=1)
        os.chmod(LANG, 0o666)
        nt.remove(LANG)
        with open(LANG, "w", encoding="utf-8", newline="\n") as f:
            f.write(out)
        print("已写出:", os.path.getsize(LANG))

    chk = json.loads(io.open(LANG, encoding="utf-8").read())
    for k in ("UltimateShield_Base", "Expunge_Base"):
        print("  %s -> %s" % (k, "".join(c["text"] for c in chk["data"][k]["description"]).replace("\n", "\\n")))
    left = {t: len(ks) for t, ks in hits.items() if any(
        is_en(c.get("text", "")) for v in chk["data"].values() for c in v["description"] if c.get("text", "").strip() == t)}
    print("修复后仍残留:", left)

if __name__ == "__main__":
    main()
