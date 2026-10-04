# cnrebase：版本重基底汉化流水线

> 目标：**整合包每发一个新版本，自动产出一套可拖进 PCL 直接用、双端都有的汉化包。**
>
> 目标整合包：Wold's Vaults（CurseForge Project ID **957311**）
> Minecraft **1.18.2** / Forge **40.3.11** / Java 17

---

## 一、为什么不是 VaultPatcher 路线

仓库里曾有两条并行通道，服务两个不同方案（A 已于 2026-09-30 归档）：

| 通道 | 代码 | 原理 | 状态 |
|---|---|---|---|
| A | `archive/i18n-vaultpatcher/` | 资源包 + VaultPatcher 运行时字节码替换 | **已归档**：设计完成但从未接入游戏，且无法承载 AI 人工翻译流程 |
| B | `tools/cnrebase/` | 复用既有 `woldsvaults_cn` Mixin 模组，只替换**载荷数据** | **用户实际在用的方案**，已跑通 |

关键事实：用户真实实例（`E:\...\versions\v`）里装的是自研 `woldsvaults_cn` 模组 +
`I18nUpdateMod`，**不是 VaultPatcher**。该模组已迭代到 **1.0.16**。

所以「整合包升级该怎么办」的答案，取决于一件事：

> `woldsvaults_cn` 的 **15 个 class 文件**（6 个顶层类 + 3 个内部类 +
> 6 个 Mixin：3 个通用 + 3 个 client）**是否与整合包版本耦合？**

反编译后确认：**不耦合**。这 15 个 class 只做三件事——读表、查表、替换文本。
它们不 import 任何 `the_vault` / `woldsvaults` 的类（Mixin 的 `target` 是用
字符串写的），所有版本相关的信息都藏在**数据**里。

于是有了整条流水线的地基：

> **新版汉化 = 保留全部 class 字节码不变 + 按新版语料重建载荷 + 改 `mods.toml` 版本约束。**
> 不需要重新编译任何一行 Java。

---

## 二、三份载荷

`woldsvaults_cn` 启动时只读取三个地方，全部在它自己的 `assets/` 下：

| 载荷 | jar 内路径 | 作用 | 0.34.1 规模 |
|---|---|---|---|
| 硬编码对照表 | `assets/woldsvaults_cn/literal_zh_cn.tsv` | 英文原文 ⇥ 中文，替换 `.class` 常量池里的字面量 | **118,364 行** |
| 语言文件 | `assets/<ns>/lang/zh_cn.json` | 标准语言表，Forge 会把 mod jar 的 `assets` 当资源包自动挂载 | **6 个 ns** |
| 配置文本载荷 | `assets/woldsvaults_cn/config_payload/` | 配置文件的文本替换 + 5 份安装清单 | **6,070 个文件** |

第 2 条的机制值得单独说：Forge 会自动把 mod jar 里的 `assets/` 目录当成资源包挂载，
所以**只要把 `zh_cn.json` 放进汉化 jar，语言表就自动生效**——这也是为什么
没必要再让玩家手动装资源包。

### 清单驱动安装

`ConfigPayloadInstaller` 读 jar 内的 5 份清单，靠**列数**区分格式：

| 文件 | 列数 | 格式 |
|---|---|---|
| `manifest.txt` | 1 | 目标路径（源 = `config_payload/` + 目标路径） |
| `manifest_client.txt` | 2 | `目标 ⇥ 源` |
| `manifest_server.txt` | 2 | `目标 ⇥ 源` |
| `repair_manifest_client.txt` | 3 | `目标 ⇥ 源 ⇥ 摘要` |
| `repair_manifest_server.txt` | 1 | 目标路径 |

**这套协议是从字节码里反推出来的，没有源码。** 做法：用 `tools/cnrebase/classfile.py`
提取 `ConfigPayloadInstaller` 的常量池（`all_strings()`），拿到 9 个关键常量
（5 个清单文件名 + 3 个路径前缀 + 自身 modId），协议就完全确定了。

---

## 二·五、先澄清一个常见误解：原版整合包带汉化吗

**基本不带。** 实测 0.34.1 官方客户端包（`Wold's Vaults-0.34.1.zip`，6,120 条 overrides）：

