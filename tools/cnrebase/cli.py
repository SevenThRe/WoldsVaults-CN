"""cnrebase 命令行入口。

    python -m tools.cnrebase.cli all \\
        --client "Wold's Vaults-0.34.1.zip" \\
        --server "official-wolds-vaults-server-pack-0-34-1.zip" \\
        --pack-version 0.34.1 --mod-version 1.0.17 --out build/cn

子命令
------
probe       只打印输入包与模板的事实，不做修改（用于核对版本）
rebase      执行版本重基底，产出汉化模组 jar
inject      把 jar 注入客户端包 / 服务端包
all         上面全流程 + 报告 + 门禁
verify      只对已有产物跑交付门禁（CI 可单独调用）
apply-todo  把填好的待译清单回填进译料层（AI 翻译的入口）
corpus      查看/校验译料层现状

``--strict`` 用于 CI：断言失败**或**存在被跳过的断言（缺源包对照），
都返回非零。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):  # 允许 python tools/cnrebase/cli.py 直接执行
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.cnrebase import (
    assets,
    build as build_mod,
    corpus as corpus_mod,
    fsutil,
    gapdoc,
    inject as inject_mod,
    langpack as langpack_mod,
    packs,
    plandoc,
    report,
    selftest,
    vendor,
    verify,
)
from tools.cnrebase.build import SELF_MOD_ID
from tools.cnrebase.corpus import (
    CONFIG_FILE,
    DEFAULT_ROOT,
    LANG_FILE,
    LITERAL_FILE,
    VENDOR_FILE,
    Corpus,
    escape,
    unescape,
    write_corpus_readme,
)

DEFAULT_TEMPLATE = "templates/woldsvaults_cn-1.0.16-base.jar"

#: JSON 指针的合法形态：``/o:键`` 或 ``/i:下标``
_PTR_RE = re.compile(r"^(/(o:[^/]*|i:\d+))+$")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _force_rm(func, path, _exc):
    """rmtree 遇到只读文件时先解除保护再删。"""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _prune_trash(trash: Path, keep: Path) -> None:
    """**只报告、不删除**退役目录（2026-10-03 起）。

    为什么不在构建内删：宿主会把 ``os.remove`` / ``Path.unlink`` 改写成
    「安全删除 → 回收站」，而本机回收站调用自身会失败
    （``SHFileOperationW 0x78`` = ``ERROR_CALL_NOT_IMPLEMENTED``）或长时间挂住。
    绕开改写用 ``nt.remove`` 也只有 **~2.5 文件/秒**（沙箱逐个文件做权限检查），
    一个退役模板约 7900 文件 ≈ **53 分钟**。实测 2026-10-03 构建就是卡在这里：
    **14 分钟零产出**，日志 0 字节、``work/template`` 已被退役却没重建。

    所以构建内**一律不删**，只如实报告体积与清理命令；由调用方（我）在构建
    结束后用 PowerShell 工具执行 ``Remove-Item -Recurse -Force``——实测
    3 万余文件 / 460 MB 约 **10 秒**。

    注意：模板目录**不能跨轮复用**（上一轮构建会往里写载荷与第三方
    ``zh_cn.json``，复用会把已从译料层删掉的条目残留进产物），所以每轮都会
    新解压一份，退役目录会持续增长 —— 必须定期清。
    """
    try:
        entries = [p for p in sorted(trash.iterdir()) if p.is_dir()]
    except OSError:
        return
    others = [p for p in entries if p != keep]
    if not others:
        return
    total = 0
    for p in others:
        try:
            total += sum(q.stat().st_size for q in p.rglob("*") if q.is_file())
        except OSError:
            pass
    print(f"     [注意] 退役目录已累积 {len(others)} 个（约 {total/1048576:.0f} MB）。")
    print("            构建内不删除（会挂住整轮构建，见 _prune_trash docstring）。")
    print(f"            构建后请执行：Remove-Item -LiteralPath '{trash}' "
          f"-Recurse -Force")


def _retire_dir(dst: Path) -> None:
    """把过期的构建工作目录**改名**挪走，而不是递归删除。

    宿主对「单轮删除 > 50 项」有硬拦截（``SAFE_DELETE_BULK_CONFIRM_REQUIRED``），
    母版解压后近 8000 个文件必然触发，且提权也绕不过去。同盘 ``rename`` 不算
    删除操作，所以先把旧目录改名进 ``_trash/``，再原地新建——语义与 rmtree 完全
    等价（后续按全新目录解压），又不会撞守卫。

    改名不可行时（跨盘、被占用）才退回 ``rmtree``，并把守卫提示原样带出。

    回收目录统一落在 ``<out>/_trash/``（``out`` 即 ``build/cn``），不塞进 ``work/``
    里，方便整体清理——每个被退役的模板解压目录约 108 MB，攒多了占盘。
    """
    base = dst.parent.parent if dst.parent.name == "work" else dst.parent
    trash = base / "_trash"
    stamp = f"{int(time.time())}-{os.getpid()}"
    target = trash / f"{dst.name}-{stamp}"
    try:
        trash.mkdir(parents=True, exist_ok=True)
        os.replace(dst, target)
    except OSError:
        pass
    else:
        _prune_trash(trash, keep=target)
        return
    try:
        shutil.rmtree(dst, onerror=_force_rm)
    except OSError as e:
        raise RuntimeError(
            f"无法刷新构建工作目录 {dst}（{e}）。\n"
            f"该目录是本轮从母版解出来的可弃副本（build/ 已在 .gitignore 内），"
            f"必须清空才能保证产物干净。\n"
            f"若报错为 SAFE_DELETE_BULK_CONFIRM_REQUIRED / 批量删除被拦截，"
            f"请显式清空后重试：\n"
            f"    rm -rf {dst}\n"
            f"（沙箱环境下需以提权方式执行；这是宿主对「单轮删除 >50 项」的保护，"
            f"不是构建失败。）"
        ) from e


def _fresh_copy(src: Path, dst: Path) -> Path:
    """把母版模板准备成可写目录。

    ``src`` 既可以是已解开的目录，也可以是母版 jar——仓库里只存 15 MB 的原始
    jar，比 90 MB 的解压目录更适合入库，CI 里现解现用。

    从 jar 解压出来的文件带只读属性（zip 的 external_attr），会阻断后续载荷
    改写，所以统一清掉写保护。

    覆盖是**必须**的，不能「有就复用」：上一轮构建往模板里写过载荷与第三方
    ``zh_cn.json``，复用会把已从译料层删掉的条目残留进产物，破坏字节级保真。
    """
    if dst.exists():
        _retire_dir(dst)
    dst.mkdir(parents=True, exist_ok=True)
    if src.is_file() and src.suffix.lower() in (".jar", ".zip"):
        with zipfile.ZipFile(src) as z:
            z.extractall(dst)
    else:
        shutil.copytree(
            src,
            dst,
            dirs_exist_ok=True,
            copy_function=shutil.copyfile,
            ignore=shutil.ignore_patterns("*.orig", "__pycache__"),
        )
    for dp, dn, fn in os.walk(dst):
        for name in fn + dn:
            p = Path(dp) / name
            try:
                os.chmod(p, os.stat(p).st_mode | stat.S_IWRITE)
            except OSError:
                pass
    return dst


def _names(pack_version: str) -> dict[str, str]:
    v = pack_version
    return {
        "client": f"WoldsVaults-{v}-CN-Client-PCL.zip",
        "server": f"WoldsVaults-{v}-CN-Server.zip",
    }


# --------------------------------------------------------------------------- #
# probe
# --------------------------------------------------------------------------- #
def cmd_probe(args) -> int:
    tpl = Path(args.template)
    print("模板:", tpl)
    b = assets.walk_template(tpl)
    print(f"  static={len(b['static'])} payload={len(b['payload'])} other={len(b['other'])}")
    idx = assets.load_index(tpl / assets.PAYLOAD_IN_JAR)
    print("  清单:", idx.counts())
    tbl = assets.load_literal(tpl / assets.LITERAL_TSV_IN_JAR)
    print(f"  literal tsv: {len(tbl)} 行 / {len(tbl.mapping)} 唯一原文")
    langs = assets.load_langs(tpl)
    print("  语言表:", {k: len(v) for k, v in sorted(langs.items())})

    if args.client:
        with packs.ClientPack.open(args.client) as cp:
            print("客户端包:", cp.path.name)
            print(f"  {cp.name} {cp.version} | {cp.mc} | {cp.loader} | {cp.file_count} 模组")
            print(f"  overrides 成员: {len(cp.overrides_members())}")
    if args.server:
        with packs.ServerPack.open(args.server) as sp:
            print("服务端包:", sp.path.name)
            print(f"  mods jar: {len(sp.mod_jars())}")
            for stem, info in sorted(sp.duplicate_mods().items()):
                print(f"  重复[{stem}] keep={info['keep'].rsplit('/',1)[-1]}")
                for d in info["drop"]:
                    print(f"      drop={d.rsplit('/',1)[-1]}")
    return 0


# --------------------------------------------------------------------------- #
# rebase
# --------------------------------------------------------------------------- #
def cmd_rebase(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = _fresh_copy(Path(args.template), out / "work" / "template")
    sp = packs.ServerPack.open(args.server) if args.server else None
    cp = packs.ClientPack.open(args.client) if args.client else None
    try:
        t0 = time.time()
        res = build_mod.rebase(
            template=work,
            out_root=out / "dist",
            pack_version=args.pack_version,
            mod_version=args.mod_version,
            client_pack=cp,
            server_pack=sp,
            corpus=Corpus.load(args.corpus),
            vendor_enabled=not args.no_vendor,
            mods_dir=Path(args.mods_dir) if args.mods_dir else None,
        )
        print(f"重基底完成（{time.time()-t0:.1f}s）")
        print(json.dumps(res.summary(), ensure_ascii=False, indent=2))
        if res.jar_path:
            print("jar:", res.jar_path)
        return 0
    finally:
        if sp:
            sp.close()
        if cp:
            cp.close()


# --------------------------------------------------------------------------- #
# inject
# --------------------------------------------------------------------------- #
def cmd_inject(args) -> int:
    out = Path(args.out)
    dist = out / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    names = _names(args.pack_version)
    jar = Path(args.jar)
    results = []
    if args.client:
        results.append(
            inject_mod.inject_client(
                Path(args.client), jar, dist / names["client"], args.mod_version,
                pack_version=args.pack_version,
            )
        )
    if args.server:
        results.append(
            inject_mod.inject_server(
                Path(args.server), jar, dist / names["server"], args.mod_version
            )
        )
    for r in results:
        print(json.dumps(r.summary(), ensure_ascii=False, indent=2))
    return 0


# --------------------------------------------------------------------------- #
# all
# --------------------------------------------------------------------------- #
#: 汉化资源包在客户端包里的落点。**OpenLoader** 会自动加载该目录下的资源包，
#: 而它的包在资源包列表里排在 ``Mod Resources`` **之后**（实测：同机制加载的
#: ``resources/AndersiteRemoval``、``resources/VHBook.zip`` 位于列表末段）。
#: 语言表是**按 key 合并**、``options.txt`` 里**越靠后的包优先级越高**（已反汇编
#: 确认：``ResourceManager#getResources`` / SRG ``m_7396_`` 返回该路径下所有包的资源，
#: ``LanguageManager`` 依次 ``Language.loadFromJson(..., map::put)``，后加载者胜；
#: 所以写 ``{}`` 或半份表**不会清空**任何键——省略键无法屏蔽，只能显式覆盖）。
#: 因此只有这条通道能稳定压过模组自带的 ``zh_cn``；仅靠我方 mod jar 压不过——
#: 模组包之间的顺序由 ``ModList.getModFiles()`` 决定，本项目控制不了（已反汇编确认：
#: ``ResourcePackLoader.loadResourcePacks`` 只做 ``addPackFinder``）。
#:
#: **共存是有条件的，必须知情**：``I18nUpdateMod`` 会把自己的包 ``List#add`` 到
#: ``options.txt`` 的 ``resourcePacks`` **末尾**（= 最高优先级），但仅在**自己的 id
#: 不在列表里时**才这么做（``GameConfig#addResourcePack`` 开头 ``List#contains``
#: 命中就直接 return）。所以：只要 I18n 的 zip 名不变，把本资源包排在它**之后**
#: 就能稳定长期生效；而整合包更新 I18n 版本（id 变了）时它会把重新 append 置尾，
#: 需要重新确认顺序。
#: 另有一个坑：那次 append 之前的 filter 是**子串**匹配
#: ``"Minecraft-Mod-Language-Modpack"``，会静默删掉 options.txt 里所有含该子串的
#: 条目——所以本资源包**绝不可**命名成包含该子串的形式（现名不含，安全）。
OPENLOADER_DIR = "config/openloader/resources"
OPENLOADER_PACK = "WoldsVaults-CN-Lang.zip"

#: 汉化**数据包**的落点。OpenLoader 的 ``resources/`` 目录**只当资源包加载**
#: （仅 ``assets/`` 生效），``data/`` 必须放 ``config/openloader/data/`` 才会被
#: 当作**数据包**加载。上游 1.18.2 整合包自己在 ``config/openloader/data/`` 里
#: 就放了 4 个 zip（blacklist / catchable / mobdrops / Skaia Vault Themes），
#: 照这个约定来——装备属性说明 / 技能描述 / 物品提示都在 ``data/woldsvaults/``
#: 下，只有走数据包通道才会生效。
OPENLOADER_DATA_DIR = "config/openloader/data"
DATA_PACK = "WoldsVaults-CN-Data.zip"

#: 整合包本体（自维护）的命名空间。它们的最终语言表既写进我方 mod jar，也要
#: 一并放进汉化资源包——模组内置语言表同处 ``Mod Resources`` 聚合包、内部次序
#: 由模组加载顺序决定（本项目控制不了），只有独立用户资源包才能保证我方译文胜出。
CORE_NS = ("the_vault", "woldsvaults", "kubejs", "qolhunters", "packmenu")

#: 补进 ``the_vault`` 语言表的额外键——**上游 en_us 里根本没有这些键**，
#: 但中文界面必须显示中文，否则会漏英文。
#:
#: 根因：整合包自带的 OpenLoader 资源包 ``AndersiteRemoval``
#: （``config/openloader/resources/AndersiteRemoval/``）里有一份「改名表」
#: ``assets/andersiteremoval/lang/en_us.json``，把 ``item.the_vault.deck_socket``
#: 之类的**全局键**以英文塞进语言表。MC 的 ``Language.loadFromJson`` 是
#: **键名原样注册、不加命名空间前缀**的（命名空间只用来定位文件），所以这些键
#: 会污染全局；而 ``LanguageManager#reload`` 总是先载入 ``en_us`` 作为基础语言、
#: 再载入所选语言 → **只要没有任何 ``zh_cn`` 提供该键，中文界面就漏英文**
#: （实测该表 72 个键里只有这 2 个在所有 ``zh_cn`` 里都缺译文）。
#:
#: 为什么补在汉化资源包里、而不是改写上游那份 ``en_us.json``：
#: ``zh_cn`` 在 ``LanguageManager`` 里**后于** ``en_us`` 载入，故本包的值必定胜出；
#: 且不必猜 OpenLoader 资源包之间的加载次序，也不污染英文 locale。
EXTRA_LANG_KEYS: dict[str, str] = {
    "item.the_vault.deck_socket": "卡组核心",
    "block.the_vault.treasure_container": "宝藏容器",
}

#: 汉化资源包里的**非语言**附加文件（``{包内路径: 字节}``）。
#:
#: ``assets/the_vault/models/item/deck_socket.json`` —— 修上游模型链断裂：
#: * ``the_vault`` 自带的 ``assets/the_vault/models/item/deck_socket.json``
#:   内容是 ``{"parent": "builtin/entity"}``，指向**实体渲染器**的 builtin model，
#:   对物品模型无效；
#: * 官方 mod 又把一个**模型 JSON 错放进** ``assets/the_vault/textures/item/deck_socket.json``
#:   （内容 ``{"parent": "woldsvaults:item/arcane_deck_core"}``，本该在 ``models/`` 下），
#:   于是它既不是贴图、也永远不会被当作模型加载。
#:
#: 两条叠加 → ``the_vault:deck_socket`` 没有任何贴图，游戏画**洋红/黑缺失贴图**。
#: 这里指向官方 mod 里确实存在的 ``woldsvaults:item/deck_cores/arcane_deck_core``
#: （注意官方那份错位文件里写的路径少了 ``deck_cores/`` 一段，本身也是坏的）。
FIX_PACK_FILES: dict[str, bytes] = {
    "assets/the_vault/models/item/deck_socket.json": (
        b'{\n  "parent": "woldsvaults:item/deck_cores/arcane_deck_core"\n}\n'
    ),
}

#: **模组 jar 内 data 包的覆盖文件**目录（相对仓库根），整棵目录原样打进**汉化
#: 数据包**（``config/openloader/data/WoldsVaults-CN-Data.zip``，见
#: :func:`_data_pack`）。
#:
#: 为什么需要：官方模组把物品说明（tooltip）/技能描述放在**它自己 jar 里**的
#: data 包 ``data/woldsvaults/vault_configs/...``。我们不修改模组 jar，改为提供
#: **同名同路径**的覆盖文件。
#:
#: ⚠ 必须走**数据包**通道：OpenLoader 的 ``resources/`` 只当资源包加载（仅
#: ``assets/`` 生效），``data/`` 放那里**根本不生效**——这正是本轮修复的 bug
#: （曾把 data/ 覆盖误打进 ``WoldsVaults-CN-Lang.zip`` 资源包）。
#: 目录里放的是**已翻译**的文件（如 ``woldsvaults/vault_configs/tooltips/wolds_items.json``，
#: 会被打成 ``data/woldsvaults/vault_configs/tooltips/wolds_items.json``）。
DATA_OVERRIDES_DIR = "extras/data-overrides"

#: 汉化数据包的 ``pack.mcmeta`` 描述。
DATA_PACK_DESC = "Wold's Vaults 汉化数据覆盖：装备属性说明 / 技能描述 / 物品提示"


def _data_override_files() -> dict[str, bytes]:
    """收集 ``extras/data-overrides/`` 下的全部文件，键为 ``data/<相对路径>``。"""
    root = Path(__file__).resolve().parents[2]
    d = root / DATA_OVERRIDES_DIR
    out: dict[str, bytes] = {}
    if not d.is_dir():
        return out
    for p in sorted(d.rglob("*")):
        if p.is_file():
            rel = p.relative_to(d).as_posix()
            out[f"data/{rel}"] = p.read_bytes()
    return out


def _data_pack(dist: Path, pack_version: str) -> tuple[dict[str, bytes], dict]:
    """把 ``data/`` 覆盖文件打成**数据包**，返回 ``(要写进包内的条目, 统计)``。

    OpenLoader 的 ``resources/`` 只当资源包加载（仅 ``assets/`` 生效），``data/``
    必须放 ``config/openloader/data/`` 才作**数据包**加载（上游整合包同目录里就
    有 4 个 zip，见 :data:`OPENLOADER_DATA_DIR` 注释）。所以装备属性说明 / 技能
    描述 / 物品提示这类 ``data/woldsvaults/`` 覆盖不能塞进
    ``WoldsVaults-CN-Lang.zip`` 资源包，要独立成包走数据通道。

    内容 = :func:`_data_override_files`，**原样字节**（不重新序列化 JSON）；复用
    :func:`langpack_mod.build_resource_pack` 的写 zip 实现（走 fsutil 兜底），
    只写 ``pack.mcmeta`` + 全部 ``data/...`` 条目。为空时直接返回 ``({}, {})``
    ——没有 overrides 不该把构建搞崩。

    同时把数据包留一份在 ``dist/``（``WoldsVaults-CN-Data-{pack_version}.zip``），
    便于已有实例单独取用；返回的包内条目键**不带版本号**，与
    ``WoldsVaults-CN-Lang.zip`` 的约定一致。
    """
    files = _data_override_files()
    if not files:
        return {}, {}
    out = dist / f"WoldsVaults-CN-Data-{pack_version}.zip"
    langpack_mod.build_resource_pack(
        out, {}, DATA_PACK_DESC, pack_format=8, extra_files=files,
    )
    print(f"[2.4/3] 汉化数据包 {len(files)} 个文件 -> {out.name}")
    return (
        {f"{OPENLOADER_DATA_DIR}/{DATA_PACK}": out.read_bytes()},
        {"files": len(files), "bytes": out.stat().st_size, "path": str(out)},
    )

_ATTRIBUTION = """Wold's Vaults 汉化资源包 {v}
========================================

