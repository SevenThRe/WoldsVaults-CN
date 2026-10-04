"""服务端开服预设：普通世界 / 天空宝库两套 server.properties + 增强版安装脚本。

为什么需要
----------
官方服务端包只发一份 ``server.properties``，其中 ``level-type=minecraft:normal``。
想开天空宝库（VoidHunters 玩法）必须手动改三处，且**改错任何一个都会让服务端
起不来或生成纯虚空**，服主往往是在反复试错中才摸清正确组合：

1. ``level-type``      —— 必须是 ``skyblockbuilder:skyblock``（VoidWorldType）
2. ``generator-settings`` —— 留空 ``{}`` 即可；填了反而会覆盖 VoidWorldType 的设置
3. 删掉已有 ``world/``  —— level-type 只在**首次生成世界**时生效，改了不重开世界没用

本模块把「原始」和「天空宝库」两份都放进包里，并让 ``install.bat`` 在装完
Forge 后询问一次要哪套，按选择复制对应文件到 ``server.properties``。

level-type 的实证依据
---------------------
``SkyblockBuilder 3.3.33`` 的 ``Registration`` 静态块构造了两个
``ForgeWorldPreset``，由 libx 以 ``modid``（``@Mod`` 注解值 = ``skyblockbuilder``）
注册进 level-type 注册表：

* ``skyblockbuilder:skyblock``  → ``VoidWorldType``  （虚空天空宝库，本模块用这个）
* ``skyblockbuilder:skylands``  → ``SkylandsType``   （浮空岛另一种玩法）

两者 ``createChunkGenerator`` 最终都产出 ``SkyblockNoiseBasedChunkGenerator``，
所以本项目 SkyblockAddon 的 Terralith 拦截对两者都生效。

⚠️ ``level-type`` 在 properties 文件里要写成 ``skyblockbuilder\\:skyblock``
（冒号需转义），这是 vanilla ``Properties`` 格式的硬性要求，写成 ``:`` 会被
解析成键 ``skyblockbuilder`` 而非 ``skyblockbuilder:skyblock``。
"""

from __future__ import annotations

#: 普通世界预设的 level-type（与官方包一致，保持默认行为不变）
LEVEL_TYPE_NORMAL = "minecraft\\:normal"

#: 天空宝库（虚空）预设。冒号按 properties 规范转义。
LEVEL_TYPE_SKYBLOCK = "skyblockbuilder\\:skyblock"

#: 另一种浮空岛玩法。保留在文档里，默认不启用。
LEVEL_TYPE_SKYLANDS = "skyblockbuilder\\:skylands"

#: 包内预设文件名（放在包根，与官方 server.properties 同级）
#: 刻意用 ASCII 文件名：install.bat 必须纯 ASCII，而它要引用这些文件，
#: 中文名会逼着 bat 里出现非 ASCII 字符，触发 cmd.exe 的断行/块错位问题。
PRESET_NORMAL = "server.properties.normal"
PRESET_SKYBLOCK = "server.properties.skyblock"
PRESET_README = "SERVER-PRESETS.txt"

#: 增强版安装脚本（替换官方那一行 java 调用）
INSTALL_SCRIPT = "install.bat"
INSTALL_SCRIPT_SH = "install.sh"


def _readme(pack_version: str) -> str:
    return f"""\
Wold's Vaults {pack_version} 服务端 —— 开服预设
================================================

install.bat 装完 Forge 后会问你要哪套世界：

  [1] 普通世界   level-type = minecraft:normal
      原版地形，正常探索挖矿开 Vault。

  [2] 天空宝库   level-type = skyblockbuilder:skyblock
      全虚空，玩家用 /island create 领自己的悬浮岛。
      已预装汉化版 Sky Vaulters Support：自动生成悬浮宝库祭坛主城，
      并修好了 Terralith 导致的天空生成失效。

注意
----
· level-type 只在【首次生成世界】时生效。已经跑过的世界改了也不会变，
  必须备份并删除 world/ 文件夹再重启。
· 天空宝库需要客户端也装 SkyblockBuilder。整合包客户端版已自带。

手动切换
--------
  copy server.properties.skyblock server.properties
  （换回普通世界则用 server.properties.normal）
  改完记得删 world/ 文件
"""


def _server_properties(base: str, level_type: str) -> str:
    """在原始 server.properties 基础上改 level-type，其余原样保留。"""
    out = []
    hit = False
    for line in base.splitlines():
        if line.startswith("level-type="):
            out.append(f"level-type={level_type}")
            hit = True
        else:
            out.append(line)
    if not hit:
        out.append(f"level-type={level_type}")
    return "\n".join(out) + "\n"