| 内容 | 原版状态 | 汉化来自哪 |
|---|---|---|
| FTB 任务书 `config/ftbquests/quests/*.snbt` | **8 个文件，0 个中文字符** | 汉化载荷（预置 + 运行期） |
| 帕秋莉手册 `patchouli_books/` | **368 个 `en_us`，0 个 `zh_cn`** | 汉化载荷 |
| `the_vault` 配置语言表 `config/the_vault/lang/zh_cn/` | ⚠️ **本来就是中文**（1,386 文件 / 112,581 字符） | **`the_vault` 官方自带**，不是汉化包的功劳 |
| 模组界面文本 | 408 个模组里仅 **138 个**自带 `zh_cn`（33%） | 语言表 + 118,364 条硬编码对照表 |

这里有个容易误判的地方：`the_vault` 把**一部分**界面文本放在
`config/the_vault/lang/zh_cn/` 下，而这一部分在官方整合包里**已经是中文**。
所以刚进游戏时会看到「有些地方已经是中文」，但 FTB 任务书、帕秋莉手册、
以及另外 270 个模组的界面仍然是英文——**那才是汉化包真正要补的部分**。

判断某个界面有没有被汉化，不能看「是不是有中文」，要看
**该条文本的来源通道**（语言表 / 硬编码表 / 配置载荷）里有没有对应译文。

---

## 三、重基底流程

`tools/cnrebase/build.py: rebase()`

```
① 继承静态部分      com/**  META-INF/**  mixins.*.json  pack.mcmeta  → 原样保留
② 重建语言表        上游 en_us + 上游 zh_cn + 我方 zh_cn → 三路合并
③ 重建硬编码表      tsv 全量保留（含冲突行），供增量比对
④ 重建配置载荷      结构感知合并（见下）→ 覆盖 config_payload/
⑤ 剪枝失效条目      新版已删除的命名空间 → 从 5 份清单剔除
⑥ 更新版本约束      mods.toml 的 modVersion + woldsvaults / the_vault 依赖区间
⑦ 静默署名提示      patches.py 掏空 WelcomeMessages 的 4 个输出方法（见 §3.1）
                    → 打包成 woldsvaults_cn-<mod>-<pack>-universal.jar
```

### ③′ 关于「class 代码零改动」

重基底成立的前提是 class 与整合包版本解耦。但**唯一的例外**是母版作者留在
编译产物里的署名 / 推广提示（见 §3.1）——那不是逻辑，是「贴纸」，
必须每次构建都撕掉，否则会跟着新版本一路继承下去。

### 3.1 静默母版遗留的署名提示（`patches.py`）

母版 `WelcomeMessages` 会在**三个时机**输出带原作者署名与 QQ 群号的横幅：

| 方法 | 时机 | 出口 |
|---|---|---|
| `logModLoaded` | mod 加载 | 控制台日志 |
| `onServerStarted` | 服务端启动 | 控制台日志 |
| `onPlayerLoggedIn` | **玩家登录** | **聊天栏（玩家看到的那条）** |
| `sendWelcome` | 上面调用 | — |

处理分两步，都在 class 字节码层面：

1. **把方法体的 `Code` 属性替换为单条 `return`**。
   为什么不只把字符串换成空串？因为 `text("") + send` 仍会投递一条
   **空消息**，聊天栏会闪出空行。掏空方法才是真静默。
2. **把常量池里的展示性 `Utf8` 常量等长覆盖为空格**——含中日韩字符的，
   以及署名 / 群号这类躲得过 CJK 规则的纯 ASCII 片段。
   常量池不会被 GC，死字符串留在 jar 里仍会被字节级扫描到；
   **等长**覆盖保证 class 内部任何偏移都不变，零风险。

非 void 的辅助方法（`line` / `label` / `text`）**故意不掏空**：
返回类型为 `MutableComponent`，只写 `return` 会缺返回值导致验证失败，
而它们已是死代码（唯一调用方 `sendWelcome` 已空），留着是最小改动。

```
原始 4059 B  →  3765 B      常量池 147 项不变（等长覆盖）
掏空 4 个方法，抹除 12 条常量，类内中文字符归零
```

幂等：重复执行结果一致。目标方法名若在母版升级后改名，
`apply_all` 会报 `unmatched` 并写入构建警告，不会静默失效。

### ④ 为什么必须「结构感知合并」而不是整文件替换

旧的 `manifest_client.txt` 用的是**整文件替换**策略，会直接覆盖
`config/the_vault/abilities.json`（1 MB）、`bingo.json`（1.4 MB）这类大文件。

