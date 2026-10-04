# 复盘：0.34.1 客户端「宝库书乱码」事故

> 时间：2026-09-30 21:00–21:40
> 现象：朋友安装 `WoldsVaults-0.34.1-CN-Client-PCL.zip` 后，**宝库书（the_vault 内置任务界面）整屏乱码**；
> 作者本机（同一份包、同一个实例）**完全正常**。

---

## 一、根因

`the_vault` 模组读配置时**跟随系统/JVM 默认编码**：

```java
// iskallia.vault.config.Config.readConfig()  —— javap 字节码实证
17: new           #241  // class java/io/FileReader
25: invokespecial #246  // Method java/io/FileReader."<init>":(Ljava/io/File;)V
34: invokevirtual #258  // Method com/google/gson/Gson.fromJson:(Ljava/io/Reader;...)
```

`java.io.FileReader` 的字符集**不写死**，取 `Charset.defaultCharset()`。而
`config/the_vault/lang/zh_cn/*.json`（宝库书任务文本、技能描述、tooltip）
在 0.34.1 产物里是**原始 UTF-8 中文**，于是：

| 机器 | 默认编码 | 读 UTF-8 中文 |
|---|---|---|
| 作者本机（Java 21） | UTF-8 | ✅ 正常 |
| 朋友（Java 17） | 系统区域编码（GBK / Big5） | ❌ 乱码 |

**这不是我们的文件坏了** —— 包内 6057 个载荷文件改前就都是合法 UTF-8。
是读的一方按「系统编码」解释 UTF-8 字节。

### 差别的真正来源：**JVM 版本**，不是系统区域

| 机器 | 日志实证 | 默认字符集 | 读 UTF-8 中文 |
|---|---|---|---|
| 作者本机 | `logs/latest.log`：`java version 21.0.10 by Oracle Corporation` | **UTF-8**（Java 18+ 的 JEP 400 强制，与系统区域无关） | ✅ 正常 |
| 朋友（推断） | 1.18.2 的**官方推荐版本 Java 17** | 跟随系统区域（简中 GBK / 繁中 Big5） | ❌ 乱码 |

⚠️ 一开始我误判成「作者机器启动参数带 `-Dfile.encoding=UTF-8`」——那是
**我们自己验收脚本**（`build/cn/work/launch_cmd.txt`）加的，与用户 PCL 的真实启动无关。
用户 PCL 的 JVM 参数实测为：
```
-XX:-OmitStackTraceInFastThrow -Djdk.lang.Process.allowAmbiguousCommands=True
-Dfml.ignoreInvalidMinecraftCertificates=True -Dfml.ignorePatchDiscrepancies=True
```
**没有** `-Dfile.encoding`。差别在 Java 版本。

**影响面（重要）**：1.18.2 官方推荐 Java 17，所以**大多数玩家**都会踩这个坑，
朋友的乱码不是特例。修复不是可选项。

同一份产物里，**语言键**（任务概览、物品名）走原版 `LanguageManager`，字符集是
显式 UTF-8，所以在朋友的机器上**正常显示** —— 这正是「同一个界面里按钮正常、
正文乱码」的原因，也是定位的关键指纹。

## 二、排除过程（为什么确定是这一处）

逐条反编译核实，我方所有通道都是**显式 UTF-8**，不可能乱：

| 通道 | 读取方 | 字符集 | 结论 |
|---|---|---|---|
| `assets/*/lang/zh_cn.json` | vanilla `Language` | 显式 UTF-8 | 安全 |
| 任务书 `*.snbt` | FTB Library `SNBT.readLines` | 显式 `StandardCharsets.UTF_8` | 安全 |
| `literal_zh_cn.tsv` | 本模组 `LiteralTranslator` | `new String(bytes, UTF_8)` | 安全 |
| `config_payload/*` 落盘 | 本模组 `ConfigPayloadInstaller.copyResource` | `Files.copy(InputStream, Path)` **按字节** | 安全（但下游读取不安全）|
| **`config/the_vault/**/*.json`** | **`the_vault` `Config.readConfig`** | **`FileReader` = 系统编码** | ❌ **根因** |