#: 增强版 install.bat。
#: 纯 ASCII（中文注释会触发 cmd.exe 断行/块错位，见 memory 里的记录），
#: CRLF 行尾，无 BOM。
INSTALL_BAT = """\
@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================================
echo  Wold's Vaults - Server Setup
echo ============================================================
echo.

where java >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Java not found in PATH.
    echo         Minecraft 1.18.2 requires Java 17. Install JDK 17 and retry.
    pause
    exit /b 1
)

echo [1/2] Installing Forge server...
java -jar forge-1.18.2-40.3.11-installer.jar --installServer
if errorlevel 1 (
    echo [ERROR] Forge installation failed.
    pause
    exit /b 1
)
echo.

echo [2/2] Choosing world type...
echo.
echo   [1] Normal world     - vanilla overworld (default)
echo   [2] Sky Vaults       - void skyblock, players get their own island
echo.
set /p CHOICE="Select 1 or 2 (default 1): "

if /i "%CHOICE%"=="2" (
    if exist server.properties.skyblock (
        copy /y server.properties.skyblock server.properties >nul
        echo.
        echo [OK] server.properties set to SKY VAULTS (skyblockbuilder:skyblock).
        echo      Existing world folder is NOT removed automatically.
        echo      If a world already exists and you want the new type to apply,
        echo      back it up and delete it, then start the server again.
    ) else (
        echo [ERROR] server.properties.skyblock not found next to this script.
        pause
        exit /b 1
    )
) else (
    if exist server.properties.normal (
        copy /y server.properties.normal server.properties >nul
        echo.
        echo [OK] server.properties set to NORMAL (minecraft:normal).
    ) else (
        echo [ERROR] server.properties.normal not found next to this script.
        pause
        exit /b 1
    )
)

echo.
echo ============================================================
echo  Setup done. Start the server with run.bat
echo  Read SERVER-PRESETS.txt for details and switching later.
echo ============================================================
pause
"""


#: 增强版 install.sh（Linux/macOS，与 bat 同一套预设）
INSTALL_SH = """\
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

echo "============================================================"
echo " Wold's Vaults - Server Setup"
echo "============================================================"
echo

if ! command -v java >/dev/null 2>&1; then
    echo "[ERROR] java not found in PATH."
    echo "        Minecraft 1.18.2 requires Java 17."
    exit 1
fi

echo "[1/2] Installing Forge server..."
java -jar forge-1.18.2-40.3.11-installer.jar --installServer
echo

echo "[2/2] Choosing world type..."
echo "  [1] Normal world   - vanilla overworld (default)"
echo "  [2] Sky Vaults     - void skyblock, players get their own island"
echo
read -r -p "Select 1 or 2 (default 1): " CHOICE || true

if [ "${CHOICE:-1}" = "2" ]; then
    if [ -f server.properties.skyblock ]; then
        cp server.properties.skyblock server.properties
        echo
        echo "[OK] server.properties set to SKY VAULTS (skyblockbuilder:skyblock)."
        echo "     An existing world folder is NOT removed automatically."
    else
        echo "[ERROR] server.properties.skyblock not found."
        exit 1
    fi
else
    if [ -f server.properties.normal ]; then
        cp server.properties.normal server.properties
        echo
        echo "[OK] server.properties set to NORMAL (minecraft:normal)."
    else
        echo "[ERROR] server.properties.normal not found."
        exit 1
    fi
fi

echo
echo "============================================================"
echo " Setup done. Start the server with run.sh"
echo " See SERVER-PRESETS.txt for details and switching later."
echo "============================================================"
"""


def build(base_properties: bytes, pack_version: str = "unknown") -> dict[str, bytes]:
    """生成预设文件与增强版安装脚本。

    :param base_properties: 官方包内原始 ``server.properties`` 字节
    :param pack_version: 整合包版本，仅用于说明文档抬头
    :return: ``{包内相对路径: 内容字节}``
    """
    base = base_properties.decode("utf-8")
    files: dict[str, bytes] = {
        PRESET_NORMAL: _server_properties(base, LEVEL_TYPE_NORMAL).encode("utf-8"),
        PRESET_SKYBLOCK: _server_properties(base, LEVEL_TYPE_SKYBLOCK).encode("utf-8"),
        PRESET_README: _readme(pack_version).encode("utf-8"),
    }
    # bat 必须是 CRLF + 无 BOM + 纯 ASCII，否则 cmd.exe 会断行/错乱。
    files[INSTALL_SCRIPT] = INSTALL_BAT.replace("\n", "\r\n").encode("ascii")
    files[INSTALL_SCRIPT_SH] = INSTALL_SH.encode("utf-8")
    return files


