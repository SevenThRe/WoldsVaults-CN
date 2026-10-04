"""整合包注入：产出可直接拖进 PCL 的客户端包与可直跑的服务端包。

两条通路都要走
--------------
汉化模组是**自包含**的，三条读取通路都不依赖外部注入：

1. 语言文件 ``assets/<ns>/lang/zh_cn.json`` —— Forge 会把 mod jar 的 assets
   当作资源包挂载，自动参与语言查找。
2. 硬编码 —— ``LiteralTranslator`` 读 jar 内 ``literal_zh_cn.tsv``。
3. 配置文本 —— ``ConfigPayloadInstaller`` 启动时按 jar 内清单把载荷铺到
   ``config/`` 等位置。

第 1、2 条靠 jar 本身即可生效，但**第 3 条是运行期动作**：FTB 任务书、
帕秋莉手册、配置文本只有在装了汉化模组的游戏进程**启动之后**才会被写出来。
这意味着「打开整合包目录看文件」时它们仍是英文，玩家也无从判断汉化到底有没有生效。

所以本模块同时做两件事：

* 把 jar 放进 ``mods/``（``LiteralTranslator`` / 语言表靠它生效）
* **把载荷预置进包内**（``overrides/`` 或服务端包根目录），让中文在
  解压那一刻就物理存在

两者的内容完全一致，因此重复安装是幂等的——模组的 repair 清单带 SHA-256，
比对的是载荷自身摘要，不会与预置内容冲突。
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from tools.cnrebase import assets
from tools.cnrebase import serverpresets
from tools.cnrebase.packs import ClientPack, ServerPack, rewrite_zip

README_NAME = "汉化说明.txt"
META_NAME = "CN-BUILD.json"

#: 各侧需要落地的清单（install + repair）。
#: repair 清单条目数远多于 install（客户端 2452 vs 94），它才是配置文本的主体，
#: 只铺 install 会漏掉绝大部分 config。
SIDE_MANIFESTS: dict[str, tuple[str, ...]] = {
    "client": ("manifest.txt", "manifest_client.txt", "repair_manifest_client.txt"),
    "server": ("manifest.txt", "manifest_server.txt", "repair_manifest_server.txt"),
}


@dataclass
class InjectResult:
    path: Path | None = None
    kind: str = ""
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    #: 服务端开服预设（server.properties.normal / .skyblock / install.bat 等）
    presets: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "kind": self.kind,
            "file": self.path.name if self.path else None,
            "added_count": len(self.added),
            "removed": self.removed,
            "presets": self.presets,
            "zip": self.stats,
        }


# --------------------------------------------------------------------------- #
# 载荷预置
# --------------------------------------------------------------------------- #
def payload_targets(jar_path: Path | str, side: str) -> dict[str, bytes]:
    """从汉化 jar 解析出该侧要落地的全部文件：``{相对游戏目录路径: 内容}``。

    路径以**游戏目录**为基准（如 ``config/ftbquests/quests/x.snbt``）——
    调用方负责加 ``overrides/`` 前缀或直接放在服务端包根目录。
    """
    root = assets.PAYLOAD_IN_JAR
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(jar_path) as z:
        names = set(z.namelist())
        for mf in SIDE_MANIFESTS[side]:
            key = f"{root}/{mf}"
            if key not in names:
                continue
            text = z.read(key).decode("utf-8", errors="replace")
            for e in assets.parse_manifest(text):
                src = f"{root}/{e.source.lstrip('/')}"
                if src in names:
                    # 后写的清单覆盖先写的：repair 集是更完整的版本
                    out[e.target.lstrip("/")] = z.read(src)
    return out


def _split_existing(
    targets: dict[str, bytes], existing: set[str]
) -> tuple[dict[str, bytes], dict[str, bytes]]:
    """按「包内是否已有同名条目」分流。

    必须分流：``rewrite_zip`` 的 ``add`` 遇到同名条目会**静默跳过**，
    直接塞进 add 会导致载荷被无声丢弃（zip 内容仍是英文）。
    """
    adds, reps = {}, {}
    for name, data in targets.items():
        (reps if name in existing else adds)[name] = data
    return adds, reps


# --------------------------------------------------------------------------- #
# 随包文档
# --------------------------------------------------------------------------- #
def _readme(pack_version: str, mod_version: str, *, server: bool,
            payload: int = 0, replaced: int = 0,
            coverage: dict | None = None) -> bytes:
    side = "服务端" if server else "客户端"
    launch = "启动服务端" if server else "启动游戏"
    lines = [
        f"Wold's Vaults 汉化补丁（{side}）",
        "=" * 60,
        f"整合包版本 : {pack_version}",
        f"汉化版本   : {mod_version}",
        "生成方式   : 自动化重基底构建（tools/cnrebase）",
        "",
        "装了什么",
        "-" * 60,
        "1) mods/ 下的 woldsvaults_cn 汉化模组",
        "   · 负责模组界面文本（语言表 + 硬编码字面量）",
        "   · 覆盖 the_vault / woldsvaults / kubejs / qolhunters / packmenu",
        "     五个本体命名空间，以及整合包内全部第三方模组",
        "2) 已预置的汉化文本文件",
        f"   · 新增 {payload} 个，覆盖原有 {replaced} 个",
        "   · 含 FTB 任务书、帕秋莉手册、KubeJS、配置文本",
    ]
    if coverage and coverage.get("namespaces"):
        lines += [
            "3) 汉化资源包（config/openloader/resources/）",
            f"   · {coverage['namespaces']} 个命名空间 / "
            f"{coverage['keys']} 条译文",
            "   · 含整合包本体五个命名空间 + 全部第三方模组",
            "   · 由 OpenLoader 自动加载。语言表是「按 key 合并」、",
            "     options.txt 里越靠后的包优先级越高，而本包稳定排在",
            "     Mod Resources 之后，因此我方的键一定生效",
            "     （模组之间的加载顺序本项目无法控制，所以不靠它）",
        ]
    lines += [
        "",
        "安装",
        "-" * 60,
        f"本包已把汉化模组与全部汉化文本预置好，{launch}即为中文，无需额外操作。",
        "",
    ]
    if server:
        lines += [
            "",
            "开服预设（新增）",
            "-" * 60,
            "本包提供两套世界生成方式，运行 install.bat 时会询问你要哪套：",
            "  [1] 普通世界   level-type = minecraft:normal",
            "  [2] 天空宝库   level-type = skyblockbuilder:skyblock",
            "             虚空世界，玩家用 /island create 领岛；",
            "             预装汉化版 Sky Vaulters Support，含悬浮宝库祭坛主城",
            "             并已修复 Terralith 导致的天空生成失效。",
            "",
            "包内文件：",
            "  server.properties.normal   普通世界预设（与官方完全一致）",
            "  server.properties.skyblock 天空宝库预设",
            "  SERVER-PRESETS.txt         详细说明与切换方法",
            "",
            "⚠ level-type 只在【首次生成世界】时生效。已存在的 world 文件夹",
            "  不会因为改了 level-type 而重新生成，需先备份并删除 world/。",
            "",
            "注意",
            "-" * 60,
            "打包时已自动剔除官方包中残留的重复 modid 旧版本 jar",
            "（Forge 会因 duplicate modid 拒绝启动）。清单见 CN-BUILD.json。",
            "汉化以语言载荷 + 硬编码补丁形式生效，不修改任何原作 jar。",
            "",
            "回退",
            "-" * 60,
            "删除 mods/woldsvaults_cn-*.jar 即可停止汉化；",
            "预置的文本文件不覆盖原作 jar，删除存档无影响。",
        ]
    else:
        lines += [
            "说明",
            "-" * 60,
            "· 语言文件与硬编码补丁内置于汉化模组，无需启用任何资源包；",
            "  第三方模组的汉化资源包由 OpenLoader 自动加载，同样无需操作。",
            "· FTB 任务书 / 帕秋莉手册的中文已直接写入包内文件，",
            "  首次启动前即可在 overrides/ 下看到。",
            "· 若需回退英文，删除 mods/ 下的 woldsvaults_cn-*.jar 与",
            "  config/openloader/resources/WoldsVaults-CN-Lang.zip 即可",
            "  （预置文本仍在，如需彻底回退请整体重装原版）。",
            "· 不修改任何原作 jar，卸载汉化不影响存档。",
            "",
            "关于 I18nUpdateMod（自动汉化更新）",
            "-" * 60,
            "本包已把 CFPA 的模组汉化资源包离线烘焙进来，不需要再装",
            "I18nUpdateMod 之类的自动汉化模组（它还要求首次启动联网下载，",
            "下载失败就静默不加载——「附属模组整包零中文」就是这么来的）。",
            "若你仍要装：它会把它的包追加到资源包列表【末尾】= 最高优先级，",
            "逐条压过本资源包；须确认本资源包 resources/WoldsVaults-CN-Lang.zip",
            "排在它的条目【之后】。整合包更新 I18n 版本后要重新确认。",
            "（它的清理逻辑按子串 \"Minecraft-Mod-Language-Modpack\" 删选项，",
            "本资源包不含该子串，安全。）",
            "",
            "第三方模组译文来源与署名",
            "-" * 60,
            "大部分第三方模组译文来自 CFPA 团队的《Minecraft 模组简体中文",
            "翻译资源包》（Minecraft-Mod-Language-Package）。",
            "署名：CFPA 团队  ·  https://cfpa.site/",
            "贡献者名单：https://github.com/CFPAOrg/Minecraft-Mod-Language-Package/graphs/contributors",
            "协议详见资源包内 LICENSE。整合包本体译文由本项目自行维护。",
        ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _meta(
    pack_version: str,
    mod_version: str,
    jar_name: str,
    side: str,
    extra: dict | None = None,
) -> bytes:
    prefix = "mods/" if side == "server" else "overrides/mods/"
    meta = {
        "pack": "Wold's Vaults",
        "packVersion": pack_version,
        "localizationVersion": mod_version,
        "side": side,
        "localizationJar": prefix + jar_name,
        "payloadLocation": "包根目录" if side == "server" else "overrides/",
        "generator": "tools/cnrebase",
    }
    if extra:
        meta.update(extra)
    return (json.dumps(meta, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _dedupe_pairs(pack: ServerPack) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _stem, info in pack.duplicate_mods().items():
        for d in info["drop"]:
            out.append((d, info["keep"]))
    return out


# --------------------------------------------------------------------------- #
# 客户端（PCL 拖拽安装）
# --------------------------------------------------------------------------- #
#: 已带标记的展示名尾缀，重跑注入时先剥掉，避免叠成
#: 「Wold's Vaults 汉化版 0.34.1 汉化版 0.34.1」
_SUFFIX_RE = re.compile(r"\s*汉化版(?:\s+[0-9][0-9A-Za-z.+\-]*)?\s*$")


def _cn_display_name(old_name: str, label_suffix: str, pack_version: str) -> str:
    """拼出带整合包版本号的展示名：``Wold's Vaults 汉化版 0.34.1``。

    PCL 拿 ``manifest.json`` 的 ``name`` 当版本目录名，``version`` 字段不进
    目录名——不带版本号就会出现一堆同名实例。
    """
    base = _SUFFIX_RE.sub("", old_name).strip() or "Wold's Vaults"
    parts = [base, label_suffix, pack_version.strip()]
    return " ".join(p for p in parts if p)


def inject_client(
    client_zip: Path,
    jar_path: Path,
    out_zip: Path,
    mod_version: str,
    label_suffix: str = "汉化版",
    pack_version: str = "",
    extra_overrides: dict[str, bytes] | None = None,
    coverage: dict | None = None,
) -> InjectResult:
    """把汉化 jar 与预置文本注入 CurseForge 客户端包的 ``overrides/``。

    ``manifest.json`` 只改展示名 ``name``，其余字段逐字保留——PCL 依赖它们
    决定要下载的 445 个模组，任何多余改动都有风险。

    **展示名必须带整合包版本号**：PCL 拖拽安装是用 ``manifest.json`` 的
    ``name`` 当版本目录名的，``version`` 字段不会拼进去。只写「汉化版」的话，
    多个版本装下来全是同名目录（`Wold's Vaults 汉化版`），根本分不清是哪个
    整合包版本。

    ``extra_overrides`` 是「相对 ``overrides/`` 的路径 → 字节」的额外产物。
    目前用来塞**汉化资源包**（``config/openloader/resources/``）——OpenLoader
    会自动加载该目录下的资源包，且它的包在资源包列表里排在最末位，而语言文件
    是「后出现者获胜」，于是这条通道能压过模组自带的 zh_cn。
    """
    jar_name = jar_path.name
    with ClientPack.open(client_zip) as cp:
        res = InjectResult(kind="client")
        manifest = dict(cp.manifest)
        old_name = manifest.get("name", "Wold's Vaults")
        manifest["name"] = _cn_display_name(old_name, label_suffix, pack_version)
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

        pre = cp.overrides_prefix
        existing = set(cp.names)

        # ① 载荷预置（加 overrides/ 前缀），按包内是否已存在分流
        targets = {pre + k: v for k, v in payload_targets(jar_path, "client").items()}
        p_add, p_rep = _split_existing(targets, existing)

        # ② 模组 jar + 随包文档
        add = {
            pre + f"mods/{jar_name}": jar_path.read_bytes(),
            pre + README_NAME: _readme(
                cp.version, mod_version, server=False,
                payload=len(p_add), replaced=len(p_rep), coverage=coverage,
            ),
            pre + META_NAME: _meta(
                cp.version, mod_version, jar_name, "client",
                extra={
                    "payloadAdded": len(p_add),
                    "payloadReplaced": len(p_rep),
                    "payloadTargets": len(targets),
                },
            ),
        }
        add.update(p_add)
        for k, v in (extra_overrides or {}).items():
            add[pre + k] = v

        res.added = sorted(k[len(pre):] for k in add)
        res.stats = rewrite_zip(
            cp.path,
            out_zip,
            add=add,
            replace={"manifest.json": manifest_bytes, **p_rep},
            order_first=("manifest.json", "modlist.html"),
        )
        res.stats["payload_added"] = len(p_add)
        res.stats["payload_replaced"] = len(p_rep)
        res.path = Path(out_zip)
        return res


# --------------------------------------------------------------------------- #
# 服务端
# --------------------------------------------------------------------------- #
def inject_server(
    server_zip: Path,
    jar_path: Path,
    out_zip: Path,
    mod_version: str,
    dedupe: bool = True,
    extra_overrides: dict[str, bytes] | None = None,
) -> InjectResult:
    """把汉化 jar 与预置文本注入官方服务端包，单次 rewrite 同时完成重复 modid 去重。

    ``extra_overrides`` 是「**相对包根**的路径 → 字节」的额外产物。语义与
    ``inject_client`` 的同名参数一致，但**没有 ``overrides/`` 这一层前缀**
    （服务端包根就是游戏目录），所以调用方给 ``mods/x.jar`` 就是包根下的
    ``mods/x.jar``、给 ``install.bat`` 就是包根下的 ``install.bat``。

    目前用于把仓库 ``extras/`` 下的两类产物接进服务端包：

    * ``extras/mods-server/*.jar`` —— **服务端专属**扩展模组（SkyblockAddon，
      让天空宝库支持多人）。客户端包**不能**带它，所以走的是这条独立通路。
    * ``extras/server/*`` —— 开服预设（两套 ``server.properties`` + 安装脚本
      + 说明文档）。

    ⚠ 同名条目必须走 ``replace`` 通道：``install.bat`` / ``install.sh`` 在官方
    包里**已经存在**（各 61 字节的原版脚本），而 ``rewrite_zip`` 的 ``add``
    对源包已存在的名字是**静默跳过**的。所以这里对 ``extra_overrides``
    同样做 add/replace 分流，而不是无脑塞进 ``add``。
    """
    jar_name = jar_path.name
    with ServerPack.open(server_zip) as sp:
        res = InjectResult(kind="server")
        pairs = _dedupe_pairs(sp) if dedupe else []
        existing = set(sp.names)

        # 载荷目标即服务端根目录下的相对路径
        targets = payload_targets(jar_path, "server")
        p_add, p_rep = _split_existing(targets, existing)

        pack_version = _server_pack_version(sp)
        add = {
            f"mods/{jar_name}": jar_path.read_bytes(),
            README_NAME: _readme(
                pack_version, mod_version, server=True,
                payload=len(p_add), replaced=len(p_rep),
            ),
            META_NAME: _meta(
                pack_version,
                mod_version,
                jar_name,
                "server",
                extra={
                    "payloadAdded": len(p_add),
                    "payloadReplaced": len(p_rep),
                    "payloadTargets": len(targets),
                    "presets": [
                        serverpresets.PRESET_NORMAL,
                        serverpresets.PRESET_SKYBLOCK,
                        serverpresets.INSTALL_SCRIPT,
                    ],
                    "levelTypeSkyblock": serverpresets.LEVEL_TYPE_SKYBLOCK,
                    "bundledServerMods": sorted(
                        k.rsplit("/", 1)[-1] for k in (extra_overrides or {})
                        if k.startswith("mods/") and k.endswith(".jar")
                    ),
                    "bundledPresets": sorted(
                        k for k in (extra_overrides or {})
                        if not k.startswith("mods/")
                    ),
                    "removedMods": [
                        {"dropped": d.rsplit("/", 1)[-1], "kept": k.rsplit("/", 1)[-1]}
                        for d, k in pairs
                    ],
                },
            ),
        }
        add.update(p_add)

        # 开服预设：普通世界 / 天空宝库两份 server.properties + 增强版安装脚本。
        # 只有源包里确实有 server.properties 时才做，避免上游改包结构后静默产出半套预设。
        #
        # ⚠ rewrite_zip 的 add 字典对**源包已存在的同名条目是静默跳过**的
        # （packs.py: `if name in written: continue`）。install.bat 与 server.properties
        # 都在源包里存在，所以增强版脚本必须走 replace 通道，否则会被无声丢掉——
        # 这个坑已经踩过一次，产物里仍留着官方那 61 字节的 install.bat。
        presets: dict[str, bytes] = {}
        p_presets_add: dict[str, bytes] = {}
        p_presets_rep: dict[str, bytes] = {}
        base_props = b""
        if "server.properties" in existing:
            base_props = sp.read("server.properties")
            presets = serverpresets.build(base_props, pack_version)
            problems = serverpresets.verify(presets, base_props)
            if problems:
                raise RuntimeError(
                    "开服预设自检失败：\n  - " + "\n  - ".join(problems)
                )
            for name, data in presets.items():
                if name in existing:
                    p_presets_rep[name] = data
                else:
                    p_presets_add[name] = data
            add.update(p_presets_add)

        # —— extras/ 产物接线（服务端专属扩展模组 + 开服预设）——
        # 放在预设块**之后**：extras/ 是仓库里的最终产物（人工维护、字节已校验），
        # 与 serverpresets.build() 的生成物同名时以 extras/ 为准
        # （实测 SERVER-PRESETS.txt：extras 2337 B 的详细版 vs 生成 1078 B 的简版）。
        #
        # 同样必须做 add/replace 分流：官方包根已有 install.bat / install.sh
        # （各 61 B），extras 里是增强版（2062 B）。无脑塞 add 会被静默跳过，
        # 产物里就会留着官方那 61 字节的脚本 —— 这个坑已经踩过一次。
        x_add: dict[str, bytes] = {}
        x_rep: dict[str, bytes] = {}
        for k, v in (extra_overrides or {}).items():
            # 同名时从预设的两个通道里摘掉，避免统计与实际写入口径不一致
            p_presets_add.pop(k, None)
            p_presets_rep.pop(k, None)
            (x_rep if k in existing else x_add)[k] = v
        add.update(x_add)
        res.presets = sorted(presets)

        res.added = sorted(add)
        res.removed = [d for d, _ in pairs]
        res.stats = rewrite_zip(
            sp.path, out_zip, add=add,
            remove={d for d, _ in pairs},
            replace={**p_rep, **p_presets_rep, **x_rep},
        )
        res.stats["payload_added"] = len(p_add)
        res.stats["payload_replaced"] = len(p_rep)
        res.stats["presets_added"] = len(p_presets_add)
        res.stats["presets_replaced"] = len(p_presets_rep)
        res.stats["extras_added"] = len(x_add)
        res.stats["extras_replaced"] = len(x_rep)
        res.path = Path(out_zip)

        # 产物级复核：生成函数的断言全绿也证明不了字节真进了包
        #（rewrite_zip 的 add 对源包同名条目静默跳过，这个坑踩过一次）。
        if presets:
            import zipfile as _zf

            with _zf.ZipFile(out_zip) as chk:
                pack_problems = serverpresets.verify_pack_mutation(chk, base_props)
            if pack_problems:
                raise RuntimeError(
                    "开服预设产物校验失败：\n  - " + "\n  - ".join(pack_problems)
                )

        # extras/ 同名条目走 replace，同样要在**产物**上再验一遍字节：
        # 这是「官方 install.bat 61 B 残留」那类静默失效的唯一兜底。
        if extra_overrides:
            import zipfile as _zf

            with _zf.ZipFile(out_zip) as chk:
                onames = set(chk.namelist())
                lost = []
                for k, v in extra_overrides.items():
                    if k not in onames:
                        lost.append(f"{k}（缺）")
                    elif chk.read(k) != v:
                        lost.append(f"{k}（{len(chk.read(k))}≠{len(v)} 字节）")
            if lost:
                raise RuntimeError(
                    "extras/ 产物校验失败：\n  - " + "\n  - ".join(lost)
                )
        return res


def _server_pack_version(sp: ServerPack) -> str:
    """服务端包没有 manifest.json，用整合包版 jar 名反推版本。"""
    import re

    cand = [n for n in sp.names if "wolds-vaults-official-mod" in n.lower()]
    if cand:
        m = re.search(r"(\d+\.\d+\.\d+)", cand[0].rsplit("/", 1)[-1])
        if m:
            return m.group(1)
    return "unknown"
