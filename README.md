# Wold's Vaults 简体中文版（0.34.1-CN）

基于官方整合包 **Wold's Vaults - Vault Hunters Expansion 0.34.1**（作者 iwolfking，CurseForge 项目 ID 957311）的全模组简体中文汉化。

本仓库分发的是**汉化层**，不是 Mod 本体。445 个第三方模组不在这里，安装时由启动器从 CurseForge 按官方清单下载。

## 下载

在 [Releases](../../releases) 页面取两个文件：

| 文件 | 用途 |
|---|---|
| `WoldsVaults-0.34.1-CN-Client-PCL.zip` | 客户端，PCL 导入安装 |
| `WoldsVaults-0.34.1-CN-Server.zip` | 服务端，跑安装脚本即可开服 |

> 文件大小与 SHA-256 校验值见 Release 的说明。

## 客户端安装

1. 打开 PCL2 → 左侧「**导入整合包**」→ 选择下载好的 `…-Client-PCL.zip`。
2. PCL 会自动下载 Forge 1.18.2-40.3.11、Minecraft 和清单里的 445 个模组，**需要联网**。下载量约 700 MB，取决于你的网络，慢的话请耐心等待，挂代理通常能解决。
3. 导入完成后，启动器会把我们的汉化配置和汉化模组放进 `overrides/` 对应的位置。
4. 内存分配：450 个模组的整合包很吃内存，**建议至少分 8 GB**；作者本机设的是 27 GB，机器差的话先在整合包首选项里调小、跑不起来再往上加。
5. 首次进游戏：选项 → 语言设为 **简体中文**；资源包里如有官方英文内容，把中文资源包置顶。

## 服务端安装

1. 确保已安装 **Java 17**（不是 Java 8，Forge 40.x 会直接报 `UnsupportedClassVersionError`）。
2. 把 zip 解压到想开服的目录，**不要放在有中文或空格的路径下**。
3. Windows 双击 `install.bat`（Linux/Mac 先 `chmod +x install.sh` 再执行）。
4. 脚本会下载官方服务端包（约 638 MB）并校验 MD5，然后把汉化层覆盖进去。若下载失败，脚本会提示你手动把 `official-wolds-vaults-server-pack-0-34-1.zip` 放到同一目录后重跑。
5. 完成后：
   - 想开**常规服**，直接用 `server.properties`；
   - 想开**硬核服**，把 `server.properties.hardcore` 改名为 `server.properties` 覆盖它。
6. `eula.txt` 已预置为 `eula=true`。**运行代表你已阅读并同意 [Mojang EULA](https://aka.ms/MinecraftEULA)。**
7. 启动：`run.bat` / `run.sh`（由官方服务端包自带），首次启动会生成世界，耗时几分钟。

## 汉化是怎么做的

不是简单的资源包，三层通道叠加：

1. **语言键**：为各模组命名空间生成 `assets/<ns>/lang/zh_cn.json`，通过汉化模组的资源包注册进游戏。
2. **硬编码字面量**：the_vault 与 woldsvaults 有大量直接写在代码里的英文（UI 标签、天赋/能力树的 `"\n Percentage Damage Absorbed: "` 这类），走 Mixin 拦截 `new TextComponent(String)` 和字体绘制，在渲染前查表替换。为此配了**上下文闸门** `LiteralContextGuard`——只在 GUI 语境替换，聊天框、命令、书与笔、告示牌、网络包一律放行不译。
3. **配置载荷**：`config/the_vault/` 下的 JSON（技能描述、研究、词条、图鉴）在构建期翻译，由汉化模组在启动时写回实例目录。数据主键（`researches.json` 的 `name` 等）**刻意保留英文原文**——之前翻成中文导致研究界面 NPE，是本项目的头号事故。

## 已知残留

- 少数纯辅助性模组（shader、部分 UI 小工具等）未翻译，不影响主线玩法。
- the_vault 研究界面底部仍有少量英文，来自 Mod Clone 走实时本地化 API 的字符串，没有稳定的拦截点。
- `config` 里少量颜色标记字段是中文，仅为可读性无影响。

## 声明

- 整合包本体与全部模组的版权归各自作者所有，本项目只做翻译。
- 若你是权利方且不希望作品出现在他这里，请开 issue 或发邮件，会第一时间移除。
- 本仓库不含任何第三方模组的 jar 或安装包云数据。

## 仓库结构

```
docs/                    事故复盘、覆盖计划、未汉化模组清单等
tools/cnrebase/          重基底流水线（CLI、构建、校验、术语）
translations/cn-rebase/  译料层：语言键 / 硬编码字面量 / 配置 / 第三方语言表
templates/               汉化模组母版 jar 与锁文件
```

译料层是项目的真正资产：四个 TSV + 一份 `config_extra.json`，按「英文原文 → 中文」存
储，整合包升级后可以重基底复用，不必重翻。
