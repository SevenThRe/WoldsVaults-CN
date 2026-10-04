# 汉化覆盖面扩展方案（第三方模组语言通道）

> 触发背景：0.34.1 汉化版装好后，JEI 里一批模组页签仍是英文。
> 本文是**查证结论 + 实施计划**，对应 `tools/cnrebase` 的下一轮改造。

---

## 一、查证结论

### 1. 不是硬编码

逐个解包核对（0.34.1 服务端包内 408 个 mod jar），截图涉及的页签名**全部来自
语言键**：

| 页签显示 | 语言键 | 命名空间 | 该模组自带 zh_cn |
|---|---|---|---|
| AE Additions | `itemGroup.ae2additions.item_group` | `ae2additions` | ❌ 无 |
| Wold's Vaults | `itemGroup.woldsvaults` | `woldsvaults` | ❌ 无 |
| Storage Drawers | `itemGroup.storagedrawers` | `storagedrawers` | ❌ 无 |
| CreateDeco Metals | `itemGroup.createdeco.metals` | `createdeco` | ❌ 无 |
| CreateDeco Props | `itemGroup.createdeco.props` | `createdeco` | ❌ 无 |
| Pipez | `itemGroup.pipez` | `pipez` | ❌ 无 |
| More Mekanism Processing | 见 `moremekanismprocessing` 词条 | `moremekanismprocessing` | ❌ 无 |
| Dark Utilities | `itemGroup.darkutils` | `darkutils` | ❌ 无 |
| Cluttered | `itemGroup.tabclutter_mod` | `luphieclutteredmod` | ❌ 无 |
| Cloud Storage | `itemGroup.cloudstorage` | `cloudstorage` | ❌ 无 |

**是「范围外」，不是「硬编码」，也不是「工具吃漏了已覆盖范围」。**

### 2. 真正的两类缺口

| 类型 | 规模 | 处理方式 |
|---|---|---|
| **A. 已有通道内的缺口** | `woldsvaults` 缺 267 键、`the_vault` 缺 180 键 | 走既有 `todo-lang.tsv` 补译，**不改代码** |
| **B. 从未在范围内** | 313 命名空间 / 76011 键 / **36297 键无 zh** / 178 个命名空间整包零 zh | 需要新增「第三方模组语言」通道 |

A 类是整合包本体，玩家天天看，**优先级最高**。

### 3. 机制上为什么「表里有词条却仍是英文」

汉化模组的硬编码通道有边界：

- `TextComponentMixin`：只在 `TextComponent` 构造时改写 —— 只拦
  `Component.literal("...")`，且服务端线程跳过。
- `FontMixin`：注入了 `Font` 的 11 个方法，但**只有 3 个 String 重载真的调用
  `LiteralTranslator.translate`**（`drawShadow` / `draw` / `width`）；
  Component / FormattedCharSequence 那 8 个处理器是空壳。

JEI 页签名走「语言键 → TranslatableComponent → Component 渲染」，
**两条硬编码通道都拦不到**。`literal_zh_cn.tsv` 里虽然已收了一批第三方词条
（Pipez / Dark Utilities / Cloud Storage / Mekanism / Create…），靠 String 路径
偶尔生效，但**不保证**界面变中文。

→ 结论：第三方模组**只能靠补语言文件**解决。

---

## 二、实施状态（✅ 已建成）

> 本通道已实现并接入管线，门禁已验证。**当前待办与全量清单见
> [`cn-vendor-plan.md`](cn-vendor-plan.md)**（本文只留查证过程与设计决策）。

| 层 | 内容 | 落点 |
|---|---|---|
| 数据层 | 扫描 `mods/*.jar` 的 `assets/<ns>/lang/{en_us,zh_cn}.json`，算缺键与伪翻译 | `tools/cnrebase/vendor.py` |
| 译料层 | 第四份 TSV（键按 `namespace` 绑定） | `translations/cn-rebase/vendor_lang_zh.tsv` |
| 构建层 | 叠加生成 `assets/<ns>/lang/zh_cn.json` 打进汉化 jar | `build.py` 第 2.5 段 |
| 清单层 | `todo-vendor.tsv` / `vendor-scan.json` / `term-table.json` | `report.export_todo` |
| 回填层 | `apply-todo` 读 `zh` 列合并进译料层 | `cli.cmd_apply_todo` |
| 门禁层 | 逐键从产物回捞，验「第三方译料已写入产物语言表」 | `verify.verify_corpus` |

命令行开关：`--mods-dir`（补纯客户端模组，如 JEI / 小地图 / 优化类）、
`--no-vendor`（关掉该通道，只跑本体 5 个命名空间）。

### 三条生成规则（缺一不可）

```
最终 zh_cn = 模组自带 zh_cn（作底）  ∪  我方 vendor 译文（覆盖同名键）
```

1. **必须以自带 zh 为底**：语言文件是**整文件覆盖**语义，只写稀疏增量会把模组
   原有中文整片顶掉（`mekanism` 自带 1446 键、`occultism` 801 键）。
