# Wold's Vaults 简体中文版（0.34.1-CN）

基于官方整合包 **Wold's Vaults - Vault Hunters Expansion 0.34.1**（作者 iwolfking）的汉化层。
第三方模组不随仓库分发，安装时由启动器或安装脚本按官方清单获取。

## 下载

[Releases](../../releases) 页面，校验值见 Release 说明：

| 文件 | 用途 |
|---|---|
| `WoldsVaults-0.34.1-CN-Client-PCL.zip` | 客户端：PCL2 →「导入整合包」选它 |
| `WoldsVaults-0.34.1-CN-Server.zip` | 服务端：解压后跑 `install.bat` / `install.sh` |
| `woldsvaults_cn-1.0.17-0.34.1-universal.jar` | 单独更新包：已装整合包的只需替换这一个 jar |

## 安装要点

- **客户端**：导入后需联网下载约 700 MB；内存建议 ≥ 8 GB；进游戏后选项 → 语言设为**简体中文**。
- **服务端**：必须 **Java 17**（Java 8 会 `UnsupportedClassVersionError`）；脚本自动下载官方服务端包（约 638 MB）并覆盖汉化层；`eula.txt` 已预置。
- 服务端含 `woldsvaults-skyblock-fix`：空岛删除命令与岛屿保护修复，需与 `skyblockaddon` 同时存在。

## 仓库结构

```
docs/                    事故复盘与覆盖清单
tools/cnrebase/          重基底流水线（构建、校验、打包）
translations/cn-rebase/  译料层：语言键 / 硬编码字面量 / 配置 / 第三方语言表
templates/               汉化模组母版 jar 与锁文件
```

译料层是项目的真正资产：整合包升级后重基底复用，不必重翻。

## 声明

整合包与全部模组的版权归各自作者所有，本项目只做翻译。权利方要求移除请开 issue，会第一时间处理。