def verify(files: dict[str, bytes], base_properties: bytes) -> list[str]:
    """对产物下断言。返回问题列表，空列表表示通过。"""
    problems: list[str] = []
    base = base_properties.decode("utf-8")

    for name, expect in ((PRESET_NORMAL, LEVEL_TYPE_NORMAL), (PRESET_SKYBLOCK, LEVEL_TYPE_SKYBLOCK)):
        if name not in files:
            problems.append(f"缺少预设文件 {name}")
            continue
        text = files[name].decode("utf-8")
        if f"level-type={expect}" not in text:
            problems.append(f"{name} 的 level-type 不是 {expect}")
        #除 level-type 外必须与原始包一致，避免手抖改坏别的键
        src = {l for l in base.splitlines() if not l.startswith("level-type=")}
        dst = {l for l in text.splitlines() if not l.startswith("level-type=")}
        if src != dst:
            only_src = sorted(src - dst)[:3]
            only_dst = sorted(dst - src)[:3]
            problems.append(f"{name} 除 level-type 外与原始不一致：缺{only_src} 多{only_dst}")

    bat = files.get(INSTALL_SCRIPT)
    if bat is None:
        problems.append("缺少 install.bat")
    else:
        if b"\r\n" not in bat:
            problems.append("install.bat 不是 CRLF 行尾")
        if bat[:3] == b"\xef\xbb\xbf":
            problems.append("install.bat 带 BOM")
        try:
            bat.decode("ascii")
        except UnicodeDecodeError as e:
            problems.append(f"install.bat 含非 ASCII 字符：{e}")
        if b"server.properties.skyblock" not in bat:
            problems.append("install.bat 未引用天空宝库预设")
        #必须明显长于官方那行调用，否则说明增强脚本被静默丢弃了
        if len(bat) < 500:
            problems.append(
                f"install.bat 仅 {len(bat)} 字节，疑似仍是官方原始脚本"
                "（检查 inject 是否走了 replace 通道）"
            )

    return problems


def verify_pack_mutation(zf, base_properties: bytes) -> list[str]:
    """对**产物 zip** 再校验一次。

    单测 ``verify`` 只能证明生成函数没问题，证明不了这些字节真的进了包。
    这里专门覆盖一个已踩过的坑：``rewrite_zip`` 的 ``add`` 字典对源包已存在的
    同名条目是**静默跳过**的，所以增强版 install.bat 曾经被无声丢掉，产物里
    仍留着官方那 61 字节 —— 而所有中间断言都是绿的。
    """
    problems: list[str] = []
    names = set(zf.namelist())

    for name in (PRESET_NORMAL, PRESET_SKYBLOCK, INSTALL_SCRIPT,
                 INSTALL_SCRIPT_SH, PRESET_README):
        if name not in names:
            problems.append(f"产物包内缺少 {name}")

    if INSTALL_SCRIPT in names:
        bat = zf.read(INSTALL_SCRIPT)
        if len(bat) < 500:
            problems.append(
                f"产物包内 install.bat 仅 {len(bat)} 字节 —— "
                "增强脚本没有真正替换官方脚本（add 通道对同名条目静默跳过，必须用 replace）"
            )
        if b"\n" in bat.replace(b"\r\n", b""):
            problems.append("产物包内 install.bat 存在裸 LF（cmd.exe 下可能出问题）")

    # 天空宝库预设必须真的改了 level-type，而不是把普通那份复制了一遍
    if PRESET_SKYBLOCK in names:
        text = zf.read(PRESET_SKYBLOCK).decode("utf-8")
        if f"level-type={LEVEL_TYPE_SKYBLOCK}" not in text:
            problems.append(
                f"产物包内 {PRESET_SKYBLOCK} 的 level-type 不是 {LEVEL_TYPE_SKYBLOCK}"
            )
    if PRESET_NORMAL in names:
        text = zf.read(PRESET_NORMAL).decode("utf-8")
        if f"level-type={LEVEL_TYPE_NORMAL}" not in text:
            problems.append(
                f"产物包内 {PRESET_NORMAL} 的 level-type 不是 {LEVEL_TYPE_NORMAL}"
            )

    return problems
