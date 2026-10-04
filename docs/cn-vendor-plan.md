# 全模组汉化改造清单

> **触发**：先发现 `Weather Control` / `Macaw's Fences & Halls` / `Compressium` / `Mystical Agriculture` / `Tiered Crystals` 显示英文，随后发现「大量模组没被汉化」。
> 本文 = **全模组扫描结论 + 可执行改造清单**。
>
> **本文由 `python -m tools.cnrebase.cli plan-doc` 自动生成**，不要手改——数据直接取自 `build/cn/todo/vendor-scan.json` 与 `todo-vendor.tsv`，每次构建后重跑即可保持与产物一致。
>
> 扫描口径：官方服务端包 mod jar + 客户端实例 `mods/`（补纯客户端模组），共 **355 个命名空间**，其中 5 个归语言表通道，**350 个走第三方语言通道**。

---

## 一、结论先行

| # | 结论 |
|---|---|
| 1 | **点名模组已全部解决**：`weather_control` / `matc` / `compressium` / `mysticalagriculture` / `mysticalagradditions` / `mcwfences` 六个命名空间待译**归零**。 |
| 2 | **页签（JEI / 创造模式物品栏第一眼）已 100% 覆盖**——`itemGroup.*` 剩余 **0** 条。这是玩家感知最强的位置。 |
| 3 | 剩余 **36457** 条待译，分布在 **303** 个命名空间；其中 **188 个模组整包零中文**（从未被汉化过），贡献 30405 条。 |
| 4 | **机制上第三方模组只能靠补语言文件**：硬编码通道拦不到语言键渲染的文本。该通道已建成并接入管线，门禁已验。 |
| 5 | **不需要汉化的量很大**：另有 **38 个命名空间**已自带完整中文，不必重复劳动。 |

> ⚠️ **「模组带中文」不等于「界面是中文」**。有 **1434** 条属于「伪翻译」——模组建了 `zh_cn` 条目，值却直接抄了英文（`Compressium` 的页签就是这种），界面照样是英文。这是最容易被误判成「汉化工具没生效」的一类。

---

## 二、全量扫描数据

| 指标 | 数量 |
|---|---|
| 扫描到的第三方命名空间 | 350 |
| 英文键总数 | 71121 |
| 模组自带中文键 | 41692 |
| 缺键（`zh_cn` 里根本没有） | 35622 |
| 伪翻译（有 `zh_cn` 但值 = 英文） | 1434 |
| **待译合计** | **36457** |
| 整包零中文的命名空间 | 188 |
| 自带中文但不完整的命名空间 | 124 |
| 已无缺口（不必动） | 38 |

逐命名空间数据：`build/cn/todo/vendor-scan.json`；逐条待译：`build/cn/todo/todo-vendor.tsv`。

---

## 三、改造清单（按玩家可见度分档）

分档口径按**语言键前缀**推断它在游戏里的位置 —— 玩家先看到什么，就先翻什么。口径实现在 `tools/cnrebase/plandoc.py:bucket_of`。

| 档 | 位置 | 待译条数 | 英文总字符 | 占比 |
|---|---|---|---|---|
| **P0** | JEI / 创造模式物品栏页签名（**已清零**） | 0 | 0 | 0.0% |
| **P1** | 背包 · JEI · 物品栏里一切名字 | 21548 | 457329 | 59.1% |
| **P2** | 容器标题 · 按钮 · tooltip · 字幕 · 报错 | 4599 | 157172 | 12.6% |
| **P3** | 帕秋莉手册 · FTB 任务书 · 进度 | 1912 | 138363 | 5.2% |
| **P4** | 机器内部文案 · 长描述 · 音效 · 杂项 | 8398 | 408766 | 23.0% |

### P0 · 页签 —— 已完成 ✅

页签是玩家打开 JEI / 创造模式物品栏第一眼看到的东西。译料：`translations/cn-rebase/vendor_lang_zh.tsv`。

### P1 · 方块与物品名（21548 条）

玩家感知第二强。`chipped` 与 `buildscape` **几乎全是变色/变体方块**（`block.chipped.*`），术语高度重复，可套模板批量生成。

| 命名空间 | 模组 jar | 本档待译 |
|---|---|---|
| `chipped` | chipped-forge-1.18.2-2.0.1.jar | 7460 |
| `buildscape` | buildscape-3.0.9-VH.jar | 3895 |
| `luphieclutteredmod` | cluttered-2.1-1.18.2.jar | 1165 |
| `buildersdelight` | BuildersDelight-1.18.2-v.1.0.jar | 740 |
| `createdeco` | createdeco-1.3.3-1.18.2.jar | 622 |
| `davebuildingmod` | dbExtended-1.18.2-6.0.1.jar | 620 |
| `dyenamicsandfriends` | dyenamicsandfriends-1.18.2-0.1.5.4.jar | 569 |
| `mcwfurnitures` | mcw-furniture-3.2.2-mc1.18.2forge.jar | 488 |
| `pneumaticcraft` | pneumaticcraft-repressurized-1.18.2-3.6.4-45.jar | 356 |
| `neoncraft2` | neoncraft2-2.2.jar | 322 |
| `lightmanscurrency` | lightmanscurrency-1.18.2-2.1.2.5e.jar | 291 |
| `auxiliaryblocks` | auxiliaryblocks-1.18.2-0.4.6.jar | 285 |

