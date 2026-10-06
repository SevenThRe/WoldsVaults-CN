# -*- coding: utf-8 -*-
"""按 qol_strings_raw.txt 的顺序生成 qol_strings_zh.tsv，并做四条自检。"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qol_translations import T

OUT_DIR = r"C:\Users\ASUS\WorkBuddy\2026-09-30-14-41-57\translations\cn-rebase"
RAW = os.path.join(OUT_DIR, "qol_strings_raw.txt")
DST = os.path.join(OUT_DIR, "qol_strings_zh.tsv")
CJK = re.compile(r"[\u4e00-\u9fff]")


def main():
    with io.open(RAW, "r", encoding="utf-8", newline="\n") as f:
        raw_lines = [ln.rstrip("\n") for ln in f if ln.rstrip("\n") != ""]
    print("raw lines: %d" % len(raw_lines))

    missing = [s for s in raw_lines if s not in T]
    extra = [k for k in T if k not in set(raw_lines)]
    if missing:
        print("!! 缺少译文 %d 条:" % len(missing))
        for s in missing:
            print("   MISSING: %r" % s)
    if extra:
        print("!! 译表中存在 raw 里没有的键 %d 条:" % len(extra))
        for s in extra:
            print("   EXTRA:   %r" % s)
    if missing or extra:
        sys.exit(1)

    with io.open(DST, "w", encoding="utf-8", newline="\n") as f:
        for s in raw_lines:
            zh = T[s]
            assert "\t" not in s and "\t" not in zh, "原文/译文里不应有制表符: %r" % s
            assert "\n" not in s and "\n" not in zh, "原文/译文里不应有真实换行: %r" % s
            f.write("%s\t%s\n" % (s, zh))
    print("wrote -> %s" % DST)

    # ---------------- 自检 ----------------
    raw_set = set(raw_lines)
    with io.open(DST, "r", encoding="utf-8", newline="\n") as f:
        content = f.read()
    assert "\r" not in content, "不应出现 CR"
    lines = [ln for ln in content.split("\n") if ln != ""]
    errs = []
    if not (len(lines) > 0):
        errs.append("(a) 行数为 0")
    for i, ln in enumerate(lines, 1):
        if ln.count("\t") != 1:
            errs.append("(b) 第 %d 行制表符数量 = %d" % (i, ln.count("\t")))
            continue
        en, zh = ln.split("\t")
        if en not in raw_set:
            errs.append("(c) 第 %d 行原文不在 raw 中: %r" % (i, en))
        if not CJK.search(zh):
            errs.append("(d) 第 %d 行译文不含中文: %r" % (i, zh))
    # 编码检查：UTF-8 无 BOM
    with open(DST, "rb") as f:
        head = f.read(3)
    if head == b"\xef\xbb\xbf":
        errs.append("(e) 文件带 BOM")

    if errs:
        print("!! 自检失败 %d 项:" % len(errs))
        for e in errs[:20]:
            print("   " + e)
        sys.exit(1)
    print("自检全部通过：%d 条（无 BOM / 每行恰好 1 个 TAB / 原文均在 raw 中 / 译文均含中文）" % len(lines))


if __name__ == "__main__":
    main()