跨版本沿用这个策略会**丢掉新版新增的字段**——0.34.1 给这些配置加了新词条，
一旦被旧文件整份盖掉，模组读配置时就会缺字段。

改成「**以新版 config 为结构基底，只按同路径回填中文叶子**」：

```
base = 新整合包里的 config/the_vault/abilities.json   ← 结构与字段以它为准
ours = 我方旧载荷里的同名文件                          ← 只贡献译文

for 每个叶子节点:
    base 是 str  → 用 ours 里同路径的值覆盖（仅当 ours 也是 str）
    base 是 dict/list → 递归，且 key 集合永远以 base 为准
```

结果：结构永不退化，新字段自动继承英文原文，旧译文按路径对齐。

实测 0.34.1：**2,465 个 config 文件**，回填 **17,818** 个中文叶子，
仅 **8 个文件**发生结构变化（需人工复核）。

---

## 四、增量分析：怎么知道哪些要翻、哪些不用翻

`tools/cnrebase/delta.py` 把「需要汉化」拆成三个可执行的集合。

### 4.1 语言表增量

`LangDelta` 分五个集合：

| 集合 | 含义 | 处理 |
|---|---|---|
| `missing` | 新版有、我方没有 | **待译** |
| `missing_from_upstream_zh` | 新版 en 有、上游 zh 缺、我方也缺 | 待译 |
| `missing_todo` | 上面两者的并集 | → `todo-lang.tsv` |
| `stale` | 我方有、但英文原文变了 | **复核**（译文可能过期） |
| 已覆盖 | 我方与上游都有 | 跳过 |

0.34.1 结果：语言键覆盖率 **91.9%**，需新译 **309** 条
（woldsvaults 267 + the_vault 39 + kubejs 3）。

### 4.2 硬编码增量

从**新版模组 jar** 的 `.class` 常量池里抓 LDC 字符串，跟我方 tsv 比对。

难点是**噪声过滤**——常量池里绝大多数字符串是内部标识符，不是给人看的文本：

```
classic_vault_ice      ← 枚举 id
luckyHitChance         ← 字段名
deck_station_tile_entity ← 注册名
```

`is_translatable()` 的判定（全部满足才算候选）：

1. 不以 `\x01` 开头（class 里用 `\x01` 标记插入点，模板串不是给人看的）
2. 长度 ≥ 6
3. 含空格或标点
4. 至少 2 个「≥2 个字母」的单词
5. 不是 `NS_ID` 形态（`mod:path`）
6. 不是 `FIELD_LIST` 形态（逗号分隔的小写标识符）

这一条把候选从 14,051 收敛到 **6,659**，todo 从 10,830 降到 **2,864**。

> 形态差异要注意：class 里模板用 `\x01` 标插入点，tsv 里用 `%s`。
> `normalize_literal()` 统一成 `%s` 后再比对。

0.34.1 结果：候选 **6,659**，复用 **3,795**，待译 **2,864**，复用率 **57.0%**。

### 4.3 配置文本增量

`merge_json_text()` 递归比对，产出 `MergeStat`：

```
filled         回填成功的中文叶子
kept_en_text   保持英文的**文本类**字段  ← 分母只算这个
kept_en_other  保持英文的非文本叶子（资源 ID / 数值 / 命名空间）
structure_changed  结构不一致，需人工复核
```

`looks_textlike()` 区分「文本字段」和「数据叶子」。

**这一步是口径修正的关键**：早期把分母算成全部叶子（含 209,972 个资源 ID），
汉化率显示 7.3%——完全误导。改成只算文本字段后是 **63.1%**
（17,818 / 28,222），这才是真实进度。

---

## 五、官方服务端包的两个坑

### 5.1 残留重复 modid

官方服务端包里同一个 modid 有**两个版本**，Forge 会因 duplicate modid **拒绝启动**。

0.34.1 实测 4 组：

| modid | 保留 | 剔除 |
|---|---|---|
| `the_vault` | 3.21.6.6884 | 3.21.5.6573 |
| `create` | 0.5.1.**i** | 0.5.1.**f** |
| `crafttweakerforge` | 9.1.213 | 9.1.211 |
| `smartresearchcost` | 1.1 | 1.0 |