### P2 · 界面与提示（4599 条）

这类条目**必须看上下文**，不能靠模板：`openpartiesandclaims` 是团队/领地模组的全套界面，`buildersdelight` 是方块名混着 GUI 键，`xaeroworldmap` 是小地图设置项。

| 命名空间 | 模组 jar | 本档待译 |
|---|---|---|
| `openpartiesandclaims` | open-parties-and-claims-forge-1.18.2-0.30.3.jar | 915 |
| `buildersdelight` | BuildersDelight-1.18.2-v.1.0.jar | 743 |
| `xaeroworldmap` | XaerosWorldMap_1.39.12_Forge_1.18.2.jar | 265 |
| `dungeons_mobs` | dungeons_mobs-1.18.2-3.0.2-beta.jar | 198 |
| `pneumaticcraft` | pneumaticcraft-repressurized-1.18.2-3.6.4-45.jar | 181 |
| `rftoolsutility` | rftoolsutility-1.18-4.0.24.jar | 170 |
| `lightmanscurrency` | lightmanscurrency-1.18.2-2.1.2.5e.jar | 147 |
| `integratedterminals` | IntegratedTerminals-1.18.2-1.4.10.jar | 98 |
| `ironfurnaces` | ironfurnaces-1.18.2-3.3.3.jar | 84 |
| `xaerominimap` | Xaeros_Minimap_25.2.10_Forge_1.18.2.jar | 84 |
| `pipez` | pipez-1.18.2-1.1.5.jar | 70 |
| `ae2` | appliedenergistics2-forge-11.7.6.jar | 65 |

### P3 · 手册任务文本（1912 条）

长文本、含 `$(br)` `$(l:...)` `$(bold)` 等标记，**翻译时必须原样保留标记与链接**（`corpus.validate` 会校验占位符与样式码一致性，不一致会在回填时被拦下）。

| 命名空间 | 模组 jar | 本档待译 |
|---|---|---|
| `occultism` | occultism-1.18.2-1.84.0.jar | 635 |
| `ftbquests` | ftb-quests-forge-1802.3.15-build.298.jar | 252 |
| `grimoireofgaia` | GrimoireOfGaia4-1.18.2-2.0.0-beta.13.jar | 91 |
| `modonomicon` | modonomicon-1.18.2-1.33.1.jar | 86 |
| `betterstrongholds` | YungsBetterStrongholds-1.18.2-Forge-2.1.1.jar | 78 |
| `betterdungeons` | YungsBetterDungeons-1.18.2-Forge-2.1.0.jar | 75 |
| `integratedcrafting` | IntegratedCrafting-1.18.2-1.1.6.jar | 70 |
| `integrateddynamics` | IntegratedDynamics-1.18.2-1.17.4.jar | 67 |
| `integratedterminals` | IntegratedTerminals-1.18.2-1.4.10.jar | 58 |
| `cloudstorage` | cloudstorage-1.1.0-1.18.2.jar | 38 |
| `cabletiers` | cabletiers-1.18.2-0.56.jar | 36 |
| `blockcarpentry` | blockcarpentry-1.18-0.5.1.jar | 35 |

### P4 · 其他（8398 条）

`pneumaticcraft` 一个模组占大头（机器内部名与长描述混排）；`rechiseled` 是变体方块（`rechiseled.*` 前缀，可模板化）。

| 命名空间 | 模组 jar | 本档待译 |
|---|---|---|
| `pneumaticcraft` | pneumaticcraft-repressurized-1.18.2-3.6.4-45.jar | 1448 |
| `rechiseled` | rechiseled-1.1.5b-forge-mc1.18.jar | 1113 |
| `hexcasting` | hexcasting-forge-1.18.2-0.9.6.jar | 794 |
| `grimoireofgaia` | GrimoireOfGaia4-1.18.2-2.0.0-beta.13.jar | 325 |
| `fancymenu` | fancymenu_forge_3.7.0_MC_1.18.2.jar | 247 |
| `vaultfilters` | vaultfilters-1.33.0.jar | 238 |
| `integrateddynamics` | IntegratedDynamics-1.18.2-1.17.4.jar | 230 |
| `rechiseledcreate` | rechiseledcreate-1.0.2-forge-mc1.18.jar | 155 |
| `botania` | Botania-1.18.2-435.jar | 149 |
| `infernalmobs` | infernalmobs-1.18.6.jar | 142 |
| `hexal` | hexal-forge-1.18.2-0.1.14.jar | 131 |
| `skyblockbuilder` | SkyblockBuilder-1.18.2-3.3.33.jar | 119 |