另外扫了服务端包全部 349 个模组：50 个模组用了 `FileReader`/`FileWriter`，
其中吃我们译文的只有 `the_vault`（22 个类，整个配置系统共用这一个入口）。

## 三、修复

**思路**：JSON / JS 原生支持 `\uXXXX` 转义。把载荷里的非 ASCII 全部转义后，
文件变成**纯 ASCII** —— 任何默认编码（GBK / Big5 / cp1252 / UTF-8）读进来都无损，
解析出的字符串与原文**完全一致**。这样就不必依赖玩家去改 JVM 参数。

### 3.1 管线修复（对以后的每次构建生效）

`tools/cnrebase/build.py`：
- 新增 `_escape_non_ascii(text)`：非 ASCII → `\uXXXX`（含代理对），**只动 >127 的字符**，
  已有 ASCII 内容（含既有 `\uXXXX`、`\\` 转义）一个字节都不碰。
- 新增 `_ascii_escape_payload(payload)`：对 `config_payload/` 下全部 `.json` / `.js`
  统一转义；失败（非法 UTF-8）则记录进 `skipped` 并跳过。
- 在**打包前**（`_pack_jar` 之前，即章节 6.9）调用，统计存入 `RebaseResult.payload_escape`。

### 3.2 产物修复（本次已发布的包）

`build/cn/work/patch_payload_ascii.py`（一次性补丁，源包已无缓存、无法整体重建）：
按原条目顺序重写 zip，改写三处：

| 产物 | 改写 |
|---|---|
| `woldsvaults_cn-1.0.17-0.34.1-universal.jar` | 357 个载荷文件 / **262,433** 个非 ASCII 字符 |
| `WoldsVaults-0.34.1-CN-Client-PCL.zip` | 内嵌 jar + `overrides/config/**` 108 项 |
| `WoldsVaults-0.34.1-CN-Server.zip` | 内嵌 jar + 根 `config/**` 91 项 |

## 四、验证（实测）

```
载荷文件 6057 个 → 仍含非 ASCII 的: 0

任务文本 client_payload_0291/.../lang/zh_cn/quest/quests.json（201,048 B，纯 ASCII）
  当 gbk    读 → 解析成功，含中文串 956 条，样例: ['宝库猎人介绍', '欢迎来到宝库猎人第三版！']
  当 big5   读 → 解析成功，含中文串 956 条，样例: ['宝库猎人介绍', '欢迎来到宝库猎人第三版！']
  当 cp1252 读 → 解析成功，含中文串 956 条，样例: ['宝库猎人介绍', '欢迎来到宝库猎人第三版！']
  当 utf-8  读 → 解析成功，含中文串 956 条，样例: ['宝库猎人介绍', '欢迎来到宝库猎人第三版！']

客户端包  config 残留非ASCII=0   内嵌 jar 与 dist 一致=True
服务端包  config 残留非ASCII=0   内嵌 jar 与 dist 一致=True
```

**回归检查**：`repair_manifest_*.txt` 的哈希字段本来就是全零（母版遗留），
改前/改后都是 2452 条不匹配 → 本次转义**未改动修复清单语义**。

## 五、教训（已进项目记忆）

1. **「我方文件是对的」不等于「玩家看到的是对的」**。整条链路要按**最弱的一环**
   评判：任何一环用平台默认编码读文件，UTF-8 译文就会在非 UTF-8 系统上乱码。
2. **发往客户端的文本载荷，一律 ASCII 化**（`ensure_ascii=True` / `\uXXXX`）。
   代价接近零（zip 内 ASCII 压缩率更高），收益是对玩家系统区域完全免疫。
3. **机器差异是线索**：同一份包「作者正常、玩家乱码」→ 先查两边 JVM/系统默认编码，
   不要先怀疑文件。
4. **测试环境必须覆盖「最差的玩家环境」**。本次两条掩盖路径：
   - 我们的验收脚本启动时加了 `-Dfile.encoding=UTF-8`；
   - 作者本人 PCL 跑的是 Java 21（默认恒为 UTF-8）。
   两条都会让 UTF-8 中文「看起来没问题」。**验收环境 = Java 17 + 简中系统**
   （或繁中系统），否则这类编码缺陷永远测不出来。