**版本比较必须处理字母段。** `create-1.18.2-0.5.1.f` 与 `0.5.1.i`，
用纯数字元组会打成平手，排序就退化成 zip 顺序——实测真的保留了旧的 `0.5.1.f`。

修法是把 token 编码成 `(rank, num, txt)`：数字 token `rank=0`，字母 token `rank=1`。

```python
def _version_key(filename: str) -> tuple:
    toks = _version_tokens(filename)          # re.findall(r"\d+|[A-Za-z]+", ver)
    return tuple(
        (0, int(t), "") if t.isdigit() else (1, 0, t.lower())
        for t in toks
    )
```

结果与 zip 里 jar 的修改时间完全吻合（保留 2024-12-30 的 `0.5.1.i`，
剔除 2024-02-26 的 `0.5.1.f`）。

> ⚠️ **不要用子串匹配判断去重是否生效。**
> `"0.5.1.f" in name` 会命中 `create_enchantment_industry-1.18.2-for-create-0.5.1.f-1.2.8.jar`
> ——那是另一个模组（Create 附属），它依赖 create 0.5.1.f 完全正常，不该被删。
> 门禁里一律用**精确文件名集合**比对。

### 5.2 版本号要从 jar 名反推

服务端包**没有** `manifest.json`，包版本得从 `wolds-vaults-official-mod-*.jar`
的文件名里提取。

---

## 六、产物三件套与 PCL 安装

```
build/cn/dist/
├── woldsvaults_cn-1.0.17-0.34.1-universal.jar      14.9 MB   汉化模组
├── WoldsVaults-0.34.1-CN-Client-PCL.zip            58.2 MB   客户端包（拖进 PCL）
└── WoldsVaults-0.34.1-CN-Server.zip               610.2 MB   服务端包（已去重）
```

### 客户端包为什么可行

整合包**没有 `overrides/options.txt`**，所以塞进 `resourcepacks/` 的资源包
不会被自动启用（需要玩家手动开）。

但走**模组 jar** 就完全绕开了这个问题：把汉化 jar 放进 `overrides/mods/`，
PCL 装整合包时一并装进去，**装完即汉化，玩家零操作**。

`manifest.json` 的修改仅限 `name` 字段（改成 `Wold's Vaults 汉化版`），
**`minecraft` / `manifestType` / `overrides` / 445 条 `{projectID, fileID}` 全部字节级保真**
——PCL 靠这些决定下载哪些模组，改错一个字段就会下错文件。

### 为什么还要「预置载荷」

汉化模组的三条读取通路里，语言表和硬编码表靠 jar 本身即可生效，
但第三条约 **FTB 任务书 / 帕秋莉手册 / 配置文本** 是**运行期动作**：

```
游戏启动 → ConfigPayloadInstaller（由 @Mod 类的构造器调用）
         → 按 jar 内 5 份清单把 config_payload/ 铺到游戏目录
```

这带来两个问题：

1. **无从验证**：打开整合包目录看，任务书仍是英文，玩家无法判断汉化到底生效没有
2. **单点故障**：只要模组没成功加载，任务书就永远不汉化

所以构建时把载荷**同时预置进整合包**（客户端 → `overrides/`，服务端 → 包根目录）。
中文在解压那一刻就物理存在，不再依赖运行期安装。

```
客户端：3,044 个目标 → 新增 377 / 覆盖 2,667    包体积 57.9 → 58.2 MB
服务端：  588 个目标 → 新增 369 / 覆盖   219    包体积 609.9 → 610.2 MB
```

预置内容与 jar 载荷**完全一致**，因此与模组的 repair 机制幂等——
repair 清单带 SHA-256，比对的是载荷自身摘要，不会冲突。

> ⚠️ 实现上必须按「包内是否已有同名条目」**分流到 add / replace**。
> `rewrite_zip` 的 `add` 遇到已存在的名字会**静默跳过**，
> 全部塞进 add 会导致载荷被无声丢弃（zip 里仍是英文，而且不报错）。
> 门禁因此加了「无重复 zip 条目」与「载荷全部预置」两项断言。

包内附：
- `overrides/汉化说明.txt`
- `overrides/CN-BUILD.json`（构建元数据：版本、来源、载荷计数）

### 服务端包

除注入汉化 jar 外，还做去重（408 → 405）。**重复 modid 会让 Forge 直接拒绝启动**，
所以这步不是优化，是必需。

### 开服场景：服务端汉化到底能覆盖什么