---

## 四、排期分档（按命名空间规模）

单看模组体量更能决定「一批做多少」。

| 规模 | 命名空间数 | 建议节奏 |
|---|---|---|
| 巨型（>500 条） | 13 | 一个模组就是一轮的工作量 |
| 大型（200–500） | 16 | 2–3 个模组一批 |
| 中型（50–200） | 74 | 5–8 个一批 |
| 小型（1–49） | 200 | 15–20 个一批，很多是 1–5 条的零头 |

**巨型**（13 个）：`chipped`(7467)、`buildscape`(4068)、`pneumaticcraft`(1985)、`buildersdelight`(1491)、`luphieclutteredmod`(1166)、`rechiseled`(1113)、`hexcasting`(921)、`openpartiesandclaims`(916)、`occultism`(700)、`davebuildingmod`(665)、`createdeco`(622)、`dyenamicsandfriends`(569)、`integrateddynamics`(567)

**大型**（16 个）：`mcwfurnitures`(490)、`grimoireofgaia`(459)、`lightmanscurrency`(458)、`neoncraft2`(323)、`ftbquests`(310)、`dungeons_mobs`(299)、`architects_palette`(297)、`mcwwindows`(288)、`auxiliaryblocks`(285)、`xaeroworldmap`(272)、`fancymenu`(247)、`vaultfilters`(246)、`rftoolsutility`(241)、`botania`(213) …

**中型**（74 个）：`incorporeal`(187)、`integratedterminals`(172)、`twigs`(171)、`draconicevolution`(160)、`rechiseledcreate`(156)、`modonomicon`(150)、`infernalmobs`(142)、`casinocraft`(140)、`framedblocks`(140)、`ironfurnaces`(139)、`hexal`(135)、`blockcarpentry`(134)、`dyenamics`(127)、`controlengineering`(124) …

**小型**（200 个）：`secondchanceforge`(49)、`lootr`(48)、`titanium`(47)、`peripherals`(45)、`createaddition`(44)、`extrastorage`(44)、`mcwdoors`(44)、`naturalist`(43)、`ars_nouveau`(41)、`drippyloadingscreen`(41)、`itemfilters`(41)、`refinedstorage`(40)、`rftoolsstorage`(40)、`sophisticatedvaultupgrades`(40) …

---

## 五、「伪翻译」专项（1434 条 / 85 个命名空间）

这些模组**带了 `zh_cn.json`，但一部分键的值直接等于英文**。玩家看到的现象是「这模组明明有中文，怎么还是英文」。逐条补译即可，且**必须**以自带 `zh_cn` 为底再叠加，否则会把它已有的中文整片顶掉。

| 命名空间 | 伪翻译条数 |
|---|---|
| `grimoireofgaia` | 459 |
| `infernalmobs` | 142 |
| `botania` | 88 |
| `cfm` | 68 |
| `immersiveengineering` | 56 |
| `lootr` | 49 |
| `naturalist` | 41 |
| `configured` | 38 |
| `fancymenu` | 33 |
| `integrateddynamics` | 30 |
| `waystones` | 29 |
| `quarryplus` | 28 |
| `create` | 24 |
| `buildinggadgets` | 23 |
| `mekanism` | 21 |

（完整 85 个见 `build/cn/CN-REPORT.md` 的「第三方模组语言」章节）

注意：**原文去掉 printf 占位符后不含字母**的条目不算伪翻译，也不进待译清单（`cropTier...1 = "1"`、`tooltip...buff_line = " - %s (%s)"`）——中文原文本来就该与英文逐字相同。判据见 `vendor._has_letter`。

---

## 六、执行手册

### 1. 重扫 + 导出待译（每次整合包更新后跑一次）

```bash
python -m tools.cnrebase.cli all \
  --client "<客户端包.zip>" --server "<服务端包.zip>" \
  --mods-dir "<实例>/mods" \
  --pack-version <版本> --mod-version <版本> --out build/cn --strict
```

产出 `build/cn/todo/todo-vendor.tsv`（表头 `namespace/key/en/zh`）、`vendor-scan.json`、`term-table.json`。

### 2. 翻译

- **只改 `zh` 列**，前三列原样不动。
- `en` 为空、或去掉占位符后不含字母的条目**不进清单**，不用管。
- 长文本里的 `$(br)` / `$(l:路径)文字$()` / `$(bold)` / `%1$s` **必须原样保留**。
- **术语优先取包内既有译法**：`build/cn/todo/term-table.json`（从全包所有 jar 的语言文件反查出的「英文→已有中文」）就是为此准备的。

