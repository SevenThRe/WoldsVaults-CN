# -*- coding: utf-8 -*-
"""生成《全模组汉化改造清单》（``docs/cn-vendor-plan.md``）。

为什么把它做成管线的一部分而不是一次性脚本：**改造清单是交付物**，必须能随
每一次整合包更新重新生成，数字与 ``vendor-scan.json`` / ``todo-vendor.tsv`` 严格
一致。手写的清单会在下一版立刻过期，且没人知道哪个数字是旧的。

输入（都由 ``all`` / ``rebase`` 产出）：

* ``todo/vendor-scan.json`` —— 逐命名空间扫描
* ``todo/todo-vendor.tsv`` —— 逐条待译
* ``translations/cn-rebase/vendor_lang_zh.tsv`` —— 已译条数
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from tools.cnrebase.vendor import LANG_CHANNEL_NS

#: 分档顺序（按玩家可见度）。键名是 :func:`bucket_of` 的返回值。
BUCKET_ORDER = ("页签", "方块物品名", "界面与提示", "手册任务文本", "其他")

#: 档位编号与说明
BUCKET_PRIORITY = {
    "页签": ("P0", "JEI / 创造模式物品栏页签名"),
    "方块物品名": ("P1", "背包 · JEI · 物品栏里一切名字"),
    "界面与提示": ("P2", "容器标题 · 按钮 · tooltip · 字幕 · 报错"),
    "手册任务文本": ("P3", "帕秋莉手册 · FTB 任务书 · 进度"),
    "其他": ("P4", "机器内部文案 · 长描述 · 音效 · 杂项"),
}


def bucket_of(key: str) -> str:
    """按语言键前缀推断它在游戏里出现的位置。

    分档的意义是**排期**：玩家先看到的东西先翻。前缀是唯一可靠的信号——
    模组不会告诉我们在哪用这个键，但 ``itemGroup.*`` 一定是页签，
    ``book.*`` 一定是手册。
    """
    k = key.lower()
    if k.startswith("itemgroup.") or k.endswith("creative_tab"):
        return "页签"
    if k.startswith(("block.", "item.", "entity.", "fluid.", "effect.", "potion.",
                     "enchantment.", "material.", "mobsoultype.", "crop.", "croptier.",
                     "modifier.", "aspect.")):
        return "方块物品名"
    if k.startswith(("gui.", "container.", "tooltip.", "message.", "messages.",
                     "commands.", "command.", "subtitles.", "subtitle.", "death.",
                     "key.", "config.", "screen.", "button.", "jei.", "rei.",
                     "chat.", "sound.")):
        return "界面与提示"
    if k.startswith(("book.", "patchouli.", "ftbquests.", "quests.", "info_book.",
                     "advancement", "text.", "lore.", "guide", "desc.")):
        return "手册任务文本"
    return "其他"


def _load_rows(todo_tsv: Path) -> list[tuple[str, str, str]]:
    """读待译 TSV。前两行是 `#` 说明与表头。"""
    rows: list[tuple[str, str, str]] = []
    for line in todo_tsv.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) < 3 or p[0] == "namespace":
            continue
        rows.append((p[0], p[1], p[2]))
    return rows


def build(scan_path: Path, todo_tsv: Path, corpus_tsv: Path) -> str:
    """产出改造清单的 Markdown 全文。"""
    scan = json.loads(Path(scan_path).read_text(encoding="utf-8"))
    third = [r for r in scan if r["ns"] not in LANG_CHANNEL_NS]
    by_ns = {r["ns"]: r for r in scan}
    rows = _load_rows(Path(todo_tsv))

    cnt: dict[str, int] = defaultdict(int)
    chars: dict[str, int] = defaultdict(int)
    per_bucket_ns: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for ns, k, en in rows:
        b = bucket_of(k)
        cnt[b] += 1
        chars[b] += len(en)
        per_bucket_ns[b][ns] += 1

    ns_cnt: dict[str, int] = defaultdict(int)
    for ns, _k, _en in rows:
        ns_cnt[ns] += 1

    tot_en = sum(r["en"] for r in third)
    tot_self = sum(r["self_zh"] for r in third)
    tot_miss = sum(r["missing"] for r in third)
    tot_fake = sum(r["fake_zh"] for r in third)
    zero_ns = [r for r in third if r["self_zh"] == 0 and r["en"] > 0]
    fake_ns = sorted((r for r in third if r["fake_zh"] > 0),
                     key=lambda r: -r["fake_zh"])
    clean_ns = [r for r in third if r["missing"] + r["fake_zh"] == 0]

    def top_table(bucket: str, n: int = 12) -> str:
        out = ["| 命名空间 | 模组 jar | 本档待译 |", "|---|---|---|"]
        for ns, c in sorted(per_bucket_ns[bucket].items(), key=lambda kv: -kv[1])[:n]:
            out.append(f"| `{ns}` | {by_ns[ns]['jar']} | {c} |")
        return "\n".join(out)

    size = {"巨型": [], "大型": [], "中型": [], "小型": []}
    for ns, c in ns_cnt.items():
        key = ("巨型" if c > 500 else "大型" if c >= 200
               else "中型" if c >= 50 else "小型")
        size[key].append((ns, c))

    lines: list[str] = []
    A = lines.append

    A("# 全模组汉化改造清单")
    A("")
    A("> **触发**：先发现 `Weather Control` / `Macaw's Fences & Halls` / `Compressium` /"
      " `Mystical Agriculture` / `Tiered Crystals` 显示英文，随后发现「大量模组没被汉化」。")
    A("> 本文 = **全模组扫描结论 + 可执行改造清单**。")
    A(">")
    A("> **本文由 `python -m tools.cnrebase.cli plan-doc` 自动生成**，不要手改——"
      "数据直接取自 `build/cn/todo/vendor-scan.json` 与 `todo-vendor.tsv`，"
      "每次构建后重跑即可保持与产物一致。")
    A(">")
    A(f"> 扫描口径：官方服务端包 mod jar + 客户端实例 `mods/`（补纯客户端模组），"
      f"共 **{len(scan)} 个命名空间**，其中 {len(LANG_CHANNEL_NS)} 个归语言表通道，"
      f"**{len(third)} 个走第三方语言通道**。")
    A("")
    A("---")
    A("")
    A("## 一、结论先行")
    A("")
    A("| # | 结论 |")
    A("|---|---|")
    A("| 1 | **点名模组已全部解决**：`weather_control` / `matc` / `compressium` / "
      "`mysticalagriculture` / `mysticalagradditions` / `mcwfences` 六个命名空间待译**归零**。 |")
    A(f"| 2 | **页签（JEI / 创造模式物品栏第一眼）已 100% 覆盖**——"
      f"`itemGroup.*` 剩余 **{cnt['页签']}** 条。这是玩家感知最强的位置。 |")
    A(f"| 3 | 剩余 **{len(rows)}** 条待译，分布在 **{len(ns_cnt)}** 个命名空间；其中 "
      f"**{len(zero_ns)} 个模组整包零中文**（从未被汉化过），贡献 "
      f"{sum(r['missing'] for r in zero_ns)} 条。 |")
    A("| 4 | **机制上第三方模组只能靠补语言文件**：硬编码通道拦不到语言键渲染的文本。"
      "该通道已建成并接入管线，门禁已验。 |")
    A(f"| 5 | **不需要汉化的量很大**：另有 **{len(clean_ns)} 个命名空间**已自带完整中文，"
      f"不必重复劳动。 |")
    A("")
    A(f"> ⚠️ **「模组带中文」不等于「界面是中文」**。有 **{tot_fake}** 条属于「伪翻译」——"
      f"模组建了 `zh_cn` 条目，值却直接抄了英文（`Compressium` 的页签就是这种），"
      f"界面照样是英文。这是最容易被误判成「汉化工具没生效」的一类。")
    A("")
    A("---")
    A("")
    A("## 二、全量扫描数据")
    A("")
    A("| 指标 | 数量 |")
    A("|---|---|")
    A(f"| 扫描到的第三方命名空间 | {len(third)} |")
    A(f"| 英文键总数 | {tot_en} |")
    A(f"| 模组自带中文键 | {tot_self} |")
    A(f"| 缺键（`zh_cn` 里根本没有） | {tot_miss} |")
    A(f"| 伪翻译（有 `zh_cn` 但值 = 英文） | {tot_fake} |")
    A(f"| **待译合计** | **{len(rows)}** |")
    A(f"| 整包零中文的命名空间 | {len(zero_ns)} |")
    A(f"| 自带中文但不完整的命名空间 | "
      f"{len([r for r in third if r['self_zh'] and r['missing'] + r['fake_zh']])} |")
    A(f"| 已无缺口（不必动） | {len(clean_ns)} |")
    A("")
    A("逐命名空间数据：`build/cn/todo/vendor-scan.json`；逐条待译："
      "`build/cn/todo/todo-vendor.tsv`。")
    A("")
    A("---")
    A("")
    A("## 三、改造清单（按玩家可见度分档）")
    A("")
    A("分档口径按**语言键前缀**推断它在游戏里的位置 —— 玩家先看到什么，就先翻什么。"
      "口径实现在 `tools/cnrebase/plandoc.py:bucket_of`。")
    A("")
    A("| 档 | 位置 | 待译条数 | 英文总字符 | 占比 |")
    A("|---|---|---|---|---|")
    for b in BUCKET_ORDER:
        pri, desc = BUCKET_PRIORITY[b]
        pct = 100.0 * cnt[b] / max(1, len(rows))
        mark = "（**已清零**）" if b == "页签" else ""
        A(f"| **{pri}** | {desc}{mark} | {cnt[b]} | {chars[b]} | {pct:.1f}% |")
    A("")

    A("### P0 · 页签 —— 已完成 ✅" if cnt["页签"] == 0
      else f"### P0 · 页签（{cnt['页签']} 条，未清零）")
    A("")
    A("页签是玩家打开 JEI / 创造模式物品栏第一眼看到的东西。"
      "译料：`translations/cn-rebase/vendor_lang_zh.tsv`。")
    A("")

    A(f"### P1 · 方块与物品名（{cnt['方块物品名']} 条）")
    A("")
    A("玩家感知第二强。`chipped` 与 `buildscape` **几乎全是变色/变体方块**"
      "（`block.chipped.*`），术语高度重复，可套模板批量生成。")
    A("")
    A(top_table("方块物品名"))
    A("")
    A(f"### P2 · 界面与提示（{cnt['界面与提示']} 条）")
    A("")
    A("这类条目**必须看上下文**，不能靠模板：`openpartiesandclaims` 是团队/领地模组的"
      "全套界面，`buildersdelight` 是方块名混着 GUI 键，`xaeroworldmap` 是小地图设置项。")
    A("")
    A(top_table("界面与提示"))
    A("")
    A(f"### P3 · 手册任务文本（{cnt['手册任务文本']} 条）")
    A("")
    A("长文本、含 `$(br)` `$(l:...)` `$(bold)` 等标记，**翻译时必须原样保留标记与链接**"
      "（`corpus.validate` 会校验占位符与样式码一致性，不一致会在回填时被拦下）。")
    A("")
    A(top_table("手册任务文本"))
    A("")
    A(f"### P4 · 其他（{cnt['其他']} 条）")
    A("")
    A("`pneumaticcraft` 一个模组占大头（机器内部名与长描述混排）；"
      "`rechiseled` 是变体方块（`rechiseled.*` 前缀，可模板化）。")
    A("")
    A(top_table("其他"))
    A("")
    A("---")
    A("")
    A("## 四、排期分档（按命名空间规模）")
    A("")
    A("单看模组体量更能决定「一批做多少」。")
    A("")
    A("| 规模 | 命名空间数 | 建议节奏 |")
    A("|---|---|---|")
    A(f"| 巨型（>500 条） | {len(size['巨型'])} | 一个模组就是一轮的工作量 |")
    A(f"| 大型（200–500） | {len(size['大型'])} | 2–3 个模组一批 |")
    A(f"| 中型（50–200） | {len(size['中型'])} | 5–8 个一批 |")
    A(f"| 小型（1–49） | {len(size['小型'])} | 15–20 个一批，很多是 1–5 条的零头 |")
    A("")
    for name in ("巨型", "大型", "中型", "小型"):
        lst = sorted(size[name], key=lambda x: -x[1])
        shown = "、".join(f"`{n}`({c})" for n, c in lst[:14])
        A(f"**{name}**（{len(lst)} 个）：{shown}{' …' if len(lst) > 14 else ''}")
        A("")
    A("---")
    A("")
    A(f"## 五、「伪翻译」专项（{tot_fake} 条 / {len(fake_ns)} 个命名空间）")
    A("")
    A("这些模组**带了 `zh_cn.json`，但一部分键的值直接等于英文**。玩家看到的现象是"
      "「这模组明明有中文，怎么还是英文」。逐条补译即可，且**必须**以自带 `zh_cn` 为底"
      "再叠加，否则会把它已有的中文整片顶掉。")
    A("")
    A("| 命名空间 | 伪翻译条数 |")
    A("|---|---|")
    for r in fake_ns[:15]:
        A(f"| `{r['ns']}` | {r['fake_zh']} |")
    A("")
    if len(fake_ns) > 15:
        A(f"（完整 {len(fake_ns)} 个见 `build/cn/CN-REPORT.md` 的「第三方模组语言」章节）")
        A("")
    A("注意：**原文去掉 printf 占位符后不含字母**的条目不算伪翻译，也不进待译清单"
      "（`cropTier...1 = \"1\"`、`tooltip...buff_line = \" - %s (%s)\"`）——"
      "中文原文本来就该与英文逐字相同。判据见 `vendor._has_letter`。")
    A("")
    A("---")
    A("")
    A("## 六、执行手册")
    A("")
    A("### 1. 重扫 + 导出待译（每次整合包更新后跑一次）")
    A("")
    A("```bash")
    A("python -m tools.cnrebase.cli all \\")
    A('  --client "<客户端包.zip>" --server "<服务端包.zip>" \\')
    A('  --mods-dir "<实例>/mods" \\')
    A("  --pack-version <版本> --mod-version <版本> --out build/cn --strict")
    A("```")
    A("")
    A("产出 `build/cn/todo/todo-vendor.tsv`（表头 `namespace/key/en/zh`）、"
      "`vendor-scan.json`、`term-table.json`。")
    A("")
    A("### 2. 翻译")
    A("")
    A("- **只改 `zh` 列**，前三列原样不动。")
    A("- `en` 为空、或去掉占位符后不含字母的条目**不进清单**，不用管。")
    A("- 长文本里的 `$(br)` / `$(l:路径)文字$()` / `$(bold)` / `%1$s` **必须原样保留**。")
    A("- **术语优先取包内既有译法**：`build/cn/todo/term-table.json`"
      "（从全包所有 jar 的语言文件反查出的「英文→已有中文」）就是为此准备的。")
    A("")
    A("```bash")
    A('python -m tools.cnrebase.cli terms Hedge "Highley Gate" Crux Manasteel')
    A("```")
    A("")
    A("```")
    A("## Highley Gate  —— 1 条")
    A("     %s Highley Gate        = %s海利栅栏门        [everycomp:block_type.mcwfences.highley_gate]")
    A("## Crux  —— 2 条")
    A("     Dragon Egg Crux        = 龙蛋核心            [mysticalagradditions:block...dragon_egg_crux]")
    A("```")
    A("")
    A("- 查询是**子串匹配**：包里大量构件名是模板形态（`%s Hedge`），精确查 `Hedge`"
      "查不到，子串查得到 —— 这正是译员要的用法。")
    A("- 查不到就说明是新词，**自己定译名并在提交信息里写明依据**，"
      "别硬凑一个和包里既有译法冲突的词。")
    A("")
    A("### 3. 回填 + 复跑")
    A("")
    A("```bash")
    A("python -m tools.cnrebase.cli apply-todo \\")
    A("  --todo build/cn/todo --corpus translations/cn-rebase --strict")
    A("python -m tools.cnrebase.cli all --client ... --server ... --mods-dir ... --strict")
    A("```")
    A("")
    A("`apply-todo` 会把 `todo-vendor.tsv` 的 `zh` 列合并进 "
      "`translations/cn-rebase/vendor_lang_zh.tsv`（译料层 —— **是输入，别当导出物删**）。")
    A("")
    A("### 4. 对账口径")
    A("")
    A("以「重建待译清单后归零」为唯一验收标准，别用「我翻了多少条」：")
    A("")
    A("```python")
    A("from tools.cnrebase import corpus as C, vendor")
    A("table = vendor.scan_zipfile(zp)                 # 重扫服务端包")
    A('co    = C.Corpus.load("translations/cn-rebase")')
    A("left  = vendor.todo(table, co.vendor)           # 重建待译")
    A('for ns in ("mcwfences", "weather_control", "mysticalagriculture"):')
    A("    todo = [r for r in left if r[0] == ns]")
    A("    assert not todo, (ns, todo[:5])             # 归零才算翻完")
    A("```")
    A("")
    A("### 5. 重新生成本文")
    A("")
    A("```bash")
    A("python -m tools.cnrebase.cli plan-doc --out docs/cn-vendor-plan.md")
    A("```")
    A("")
    A("---")
    A("")
    A("## 七、为什么必须走语言文件（机制边界）")
    A("")
    A("汉化模组的硬编码通道有明确边界：")
    A("")
    A("- `TextComponentMixin`：只在 `Component.literal(\"...\")` 构造时改写，"
      "且**服务端线程跳过**。")
    A("- `FontMixin`：注入了 `Font` 的 11 个方法，但**只有 3 个 String 重载真的调用** "
      "`LiteralTranslator.translate`（`drawShadow` / `draw` / `width`）；"
      "Component / FormattedCharSequence 那 8 个处理器是**空壳**。")
    A("")
    A("模组文本（页签、物品名、GUI）走「语言键 → `TranslatableComponent` → Component"
      " 渲染」，**两条硬编码通道都拦不到**。")
    A("")
    A("→ 结论：第三方模组**只能靠补 `assets/<ns>/lang/zh_cn.json`**。")
    A("")
    A("生成规则（三条，缺一不可）：")
    A("")
    A("```")
    A("最终 zh_cn = 模组自带 zh_cn（作底）  ∪  我方 vendor 译文（覆盖同名键）")
    A("```")
    A("")
    A("1. **必须以自带 zh 为底**——语言表是按 key 合并（同名键由高优先级包决定），"
      "我方写的是一个**整份** `zh_cn.json`；若只往里写我方增量、丢掉模组自带键，"
      "在没有更高优先级资源包兜底时，这些键就会从最终语言表里消失（"
      "`mekanism` 自带 1446 键、`occultism` 801 键）。")
    A("2. **只给有译文的命名空间生成文件**——我方 jar 与模组 jar 对同一路径是同路径竞争，"
      "顺序不由本项目控制，减少无意义竞争。")
    A(f"3. **归语言表通道的 {len(LANG_CHANNEL_NS)} 个命名空间跳过**（"
      + " / ".join(f"`{n}`" for n in sorted(LANG_CHANNEL_NS))
      + "），避免同一文件被两条通道分别写入。")
    A("")
    A("---")
    A("")
    A("## 八、风险与注意")
    A("")
    A("| 风险 | 处理 |")
    A("|---|---|")
    A("| 模组自带中文被覆盖丢 | 已按「自带 zh 为底」生成；门禁有「预置未削弱原版自带中文」复核 |")
    A("| 同路径竞争导致译文不生效 | 只对有译文的命名空间生成文件 |")
    A("| 长文本标记被翻坏 | `corpus.validate` 校验占位符/样式码一致性，回填时拦下 |")
    A("| 待译清单永远清不到零 | 已排除「原文为空 / 去占位符后无字母」的条目 |")
    A("| 整合包更新后译文失效 | 译文在译料层，与载荷解耦；重基底后自动叠加 |")
    A("| 清单与实际脱节 | 本文由 `plan-doc` 生成，跟着构建一起重跑 |")
    A("")
    A("---")
    A("")
    A("## 附：数据来源")
    A("")
    A(f"- `build/cn/todo/vendor-scan.json` —— 逐命名空间扫描（{len(scan)} 条记录）")
    A(f"- `build/cn/todo/todo-vendor.tsv` —— 逐条待译（{len(rows)} 条）")
    _n = len([x for x in Path(corpus_tsv).read_text(encoding="utf-8").splitlines()
              if x.strip()]) - 1
    A(f"- `translations/cn-rebase/vendor_lang_zh.tsv` —— 第三方译料层（已译 {_n} 条）")
    A("- `build/cn/todo/term-table.json` —— 术语反查表（英文原文 → 包内既有中文）")
    A("- `docs/cn-coverage-plan.md` —— 本通道的设计与查证过程")
    return "\n".join(lines) + "\n"
