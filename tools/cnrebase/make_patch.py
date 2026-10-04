"""生成 0.34.1 汉化【升级补丁】包：只含修正后的汉化模组 jar + 说明。纯标准库。

为什么只需要一个 jar（已实测论证）
-----------------------------------
1. ``ConfigPayloadInstaller.install()`` 对载荷清单里的每个目标**无条件**
   ``Files.copy(..., REPLACE_EXISTING)``（字节码偏移 150-187，无任何 exists 判断）
   → 每次启动都会把所有配置重写一遍；
2. 客户端包 ``overrides/config/`` 里含中文的配置**全部**在载荷清单覆盖范围内
   → 换 jar 后启动即自动修正，玩家不需要删配置、不需要改启动参数、不需要换 Java。

发布前的自检（替代早期「硬编码 sha256 前 16 位」的写法）
--------------------------------------------------------
早期版本把上一轮 jar 的 sha 写死在断言里，重基底一跑 jar 就变了，断言必然失败 ——
那是**假守卫**：它只证明「文件没变」，不证明「修好了」。
现在改成对**产物内容**下断言（见 :func:`_assert_fixed`）：载荷里受保护的标识符
字段不许有中文、显示名必须在字面量对照表里有中文。这才是这次要保证的事。

用法
----
    python -m tools.cnrebase.make_patch
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

CJK = re.compile(r"[\u4e00-\u9fff]")

PACK_VERSION = "0.34.1"
MOD_VERSION = "1.0.17"
JAR_NAME = f"woldsvaults_cn-{MOD_VERSION}-{PACK_VERSION}-universal.jar"
PATCH_NAME = f"WoldsVaults-{PACK_VERSION}-CN-Patch.zip"
README_NAME = "安装说明.txt"

#: 载荷在 jar 内的根，与 ``assets.PAYLOAD_IN_JAR`` 保持一致。
PAYLOAD_ROOT = "assets/woldsvaults_cn/config_payload"
LITERAL_IN_JAR = "assets/woldsvaults_cn/literal_zh_cn.tsv"

#: 受保护的标识符字段。与 ``build.PROTECTED_FIELDS`` 同义，这里硬编码一份
#: 是为了让本脚本**不 import 构建模块**也能独立跑（发布收尾时更省心）；
#: 两边不一致会被 :func:`_assert_fixed` 的第 1 条断言当场抓出来。
PROTECTED_FIELDS: dict[str, list[str]] = {
    "the_vault/researches.json": ["name"],
    "the_vault/eternal_aura.json": ["name", "value"],
    "the_vault/vault_chest.json": ["name", "value"],
}


def _repo_root() -> Path:
    """从本文件向上找同时含 ``templates/`` 与 ``tools/`` 的目录。"""
    for p in Path(__file__).resolve().parents:
        if (p / "templates").is_dir() and (p / "tools").is_dir():
            return p
    raise RuntimeError(f"找不到仓库根目录（从 {__file__} 向上）")


def _values(obj, fields: list[str]) -> list[str]:
    out: list[str] = []

    def walk(o) -> None:
        if isinstance(o, dict):
            for k, v in o.items():
                if k in fields and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(obj)
    return out


def _manifest_client_map(z: zipfile.ZipFile) -> dict[str, str]:
    """``manifest_client.txt``：``目标路径<TAB>载荷内路径``，取客户端真正分发的副本。"""
    raw = z.read(f"{PAYLOAD_ROOT}/manifest_client.txt").decode("utf-8")
    m: dict[str, str] = {}
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            m[parts[0].strip()] = parts[1].strip()
    return m


def _assert_fixed(jar: Path, dist: Path) -> str:
    """对产物内容下断言；返回 jar 的 sha256 前 16 位（大写）。

    抛 ``AssertionError`` 即表示这个 jar 不该被发出去。
    """
    with zipfile.ZipFile(jar) as z:
        names = set(z.namelist())
        cmap = _manifest_client_map(z)

        # 读字面量对照表（en -> zh）
        table: dict[str, str] = {}
        for line in z.read(LITERAL_IN_JAR).decode("utf-8").splitlines():
            if not line or line.startswith("en\t"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                table[parts[0]] = parts[1]

        checked = 0
        for rel, fields in PROTECTED_FIELDS.items():
            target = f"config/{rel}"
            src = cmap.get(target)
            assert src, f"客户端载荷清单里没有 {target}（清单与 PROTECTED_FIELDS 不同步？）"
            obj = json.loads(z.read(f"{PAYLOAD_ROOT}/{src}").decode("utf-8"))
            vals = _values(obj, fields)
            assert vals, f"{target} 里没取到 {fields} 字段（结构变了？）"
            bad = [v for v in vals if CJK.search(v)]
            assert not bad, (
                f"{target} 的 {fields} 仍含中文 {len(bad)}/{len(vals)} 例={bad[:3]}\n"
                f"  → 主键被翻译会导致 ResearchDialog.render() NPE / 查表落空，"
                f"不能发这个 jar。"
            )
            # 显示名必须能译回中文，否则「修好崩溃、界面变英文」
            for v in sorted(set(_values(obj, ["name"]))):
                assert v in table, (
                    f"{target} 的显示名 {v!r} 在字面量对照表里没有中文译文\n"
                    f"  → 界面会露英文。请补进 translations/cn-rebase/literal_zh_cn.tsv"
                )
            checked += len(vals)

        # 客户端包 overrides/ 里实际落地的配置也要干净（玩家首启读的就是它）
        client_zip = dist / f"WoldsVaults-{PACK_VERSION}-CN-Client-PCL.zip"
        if client_zip.is_file():
            with zipfile.ZipFile(client_zip) as cz:
                for rel, fields in PROTECTED_FIELDS.items():
                    member = f"overrides/config/{rel}"
                    if member not in cz.namelist():
                        continue
                    obj = json.loads(cz.read(member).decode("utf-8"))
                    bad = [v for v in _values(obj, fields) if CJK.search(v)]
                    assert not bad, (
                        f"客户端包里 {member} 的 {fields} 仍含中文 {len(bad)} 例={bad[:3]}"
                    )

    print(f"  内容自检通过：{len(PROTECTED_FIELDS)} 份配置 / {checked} 处标识符"
          f"，显示名译文齐备")
    return hashlib.sha256(jar.read_bytes()).hexdigest()[:16].upper()


def _readme(sha16: str) -> str:
    return f"""\
