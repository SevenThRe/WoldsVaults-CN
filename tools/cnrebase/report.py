"""报告与待译清单导出。"""

from __future__ import annotations

import json
from pathlib import Path

from tools.cnrebase.build import RebaseResult
from tools.cnrebase.corpus import (
    CONFIG_HEADER,
    LANG_HEADER,
    LITERAL_HEADER,
    VENDOR_HEADER,
    escape,
)
from tools.cnrebase.delta import normalize_literal
from tools.cnrebase.inject import InjectResult
from tools.cnrebase.vendor import LANG_CHANNEL_NS

BAR = "\u2588"
EMPTY = "\u2591"

#: 待译清单表头注释。这些文件是给 AI/译员直接编辑的，得自带填写说明。
TODO_NOTE = (
    "# 只填最后一列 zh，留空 = 不译（保持英文）。前三列请勿改动。\n"
    "# 换行写作 \\n、制表符 \\t、占位符标记写作 \\x01，与译文无关的字符不要动。\n"
)

#: 第三方缺口台账表头（``vendor-residual.tsv``）。这是**派活用**的清单：
#: ``residual`` 是已扣掉模组自带中文与 CFPA 底之后的**真实残差**，
#: 按它降序排列，先打缺口最大的模组。列依次为：
#: 命名空间 \t 残差 \t 英文键 \t 自带中文 \t CFPA 底 \t 我方译料。
VENDOR_RESIDUAL_HEADER = "ns\tresidual\ten\tself_zh\tcfpa\tours\n"


