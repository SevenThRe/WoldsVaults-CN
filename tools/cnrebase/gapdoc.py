# -*- coding: utf-8 -*-
"""生成《未汉化模组清单》—— 回答「哪些模组没中文、还差多少、先做哪个」。

数据来源（全部是本轮构建的产物，不另起炉灶）：
  build/cn/todo/vendor-scan.json   逐命名空间体检：en / self_zh / missing / fake_zh
  build/cn/todo/todo-vendor.tsv    逐条待译（已过 _has_letter 判据）

「零中文」的定义：`self_zh == 0` 且 `en > 0`。
  —— 只要求 self_zh==0 不够：有些模组压根没有语言文件（en==0），
     它们的文本是硬编码的，走的是另一条通道，别混进这份清单。
"""
from __future__ import annotations

import csv
import io
import json
from collections import Counter
from pathlib import Path

LEGACY_NS = {"the_vault", "woldsvaults", "kubejs", "qolhunters", "packmenu"}

# AE 系（用户点名）：主模组 + 生态
AE_FAMILY = [
    "ae2", "ae2additions", "ae2things", "aeinfinitybooster", "ae2insertexportcard",
    "ae2searchimprovementsbackport", "ae2qolrecipes", "ae2tabs", "appmek",
    "appbot", "appliedcooking", "megacells", "merequester", "expatternprovider",
    "appliedenergistics2",
]


def _load_todo_counts(todo_tsv: Path) -> Counter:
    """每命名空间的**实际**待译条数（已排除空原文与去占位符后无字母的条目）。"""
    lines = todo_tsv.read_text(encoding="utf-8").splitlines()
    rows = csv.DictReader(io.StringIO("\n".join(lines[2:])), delimiter="\t")
    return Counter(r["namespace"] for r in rows)


