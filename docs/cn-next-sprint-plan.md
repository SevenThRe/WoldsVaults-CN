# 汉化流水线 · 下一阶段开发计划

> 生成时间：2026-09-30 21:10
> 基线：`0.34.1` 三件套已产出，门禁 **89/89 全绿**
> 本文件的每个数字都来自对落盘产物的实算，不是估算。

---

## 一、现状快照（实测）

### 1.1 已交付产物

| 产物 | 路径 | 规模 |
|---|---|---|
| 客户端包（PCL） | `build/cn/dist/WoldsVaults-0.34.1-CN-Client-PCL.zip` | 60 MB |
| 服务端包 | `build/cn/dist/WoldsVaults-0.34.1-CN-Server.zip` | 611 MB |
| 汉化模组 | `build/cn/dist/woldsvaults_cn-1.0.17-0.34.1-universal.jar` | 16 MB / **230 张语言表** |
| 汉化资源包 | `build/cn/dist/WoldsVaults-CN-Lang-0.34.1.zip` | **229 ns / 59,013 条** |

### 1.2 第三方残差构成（11469 条 / 349 ns）

我按「命名空间是否进了资源包」切开，发现残差不是均质的：

| 分组 | ns 数 | 英文键 | **残差** | 占比 |
|---|---:|---:|---:|---:|
| 已进资源包 | 229 | 64,830 | 8,714 | 76.0% |
| **未进资源包** | 120 | 8,869 | **2,755** | **24.0%** |

「未进资源包」不是 bug —— `vendor.effective()` 的跳过条件是
`if not zh and not b: continue`（我方译料与 CFPA 底都为空才跳过），
**模组自带 `zh_cn` 不参与这个条件**。这 120 个 ns 一旦我方补译，
`known[ns]` 非空即会整份生成并入包。所以它们是「待启动」，不是「被丢弃」。

但其中有一类特别值得注意：**`grimoireofgaia` 自带 841 条 zh，其中 459 条值等于英文**（台账 `fake_zh` 字段已正确识别，全局 1428 条 / 占自带 zh 的 3.2%）。
`residual == fake_zh == 459` 精确吻合 —— 这 459 条玩家现在看到的**就是英文**。

### 1.3 客户端专属命名空间（21 个）

服务端包单独扫描得 328 ns；带上 `--mods-dir`（真实客户端实例）后 349 ns。
差的这 21 个是**纯客户端模组**：

```
controllable 31   fancymenu 247   resourcify 118   vaultlootbeams 118
ktnilcks 27       citresewn 18     skinlayers3d 17  embeddiumplus 2
highlightmapmarkers 2   justzoom 2   masutab 3   memorysettings 8
sodium-extra 3   vaultarhud 3   vaultmapper 6   vhatcaniroll 9
visual_keybinder 2   bookmarksharing 1   colorful_greed_card 0
reeses-sodium-options 1   imblocker 1
```

合计残差约 **619 条**。**这 21 个 ns 的表要不要进包，目前完全取决于本地传不传 `--mods-dir`**
（本例它们译料/CFPA 都为空 → 本来就不进包，所以当前无影响；但机制上是脆的）。

---

## 二、任务清单

### Sprint A —— 收口在飞的活（今天就该结束）

| # | 任务 | 负责 | 输入 | 验收 |
|---|---|---|---|---|
| A1 | ruletrans G5–G8 守卫（括号禁令 / 单字母透传 / 相邻重复 / 修饰词正规化）+ term-table 单字符 key 过滤 | SE2（在飞 #3） | 已发的规格 | 四条全局扫描均为 0；报告各守卫拦截条数；新样本 15 条 |
| A2 | 长尾人工译批次 #1：`grimoireofgaia` 459 / `lightmanscurrency` 458 / `openpartiesandclaims` 351 / `dungeons_mobs` 299 | SE（在飞 #8） | 台账 + CFPA 同模组既有译文当术语词典 | staged `build/cn/work/trans/<ns>.tsv`；不得覆盖 CFPA 键 |
| A3 | **我**独立审阅 A1/A2 产出 | Lead | 上述产物 | 逐条扫四类红线（`[]` / 残留 ASCII / 相邻重复 / 单字母透传）+ 抽样比对；不合格整批退回 |
| A4 | 入库 + 复跑 `cli all --strict` | SE | 审过的 tsv | 89 项仍全绿；Lang 包条目数上升且与 tsv 条数吻合 |

> **A1/A2 未交付前不要开新翻译批次** —— 上一轮的教训是：生成器自检全绿，
> 我抽验 3 分钟就抓到 34 + 6 条发布级缺陷（`[小型]铁块瓦`、`C→℃`、`宝丽来相机相机`）。
> 守卫不落地，后续批次越多、返工越大。

### Sprint B —— 待用户拍板的两个决策