def _pct(part: int, whole: int, width: int = 19) -> str:
    if whole <= 0:
        return f"{EMPTY * width} 0.0%"
    r = part / whole
    n = int(round(r * width))
    return f"{BAR * n}{EMPTY * (width - n)} {r * 100:.1f}%"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def export_todo(res: RebaseResult, out_dir: Path) -> dict[str, str]:
    """导出待译清单。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}

    if res.todo_lang:
        p = out_dir / "todo-lang.json"
        p.write_text(
            json.dumps(res.todo_lang, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written["lang"] = p.name
        # 同时给一份便于翻译的 TSV：命名空间 \t 键 \t 英文 \t 中文
        t = out_dir / "todo-lang.tsv"
        with t.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(TODO_NOTE)
            fh.write(LANG_HEADER)
            for ns in sorted(res.todo_lang):
                for k in sorted(res.todo_lang[ns]):
                    fh.write(f"{ns}\t{escape(k)}\t{escape(res.todo_lang[ns][k])}\t\n")
        written["lang_tsv"] = t.name

    if res.todo_literal:
        p = out_dir / "todo-literal.json"
        p.write_text(
            json.dumps(res.todo_literal, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written["literal"] = p.name
        t = out_dir / "todo-literal.tsv"
        # class 常量用 x01 标记插入点，母版 tsv 却一律用 %s。导出时统一成 %s：
        # 一是与母版写法一致，二是 %s 形态才能被 validate() 做占位符等量校验
        # （裸控制字符在正则里看不见，译丢了也不报错，直到运行时文本拼接错位）。
        # 归一化后还要去重——多个原始字面量可能归一到同一个 %s 形态。
        norm: dict[str, str] = {}
        for en, hint in res.todo_literal.items():
            norm.setdefault(normalize_literal(en), hint)
        with t.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(TODO_NOTE)
            fh.write(LITERAL_HEADER)
            for en in sorted(norm):
                fh.write(f"{escape(en)}\t\n")
        written["literal_tsv"] = t.name

    if res.todo_config:
        # 按 en 排序而不是按文件路径：同一句原文（如 8 个 palette 文件里
        # 重复出现的怪名）会排在一起，译员一眼能看出要复用同一译文。
        t = out_dir / "todo-config.tsv"
        with t.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(TODO_NOTE)
            fh.write(CONFIG_HEADER)
            for target, ptr, en in sorted(res.todo_config, key=lambda r: (r[2], r[0], r[1])):
                fh.write(f"{escape(target)}\t{ptr}\t{escape(en)}\t\n")
        written["config_tsv"] = t.name

    if res.todo_vendor:
        # 按 命名空间 → 键 排序，不按英文原文：同一模组的键聚在一起，
        # 译员能顺着 `block.* → item.* → itemGroup.*` 的脉络看上下文，
        # 术语也容易统一。
        t = out_dir / "todo-vendor.tsv"
        with t.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(TODO_NOTE)
            fh.write(VENDOR_HEADER)
            for ns, k, en in sorted(res.todo_vendor, key=lambda r: (r[0], r[1])):
                fh.write(f"{ns}\t{escape(k)}\t{escape(en)}\t\n")
        written["vendor_tsv"] = t.name

    if res.vendor_stats:
        p = out_dir / "vendor-scan.json"
        p.write_text(
            json.dumps(res.vendor_stats, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written["vendor_scan"] = p.name
        # 派活台账：按**真实残差**降序（已扣模组自带 zh 与 CFPA 底）。行顺序是
        # 这份文件的全部意义 —— 先打缺口最大的模组。与 todo-vendor.tsv 同源，
        # 门禁断言 sum(residual) == todo-vendor 条数 保证二者不脱节。
        t = out_dir / "vendor-residual.tsv"
        ranked = sorted(
            res.vendor_stats, key=lambda s: (-s.get("residual", 0), s["ns"])
        )
        with t.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(VENDOR_RESIDUAL_HEADER)
            for s in ranked:
                fh.write(
                    f"{s['ns']}\t{s.get('residual', 0)}\t{s['en']}\t"
                    f"{s['self_zh']}\t{s.get('cfpa', 0)}\t{s.get('ours', 0)}\n"
                )
        written["vendor_residual"] = t.name

    if res.term_table:
        # 术语反查表：翻新模组前先查这里，沿用包内既有译法，全包译名才统一。
        # 放在 todo/ 里而不是 work/ 里 —— 它是可复现的管线产物，不是临时脚本。
        p = out_dir / "term-table.json"
        p.write_text(
            json.dumps({"table": res.term_table, "srcs": res.term_src},
                       ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        written["term_table"] = p.name

    # 结构发生变化的 config 文件（人工复核重点）
    changed = [c for c in res.config_stats if c["structure_changed"]]
    if changed:
        p = out_dir / "review-config-structure.json"
        p.write_text(
            json.dumps(changed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        written["config_review"] = p.name

    return written


def build_markdown(
    res: RebaseResult,
    injects: list[InjectResult],
    meta: dict,
) -> str:
    L: list[str] = []
    L.append("# Wold's Vaults 汉化重基底报告")
    L.append("")
    L.append(
        f"- 整合包版本：`{meta.get('pack_version')}`　"
        f"汉化版本：`{meta.get('mod_version')}`"
    )
    L.append(f"- 生成时间：`{meta.get('generated_at')}`")
    L.append(f"- 模板：`{meta.get('template')}`")
    L.append("")

    # 一、语言键
    L.append("## 一、语言键对齐")
    L.append("")
    if res.lang_stats:
        rows = []
        for s in res.lang_stats:
            rows.append(
                [
                    f"`{s.get('label') or s['ns']}`",
                    s["upstream_en"],
                    s["upstream_zh"],
                    s["ours"],
                    s["missing"],
                    s["missing_fillable"],
                    f"**{s['missing_todo']}**",
                    s["stale"],
                ]
            )
        L.append(
            _table(
                ["命名空间", "上游 en_us", "上游自带 zh_cn", "我方 zh_cn",
                 "我方缺键", "上游可补", "需新译", "已失效键"],
                rows,
            )
        )
        tot_todo = sum(s["missing_todo"] for s in res.lang_stats)
        L.append("")
        L.append(f"语言键覆盖率：`{_pct(sum(s['ours'] for s in res.lang_stats), sum(s['upstream_en'] for s in res.lang_stats))}`")
        L.append(f"需新译语言键合计：**{tot_todo}**")
    else:
        L.append("_无数据_")
    L.append("")

    # 二、硬编码
    L.append("## 二、硬编码字面量")
    L.append("")
    ls = res.literal_stats
    if ls:
        L.append(
            _table(
                ["指标", "数量"],
                [
                    ["已有译文（tsv 对照表）", ls.get("known_pairs", 0)],
                    ["新版扫描到的原始字面量", ls.get("scanned_raw", 0)],
                    ["过滤后候选", ls.get("candidates", 0)],
                    ["已复用译文", ls.get("covered", 0)],
                    ["**需新译**", f"**{ls.get('todo', 0)}**"],
                ],
            )
        )
        L.append("")
        L.append(
            f"复用率：`{_pct(ls.get('covered', 0), ls.get('candidates', 0))}`"
        )
    else:
        L.append("_未执行硬编码扫描（未提供服务端包）_")
    L.append("")

    # 三、配置文本
    L.append("## 三、配置文本（结构感知合并）")
    L.append("")
    cs = res.config_stats
    if cs:
        filled = sum(c["filled"] for c in cs)
        kept = sum(c["kept_en"] for c in cs)
        kept_txt = sum(c.get("kept_en_text", 0) for c in cs)
        kept_oth = sum(c.get("kept_en_other", 0) for c in cs)
        chg = [c for c in cs if c["structure_changed"]]
        L.append(
            _table(
                ["指标", "数量", "说明"],
                [
                    ["合并处理的 config 文件", len(cs), "一律以新版结构为基底"],
                    ["回填的中文叶子", filled, "旧译文按同路径回填"],
                    ["保留英文的**疑似文本**叶子", kept_txt, "新增或未译的可见文本"],
                    ["保留英文的非文本叶子", kept_oth, "资源 ID / 数值 / 命名空间"],
                    ["结构发生变化的文件", len(chg), "建议人工复核"],
                ],
            )
        )
        L.append("")
        denom = filled + kept_txt
        L.append(f"**文本字段汉化率**：`{_pct(filled, denom)}`（{filled} / {denom}）")
        L.append(
            f"（分母若计入全部 {filled + kept} 个叶子则显示为 "
            f"`{_pct(filled, filled + kept)}`——因为其中 {kept_oth} 个是无需翻译的 ID）"
        )
        if chg:
            L.append("")
            L.append("**结构变化文件**")
            L.append("")
            for c in chg[:20]:
                L.append(f"- `{c['path']}`")
    else:
        L.append("_无 config 载荷_")
    L.append("")

    # 四、集合类
    L.append("## 四、手册与脚本资源")
    L.append("")
    if res.set_stats:
        L.append(
            _table(
                ["类别", "我方", "新版 en", "缺页", "多余"],
                [
                    [s["label"], s["ours"], s["base_en"], s["missing"], s["extra"]]
                    for s in res.set_stats
                ],
            )
        )
    else:
        L.append("_无数据_")
    L.append("")

    # 四·五、第三方模组语言
    vs_all = res.vendor_stats
    vs = [s for s in vs_all if s["ns"] not in LANG_CHANNEL_NS]
    if vs:
        L.append("## 四·五、第三方模组语言")
        L.append("")
        zero = [s for s in vs if s["self_zh"] == 0]
        fake = [s for s in vs if s["fake_zh"]]
        tot_en = sum(s["en"] for s in vs)
        tot_self = sum(s["self_zh"] for s in vs)
        tot_cfpa = sum(s.get("cfpa", 0) for s in vs)
        tot_ours = sum(s.get("ours", 0) for s in vs)
        L.append(
            _table(
                ["指标", "数量", "说明"],
                [
                    ["扫描到的第三方命名空间", len(vs),
                     f"另有 {len(vs_all) - len(vs)} 个归语言表通道"],
                    ["**整包零中文**", len(zero), "这些模组从未被汉化过"],
                    ["自带 zh_cn 但值为英文", len(fake),
                     "键在、值是英文原文，界面仍显示英文"],
                    ["英文键总数", tot_en, ""],
                    ["模组自带中文键", tot_self, ""],
                    ["CFPA 底覆盖键", tot_cfpa, "CFPA 资源包提供的、本包模组用到的键"],
                    ["我方译料覆盖键", tot_ours, "`translations/cn-rebase` vendor 层"],
                    ["**待译键（真实残差）**", f"**{len(res.todo_vendor)}**",
                     "已扣模组自带 zh 与 CFPA 底 → `todo-vendor.tsv`"],
                    ["本轮写入产物的语言文件", res.vendor_files, ""],
                ],
            )
        )
        L.append("")
        if fake:
            L.append("**「伪翻译」命名空间**（有中文文件却仍是英文，最易误判为工具失效）")
            L.append("")
            for s in sorted(fake, key=lambda x: -x["fake_zh"])[:10]:
                L.append(f"- `{s['ns']}`：{s['fake_zh']} 个键的值等于英文原文")
            L.append("")
        # 按**真实残差**（已扣模组自带 zh 与 CFPA 底）降序，而不是旧的
        # 「模组英文键 − 自带 zh」—— 后者会把 CFPA 已整包覆盖的模组（如 chipped）
        # 排在榜首，把派活引向其实已完成的目标。
        top = sorted(vs, key=lambda s: (-s.get("residual", 0), s["ns"]))[:20]
        L.append(
            "**缺口最大的 20 个命名空间**"
            "（残差 = 已扣掉模组自带中文与 CFPA 底之后仍需翻译的键；"
            f"CFPA 底在本包共覆盖 {tot_cfpa} 条，我方译料 {tot_ours} 条）"
        )
        L.append("")
        L.append(
            _table(
                ["命名空间", "模组 jar", "英文键", "自带中文", "CFPA 底", "我方", "残差"],
                [
                    [f"`{s['ns']}`", s["jar"][:34], s["en"], s["self_zh"],
                     s.get("cfpa", 0), s.get("ours", 0), s.get("residual", 0)]
                    for s in top
                ],
            )
        )
        L.append("")
    elif vs_all:
        L.append("## 四·五、第三方模组语言")
        L.append("")
        L.append("_扫描到命名空间，但全部归语言表通道管理_")
        L.append("")

    # 五、产物
    L.append("## 五、构建产物")
    L.append("")
    rows = []
    if res.jar_path:
        rows.append(["汉化模组 jar", f"`{res.jar_path.name}`", f"{res.jar_path.stat().st_size / 1048576:.1f} MB"])
    for r in injects:
        if r.path and r.path.is_file():
            rows.append(
                [
                    "客户端拖拽包" if r.kind == "client" else "服务端包",
                    f"`{r.path.name}`",
                    f"{r.path.stat().st_size / 1048576:.1f} MB",
                ]
            )
    L.append(_table(["产物", "文件名", "大小"], rows))
    L.append("")

    if any(r.removed for r in injects):
        L.append("**服务端重复 modid 去重**")
        L.append("")
        for r in injects:
            for d in r.removed:
                L.append(f"- 剔除 `{d.rsplit('/', 1)[-1]}`")
        L.append("")

    if res.patch_stats:
        L.append("**字节码补丁：静默母版遗留的署名提示**")
        L.append("")
        for rel, info in res.patch_stats.items():
            short = rel.rsplit("/", 1)[-1]
            if info.get("override"):
                # class_overrides/ 的成品类覆盖（如 EMBEDDED_TERMS 扩容）
                L.append(
                    f"- `{short}`：class 覆盖（{info.get('bytes', 0)} B，"
                    f"{'已写入' if info.get('written') else '无变化'}）"
                )
                continue
            ms = "、".join(f"`{m}`" for m in info.get("methods", []))
            L.append(
                f"- `{short}`：掏空 {ms or '（未匹配到方法，见警告）'}，"
                f"抹除展示常量 {info.get('constants', 0)} 条"
            )
        L.append("")

    # 六、待办
    L.append("## 六、待人工处理")
    L.append("")
    tl = sum(len(v) for v in res.todo_lang.values())
    L.append(
        _table(
            ["项目", "数量", "清单文件"],
            [
                ["待译语言键", tl, "`todo-lang.tsv`"],
                ["待译硬编码字面量", len(res.todo_literal),
                 ("`todo-literal.tsv`（另有 %d 条含换行无法承载）"
                  % res.literal_unrepresentable)
                 if res.literal_unrepresentable else "`todo-literal.tsv`"],
                ["待译配置文本", len(res.todo_config), "`todo-config.tsv`"],
                ["待译第三方模组语言键", len(res.todo_vendor), "`todo-vendor.tsv`"],
                ["结构变化 config", sum(1 for c in res.config_stats if c["structure_changed"]), "`review-config-structure.json`"],
            ],
        )
    )
    L.append("")
    total_todo = tl + len(res.todo_literal) + len(res.todo_config) + len(res.todo_vendor)
    L.append(
        f"四份清单的 zh 列填好后，用 "
        f"`python -m tools.cnrebase.cli apply-todo` 回填译料层，"
        f"再复跑一次构建即可让它们从本表消失（当前合计 **{total_todo}** 条）。"
    )
    # 含换行/制表符的字面量永远进不了行式对照表。不说明的话，那个数字
    # 永远清不到 0，维护者会以为是工具坏了。
    if res.literal_unrepresentable:
        L.append(
            f"其中 **{res.literal_unrepresentable}** 条硬编码字面量含换行/制表符，"
            f"行式对照表（`literal_zh_cn.tsv`）结构上无法承载，不参与上述计数；"
            f"如需汉化只能另走语言文件或字节码补丁。"
        )
        L.append("")
    L.append("")

    ca = res.corpus_applied
    if any(ca.values()):
        L.append("**本轮从译料层叠加的译文**")
        L.append("")
        L.append(
            _table(
                ["通道", "条目"],
                [
                    ["语言键", ca.get("lang", 0)],
                    ["硬编码字面量", ca.get("literal", 0)],
                    ["配置文本", ca.get("config", 0)],
                    ["第三方模组语言", ca.get("vendor", 0)],
                ],
            )
        )
        L.append("")

    if res.warnings:
        L.append("## 七、警告")
        L.append("")
        for w in res.warnings:
            L.append(f"- {w}")
        L.append("")

    return "\n".join(L) + "\n"


def write_report(
    res: RebaseResult, injects: list[InjectResult], out_dir: Path, meta: dict
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    md = build_markdown(res, injects, meta)
    p = out_dir / "CN-REPORT.md"
    p.write_text(md, encoding="utf-8", newline="\n")
    written["report"] = p.name

    summary = {
        "meta": meta,
        "rebase": res.summary(),
        "injects": [r.summary() for r in injects],
    }
    s = out_dir / "cn-build-summary.json"
    s.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    written["summary"] = s.name

    written.update(export_todo(res, out_dir / "todo"))
    return written
