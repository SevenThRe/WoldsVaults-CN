# 可选模组决策书：I18nUpdateMod 与 IMBlocker

面向 Wold's Vaults **0.34.1** 汉化包。全部结论由**实测对撞**得出，不是推断。

对撞样本：

| 文件 | 说明 |
|---|---|
| `E:\...\versions\Wold's Vaults 汉化版\resourcepacks\Minecraft-Mod-Language-Modpack-Converted-1.18.2.zip` | I18nUpdateMod 3.7.0 在**验收实例**上真实生成的那份包（3,870,993 B） |
| `build/cn/dist/WoldsVaults-CN-Lang-0.34.1.zip` | 我方汉化资源包（229 ns / 59,013 条） |
| `E:\...\versions\Wold's Vaults 汉化版\mods\*.jar` | 验收实例实测 445 个 jar → 337 个 asset 命名空间 |

### 0. 先说一个更要紧的发现：验收实例根本没装我方 Lang 包

```
[mods]                             445 项
   → I18nUpdateMod-3.7.0-all.jar
   → IMBlocker-5.6.1-forge+1.17-1.20.4.jar
   → woldsvaults_cn-1.0.17-0.34.1-universal.jar      ← 我方 jar 在
[config/openloader/resources]        2 项
   → AndersiteRemoval, VHBook.zip
   → ✘ 没有 WoldsVaults-CN-Lang.zip                   ← 我方资源包**不在**
[options.txt] resourcePacks
   [0] vanilla                          [5] packmenu
   [1] mod_resources                    [6] quark:emote_resources
   [2] Everycomp Generated Pack         [7] resources/AndersiteRemoval
   [3] Supplementaries Generated Pack   [8] resources/VHBook.zip
   [4] mod_resources:masuplots_injected [9] file/Minecraft-Mod-Language-Modpack-Converted-1.18.2.zip
```

客户端包 `WoldsVaults-0.34.1-CN-Client-PCL.zip` 里 **确实带了**
`overrides/config/openloader/resources/WoldsVaults-CN-Lang.zip` —— 是**手工拼装验收实例时漏拷了**。
所以那次验收跑的是「只有 I18n 一份第三方译文」的世界，**「AE 附属模组整包零中文」的真正原因在这里**，
不是 I18n 的问题，也不是我方译料的问题。

同时注意 `[9]`：**I18n 的包排在队尾＝最高优先级**。这直接推翻「它排在第 2 位所以无害」的旧结论。

---

## 一、I18nUpdateMod 3.7.0 —— 结论：**不要打进包**

### 1.1 它到底带来多少中文

| 口径 | 我方包 | I18n 包 |
|---|---|---|
| 命名空间（非空） | **229** | 1262 |
| 条目 | **59,013** | 185,072 |

单看总量 I18n 更大 —— 但那是**全 MC 生态的 CFPA 语料**，绝大多数命名空间属于**根本没装的模组**。限定到「实际已装的模组」，逐键对撞：

| 方向 | 命名空间 | 条目 |
|---|---|---|
| **I18n 相对我方包独有** | **8** | **95** |
| 我方相对 I18n 独有 | 110 | 15,439 |

I18n 那 95 条的完整明细（这是它全部的边际价值）：

| 命名空间 | I18n 独有 | I18n 总 | 我方总 | 说明 |
|---|---:|---:|---:|---|
| `xray` | 50 | 50 | **0** | 我方扫描漏掉整个 ns |
| `davebuildingmod` | 34 | 703 | 669 | 我方只取了 en 表里有的键 |
| `moremekanismprocessing` | 5 | 57 | 52 | 同上 |
| `irongenerators` | 2 | 55 | 53 | 同上 |
| `draconicevolution` | 1 | 728 | 764 | 同上 |
| `hexcasting` | 1 | 925 | 924 | 同上 |
| `packmenu` | 1 | 1 | 2 | 同上 |
| `reauth` | 1 | 66 | 65 | 同上 |

反过来我方独有 15,439 条，头部就是 I18n **完全没有**的：

```
create                2871   the_vault            2323
thermal               1075   woldsvaults          1053
rechiseled             959   ae2                   949
openpartiesandclaims   717   lightmanscurrency     672
occultism              595   dyenamicsandfriends   569
pneumaticcraft         312   botanypotstiers       295
```

> **为什么我方包反而更全**：`vendor.effective()` 的合并层级是
> **模组自带 `zh_cn` → CFPA 底 → 我方译料**。也就是说我方包除了 CFPA，
> 还顺手把每个模组 jar **自带的官方中文**并了进去。I18n 只搬 CFPA，
> CFPA 没有的（`create` / `the_vault` / `ae2` …）它就是空白。

### 1.2 那 95 条怎么拿 —— 不用装 I18n