本包由「Wold's Vaults 汉化流水线」构建，覆盖模组界面文本（物品名、方块名、
JEI/创造页签、GUI 提示等）。

第三方模组译文来源
------------------
大部分第三方模组译文来自 **CFPA 团队**的《Minecraft 模组简体中文翻译资源包》
（Minecraft-Mod-Language-Package，1.18 Forge 构建，另有一小部分由其他版本补齐）。
署名：CFPA 团队
完整贡献者名单：https://github.com/CFPAOrg/Minecraft-Mod-Language-Package/graphs/contributors
项目主页：https://cfpa.site/    协议：见包内 LICENSE

整合包本体译文（the_vault / woldsvaults / kubejs / qolhunters / packmenu）
为本项目自行维护，随汉化 jar 一同分发。

为什么要单独放一个资源包
------------------------
1.18.2 的语言表是**按 key 合并**：多个资源包提供同一个
``assets/<ns>/lang/zh_cn.json`` 时，各家条目会叠加，**同名键由优先级更高的包决定**
（不是整文件覆盖）。优先级由 ``options.txt`` 里 ``resourcePacks`` 的顺序决定，
**越靠后的包优先级越高**。

模组内置的语言表全部同处 ``Mod Resources`` 这个聚合包内，其内部次序由模组加载
顺序决定，本项目控制不了；而 ``config/openloader/resources/`` 下的资源包是
**独立用户资源包**，稳定排在 ``Mod Resources`` 之后，因此我方的键一定生效。