这是最容易误解的一点——「服务端装了汉化，玩家进来就全中文」**不成立**。

服务端能把内容送到玩家面前的只有一条路：**服务端权威数据**。其余全是客户端本地资源。

| 通路 | 开服时对玩家有效？ | 原因 |
|---|---|---|
| FTB 任务书 `config/ftbquests/` | ✅ **有效** | 服务端权威，玩家登录后整份同步覆盖本地 |
| KubeJS `kubejs/data/`（进度等） | ✅ 有效 | 数据包，服务端加载并同步 |
| `config/the_vault/` 服务端配置 | △ 半有效 | 服务端逻辑生效，客户端 GUI 文案不跟随 |
| 帕秋莉手册 `patchouli_books/` | ❌ 无效 | `ResourceManager` 本地读取，服务端不传 |
| 语言文件 `assets/*/lang/zh_cn.json` | ❌ 无效 | 客户端资源 |
| 硬编码对照表（`LiteralTranslator`） | ❌ 无效 | 客户端 Mixin 替换 |

实测（0.34.1）：

| 目录 | 官方服务端 | 汉化服务端 |
|---|---|---|
| `config/ftbquests` | 8 文件 / **0 中文字符** | 8 / **29,860** |
| `patchouli_books` | 403 / 0 | 771 / 25,165（+368 个 `zh_cn`）|
| `config/the_vault/lang` | 49 / 25,434（官方自带）| 50 / 52,407 |
| `kubejs/` | 1,095 / 441 | 1,095 / 1,348 |
| `mods/` 自带 `zh_cn` | 138 / 408（33%）| 136 / 405（33%）|

> 服务端包里的 `patchouli_books/*/zh_cn/` 属于**冗余预置**：它跟随原版结构
> （原版服务端本来就带 403 条 `en_us`），但玩家读的是自己本地的
> `.minecraft/patchouli_books/`，服务端那份不会传过去。压缩后仅几百 KB，
> 保留是为了两端结构一致、便于比对。

**开服的正确姿势是两边都装：**

| 角色 | 装什么 | 得到 |
|---|---|---|
| 服务端管理员 | `WoldsVaults-<ver>-CN-Server.zip` | 任务书 / 进度对所有玩家统一中文 |
| 每个玩家 | `WoldsVaults-<ver>-CN-Client-PCL.zip`，或单独把 `woldsvaults_cn-*.jar` 丢进自己 `mods/` | 界面文本、tooltip、手册、字体全中文 |

玩家若只装原版客户端连服：**只有 FTB 任务书是中文**，其余仍是英文。

#### 服务端加载汉化模组安全吗

安全。6 个 Mixin 的分组：

| 配置 | 分组 | 成员 | 服务端行为 |
|---|---|---|---|
| `mixins.woldsvaults_cn.json` | `mixins`（双端）| `TextComponentMixin`、`ClientboundToastMessageMixin` | 加载 |
| `mixins.woldsvaults_cn.client.json` | `client` | `FontMixin`、`ResearchDialogMixin`、`ChatComponentMixin` | **不加载** |

双端那 2 个的目标是 `net/minecraft/network/chat/TextComponent` 与
`iskallia/vault/network/message/ClientboundToastMessage`；客户端专属那 3 个
目标是 `net/minecraft/client/gui/Font`、`.../components/ChatComponent`、
`iskallia/vault/client/gui/.../ResearchDialog`——全是客户端类，声明在 `client`
分组里，服务端不会去注入一个它没有的类。

> ⚠️ 这里有个**必须警惕**的点：Mixin 配置是 `required: true` +
> `defaultRequire: 1`，目标类缺失时**不是降级而是启动崩溃**。母版基于 0.30.0，
> `iskallia/vault/...` 这类路径随时可能随上游重构而变（`ResearchDialog` 的包
> 就有 7 层深），所以门禁里专门有【4】节逐类核对。

---

## 七、CI 用法

`.github/workflows/cn-release.yml`

三种触发方式：

```yaml
workflow_dispatch:            # 手动，可指定版本 / 直链
repository_dispatch:          # 类型 wolds-vaults-released（可用 webhook 联动）
schedule: "41 5 * * *"        # 每天 05:41 UTC 检查有没有新版
```

流程里的关键设计：

1. **版本可留空** → 走 CurseForge API 取最新
   （`api.curseforge.com/v1/mods/957311/files`，筛掉 `isServerPack`）