`xray` 是我方扫描漏了 ns（`davebuildingmod` 等是「CFPA 有、en 表无」的键被 `effective()` 过滤掉了）。
把这 8 个命名空间补进我方 Lang 包即可 —— **同一份 CFPA 源头、结果一样、零外部依赖、零下载、可复现**。

### 1.3 装它的代价（这才是决定因素）

1. **每次启动同步阻塞下载 3.7 MB**。3 个源轮询（`raw.githubusercontent` / 502y 镜像 / buy-all-the-things 兜底），connect 3s / read 33s，**阻塞在游戏构造函数之前**。失败被 catch 掉 → 该次启动不应用（不崩，但你看到的是英文）。
2. **改写 `options.txt`（全局副作用）**。`ModLauncherService` 在 `Minecraft` 构造 `Options` 之前就把包 id 塞进去了。`GameConfig.addResourcePack` 的清理分支用的是
   ```java
   resourcePacks.removeIf(id -> id.contains("Minecraft-Mod-Language-Modpack"))
   ```
   **子串匹配** —— 任何 id 里含 `Minecraft-Mod-Language-Modpack` 的条目都会被静默删掉。我方包命名必须永久避开这个子串（当前 `WoldsVaults-CN-Lang.zip` 安全）。
3. **优先级已经翻转（实测）。** `addResourcePack` 只在 id **不存在**时才 `append` 置尾（存在则 `return`，顺序不动）。验收实例的实测结果就是**被顶到了队尾**：

   ```
   [8] resources/VHBook.zip
   [9] file/Minecraft-Mod-Language-Modpack-Converted-1.18.2.zip   ← I18n，最高优先级
   ```

   一旦我方 Lang 包也进来，它会落在 `resources/...` 一档（实测为 `[7]`/`[8]` 位置），**排在 I18n 之前＝优先级更低**。同键冲突时 CFPA 赢，我方译料被顶掉 ——
   例如 `pneumaticcraft`：我方 1982 条 / CFPA 1670 条 → 会**退化 312 条**。
   这不是理论风险，是当前实例的顺序决定的。
4. **跨大版本维护**。id 里的版本号来自 `--fml.mcversion`；升 MC 版本后旧 id 变孤儿，历史条目残留在 options.txt。
5. **350 / 1612 个命名空间是 2 字节的 `{}`**（含 `ae2`）。空表**不会清空任何键**（`Language.loadFromJson` 零次迭代），所以无害 —— 但也说明它对 `ae2` 本体毫无贡献，你看到的 AE2 中文来自**模组自带**的 857 条。

### 1.4 附带澄清：AE 家族到底缺什么

逐 jar 实测（`自带zh` = 模组 jar 内 `assets/<ns>/lang/zh_cn.json`）：

| jar | ns | 自带 zh | I18n | 我方包 | en |
|---|---|---:|---:|---:|---:|
| `appliedenergistics2-forge-11.7.6.jar` | `ae2` | **857** | 0 | **949** | 943 |
| `MEGACells-1.4.2-1.18.2.jar` | `megacells` | 0 | 52 | 52 | 52 |
| `AE2-Things-1.0.7.jar` | `ae2things` | 0 | 17 | 17 | 17 |
| `merequester-1.18.2-1.1.2.jar` | `merequester` | **21** | 0 | 0 | 21 |
| `ae2insertexportcard-1.18.2-1.0.0.jar` | `ae2insertexportcard` | **5** | 0 | 0 | 5 |
| `ae2searchimprovementsbackport-1.0-all.jar` | `ae2searchimprovements` | 0 | 0 | **2** | 2 |
| `ae2qolrecipes-forge-...-1.1.1.jar` | — | **无 lang 文件** | — | — | — |
| `ae2tabs-1.1.jar` | — | **无 lang 文件** | — | — | — |

要点：