def build(scan_path: Path, todo_tsv: Path, out_path: Path) -> str:
    scan = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    todo = _load_todo_counts(Path(todo_tsv))

    third = [r for r in scan if r["ns"] not in LEGACY_NS]
    zero = [r for r in third if r["self_zh"] == 0 and r["en"] > 0]
    partial = [r for r in third if r["self_zh"] > 0 and (r["missing"] + r["fake_zh"]) > 0]
    perfect = [r for r in third if r["en"] > 0 and r["self_zh"] > 0
               and r["missing"] == 0 and r["fake_zh"] == 0]

    zero.sort(key=lambda r: -todo.get(r["ns"], r["en"]))
    partial.sort(key=lambda r: -todo.get(r["ns"], 0))

    tot_en = sum(r["en"] for r in third)
    tot_zh = sum(r["self_zh"] for r in third)
    tot_missing = sum(r["missing"] for r in third)
    tot_fake = sum(r["fake_zh"] for r in third)
    tot_todo = sum(todo.get(r["ns"], 0) for r in third)

    L: list[str] = []
    A = L.append

    A("# 未汉化模组清单")
    A("")
    A("> 回答三个问题：**哪些模组没中文**、**每个还差多少**、**先做哪个**。")
    A(">")
    A("> 本文由 `python -m tools.cnrebase.cli gap-doc` 自动生成，数据取自"
      " `build/cn/todo/vendor-scan.json` 与 `todo-vendor.tsv`，随构建重跑即可保持一致。")
    A("")

    A("## 一、总览")
    A("")
    A("| 指标 | 数量 |")
    A("|---|---|")
    A(f"| 第三方命名空间 | {len(third)} |")
    A(f"| 英文键总数 | {tot_en} |")
    A(f"| 模组自带中文键 | {tot_zh} |")
    A(f"| 缺键（`zh_cn` 里没有） | {tot_missing} |")
    A(f"| 伪翻译（有 `zh_cn` 但值=英文） | {tot_fake} |")
    A(f"| **待译合计**（已滤掉无需翻译的条目） | **{tot_todo}** |")
    A(f"| **整包零中文**（从未被汉化过） | **{len(zero)} 个命名空间** |")
    A(f"| 有中文但不完整 | {len(partial)} |")
    A(f"| 有中文且完整（不必动） | {len(perfect)} |")
    A("")
    A(f"零中文的 {len(zero)} 个命名空间贡献了 "
      f"**{sum(todo.get(r['ns'], 0) for r in zero)}** 条待译，"
      f"占全部的 "
      f"{sum(todo.get(r['ns'], 0) for r in zero) / max(tot_todo, 1) * 100:.1f}%。")
    A("")

    # ---------- 二、零中文清单 ----------
    A("## 二、零中文模组清单（需要汉化，且从未被汉化过）")
    A("")
    A("按待译条数降序。`待译` 已排除「原文为空」与「去掉 printf 占位符后无实义字母」"
      "的条目（后者中文本来就该与英文逐字相同）。")
    A("")
    A("| # | 命名空间 | 模组 jar | 英文键 | 待译 |")
    A("|---|---|---|---|---|")
    for i, r in enumerate(zero, 1):
        A(f"| {i} | `{r['ns']}` | {r['jar']} | {r['en']} | {todo.get(r['ns'], 0)} |")
    A("")

    big = [r for r in zero if todo.get(r["ns"], 0) >= 100]
    A(f"其中 **{len(big)} 个模组待译 ≥100 条**，是性价比最高的批次：")
    A("")
    A("| 命名空间 | 模组 jar | 待译 |")
    A("|---|---|---|")
    for r in big:
        A(f"| `{r['ns']}` | {r['jar']} | {todo.get(r['ns'], 0)} |")
    A("")

    # ---------- 三、有中文但不完整 ----------
    A("## 三、有中文但不完整（补漏即可）")
    A("")
    A("这些模组**自带部分中文**，缺的是剩下的。补译时必须**以自带 `zh_cn` 为底**再叠加，"
      "否则会把已有中文整片顶掉。")
    A("")
    A("| 命名空间 | 模组 jar | 英文键 | 自带中文 | 缺键 | 伪翻译 | 待译 |")
    A("|---|---|---|---|---|---|---|")
    for r in partial[:40]:
        A(f"| `{r['ns']}` | {r['jar']} | {r['en']} | {r['self_zh']} | "
          f"{r['missing']} | {r['fake_zh']} | {todo.get(r['ns'], 0)} |")
    if len(partial) > 40:
        A(f"| … | 其余 {len(partial) - 40} 个见 `vendor-scan.json` | | | | | |")
    A("")

    # ---------- 四、AE 系专项 ----------
    A("## 四、AE 系专项体检（点名模组）")
    A("")
    by_ns = {r["ns"]: r for r in scan}
    A("| 命名空间 | 模组 jar | 英文键 | 自带中文 | 覆盖率 | 待译 | 状态 |")
    A("|---|---|---|---|---|---|---|")
    ae_total = 0
    for ns in AE_FAMILY:
        r = by_ns.get(ns)
        if not r:
            continue
        n = todo.get(ns, 0)
        ae_total += n
        cov = (r["self_zh"] / r["en"] * 100) if r["en"] else 0.0
        if r["en"] == 0:
            st = "无语言文件（文本硬编码）"
        elif n == 0:
            st = "✅ 已完整"
        elif r["self_zh"] == 0:
            st = "❌ 零中文"
        else:
            st = "⚠️ 不完整"
        A(f"| `{ns}` | {r['jar']} | {r['en']} | {r['self_zh']} | "
          f"{cov:.0f}% | {n} | {st} |")
    A("")
    A(f"**AE 系合计待译 {ae_total} 条。**")
    A("")
    A("> 说明：`ae2` 本体（appliedenergistics2）**自带 857 键中文、覆盖率 91%**，"
      "并不是「没汉化」——它缺的是 93 个键 + 9 条伪翻译。真正整包零中文的是"
      " `ae2additions` 等生态模组。所以「AE 没汉化」的体感，大多来自"
      "**AE 的附属模组**和**页签/物品名的分散缺口**，不是本体的锅。")
    A("")

    Path(out_path).write_text("\n".join(L) + "\n", encoding="utf-8")
    return "\n".join(L[:0])  # 内容已落盘


def main(argv: list[str] | None = None) -> int:
    import sys

    argv = argv if argv is not None else sys.argv[1:]
    root = Path(__file__).resolve().parents[2]
    scan = root / "build/cn/todo/vendor-scan.json"
    todo = root / "build/cn/todo/todo-vendor.tsv"
    out = root / "docs/cn-untranslated-mods.md"
    if not scan.exists():
        print(f"缺少扫描数据：{scan}\n请先跑一次构建（cli all）以生成 vendor-scan.json")
        return 1
    build(scan, todo, out)
    print(f"已生成 {out.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