2. **幂等**：先 `gh release view "cn-v<VER>"`，已存在就跳过整个构建
3. **缓存**：`actions/cache` 缓存 `work/packs`（服务端包 590 MB，重下有成本）
4. **服务端包只进 Release，不进 artifact**：590 MB 上传两次没必要
5. **末尾跑交付门禁**，不通过即非零退出，Release 步骤不会执行

> 需要配置 secret：`CF_API_KEY`（CurseForge API Key）

### 本地跑一遍

```bash
python -m tools.cnrebase.cli all \
  --client "C:/Users/ASUS/Downloads/Wold's Vaults-0.34.1.zip" \
  --server "C:/Users/ASUS/Downloads/official-wolds-vaults-server-pack-0-34-1.zip" \
  --pack-version 0.34.1 --mod-version 1.0.17 --out build/cn
```

实测耗时：重基底 11.2s + 客户端注入 4.9s + 服务端注入 23.3s + 门禁扫描
≈ **1 分 4 秒**（Windows / SSD）。

其它子命令：

```bash
python -m tools.cnrebase.cli probe   ...   # 只看事实，不改文件（核对版本用）
python -m tools.cnrebase.cli rebase  ...   # 只出汉化 jar
python -m tools.cnrebase.cli inject  ...   # 只做注入
python -m tools.cnrebase.cli verify  ...   # 只跑门禁（CI 可单独调）
python -m tools.cnrebase.fetch --version 0.34.1 --out work/packs
```

---

## 八、交付门禁

`tools/cnrebase/verify.py` —— 断言条目数随场景浮动（本地无源包时约 71 项，
CI 带 `--client/--server` 时约 85 项），以报告末尾「结果: N 项全部通过」
为准，`all` 末尾自动执行。

**为什么不一刀切写死数字**：门禁里有一大批「与源包逐条对照」的断言
（manifest 的 projectID/fileID 保真、模组数恒等式、剔除集合、预置 JSON
结构退化…）。这些断言在没给源包时**根本没法跑**——如果只是静静地不跑，
报告仍然写着「全部通过」，绿灯就被误读成「全量校验通过」。因此：

* 没跑成的断言一律登记为 **SKIP** 并在报告里列出来；
* `--strict` 让「存在 SKIP」也判定失败。**CI 里必须带 `--strict`** ——
  宁可因为服务端包没下载下来而构建失败，也不要发一个只做过半边校验的包。

设计原则（决定了它会不会变成噪声源）：

1. **以母版模板为参照系**，不写死数字。
   class 集合与母版**完全相等**、语言键数只增不减、清单行数只减不增——
   母版升级时门禁自动跟随，不会因为一个魔法数字过期而误报。
2. **以源整合包为参照系**。
   模组数 445、jar 数 408 全从原始 zip 现算，不硬编码。
3. **需要判定「不存在」时一律用精确集合差，禁止子串匹配**（理由见 §5.1）。
4. **重复 modid 不对名单，对产物重新跑一边检测**——这才是真验收。
5. **中文判定要 JSON 感知**。载荷里的 JSON 大量用 `\uXXXX` 转义，
   直接在字节流上跑 CJK 正则会得到「没有中文」的假结论。
6. **门禁不复用被验实现的解析器**。校验 class 方法体用的是 verify.py 里
   另写的一份最简解析（`_method_codes`）——共用解析代码的话，
   解析器自身的 bug 就永远查不出来。

五段结构：

| 段 | 覆盖 |
|---|---|
| 【1】汉化模组 jar | class 集合 = 母版、6 个 Mixin 齐全、tsv 未缩水、五份清单 3,141 条全部有实体文件、语言表逐 ns 只增不减、无 izzy_vault 残留、**署名提示已静默（见下）**、CRC |
| 【2】客户端拖拽包 | 无重复 zip 条目、445 条 `projectID/fileID` 逐条保真、`manifestType`/`overrides`/`minecraft` 未改、原 overrides 成员零丢失、**3,044 个载荷目标全部预置且抽样确认是中文**、CRC |
| 【3】服务端包 | 无重复 zip 条目、`405 = 408 − 4 + 1`（源 − 剔除 + 注入）、剔除集合 = 同 modid 旧版本集合、其余成员零丢失、**产物内无重复 modid**、**588 个载荷目标全部预置**、CRC |
| 【4】Mixin 目标类 | 配置引用的 5 个 class 全在 jar 内、`client` 分组未混入双端、**2 个模组侧目标类在 0.34.1 仍存在**（缺失 = 启动崩溃）|
| 【5】报告与待译清单 | 5 个文件非空 + 报告含四个必需章节 |