- **AE2 本体自带 857 条官方中文**（91%），我方包补到 949 → 全覆盖。它显示英文 ≠ 翻译缺失。
- `ae2qolrecipes` / `ae2tabs` **jar 里连 `en_us.json` 都没有** → 文本是**硬编码**，语言文件通道**永远够不着**。I18n 也救不了。
- 真正需要排查的**不是**「装什么模组」，而是**这个实例根本没装我方的 0.34.1 产物**：
  实测 `versions\v\config\openloader\resources\` 下只有 `AndersiteRemoval` 与 `VHBook.zip`，
  **没有 `WoldsVaults-CN-Lang-*.zip`**；`mods\` 里挂的还是 0.30.0 时代的
  `woldsvaults_cn-1.0.16-0.30.0-universal.jar`（旁边还躺着一个 `.disabled` 的 1.0.15）。

---

## 二、IMBlocker —— 结论：**装，只进客户端包**

| 项 | 结论 |
|---|---|
| 上游 | `reserveword/IMBlocker`（`leitingsd` / `LitnhJacuzzi` 均为停更 fork） |
| 版本 | 本机实例实测 `[输入法冲突修复] IMBlocker-5.5.3-forge+1.17-1.20.4.jar`；Modrinth 现役 slug `imblocker-original` |
| 架构 | 5.x 是**纯 Mixin + 统一焦点管理层**（`FocusManager` / `MinecraftFocusContext` / `MinecraftScreenMonitor`），不是 2.x/3.x 那套「ASM 改 EditBox + BookEditScreen 白名单」 |
| 平台 | **不是 Windows 独占**。自动切输入法 / 命令框切英文：Windows + macOS + Linux 全支持；只有可选的「游戏内渲染输入法候选框」是 Windows 独占 |
| FTB Quests | 走 FTB Library 已被覆盖 |
| 未适配 | `the_vault` / JEI 不在适配清单 → 表现为**输入法不激活**（不会崩） |
| 放服务端 | **会崩**。issue #149「server compatibility」PR **closed 未合并**；`mods.toml` 无 `displayTest` / `clientSideOnly` |

**所以：只进 `overrides/mods/`，绝不进服务端包 `mods/`。**

---

## 三、落进构建要动什么

当前 `verify.py` 有一处硬契约会拦下 IMBlocker：

```python
# verify.py:475-477
jar_in = [n for n in names if n.startswith("overrides/mods/") and n.endswith(".jar")]
r.check(len(jar_in) == 1 and mod_version in jar_in[0], "汉化 jar 已注入 overrides/mods/", ...)
```

客户端包现在 `overrides/mods/` 里**恰好 1 个 jar**（`woldsvaults_cn-1.0.17-0.34.1-universal.jar`）。
加 IMBlocker 后变成 2 个 → 该断言必挂。

改法（**白名单式**，不是简单放宽）：

```python
jar_in = [n for n in names if n.startswith("overrides/mods/") and n.endswith(".jar")]
cnjar = [n for n in jar_in if mod_version in n]
extra = [n for n in jar_in if n not in cnjar]
bad   = [n for n in extra if not _is_whitelisted_extra(n)]
r.check(len(cnjar) == 1 and not bad,
        "汉化 jar 已注入 overrides/mods/（额外 jar 仅限白名单）", ...)
```

白名单常量建议放 `cli.py`，与 `_openloader_overrides` 同级：

```python
#: 允许多打的第三方 jar（只进客户端）。每项 (文件名前缀, 理由)。
CLIENT_EXTRA_JARS = {
    "IMBlocker-": "输入法冲突修复；纯客户端，服务端会崩（issue #149 未合并）",
}
```

服务端侧 `verify.py:540-543` 的 `len(injected) == 1` **不要动** —— 它正是防「客户端模组漏到服务端」的那道闸。

---

## 四、执行清单

0. **先把我方 Lang 包部署进实例**（这件事优先级最高，跟 I18n/IMBlocker 无关）：
   把 `build/cn/dist/WoldsVaults-CN-Lang-0.34.1.zip` 拷到
   `E:\...\versions\Wold's Vaults 汉化版\config\openloader\resources\`。
   验收脚本 `build/cn/work/prepare_acceptance.py` 只拷了 CN jar，漏了这一个 —— 需要一并补上。
1. **从客户端包与实例里移除 I18nUpdateMod**：`mods/I18nUpdateMod-3.7.0-all.jar` 删掉；
   同时删掉 `resourcepacks/Minecraft-Mod-Language-Modpack-Converted-1.18.2.zip`，
   并把 `options.txt` 里那条 `file/Minecraft-Mod-Language-Modpack-Converted-1.18.2.zip` 条目去掉。
2. 客户端包 `overrides/mods/` 加 `IMBlocker-5.6.2-forge+1.17-1.20.4.jar`（实例里现为 5.6.1）。
3. `verify.py` 的 jar 断言改**白名单式**；**服务端那条 `len(injected) == 1` 保持原样**。
4. 把 `xray` / `davebuildingmod` 等 8 个命名空间补进我方 Lang 包（来源同为 CFPA），补齐那 95 条。
5. 发布前 checklist（已入项目记忆）：本地包命名永久避开子串 `Minecraft-Mod-Language-Modpack`。

---

## 五、为什么「不装 I18n」是稳的

| 维度 | 不装 I18n，只用我方包 | 装 I18n |
|---|---|---|
| 第三方译文条目 | 59,013 | 59,013 + 95（其中 34 条是死键） |
| 启动开销 | 0 | 每次同步下载 3.7 MB（connect 3s / read 33s） |
| options.txt 副作用 | 无 | 每次启动改写；子串清理会误删同名条目 |
| 覆盖顺序 | 我方说了算 | 实测被顶到队尾，CFPA 反压我方（退化可达数百条） |
| 跨 MC 版本 | 重建即可（约 15s） | id 变孤儿，残留条目 |
| 维护面 | 1 个自研包 | 自研包 + 上游 jar 行为变更（需 `javap` diff 三个类） |