```bash
python -m tools.cnrebase.cli terms Hedge "Highley Gate" Crux Manasteel
```

```
## Highley Gate  —— 1 条
     %s Highley Gate        = %s海利栅栏门        [everycomp:block_type.mcwfences.highley_gate]
## Crux  —— 2 条
     Dragon Egg Crux        = 龙蛋核心            [mysticalagradditions:block...dragon_egg_crux]
```

- 查询是**子串匹配**：包里大量构件名是模板形态（`%s Hedge`），精确查 `Hedge`查不到，子串查得到 —— 这正是译员要的用法。
- 查不到就说明是新词，**自己定译名并在提交信息里写明依据**，别硬凑一个和包里既有译法冲突的词。

### 3. 回填 + 复跑

```bash
python -m tools.cnrebase.cli apply-todo \
  --todo build/cn/todo --corpus translations/cn-rebase --strict
python -m tools.cnrebase.cli all --client ... --server ... --mods-dir ... --strict
```

`apply-todo` 会把 `todo-vendor.tsv` 的 `zh` 列合并进 `translations/cn-rebase/vendor_lang_zh.tsv`（译料层 —— **是输入，别当导出物删**）。

### 4. 对账口径

以「重建待译清单后归零」为唯一验收标准，别用「我翻了多少条」：

```python
from tools.cnrebase import corpus as C, vendor
table = vendor.scan_zipfile(zp)                 # 重扫服务端包
co    = C.Corpus.load("translations/cn-rebase")
left  = vendor.todo(table, co.vendor)           # 重建待译
for ns in ("mcwfences", "weather_control", "mysticalagriculture"):
    todo = [r for r in left if r[0] == ns]
    assert not todo, (ns, todo[:5])             # 归零才算翻完
```

### 5. 重新生成本文

```bash
python -m tools.cnrebase.cli plan-doc --out docs/cn-vendor-plan.md
```

---

## 七、为什么必须走语言文件（机制边界）

汉化模组的硬编码通道有明确边界：

- `TextComponentMixin`：只在 `Component.literal("...")` 构造时改写，且**服务端线程跳过**。
- `FontMixin`：注入了 `Font` 的 11 个方法，但**只有 3 个 String 重载真的调用** `LiteralTranslator.translate`（`drawShadow` / `draw` / `width`）；Component / FormattedCharSequence 那 8 个处理器是**空壳**。

模组文本（页签、物品名、GUI）走「语言键 → `TranslatableComponent` → Component 渲染」，**两条硬编码通道都拦不到**。

→ 结论：第三方模组**只能靠补 `assets/<ns>/lang/zh_cn.json`**。

生成规则（三条，缺一不可）：

```
最终 zh_cn = 模组自带 zh_cn（作底）  ∪  我方 vendor 译文（覆盖同名键）
```

1. **必须以自带 zh 为底**——语言文件是**整文件覆盖**语义，只写稀疏增量会把模组原有中文整片顶掉（`mekanism` 自带 1446 键、`occultism` 801 键）。
2. **只给有译文的命名空间生成文件**——我方 jar 与模组 jar 对同一路径是同路径竞争，顺序不由本项目控制，减少无意义竞争。
3. **归语言表通道的 5 个命名空间跳过**（`kubejs` / `packmenu` / `qolhunters` / `the_vault` / `woldsvaults`），避免同一文件被两条通道分别写入。

---

## 八、风险与注意

| 风险 | 处理 |
|---|---|
| 模组自带中文被覆盖丢 | 已按「自带 zh 为底」生成；门禁有「预置未削弱原版自带中文」复核 |
| 同路径竞争导致译文不生效 | 只对有译文的命名空间生成文件 |
| 长文本标记被翻坏 | `corpus.validate` 校验占位符/样式码一致性，回填时拦下 |
| 待译清单永远清不到零 | 已排除「原文为空 / 去占位符后无字母」的条目 |
| 整合包更新后译文失效 | 译文在译料层，与载荷解耦；重基底后自动叠加 |
| 清单与实际脱节 | 本文由 `plan-doc` 生成，跟着构建一起重跑 |

---

## 附：数据来源

- `build/cn/todo/vendor-scan.json` —— 逐命名空间扫描（355 条记录）
- `build/cn/todo/todo-vendor.tsv` —— 逐条待译（36457 条）
- `translations/cn-rebase/vendor_lang_zh.tsv` —— 第三方译料层（已译 493 条）
- `build/cn/todo/term-table.json` —— 术语反查表（英文原文 → 包内既有中文）
- `docs/cn-coverage-plan.md` —— 本通道的设计与查证过程