另有两条**全量结构断言**挂在【2】【3】里：产物中每个预置 JSON 的叶子集合
必须 ⊇ 原版同路径文件——这条就是为下述「配置无效」事故加的回归防线。

署名静默走**四重口径**（§3.1）：字节级（署名 / 群号不残留）、
常量级（类内中文归零）、语义级（4 个方法体均为空 `return`）、
结构级（class 完整遍历恰好落到文件末尾——补丁改过长度，必须自证没算错偏移）。

另有两条一致性断言：客户端包 / 服务端包里注入的 jar 必须与 dist 产物
**sha256 相同**，防将来重构 inject 时错配。

---

## 九、文件速查

```
templates/
  woldsvaults_cn-1.0.16-base.jar    15 MB 母版（入库）
  template.lock.json                母版指纹：sha256 + 8493 entries
                                    （解压目录 90 MB 现用现生成，已 gitignore）

tools/cnrebase/
  assets.py    译料库读写：三份载荷 / 清单解析 / 静态-载荷判定
  packs.py     整合包 zip 读写：流式改写保 ZipInfo 元数据 / 版本比较 / 去重
  mods.py      模组 jar 解析：mods.toml 极简解析 / LDC 常量池提取 / 内部标识符过滤
  delta.py     增量分析：语言表 / 硬编码 / 配置文本，三套 delta + 结构感知合并
  build.py     版本重基底：六步流程
  inject.py    整合包注入：载荷预置（add/replace 分流）+ 服务端去重
  patches.py   字节码补丁：静默母版遗留的署名提示（见 §3.1）
  report.py    CN-REPORT.md + cn-build-summary.json + todo/
  verify.py    交付门禁：SKIP 显式登记 + --strict
  fetch.py     CurseForge 拉包（API 查版本 → CDN 下载）
  cli.py       probe / rebase / inject / all / verify
```

产物：

```
build/cn/
  dist/                       三件产物
  CN-REPORT.md                构建报告（七章）
  cn-build-summary.json       机器可读摘要
  todo/todo-lang.tsv          待译语言键（309 条）
  todo/todo-literal.tsv       待译硬编码（2,864 条）
  todo/review-config-structure.json  结构变化待复核（8 个文件）
  work/template/              展开的模板（中间产物，已 gitignore）
```

---

## 九·五、事故复盘：「配置无效」（0.34.1 首轮构建）

用户实测报错：`abilities_vignette.json — Cannot read field "color" because
"vignetteData" is null`，the_vault 弹「Some configs are invalid」。

**根因**：`build._merge_config_payload` 的旧逻辑——

```python
if st.filled == 0 and not st.structure_changed:
    continue            # 保留旧版载荷
```

`filled == 0` 表示「没有中文可回填」，而 the_vault 大量配置是**纯数据**
（颜色 / 数值 / 图标路径，共 34 个文件）。这些文件走了上面的短路，
**0.30.0 的旧结构被原样预置进 0.34.1 包**，新版新增字段全部丢失，
mod 读不到就回退默认值并弹「配置无效」。

**修复**（双保险）：

1. `filled == 0` 时改写**新版原始字节**（merged 恒等于 base，落原文格式零改动）；
   基底解析失败时同样落新版原文 + 警告。
2. 同一 target 在 universal 与 repair 清单里各有一份载荷源——**每份都必须
   写相同内容**（旧逻辑只更新第一份，预置取到另一份旧版）。
3. 门禁加全量结构断言（见 §8）。

修复后独立复核：34 个退化文件 → 0（唯一例外 `gear_model_roll_rarities.json`
产物与原版字节一致，解析失败是扫描脚本未容错注释，无害）。

**连带查明**：非 JSON 载荷（FTB 任务书 snbt / 3 个 KubeJS 脚本）预置的是
旧版中文文件，逐个 diff 确认全部为**翻译增强**（行数一致或新增中文名映射，
null 检查写法 `!= null` 与 `!= null && != undefined` 在 JS 中语义等价），
无功能回退，保留。

## 十、已知限制

