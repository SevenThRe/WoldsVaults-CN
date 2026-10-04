"""整合包 zip 读写：CurseForge 客户端包 + 官方服务端包。

设计约束
--------
1. **manifest.json 必须字节级原样保留**。PCL / CurseForge 靠它决定要下载
   哪 445 个模组；任何重新序列化都可能改变校验行为。
2. 重打包要**保留原始 ZipInfo 元数据**（时间戳、压缩方式、权限位、UTF-8 标志），
   否则 PCL 解压出的目录结构可能与预期不符。
3. 逐条流式复制，避免把 638 MB 服务端包整体读进内存。
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: 客户端包内 manifest 的位置
MANIFEST_NAME = "manifest.json"
MODLIST_NAME = "modlist.html"
OVERRIDES_DEFAULT = "overrides"

#: 服务端包内 mods 目录
SERVER_MODS = "mods/"


# --------------------------------------------------------------------------- #
# 通用 zip 操作
# --------------------------------------------------------------------------- #
def read_text(zf: zipfile.ZipFile, name: str, encoding: str = "utf-8") -> str:
    return zf.read(name).decode(encoding, "replace")


def read_json(zf: zipfile.ZipFile, name: str):
    return json.loads(read_text(zf, name))


def _copy_info(info: zipfile.ZipInfo) -> zipfile.ZipInfo:
    """复制 ZipInfo 元数据，尽量保住原始字节行为。"""
    ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
    ni.compress_type = info.compress_type
    ni.external_attr = info.external_attr
    ni.internal_attr = info.internal_attr
    ni.create_system = info.create_system
    ni.comment = info.comment
    if info.flag_bits & 0x800:  # UTF-8 文件名标志
        ni.flag_bits |= 0x800
    return ni


def rewrite_zip(
    src: Path | str,
    dst: Path | str,
    add: dict[str, bytes] | None = None,
    remove: set[str] | None = None,
    replace: dict[str, bytes] | None = None,
    order_first: tuple[str, ...] = (),
) -> dict[str, int]:
    """把 ``src`` 复制成 ``dst``，同时增/删/替换条目。

    ``order_first`` 里的条目会被放到 zip 最前面（PCL 读 manifest 更稳）。
    返回统计信息。
    """
    src, dst = Path(src), Path(dst)
    add = dict(add or {})
    remove = set(remove or ())
    replace = dict(replace or {})
    dst.parent.mkdir(parents=True, exist_ok=True)

    stats = {"copied": 0, "replaced": 0, "removed": 0, "added": 0, "kept_bytes": 0}
    written: set[str] = set()

    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(
        dst, "w", zipfile.ZIP_DEFLATED, allowZip64=True
    ) as zout:
        # 1) 需要前置的条目先写
        front = []
        for info in zin.infolist():
            if info.filename in order_first:
                front.append(info)
        front.sort(key=lambda i: order_first.index(i.filename))

        def _emit(info: zipfile.ZipInfo) -> None:
            name = info.filename
            ni = _copy_info(info)
            if name in replace:
                zout.writestr(ni, replace[name])
                stats["replaced"] += 1
            else:
                with zin.open(info) as fsrc, zout.open(ni, "w") as fdst:
                    shutil.copyfileobj(fsrc, fdst, 1 << 20)
                stats["copied"] += 1
            written.add(name)

        for info in front:
            _emit(info)
        for info in zin.infolist():
            if info.filename in written or info.filename in remove:
                if info.filename in remove:
                    stats["removed"] += 1
                continue
            _emit(info)

        for name, data in add.items():
            if name in written:
                continue
            zout.writestr(name, data)
            written.add(name)
            stats["added"] += 1

    return stats


# --------------------------------------------------------------------------- #
# CurseForge 客户端整合包
# --------------------------------------------------------------------------- #
@dataclass
class ClientPack:
    """CurseForge 格式客户端整合包（manifest.json + overrides/）。"""

    path: Path
    manifest: dict = field(default_factory=dict)
    names: list[str] = field(default_factory=list)
    _zf: zipfile.ZipFile | None = None

    @classmethod
    def open(cls, path: Path | str) -> "ClientPack":
        p = Path(path)
        zf = zipfile.ZipFile(p)
        if MANIFEST_NAME not in zf.namelist():
            zf.close()
            raise ValueError(f"不是 CurseForge 整合包（缺少 {MANIFEST_NAME}）: {p}")
        return cls(path=p, manifest=read_json(zf, MANIFEST_NAME), names=zf.namelist(), _zf=zf)

    def close(self) -> None:
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def __enter__(self) -> "ClientPack":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- 元数据 ----
    @property
    def name(self) -> str:
        return self.manifest.get("name", "")

    @property
    def version(self) -> str:
        return str(self.manifest.get("version", ""))

    @property
    def overrides_prefix(self) -> str:
        ov = self.manifest.get("overrides", OVERRIDES_DEFAULT).strip("/")
        return ov + "/"

    @property
    def mc(self) -> str:
        return (self.manifest.get("minecraft") or {}).get("version", "")

    @property
    def loader(self) -> str:
        mls = (self.manifest.get("minecraft") or {}).get("modLoaders") or []
        for m in mls:
            if m.get("primary"):
                return m.get("id", "")
        return mls[0].get("id", "") if mls else ""

    @property
    def file_count(self) -> int:
        return len(self.manifest.get("files") or [])

    def overrides_members(self) -> list[str]:
        pre = self.overrides_prefix
        return [n for n in self.names if n.startswith(pre) and not n.endswith("/")]

    def has_override(self, rel: str) -> bool:
        return (self.overrides_prefix + rel.lstrip("/")) in set(self.names)

    def read_override(self, rel: str) -> bytes | None:
        key = self.overrides_prefix + rel.lstrip("/")
        if self._zf is None or key not in self.names:
            return None
        return self._zf.read(key)

    def read(self, name: str) -> bytes:
        assert self._zf is not None
        return self._zf.read(name)

    # ---- 注入 ----
    def inject(
        self,
        dst: Path | str,
        files: dict[str, bytes],
        remove: set[str] | None = None,
    ) -> dict[str, int]:
        """把 ``files``（键为相对 overrides 的路径）注入并另存为 ``dst``。"""
        pre = self.overrides_prefix
        add = {pre + k.lstrip("/"): v for k, v in files.items()}
        rm = {(pre + r.lstrip("/")) for r in (remove or set())}
        return rewrite_zip(
            self.path,
            dst,
            add=add,
            remove=rm,
            order_first=(MANIFEST_NAME, MODLIST_NAME),
        )


# --------------------------------------------------------------------------- #
# 官方服务端包
# --------------------------------------------------------------------------- #
def _version_tokens(filename: str) -> list[str]:
    """取出文件名里从第一段版本号开始的全部 token（数字或字母段）。

    ``create-1.18.2-0.5.1.i.jar`` -> ``['1','18','2','0','5','1','i']``
    """
    stem = filename.rsplit("/", 1)[-1]
    stem = re.sub(r"\.jar(\.disabled)?$", "", stem, flags=re.I)
    m = re.search(r"[-_ ]v?(\d.*)$", stem)
    ver = m.group(1) if m else stem
    return re.findall(r"\d+|[A-Za-z]+", ver)


def _version_key(filename: str) -> tuple:
    """版本比较用键。

    数字段与字母段都要纳入，否则 ``0.5.1.f`` 与 ``0.5.1.i`` 会打成平手，
    排序退化成 zip 顺序，可能把旧 jar 当新版留下。

    编码为 ``(rank, num, txt)``：数字 token 的 rank=0，字母 token 的 rank=1。
    同一版本串的各 token 类型序列一致，因此逐位可安全比较。
    """
    toks = _version_tokens(filename)
    if not toks:
        return ((0, 0, ""),)
    return tuple(
        (0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in toks
    )


def _mod_stem(filename: str) -> str:
    """归组用的模组标识：去掉扩展名、去掉尾部版本号与加载器标记。"""
    stem = filename.rsplit("/", 1)[-1]
    stem = re.sub(r"\.jar(\.disabled)?$", "", stem, flags=re.I)
    # 砍掉第一个形如 -1.2.3 或 _1.2.3 的版本段
    m = re.search(r"[-_ ]v?\d", stem)
    if m and m.start() > 0:
        stem = stem[: m.start()]
    return re.sub(r"[\s_\-]+", "", stem).lower()


@dataclass
class ServerPack:
    """官方服务端包（完整可运行：mods/ + config/ + forge installer）。"""

    path: Path
    names: list[str] = field(default_factory=list)
    _zf: zipfile.ZipFile | None = None

    @classmethod
    def open(cls, path: Path | str) -> "ServerPack":
        p = Path(path)
        zf = zipfile.ZipFile(p)
        return cls(path=p, names=zf.namelist(), _zf=zf)

    def close(self) -> None:
        if self._zf is not None:
            self._zf.close()
            self._zf = None

    def __enter__(self) -> "ServerPack":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def mod_jars(self) -> list[str]:
        return [
            n
            for n in self.names
            if n.startswith(SERVER_MODS) and n.lower().endswith(".jar") and not n.endswith("/")
        ]

    def duplicate_mods(self) -> dict[str, dict]:
        """找出同一模组的多版本 jar。

        官方服务端包会残留上一版 jar（实测 0.34.1 里 the_vault 同时存在
        ``3.21.5.6573`` 与 ``3.21.6.6884``），Forge 会因 duplicate modid 拒绝启动。

        返回 ``{分组: {"keep": 最新, "drop": [其余], "versions": [...]}}``。
        """
        groups: dict[str, list[str]] = {}
        for n in self.mod_jars():
            groups.setdefault(_mod_stem(n), []).append(n)
        out: dict[str, dict] = {}
        for stem, members in groups.items():
            if len(members) < 2:
                continue
            ranked = sorted(members, key=_version_key, reverse=True)
            out[stem] = {
                "keep": ranked[0],
                "drop": ranked[1:],
                "versions": [_version_key(m) for m in ranked],
            }
        return out

    def read(self, name: str) -> bytes:
        assert self._zf is not None
        return self._zf.read(name)

    def exists(self, name: str) -> bool:
        return name in set(self.names)

    def inject(
        self,
        dst: Path | str,
        add: dict[str, bytes],
        remove: set[str] | None = None,
        dedupe: bool = True,
    ) -> dict[str, int]:
        """注入文件、可选自动剔除重复 modid 旧 jar，另存为 ``dst``。

        返回 ``rewrite_zip`` 的统计并附加 ``deduped`` 列表。
        """
        rm = set(remove or set())
        deduped: list[tuple[str, str]] = []
        if dedupe:
            for _stem, info in self.duplicate_mods().items():
                for d in info["drop"]:
                    if d not in rm:
                        rm.add(d)
                        deduped.append((d, info["keep"]))
        stats = rewrite_zip(self.path, dst, add=add, remove=rm)
        stats["deduped"] = deduped  # type: ignore[assignment]
        return stats