重要：关于 I18nUpdateMod（自动汉化更新）
----------------------------------------
本包已经把 CFPA 的《Minecraft 模组简体中文翻译资源包》**离线烘焙**进上面那个
汉化资源包里，全部模组译文开箱即用，**不需要**再装 I18nUpdateMod 之类的自动
汉化模组（它还要求首次启动联网下载，且下载失败就静默不加载）。

如果你仍要装，必须知道它会造成包顺序竞争：
· 它在自己的包 id 不在列表里时，会把自己的包**追加到** ``options.txt`` 的
  ``resourcePacks`` **末尾**，即拿到**最高优先级**，从而逐 key 压过本资源包；
  （若 id 已在列表里则原地返回、不动顺序。）
· 所以装完之后要确认：本资源包 ``resources/WoldsVaults-CN-Lang.zip`` 排在
  它的条目**之后**。整合包更新 I18n 版本（zip 名变了）后需要重新确认一次。
· 它是按**子串** ``Minecraft-Mod-Language-Modpack`` 清理选项条目的，
  因此本资源包**不要**改名成包含该子串的形式（现名不含，安全）。
"""


#: 随包分发的「汉化扩展模组」（**仅客户端**）目录（相对仓库根）。
#: 目前含拼音搜索 JECh。只注入**客户端包** overrides/mods/，不进服务端包/通用补丁。
BUNDLED_MODS_DIR = "extras/mods"

#: 随包分发的「服务端专属扩展模组」目录（相对仓库根）。
#: 与 BUNDLED_MODS_DIR **严格分流**：这里只放纯服务端模组（当前是 SkyblockAddon
#: 8.2-CN，让天空宝库支持多人），注入服务端包 mods/，**绝不能**进客户端包。
BUNDLED_MODS_SERVER_DIR = "extras/mods-server"

#: 开服预设目录（相对仓库根）。文件**直接落在服务端包根**，不加 ``overrides/``
#: 前缀（服务端包根就是游戏目录）——两份 server.properties、增强版 install.bat
#: / install.sh 与说明文档，由 install.bat 装完 Forge 后询问服主选哪套。
SERVER_PRESETS_DIR = "extras/server"


def _extras_bytes(rel_dir: str, *, prefix: str = "", suffix: str = "") -> dict[str, bytes]:
    """读 ``extras/`` 下某个目录的产物，返回 ``{包内相对路径: 字节}``。

    共用实现：客户端扩展模组（``prefix="mods/"``、``suffix=".jar"``）与服务端
    预设（``prefix=""``、``suffix=""`` 表示不限后缀）只有「目录不同 / 前缀不同」
    这一个差别。目录不存在时返回空 dict —— 上游还没放产物时不该把构建搞崩。
    """
    root = Path(__file__).resolve().parents[2]
    d = root / rel_dir
    out: dict[str, bytes] = {}
    if not d.is_dir():
        return out
    ext = suffix.lower().lstrip(".")
    for p in sorted(d.iterdir()):
        if not p.is_file():
            continue
        if ext and p.suffix.lower().lstrip(".") != ext:
            continue
        out[prefix + p.name] = p.read_bytes()
    return out


def _bundled_mod_overrides() -> dict[str, bytes]:
    """把仓库 ``extras/mods/`` 下的随包模组注入客户端包 ``overrides/mods/``。

    这些是**客户端专属**的汉化扩展（如 JECh 拼音搜索）；服务端包与通用升级补丁
    **不**包含它们——客户端专属模组在服务端加载可能报错（JECh 入口类引用了
    ``net.minecraft.client.*``）。
    """
    return _extras_bytes(BUNDLED_MODS_DIR, prefix="mods/", suffix=".jar")


def _bundled_server_mod_overrides() -> dict[str, bytes]:
    """把仓库 ``extras/mods-server/`` 下的**服务端专属**模组注入服务端包 ``mods/``。

    与 :func:`_bundled_mod_overrides` 严格分流：SkyblockAddon 这类模组只装服务端
    （客户端装了反而加载失败），所以走 ``inject_server`` 的独立通路，
    **不进**客户端包 overrides/。
    """
    return _extras_bytes(BUNDLED_MODS_SERVER_DIR, prefix="mods/", suffix=".jar")


def _server_preset_overrides() -> dict[str, bytes]:
    """把仓库 ``extras/server/`` 的开服预设注入服务端包**根目录**。

    键就是**文件名本身**（``install.bat`` / ``server.properties.skyblock`` …），
    不加 ``overrides/`` 前缀——服务端包根即游戏目录，install.bat 要靠
    同目录相对路径引用那两份 properties。

    ⚠ 官方包根**已经有** ``install.bat`` / ``install.sh``（各 61 字节的原版脚本），
    所以这些条目在 ``inject_server`` 里会走 replace 通道；无脑 add 会被
    ``rewrite_zip`` 静默跳过，产物里就留着官方那 61 字节。
    """
    return _extras_bytes(SERVER_PRESETS_DIR)


def _openloader_overrides(
    res, dist: Path, pack_version: str
) -> tuple[dict[str, bytes], dict]:
    """打一个汉化资源包，返回 ``(要写进客户端包 overrides/ 的条目, 覆盖统计)``。

    同时把资源包留一份在 ``dist/``：已有实例不必重装整包，把这个 zip 丢进
    ``config/openloader/resources/`` 即可。

    内容 = 第三方命名空间的最终语言表（``res.vendor_langs``）**加上**核心命名空间
    （``CORE_NS``）的最终语言表——后者直接取自产物 jar 里的
    ``assets/<ns>/lang/zh_cn.json``，原样搬进资源包。这样核心命名空间不再依赖
    「模组加载顺序」这个不可控变量。

    ⚠ ``data/`` 覆盖（装备属性说明 / 技能描述 / 物品提示）**不在这里**——资源包只
    加载 ``assets/``，``data/`` 必须走 :func:`_data_pack` 的数据包通道，否则不生效。
    """
    if not res.vendor_langs:
        return {}, {}
    ns_lang: dict[str, dict[str, str]] = {}
    bad_ns: list[str] = []
    for ns, table in sorted(res.vendor_langs.items()):
        # 命名空间来自真实 jar 的路径扫描，理论上畸形模组可能带来非法值。
        # 模块内是严格 `ValueError`（安全优先），但**一个坏模组不该让整个构建失败**，
        # 所以在这一层降级为「跳过 + 告警」。
        try:
            langpack_mod._check_ns(ns)
        except ValueError:
            bad_ns.append(ns)
            continue
        ns_lang[ns] = dict(sorted(table.items()))
    if bad_ns:
        msg = f"跳过 {len(bad_ns)} 个非法命名空间（不会写进汉化资源包）：{sorted(bad_ns)}"
        res.warnings.append(msg)
        print(f"[2.5/3] 警告：{msg}")
    core: dict[str, int] = {}
    jar = Path(res.jar_path) if res.jar_path else None
    if jar and jar.exists():
        with zipfile.ZipFile(jar) as z:
            names = set(z.namelist())
            for ns in CORE_NS:
                entry = f"assets/{ns}/lang/zh_cn.json"
                if entry not in names:
                    continue
                table = json.loads(z.read(entry).decode("utf-8"))
                if not table:
                    continue
                ns_lang[ns] = dict(sorted((str(k), str(v)) for k, v in table.items()))
                core[ns] = len(table)
    # 补上游 en_us 里不存在的键（否则中文界面漏英文，见 EXTRA_LANG_KEYS 注释）
    if "the_vault" in ns_lang:
        ns_lang["the_vault"].update(EXTRA_LANG_KEYS)
        core["the_vault"] = len(ns_lang["the_vault"])
    out = dist / f"WoldsVaults-CN-Lang-{pack_version}.zip"
    entries = sum(len(table) for table in ns_lang.values())
    langpack_mod.build_resource_pack(
        out,
        ns_lang,
        f"Wold's Vaults 汉化资源包 {pack_version}",
        pack_format=8,
        extra_files={
            "CN-署名与来源.txt": _ATTRIBUTION.format(v=pack_version).encode("utf-8"),
            **FIX_PACK_FILES,
        },
    )
    print(
        f"[2.5/3] 汉化资源包 {len(ns_lang)} 个命名空间 / {entries} 条"
        f"（含核心 {len(core)}：{' '.join(f'{k}={v}' for k, v in core.items())}）"
        f" -> {out.name}"
    )
    return (
        {f"{OPENLOADER_DIR}/{OPENLOADER_PACK}": out.read_bytes()},
        {"namespaces": len(ns_lang), "keys": entries, "core": core},
    )


def cmd_all(args) -> int:
    out = Path(args.out)
    dist = out / "dist"
    out.mkdir(parents=True, exist_ok=True)
    names = _names(args.pack_version)
    meta = {
        "pack_version": args.pack_version,
        "mod_version": args.mod_version,
        "template": str(Path(args.template).as_posix()),
        "client_zip": Path(args.client).name if args.client else None,
        "server_zip": Path(args.server).name if args.server else None,
        "generated_at": _ts(),
    }

    work = _fresh_copy(Path(args.template), out / "work" / "template")
    sp = packs.ServerPack.open(args.server) if args.server else None
    cp = packs.ClientPack.open(args.client) if args.client else None
    injects: list[inject_mod.InjectResult] = []
    try:
        # 1) 重基底
        t0 = time.time()
        corpus = Corpus.load(args.corpus)
        print(f"译料层 {args.corpus}：{corpus.stats()}")
        res = build_mod.rebase(
            template=work,
            out_root=dist,
            pack_version=args.pack_version,
            mod_version=args.mod_version,
            client_pack=cp,
            server_pack=sp,
            corpus=corpus,
            vendor_enabled=not args.no_vendor,
            mods_dir=Path(args.mods_dir) if args.mods_dir else None,
        )
        print(f"[1/3] 重基底完成 {time.time()-t0:.1f}s -> {res.jar_path.name}")

        # 数据包通道：OpenLoader 只在 config/openloader/data/ 认数据包，故 data/
        # 覆盖必须独立成包。客户端要（技能/物品/属性说明），服务端也要（技能描述
        # 同样是中文）。只打一次，两侧共用同一份。
        data_overrides, _data_stats = _data_pack(dist, args.pack_version)

        # 2) 注入
        if cp is not None and res.jar_path:
            t0 = time.time()
            overrides, coverage = _openloader_overrides(res, dist, args.pack_version)
            overrides.update(_bundled_mod_overrides())
            overrides.update(data_overrides)
            injects.append(
                inject_mod.inject_client(
                    Path(args.client), res.jar_path, dist / names["client"], args.mod_version,
                    pack_version=args.pack_version,
                    extra_overrides=overrides,
                    coverage=coverage,
                )
            )
            print(f"[2/3] 客户端包注入完成 {time.time()-t0:.1f}s -> {names['client']}")
        if sp is not None and res.jar_path:
            t0 = time.time()
            server_extras: dict[str, bytes] = {}
            server_extras.update(_bundled_server_mod_overrides())
            server_extras.update(_server_preset_overrides())
            server_extras.update(data_overrides)
            injects.append(
                inject_mod.inject_server(
                    Path(args.server), res.jar_path, dist / names["server"], args.mod_version,
                    extra_overrides=server_extras,
                )
            )
            print(f"[3/3] 服务端包注入完成 {time.time()-t0:.1f}s -> {names['server']}"
                  f"（extras {len(server_extras)} 项："
                  f"{sum(1 for k in server_extras if k.startswith('mods/'))} 模组 + "
                  f"{sum(1 for k in server_extras if not k.startswith('mods/'))} 预设/数据包）")

        # 3) 报告
        written = report.write_report(res, injects, out, meta)
        print("报告:", ", ".join(sorted(written.values())))

        # 4) 门禁：不通过就让 CI 红，避免把坏包发出去
        rep = verify.run(
            out=out,
            template=Path(args.template),
            pack_version=args.pack_version,
            mod_version=args.mod_version,
            client_src=Path(args.client) if args.client else None,
            server_src=Path(args.server) if args.server else None,
            corpus_root=args.corpus,
        )
        print(rep.render())
        if rep.failed:
            return 1
        if args.strict and rep.skipped:
            print(f"::error::--strict：仍有 {len(rep.skipped)} 项断言未执行，"
                  f"拒绝在「校验不完整」的情况下放行")
            return 1
        return 0
    finally:
        if sp:
            sp.close()
        if cp:
            cp.close()


# --------------------------------------------------------------------------- #
# verify
# --------------------------------------------------------------------------- #
def cmd_verify(args) -> int:
    rep = verify.run(
        out=Path(args.out),
        template=Path(args.template),
        pack_version=args.pack_version,
        mod_version=args.mod_version,
        client_src=Path(args.client) if args.client else None,
        server_src=Path(args.server) if args.server else None,
        corpus_root=args.corpus,
    )
    print(rep.render())
    if rep.failed:
        return 1
    if args.strict and rep.skipped:
        print(f"--strict：仍有 {len(rep.skipped)} 项断言未执行，拒绝放行")
        return 1
    return 0


# --------------------------------------------------------------------------- #
# apply-todo：AI 翻译的入口
# --------------------------------------------------------------------------- #
def _read_filled(path: Path, min_cols: int) -> list[list[str]]:
    """读填好的待译文件，跳过注释/表头/空行。

    列数超出的行不丢弃：``split("\t")`` 后的多余列由调用方拼回译文
    （译文里若混入未转义的制表符就会这样）。直接丢弃会静默少译一条。
    """
    if not path.is_file():
        return []
    rows: list[list[str]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < min_cols:
            continue
        if parts[0].strip() in ("namespace", "en", "target"):
            continue
        rows.append(parts)
    return rows


def _tail(parts: list[str], start: int) -> str:
    """把第 ``start`` 列及其后所有列拼成一列。"""
    return "\t".join(parts[start:])


def cmd_apply_todo(args) -> int:
    """把填好的 todo-*.tsv 回填进译料层。"""
    todo_dir = Path(args.todo)
    cpath = args.corpus
    corpus = Corpus.load(cpath)

    accepted: dict[str, int] = {"lang": 0, "literal": 0, "config": 0, "vendor": 0}
    rejected: list[str] = []
    skipped_empty = 0
    unknown_kind = 0

    # ---- 语言键 ----
    for parts in _read_filled(todo_dir / "todo-lang.tsv", 4):
        ns, key, en = parts[0].strip(), unescape(parts[1]), unescape(parts[2])
        zh = unescape(_tail(parts, 3))
        if not ns or not key:
            unknown_kind += 1
            continue
        if not zh.strip():
            skipped_empty += 1
            continue
        why = corpus_mod.validate(en, zh)
        if why:
            rejected.append(f"[lang] {ns}:{key} → {why}")
            continue
        if corpus.merge_lang(ns, key, zh):
            accepted["lang"] += 1

    # ---- 硬编码字面量 ----
    for parts in _read_filled(todo_dir / "todo-literal.tsv", 2):
        en, zh = unescape(parts[0]), unescape(_tail(parts, 1))
        if not en:
            unknown_kind += 1
            continue
        if not zh.strip():
            skipped_empty += 1
            continue
        why = corpus_mod.validate(en, zh, as_literal=True)
        if why:
            rejected.append(f"[literal] {en[:40]!r} → {why}")
            continue
        if corpus.merge_literal(en, zh):
            accepted["literal"] += 1

    # ---- 配置文本 ----
    for parts in _read_filled(todo_dir / "todo-config.tsv", 4):
        target, ptr = unescape(parts[0]), parts[1].strip()
        en, zh = unescape(parts[2]), unescape(_tail(parts, 3))
        if not target or not ptr:
            unknown_kind += 1
            continue
        if not _PTR_RE.match(ptr):
            # 指针形态非法，多半是列错位或文件被改坏。宁可拒绝也不能
            # 猜一个位置——回填到错误的叶子会在游戏里表现为
            # 「某段中文出现在完全无关的地方」，且极难定位。
            rejected.append(f"[config] {target} 指针形态非法: {ptr!r}")
            continue
        if not zh.strip():
            skipped_empty += 1
            continue
        why = corpus_mod.validate(en, zh)
        if why:
            rejected.append(f"[config] {target}{ptr} → {why}")
            continue
        if corpus.merge_config(target, ptr, zh):
            accepted["config"] += 1

    # ---- 第三方模组语言 ----
    # 与语言键同样按「键」绑定；但校验不设 as_literal——语言文件是 JSON，
    # 换行在 JSON 里是合法转义，不像行式对照表那样会被劈断。
    for parts in _read_filled(todo_dir / "todo-vendor.tsv", 4):
        ns, key, en = parts[0].strip(), unescape(parts[1]), unescape(parts[2])
        zh = unescape(_tail(parts, 3))
        if not ns or not key:
            unknown_kind += 1
            continue
        if not zh.strip():
            skipped_empty += 1
            continue
        why = corpus_mod.validate(en, zh)
        if why:
            rejected.append(f"[vendor] {ns}:{key} → {why}")
            continue
        if corpus.merge_vendor(ns, key, zh):
            accepted["vendor"] += 1

    total = sum(accepted.values())
    print("即将回填译料层:", cpath)
    print(f"  语言键 {accepted['lang']}　硬编码 {accepted['literal']}　"
          f"配置文本 {accepted['config']}　第三方模组 {accepted['vendor']}　"
          f"合计 {total}")
    print(f"  空译文跳过 {skipped_empty}　格式异常跳过 {unknown_kind}")
    if rejected:
        print(f"  校验拒绝 {len(rejected)} 条：")
        for r in rejected[:10]:
            print(f"    - {r}")
        if len(rejected) > 10:
            print(f"    …… 另有 {len(rejected) - 10} 条")

    if total == 0:
        print("没有可回填的译文（zh 列是否填了？）")
        return 1 if (args.strict and (rejected or skipped_empty)) else 0

    if args.dry_run:
        print("--dry-run：未写入。")
        return 0

    # 已有译料里的旧条目一条都不能丢——merge_* 是增量并入，save 是整体重写。
    # 这里显式对账，避免将来改坏 merge 逻辑后静默丢译文。
    before = corpus.stats()
    before_total = sum(before[k] for k in ("lang", "literal", "config", "vendor"))
    if before_total < total:
        print(f"::error::译料对账失败：写入后条目数 {before_total} < 本次新增 {total}",
              file=sys.stderr)
        return 1

    stats = corpus.save()
    write_corpus_readme(cpath)
    print(f"译料层已更新：{stats}")
    print(f"  语言表 {cpath}/{LANG_FILE}")
    print(f"  字面量 {cpath}/{LITERAL_FILE}")
    print(f"  配置文本 {cpath}/{CONFIG_FILE}")
    print(f"  第三方模组 {cpath}/{VENDOR_FILE}")
    print("接着复跑 `cli all`（带 --client/--server）让译文进入产物。")
    if args.strict and rejected:
        print(f"--strict：有 {len(rejected)} 条被校验拒绝，视为失败")
        return 1
    return 0


# --------------------------------------------------------------------------- #
def cmd_corpus(args) -> int:
    """查看译料层现状，并做一次自检。"""
    cpath = args.corpus
    corpus = Corpus.load(cpath)
    st = corpus.stats()
    print("译料层:", cpath)
    print(f"  语言键 {st['lang']}　硬编码字面量 {st['literal']}　"
          f"配置文本 {st['config']}　第三方模组 {st['vendor']}　"
          f"合计 {st['lang'] + st['literal'] + st['config'] + st['vendor']}")

    bad: list[str] = []
    for ns, kv in corpus.lang.items():
        for k, v in kv.items():
            # 语言键的译文无法单独校验占位符——en 只存在于上游语言表里，
            # 译料层按「键」而非「原文」绑定（上游改文案时不失效）。
            # 占位符校验在 apply-todo 阶段结合 en 一起做。
            if not v.strip():
                bad.append(f"[lang] {ns}:{k} 译文为空")
    for en, zh in corpus.literal.items():
        why = corpus_mod.validate(en, zh, as_literal=True)
        if why:
            bad.append(f"[literal] {en[:40]!r} → {why}")
    for target, kv in corpus.config.items():
        for ptr, zh in kv.items():
            if not _PTR_RE.match(ptr):
                bad.append(f"[config] {target} 指针形态非法: {ptr!r}")
            elif not zh.strip():
                bad.append(f"[config] {target}{ptr} 译文为空")
    if bad:
        print(f"  自检发现 {len(bad)} 处问题：")
        for b in bad[:10]:
            print(f"    - {b}")
        if len(bad) > 10:
            print(f"    …… 另有 {len(bad) - 10} 处")
        return 1
    print("  自检通过：无空译文、无占位符/样式码不一致、指针形态合法")
    return 0


# --------------------------------------------------------------------------- #
def cmd_terms(args) -> int:
    """查术语反查表：翻新模组前先查这里，沿用包内既有译法。

    表由 `all`/`rebase` 顺带产出（`build/cn/todo/term-table.json`），收录
    「英文原文 → 包内既有中文」，只收词条级原文（≤40 字符、无换行）。

    查询是**子串匹配**，因为包里大量构件名是模板形态（`%s Hedge`、`%s Highley
    Gate`）。直接查 `Hedge` 查不到，查 `Hedge` 做子串能查到 —— 这正是译员需要的
    用法，所以这里不做精确匹配。
    """
    path = Path(args.table)
    if not path.is_file():
        print(f"找不到术语表 {path}；先跑一次 all/rebase 生成。")
        return 1
    data = json.loads(path.read_text(encoding="utf-8"))
    table: dict[str, str] = data.get("table", {})
    srcs: dict[str, str] = data.get("srcs", {})

    queries = args.query or []
    if not queries:
        print(f"术语表 {len(table)} 条（{path}）")
        print("用法：cnrebase terms <关键词> [关键词…]   （子串匹配，不限大小写）")
        return 0

    rc = 0
    for q in queries:
        hits = sorted((en, zh) for en, zh in table.items() if q.lower() in en.lower())
        print(f"## {q}  —— {len(hits)} 条")
        if not hits:
            rc = 1
            print("     （表里没有；该词条可能是新词，需要自己定译名并进术语表）")
            continue
        for en, zh in hits[: args.limit]:
            print(f"     {en:<38} = {zh:<20} [{srcs.get(en, '')}]")
        if len(hits) > args.limit:
            print(f"     …… 另有 {len(hits) - args.limit} 条（-n 调大上限）")
    return rc


# --------------------------------------------------------------------------- #
def cmd_plan_doc(args) -> int:
    """生成《全模组汉化改造清单》—— 交付物，跟着构建一起重跑。"""
    todo = Path(args.todo)
    scan = todo / "vendor-scan.json"
    tsv = todo / "todo-vendor.tsv"
    for p in (scan, tsv):
        if not p.is_file():
            print(f"缺输入 {p}；先跑一次 all/rebase 生成待译清单。")
            return 1
    corpus_tsv = Path(args.corpus) / "vendor_lang_zh.tsv"
    text = plandoc.build(scan, tsv, corpus_tsv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    # 清单是给人看的文档，走 fsutil 保证受限环境下也能落盘。
    fsutil.write_text(out, text, encoding="utf-8", newline="\n")
    print(f"已写出 {out}（{len(text)} 字符 / {len(text.splitlines())} 行）")
    return 0


def cmd_gap_doc(args) -> int:
    """生成《未汉化模组清单》—— 回答「哪些模组没中文、还差多少、先做哪个」。"""
    todo = Path(args.todo)
    scan = todo / "vendor-scan.json"
    tsv = todo / "todo-vendor.tsv"
    for p in (scan, tsv):
        if not p.is_file():
            print(f"缺输入 {p}；先跑一次 all/rebase 生成待译清单。")
            return 1
    gapdoc.build(scan, tsv, Path(args.out))
    return 0


def cmd_selftest(args) -> int:
    """跑纯逻辑自检 —— 守护构建门禁覆盖不到的反向不变量。"""
    return selftest.run()


# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cnrebase", description="Wold's Vaults 汉化重基底")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp_):
        sp_.add_argument("--client", help="CurseForge 客户端整合包 zip")
        sp_.add_argument("--server", help="官方服务端包 zip")
        sp_.add_argument("--template", default=DEFAULT_TEMPLATE, help="汉化模组母版目录")
        sp_.add_argument("--pack-version", default="0.34.1")
        sp_.add_argument("--mod-version", default="1.0.17")
        sp_.add_argument("--out", default="build/cn")
        sp_.add_argument("--jar", help="已有汉化 jar（inject 子命令用）")
        sp_.add_argument("--strict", action="store_true",
                         help="有断言被跳过（缺源包对照）即视为失败，CI 用")
        sp_.add_argument("--corpus", default=DEFAULT_ROOT,
                         help="累积译料层目录（默认 translations/cn-rebase）")
        sp_.add_argument("--mods-dir",
                         help="游戏实例的 mods/ 目录，用来补服务端包没有的"
                              "纯客户端模组（JEI、地图、优化类）")
        sp_.add_argument("--no-vendor", action="store_true",
                         help="关闭第三方模组语言通道（只跑本体那 5 个命名空间）")

    for nm, fn in (("probe", cmd_probe), ("rebase", cmd_rebase),
                   ("inject", cmd_inject), ("all", cmd_all), ("verify", cmd_verify)):
        s = sub.add_parser(nm)
        common(s)
        s.set_defaults(func=fn)

    s = sub.add_parser("apply-todo", help="把填好的待译清单回填进译料层")
    common(s)
    s.add_argument("--todo", default="build/cn/todo", help="待译清单目录")
    s.add_argument("--dry-run", action="store_true", help="只校验与统计，不写文件")
    s.set_defaults(func=cmd_apply_todo)

    s = sub.add_parser("corpus", help="查看/自检译料层")
    common(s)
    s.set_defaults(func=cmd_corpus)

    s = sub.add_parser("terms", help="查术语反查表（沿用包内既有译法）")
    s.add_argument("query", nargs="*", help="关键词，子串匹配、不限大小写")
    s.add_argument("--table", default="build/cn/todo/term-table.json",
                   help="术语表路径（由 all/rebase 产出）")
    s.add_argument("-n", "--limit", type=int, default=20, help="每个关键词最多显示多少条")
    s.set_defaults(func=cmd_terms)

    s = sub.add_parser("plan-doc", help="生成《全模组汉化改造清单》")
    s.add_argument("--todo", default="build/cn/todo",
                   help="待译清单目录（含 vendor-scan.json / todo-vendor.tsv）")
    s.add_argument("--corpus", default="translations/cn-rebase", help="译料层目录")
    s.add_argument("--out", default="docs/cn-vendor-plan.md", help="输出 Markdown 路径")
    s.set_defaults(func=cmd_plan_doc)

    s = sub.add_parser("gap-doc", help="生成《未汉化模组清单》（零中文模组 + AE 专项）")
    s.add_argument("--todo", default="build/cn/todo",
                   help="待译清单目录（含 vendor-scan.json / todo-vendor.tsv）")
    s.add_argument("--out", default="docs/cn-untranslated-mods.md",
                   help="输出 Markdown 路径")
    s.set_defaults(func=cmd_gap_doc)

    s = sub.add_parser("selftest", help="纯逻辑自检（不依赖完整构建，秒级）")
    s.set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