2. **只给有译文的命名空间生成文件**：我方 jar 与模组 jar 对同一路径是同路径竞争，
   顺序不由本项目控制，减少无意义竞争。
3. **`LANG_CHANNEL_NS` 排除集**（`the_vault` / `woldsvaults` / `kubejs` /
   `qolhunters` / `packmenu`）归语言表通道管，vendor 跳过，避免同一文件被两条
   通道分别写入。

### 术语一致性

`build/cn/todo/term-table.json` —— 从全包所有 jar 的语言文件反查出的
「英文原文 → 包内既有中文」（约 2.4 万条）。翻新模组前先查这里，沿用包内已有
译法（`Hedge → 树篱`、`Crux → 核心`、`Inferium → 下级`…），全包译名才统一。

---

## 三、为什么不该改 Mixin

要覆盖 Component / FormattedCharSequence 渲染路径就得改 Java 并**重编母版 jar**
（本管线目前不编译任何 Java），且 FCS 重排会牵动**宽度计算与自动换行**，
容易引出 UI 错位。**语言文件路线更精准、零风险**，只在遇到 lang 覆盖不到的场景
（自绘文本）时才考虑。

---

## 四、查证过程留档（0.34.1 首轮）

### 4.1 不是硬编码

逐个解包核对（0.34.1 服务端包内 408 个 mod jar），截图涉及的页签名**全部来自
语言键**：

| 页签显示 | 语言键 | 命名空间 | 该模组自带 zh_cn |
|---|---|---|---|
| AE Additions | `itemGroup.ae2additions.item_group` | `ae2additions` | ❌ 无 |
| Wold's Vaults | `itemGroup.woldsvaults` | `woldsvaults` | ❌ 无 |
| Storage Drawers | `itemGroup.storagedrawers` | `storagedrawers` | ❌ 无 |
| CreateDeco Metals | `itemGroup.createdeco.metals` | `createdeco` | ❌ 无 |
| CreateDeco Props | `itemGroup.createdeco.props` | `createdeco` | ❌ 无 |
| Pipez | `itemGroup.pipez` | `pipez` | ❌ 无 |
| Dark Utilities | `itemGroup.darkutils` | `darkutils` | ❌ 无 |
| Cluttered | `itemGroup.tabclutter_mod` | `luphieclutteredmod` | ❌ 无 |
| Cloud Storage | `itemGroup.cloudstorage` | `cloudstorage` | ❌ 无 |

**是「范围外」，不是「硬编码」，也不是「工具吃漏了已覆盖范围」。**

### 4.2 两类真实缺口

| 类型 | 处理方式 |
|---|---|
| **A. 已有通道内的缺口**（`woldsvaults` / `the_vault`） | 走 `todo-lang.tsv` 补译，**不改代码** |
| **B. 从未在范围内**（第三方模组） | 新增「第三方模组语言」通道（已建成） |

A 类是整合包本体，玩家天天看，**优先级最高**。

### 4.3 机制上为什么「表里有词条却仍是英文」

汉化模组的硬编码通道有边界：

- `TextComponentMixin`：只在 `TextComponent` 构造时改写 —— 只拦
  `Component.literal("...")`，且服务端线程跳过。
- `FontMixin`：注入了 `Font` 的 11 个方法，但**只有 3 个 String 重载真的调用
  `LiteralTranslator.translate`**（`drawShadow` / `draw` / `width`）；
  Component / FormattedCharSequence 那 8 个处理器是空壳。

JEI 页签名走「语言键 → TranslatableComponent → Component 渲染」，
**两条硬编码通道都拦不到**。`literal_zh_cn.tsv` 里虽收了一批第三方词条
（Pipez / Dark Utilities / Cloud Storage / Mekanism / Create…），靠 String 路径
偶尔生效，但**不保证**界面变中文。

→ 结论：第三方模组**只能靠补语言文件**解决。

### 4.4 一个容易误判的陷阱：伪翻译

`itemGroup.compressium` 在 Compressium 自带的 `zh_cn.json` 里**存在**，
但值是 `Compressium` —— 与英文完全相同。于是「有中文文件」却仍是英文页签。
`vendor.ModLang.fake()` 专门识别这一类，共 1434 条 / 85 个命名空间。

另有一类**不该进待译清单**的条目：原文去掉 printf 占位符后不含字母
（`cropTier...1 = "1"`、`tooltip...buff_line = " - %s (%s)"`）。中文原文就该与
英文逐字相同，收进清单只会制造永远清不清的尾巴。判据见 `vendor._has_letter`。

### 4.5 曾待确认、现已闭环的前提

0.34.1 首轮曾提出：`itemGroup.woldsvaults` 在本方语言文件里有译文却显示英文，
需先确认①实例 `mods/` 里有汉化 jar②游戏语言是简体中文③启动的是汉化版实例。

现已闭环：本轮 `all --strict` 门禁含「汉化 jar 已注入 `mods/`」「注入的 jar 与
构建产物字节一致」「语言键译料已写入产物」三条，均为 OK；页签通道也已全量补齐。