1. **翻译仍需 AI 人工介入，不是 CI 能替代的**。流水线保证「不重复翻」「不错翻」「不漏包」，并把缺口导出成 `todo/*.tsv`；译文经 `apply-todo` 落入译料层后即可复用。
2. **模组覆盖面天然不完整**。408 个模组里 138 个自带官方 `zh_cn`，
   其余 270 个的界面文本只能靠 118,364 条硬编码对照表命中。
   命中不了的（2,864 条）就是「部分模组没汉化」的直接原因，
   清单在 `build/cn/todo/todo-literal.tsv`。这不是构建问题，是译料库缺口。
3. **配置文本汉化率 63.1%** 里含低置信度条目。`review-config-structure.json`
   列出的 8 个结构变化文件必须人工过一眼，其余按路径对齐是安全的。
4. **母版 1.0.16 的 tsv 有冲突行**（同一英文多译），`LiteralTable.mapping`
   取**首次出现**以保持原文件优先级——这跟模组运行时行为一致，别改。
5. **`the_vault` 依赖区间是硬编码进 `build.py` 的**。换大版本时
   （比如 1.18.2 → 1.19.2）需要人工确认新版本号并更新。
6. **预置载荷后回退不彻底**。删掉汉化 jar 会停止语言表/硬编码汉化，
   但已预置的文本文件仍在包内，要彻底回退需整体重装原版。
7. 服务端包 610 MB，**首次 CI 运行下载较慢**，之后走 cache。

## 十·五、译料层与翻译回填闭环

**问题**：载荷（`literal_zh_cn.tsv` / `lang/*.json` / `config_payload/`）每轮
重基底都是从源包重建的。译文若直接写在载荷里，下一轮就被冲掉——「翻完就丢」。

**解法**：译文单独存一层，构建时叠加。

```
translations/cn-rebase/
  lang_zh.tsv        namespace  key      en  zh     -> 语言文件通道
  literal_zh_cn.tsv  en                  zh         -> 硬编码字面量通道
  config_zh.tsv      target     pointer  en  zh     -> 配置文本通道
```

每轮构建：

```
新版源包 --重基底--> 载荷（英文基线）
                        |  叠加（按键绑定匹配）
译料层 -----------------+
                        v
                  覆盖写入模板 -> 打包
```

### 键绑定：为什么不按英文原文绑

- **语言键按 `key` 绑**。上游把 `Echo` 改成 `Echo!` 时译文仍在；若按原文绑，
  上游每改一次文案就丢一次译文。
- **字面量按 `en` 绑**。字面量本来就没有稳定 key，只能按原文。
- **配置按 `(target, pointer)` 绑**。`pointer` 是 JSON 位置
  （`/o:skills/i:3/o:name`：`o:` 对象键、`i:` 数组下标，键内 `/` `~` 转义为 `~1` `~0`）。

代价：**改 key 或改结构（指针移动）会让译文变孤儿**——不报错，只是静默不生效。
所以每轮要看构建报告里的 `corpus_applied` 命中数。

### 回填

```bash
python -m tools.cnrebase.cli apply-todo --todo build/cn/todo --corpus translations/cn-rebase
```

逐条校验（占位符等量、样式码等量、无换行、非空、非照抄英文）、转义、**排序**
后合并进译料层。`--dry-run` 只校验不写；`--strict` 有拒收即非零退出（CI 用）。

排序是刻意的：否则每次构建都产生上万行无意义 diff，真正的译文改动会被淹没。

### 通道细节

- **硬编码通道**：除叠加外还要 `assets.save_literal` 回写模板里的
  `literal_zh_cn.tsv`——产物 jar 里那份是从模板取的，只改内存映射会导致
  「待译清单变短、玩家侧却查不到译文」。
- **配置通道**：译料以 overlay 形式先写进 ours 字节，再走原有的结构感知合并，
  保证「结构永远以新版为准、只覆盖已存在叶子」。
- **行式对照表的硬约束**：含换行/制表符的字面量（0.34.1 实测 161 条）在
  `literal_zh_cn.tsv` 里结构上无法承载，写进去会让译文错配到下一条原文上。
  这类条目在回填时**直接拒收并给出原因**，构建报告单列数量，不静默丢弃。

### 门禁

`verify` 的【6】节「译料层已消费」核对译料层的译文**确实写进了产物**，
防「只更新了内存映射、没落盘」的静默失效。
