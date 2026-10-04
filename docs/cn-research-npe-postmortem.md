# 复盘：0.34.1 客户端「研究界面打不开」事故

> 现象一句话：**点开宝库书里的任意研究会直接报错、界面弹不出来。**
> 用户同时反馈「部分内容还是英文」——那是**另一件事**，见第五节。

---

## 一、现象

```
java.lang.NullPointerException
    at iskallia.vault.client.gui.screen.ResearchDialog.render(...)
```

`ResearchDialog` 的 `render()` 在偏移 65-72 处读 `descriptionComponent` 字段并
`setBounds(...)`，**没有任何空值检查**；一旦该字段为 `null` 就抛 NPE，整个界面
渲染中断 → 玩家看到的是「点了没反应 / 直接报错」。

---

## 二、根因

### 2.1 崩溃链（字节码 + 数据双向核实）

```
ResearchDialog.researchName
  ← ResearchesGUIConfig.getStyles() 的【键】（英文）
  → ResearchConfig.getByName(name)            // 查不到 → null
  → ResearchTree.getResearchCost(null)        // 偏移处解引用 → NPE
  → 中断 update()，descriptionComponent（偏移 199 才赋值）恒为 null
  → render() 偏移 65-72 解引用 → NPE
```

**真正的问题在数据，不在代码。**

`getStyles()` 返回的**键**是英文，而旧版汉化把 `researches.json` 里
`name` 字段**翻译成了中文**：

| 指标 | 旧版载荷（坏） | 修复后 |
|---|---|---|
| `researches.json` 的 `name` | 95 处 / 94 个不同值，**94 个是中文** | 95 处 / 94 个不同值，**0 个中文** |
| `researches_gui_styles.json` 的键 | 91 个（英文，从未被翻译） | 同左 |
| 两者**交集** | **1 / 95** | **95 / 95** |

交集 1/95 → `getByName` 查到的永远是 `null` → 必崩。

### 2.2 为什么会翻译「主键」

这是**翻译粒度**的问题，不是手误。旧的构建流程把 config 当成「文本文件」，
按 `(target, pointer)` 逐条回填中文。对 `researches.json` 的 `name`，
**人眼看到的就是一个名字**，翻它完全合理 —— 但游戏拿这个字段当**主键**用。

**「看起来像显示文本」和「实际是主键」在 JSON 里长得一模一样**，
这是这类事故的结构性成因。

### 2.3 母版其实有兜底，但兜底有损

母版的 `ResearchDialogMixin` 走的是**相反方向**：

```java
@ModifyVariable(...)  // setResearchName 入参
@Inject(method = "update()V", at = @At("HEAD"))  // 字段
→ 都调用 LiteralTranslator.translateBack(...)   // 中 → 英
```

也就是说**母版作者的原意就是「配置里放中文、渲染/查找前译回英文」**。

但 `translateBack` 的反查表**一对多，且大小写/空格敏感**：

* 118366 条对照表 → **68929 个不同中文，其中 46099 个映射到多个英文**
* 实测 `researches.json` 还原错 **3 条**：
  `Stack Upgrading` → `Stack Upgrade`、`Backpacks` → `backpack`、
  `RFTools Storage` → `RF Tools Storage␠`（带尾空格）

**这是不可靠的逆变换**，所以修复方向选「主键保持英文原名」——
这样 `translateBack` 恒为**恒等变换**，反查表的缺陷再也碰不到。

---

## 三、修复

### 3.1 数据层：把主键回写成英文原文

`tools/cnrebase/build.py` 新增：

```python
PROTECTED_FIELDS: dict[str, frozenset[str]] = {
    "config/the_vault/researches.json":     frozenset({"name"}),
    "config/the_vault/eternal_aura.json":   frozenset({"name", "value"}),
    "config/the_vault/vault_chest.json":    frozenset({"name", "value"}),
}
```

合并**之后**调 `_restore_identifier_fields(merged, base, fields)`，
把受保护字段强制回写成**新版英文原文**。本轮实际回写：

| 配置 | 回写处数 |
|---|---|
| `researches.json` | 94 |
| `eternal_aura.json` | 15 |
| `vault_chest.json` | 16 |

**显示层不受影响**：`TextComponentMixin`（`@Inject` 到 `TextComponent.<init>(String)`，
改写 `f_131283_`）+ `FontMixin`（11 个 Font 重载方法）在**渲染时**按
`literal_zh_cn.tsv` 把英文名正向译成中文。所以玩家看到的仍然是中文。

### 3.2 门禁层：四向守（`verify.py`【8】）

光「主键不许中文」不够 —— 那会把界面修成英文。所以守**两个方向、四条**：

| # | 断言 | 防的是 |
|---|---|---|
| 1 | 保护配置的标识符字段保持英文 | 崩溃复现 |
| 2 | 受保护配置的样式键能被其 `name`/`id` 覆盖 | 交集重新掉下来 |
| 3 | 回写为英文的主键在字面量对照表里有中文 | **「修好崩溃、界面反而变英文」** |
| 4 | 英文主键不会被中文反查表改写 | `translateBack` 把英文名反向改坏 |

两条实现注意（都踩过坑）：

* 载荷是 `\uXXXX` 转义的，**必须解一层 JSON 再判中文**。直接在字节流上跑 CJK
  正则会得到「没有中文」的假绿灯。
* 第 2 条**只查受保护配置自己的同名样式表**，不横扫全部 `*_gui_styles.json`。
  同目录 `greed/greed_gui_styles.json` 的 117 个键属于 `greed_nodes.json` 的
  `tree.skills[].id`，按文件名硬配对会误报，把门禁变成噪声源。

### 3.3 产物层