Wold's Vaults {PACK_VERSION} 汉化 · 升级补丁
========================================

◆ 这个补丁修的是什么（两个问题都修了）

  1) 研究界面打不开（点击宝库书里的任意研究会直接报错、界面弹不出来）
     原因：汉化版把研究配置里的「名字」翻成了中文，而游戏是拿这个名字当
     查表主键用的 —— 一翻就查不到，界面代码在取空值时就崩了。
     新版把主键改回英文原名，中文改在「显示的时候」替换，界面既能打开
     又是中文。

  2) 宝库书（the_vault 内置任务）、技能描述等文本整屏乱码
     原因：出现在「Java 17 + 中文系统」的电脑上，是游戏模组读取配置的方式
     带来的，不是汉化文件本身坏了。新版把配置改成任何系统编码都能正确
     读取的形式。

◆ 安装（3 步，1 分钟）
  1) 关闭游戏
  2) 把本压缩包里的 mods 文件夹解压到 你的实例根目录，覆盖同名文件
     （也就是覆盖掉 mods\\{JAR_NAME}）
  3) 启动游戏 —— 完成

  ※ 不需要删除任何配置
  ※ 不需要改启动参数
  ※ 不需要更换 Java 版本
  汉化模组每次启动都会自动把配置重写一遍，所以换掉这一个 jar 就够。

◆ 开服务器的话
  把同一个 jar 放进服务端的 mods 文件夹即可（客户端服务端通用）。

◆ 怎么确认装对了
  新版 jar 的 SHA-256 前 16 位：
      {sha16}
  如果和你 mods 里那个文件的校验值一致，就是新版。

◆ 如果研究界面还是打不开
  说明 mods 里有多份 woldsvaults_cn 开头的 jar，把旧的删掉只留一份。
"""


def main() -> int:
    root = _repo_root()
    dist = root / "build" / "cn" / "dist"
    jar = dist / JAR_NAME
    if not jar.is_file():
        print("找不到汉化 jar:", jar, file=sys.stderr)
        return 1

    print(f"自检 {jar.name} …")
    sha16 = _assert_fixed(jar, dist)

    out = dist / PATCH_NAME
    # 覆盖写：走 fsutil 的「先删后建」兜底，受限环境下 os.replace 会被拒
    sys.path.insert(0, str(root))
    from tools.cnrebase import fsutil  # noqa: PLC0415

    fsutil.install()
    body = jar.read_bytes()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mods/" + jar.name, body, zipfile.ZIP_DEFLATED)
        z.writestr(README_NAME, _readme(sha16).encode("utf-8-sig"),
                   zipfile.ZIP_DEFLATED)

    print(f"生成 {out.name}  {out.stat().st_size / 1048576:.1f} MB  sha16={sha16}")
    with zipfile.ZipFile(out) as z:
        for i in z.infolist():
            print(f"   {i.filename:52s} {i.file_size:10d}")
    # 复核：补丁内的 jar 必须与构建产物逐字节一致
    with zipfile.ZipFile(out) as z:
        inner = z.read("mods/" + jar.name)
    assert inner == body, "补丁内 jar 与构建产物不一致"
    inner_sha16 = hashlib.sha256(inner).hexdigest()[:16].upper()
    assert inner_sha16 == sha16, f"补丁内 jar 校验值对不上 {inner_sha16} != {sha16}"
    print("   复核：补丁内 jar 与构建产物字节一致 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