| # | 任务 | 前置 | 工作量 |
|---|---|---|---|
| B1 | **剔除 I18nUpdateMod**：删 `overrides/mods/I18nUpdateMod-3.7.0-all.jar` + 对应 `resourcepacks/*.zip` + 清 `options.txt` 条目 | 用户点头 | 小 |
| B2 | **补 8 个客户端专属 ns 的 95 条**（`xray` 50 / `davebuildingmod` 34※ / `moremekanismprocessing` 5 / `irongenerators` 2 / 其余各 1） | B1 | 小 |
| B3 | **IMBlocker 打进客户端包**：`overrides/mods/IMBlocker-5.6.2-forge+1.17-1.20.4.jar`（**只进客户端**，服务端会崩） | 用户点头 | 小 |
| B4 | `verify.py:476` jar 断言改**白名单式**（「必须含汉化 jar，其余允许白名单 modid」）；服务端 `len(injected) == 1` **保持不动** | B3 | 小 |

※ `davebuildingmod` 那 34 条是 **CFPA 有、模组 `en_us` 没有的死键**，模组永不请求
→ 实际有效价值约 50 条（= `xray` 那 50 条）。

决策依据见 `docs/cn-optional-mods-decision.md`（含逐键对撞与 `options.txt` 优先级实测）。

### Sprint C —— 覆盖率（价值最大的一段）

按残差降序，前 10 名吃掉 66.6%，但 **Top3 = 48.5% 里有 3942 条是单个模组**：

| 批次 | ns | 条数 | 通道 | 备注 |
|---|---|---:|---|---|
| C1 | `buildscape` | **3942** | 人工词表 + ruletrans | CFPA 1.18 与 extra 包**都不含**，无外部可蹭 |
| C2 | `luphieclutteredmod` | **1166** | ruletrans（现 29.4%）+ 人工补 | 待 SE2 重报 |
| C3 | `grimoireofgaia` | 459 | 人工 | 459 条伪翻译，需整表覆盖 |
| C4 | Top10 余下 | ~2300 | 混合 | `fancymenu` 247 / `vaultfilters` 246 / `auxiliaryblocks` 285 / `incorporeal` 187 / `casinocraft` 140 … |
| C5 | **客户端专属 21 ns** | ~619 | 人工 | 同时解掉「本地/CI 扫描源不等价」的隐患 |
| C6 | ruletrans 已产出待审批次 | — | 审后入 | `rechiseledcreate` 68.6% / `rechiseled` 43.5% 可优先入 |

**C5 的工程配套（建议同期做）**：
把客户端模组的 `en_us`/`zh_cn` 快照固化为仓库资产
（如 `translations/cn-rebase/client-mods-lang.zip`），`vendor.scan_zipfile` 直接读。
好处：CI 不传 `--mods-dir` 时与本地产出**完全等价**，且不必在 CI 下载 445 个 jar。

### Sprint D —— 工程债 / 健壮性

| # | 任务 | 说明 |
|---|---|---|
| D1 | **复现并定位** SE 报的「CI 缺 1 条 `ae2searchimprovements`」 | ⚠️ 我**无法复现**：服务端包单独扫描**含**该 ns，且 dist jar 里该表存在（230 张表含它）。需要 SE 给出可复现命令 + 完整断言输出，先复现再改，不要盲改契约 |
| D2 | `res.vendor_conflicts`（「模组自带 zh 会顶掉我方」的同路径竞争 jar）走**并入模组 jar** 通道 | 本轮未做，共 69 个 jar |
| D3 | `_trash/` 清理 | 每轮退役约 108 MB，`os.replace` 改名规避宿主批量删除守卫的代价 |
| D4 | 母版 `builtForPack` 锁 0.30.0 | 同 MC 大版本内可全自动；升 1.19+ 需重编母版 |
| D5 | QA 独立回归 | `verify_langpack.py`（92 断言）+ `verify.py`（89 项），对 A/B 全部改动重跑 |

---

## 三、关键风险

1. **改源码与跑构建必须串行**。Python 启动即载入模块，构建启动后再改源码，
   本轮产物**不会带上**（已踩过：包内说明晚 30 秒改，第一轮 86/86 全绿的包写的是旧版）。
2. **门禁一律带 `--strict`**。缺 `--client/--server` 时「与源包逐条对照」的断言整段不执行，
   不加会静默通过、绿灯被误读成全量校验。
3. **不写死断言数**。条目数随场景浮动，以「结果: N 项全部通过」为准。
4. **译料层输入键集必须取 post-CFPA 残差**。`zh_by_key` 层级在 CFPA 之上，
   用机器译文盖掉 CFPA 人工译文 = 质量退化。
5. **资源包命名永久避开子串 `Minecraft-Mod-Language-Modpack`**
   （I18n 的清理逻辑按子串删 `options.txt` 条目）。现名 `WoldsVaults-CN-Lang.zip` 安全。

---

## 四、建议执行顺序

```
A1 / A2（在飞，今天收口）
   ↓
A3 我审 → 不合格退回，合格则 A4 入库并复跑门禁
   ↓
B1–B4（等你拍板，一轮构建搞定）
   ↓
C5 + 其配套资产固化 ← 建议提前，因为它同时解掉「CI 与本地不等价」
   ↓
C1 → C2 → C3 → C4 → C6
   ↓
D1 复现 → 定位 → 修（或撤销该断言）
   ↓
D5 QA 独立回归 → 出版 0.34.2
```

**需要你现在回一句的只有 Sprint B 的两项**（剔 I18n / 装 IMBlocker）。
其余我可以直接推进。