`cli all --strict` 全量重建，**94 项门禁全绿**。四件产物 + 升级补丁全部重出。

---

## 四、验证（实测）

### 4.1 门禁

```
【8】配置数据标识符
  OK   保护配置的标识符字段保持英文  核对 3 个配置
  OK   受保护配置的样式键能被其 name/id 覆盖  1 组配对全部对齐
  OK   回写为英文的主键在字面量对照表里有中文  复核 114 个显示名
  OK   英文主键不会被中文反查表改写  复核 114 个显示名
结果: 94 项全部通过 ✓
```

114 = `researches.json` 94 个不同名 + `eternal_aura.json` 13 个 + `vault_chest.json`
7 个显示名。

### 4.2 独立复核（不看门禁自报，自己拿产物算）

对 `client_payload_0291`（**客户端真正分发的那一份**，由 `manifest_client.txt` 指向）
逐字段查中文：

| 配置 | `name`/`value` 处数 | 仍是中文 | 无中文译文 |
|---|---|---|---|
| `researches.json` | 95 | **0** | **0** |
| `eternal_aura.json` | 26 | **0** | **0** |
| `vault_chest.json` | 25 | **0** | 2（`Plating` / `Zoomies`，在 `value` 上） |

玩家实际落地的两份也要干净（首启读的是 `overrides/`，之后每次启动被载荷重写）：

```
客户端 PCL 包  overrides/config/the_vault/researches.json : 95 处 / 含中文 0
服务端包        config/the_vault/researches.json           : 95 处 / 含中文 0
```

### 4.3 补丁

`WoldsVaults-0.34.1-CN-Patch.zip` 12.8 MB，内含 jar 与 `dist/` 产物**逐字节一致**，
sha256 前 16 位 `C1019E5E3AA24BC5`。

补丁生成器 `tools/cnrebase/make_patch.py` 早期把**上一轮 jar 的 sha256 写死在
断言里** —— 重基底一跑 jar 就变，断言必然失败。那是**假守卫**：它只证明
「文件没变」，不证明「修好了」。现已改为对**产物内容**下断言
（受保护字段无中文 + 显示名有中文译文 + 双端 `overrides/` 干净）。

---

## 五、用户反馈的「部分内容还是英文」

**与崩溃无关，是另一件事。** 已归因成两处：

### 5.1 研究说明缺失（38/91）—— **上游内容缺口，不是我们弄坏的**

说明来自 `SkillDescriptionsConfig.getDescriptionFor(name)`，读
`config/the_vault/skill_descriptions.json`（442 键）+ 本地化覆盖
`config/the_vault/lang/<locale>/skill_descriptions.json`。

**界面上能点开的 91 个研究里，上游只给了 53 条说明**，剩下 **38 条**落回硬编码兜底
`No description for X, yet`（Advanced Peripherals、Ars Nouveau、Bag Inception、
Bonsai Pots、Botanical Machinery、Cable Tiers…）。另有 2 条有说明但无中文。

→ 这是**内容活**（要我们凭空补 38 条研究说明），不是 bug 修复，需用户拍板后再开工。

### 5.2 显示名缺失（2 条）

`vault_chest.json` 的 `pool[].value` 里 `Plating` / `Zoomies` 在对照表里没有中文。
**注意**：门禁第 3 条只看 `name`（`value` 是查表键、通常不直接显示），所以门禁是绿的
—— 这两条属于「补了也未必有用」的待确认项，正在核实 `pool[].value` 是否真的会进渲染层。

---

## 六、顺带发现的同类隐患（不崩，但机制静默失效）

| 配置 | 机制 | 旧版症状 |
|---|---|---|
| `eternal_aura.json` | `EternalAuraConfig.getByName` 按 `name` 匹配，`availableAuras[].value` 引用它 | 永久光环查不到 |
| `vault_chest.json` | `VaultChestConfig.getEffectByName` 解析 `LEVELS[].pool[].value` | `Optional.map` 链整段跳过 → **该类陷阱被静默丢弃** |

两者都已在 `PROTECTED_FIELDS` 里保护。

**同时确认「不要扩大范围」**（否则界面会变英文）：

* `talents.json` / `expertises.json` 的 `name` —— `TalentsConfig.getTalentById(String)`
  与 `ExpertisesConfig.getAll()` 遍历，`SkillGates` 判前置一律用 `Skill.getId()`，
  `name` 是**纯显示文本**
* `researches_groups.json` 的 `title` —— 组的主键是 JSON 键（`Special`/`Omega`），
  从未被翻译

---

## 七、教训（已进项目记忆）

1. **config 里的「数据标识符」字段绝不能翻。**
   判据不是「字段名叫什么」，而是**字节码里它被喂给了谁** ——
   喂给 `getByName`/`getEffectByName`/`Map.get` 的就是主键。
   → 项目记忆规则 13。
2. **有损的逆变换不是兜底。** `translateBack` 的反查表 2/3 的中文是一对多，
   拿它当「翻译后还原」的安全网，等于把随机性引进主键。
3. **门禁要守双向。** 只守「主键不许中文」会把界面修成英文；
   必须同时守「显示名有中文译文」。
4. **假守卫比没有守卫更危险。** 写死 sha256 的断言会在每次重基底后失败，
   而人会习惯性地把它改掉 —— 改成对**内容**下断言。
5. **宿主对「已存在文件」的修改会被拒**（`os.replace` 也不再放行）。
   写文件统一走 `tools/cnrebase/fsutil.py`：兜底动作 = `nt.remove`（清只读后）
   + 新建，并同时接管 `builtins.open`/`io.open`（`zipfile` 与 `shutil.copyfile`
   不走 `pathlib`）。→ 项目记忆规则 6、用户记忆规则 6。
