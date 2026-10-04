"""模组 jar 解析：语言表、mods.toml、硬编码字面量。

支持两种来源：
* 磁盘上的 jar 文件
* 嵌套在整合包 zip 里的 jar（服务端包 408 个 jar 全靠这条路径）

对嵌套 jar 会做 LRU 缓存，避免同一个 59 MB 的 the_vault 被反复读。
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.cnrebase import classfile as cf  # noqa: E402

LANG_RE = re.compile(r"^assets/([^/]+)/lang/([a-zA-Z_]+)\.json$")


@dataclass
class ModMeta:
    """jar 的 mods.toml 摘要。"""

    mod_id: str = ""
    name: str = ""
    version: str = ""
    author: str = ""
    raw: dict = field(default_factory=dict)


def _toml_lite(text: str) -> dict:
    """极简 TOML 读取：只取我们需要的顶层键与 [[mods]] 段。

    不引第三方依赖；mods.toml 结构固定，正则足够。
    """
    out: dict = {"mods": []}
    cur: dict | None = None
    for raw in text.splitlines():
        line = raw.split("#")[0].strip()
        if not line:
            continue
        if line.startswith("[[") and line.endswith("]]"):
            sec = line[2:-2].strip()
            if sec == "mods":
                cur = {}
                out["mods"].append(cur)
            elif sec.startswith("dependencies"):
                cur = {}
                out.setdefault("dependencies", []).append(cur)
            else:
                cur = {}
                out.setdefault(sec, []).append(cur)
            continue
        m = re.match(r'^([A-Za-z0-9_.\-]+)\s*=\s*(.+)$', line)
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        if cur is not None:
            cur[key] = val
        else:
            out[key] = val
    return out


def _open_jar(obj: bytes | bytearray | io.BytesIO) -> zipfile.ZipFile:
    if isinstance(obj, io.BytesIO):
        return zipfile.ZipFile(obj)
    return zipfile.ZipFile(io.BytesIO(bytes(obj)))


class JarReader:
    """读取 jar（磁盘或内存），带语言表 / 元数据 / 硬编码接口。

    嵌套 jar 场景下重复构造代价高，调用方应复用实例。
    """

    def __init__(self, source: bytes | Path | str, label: str = ""):
        self.label = label or (source if isinstance(source, str) else "<bytes>")
        if isinstance(source, (bytes, bytearray)):
            self._data = bytes(source)
            self._zf = _open_jar(self._data)
        else:
            self._data = None
            self._zf = zipfile.ZipFile(source)

    def close(self) -> None:
        self._zf.close()

    def __enter__(self) -> "JarReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- 基础 ----
    @property
    def names(self) -> list[str]:
        return self._zf.namelist()

    def has(self, name: str) -> bool:
        return name in self._zf.namelist()

    def read(self, name: str) -> bytes:
        return self._zf.read(name)

    # ---- 语言表 ----
    def langs(self) -> dict[str, dict[str, str]]:
        """``{命名空间/语言码: {key: value}}``。"""
        out: dict[str, dict[str, str]] = {}
        for n in self._zf.namelist():
            m = LANG_RE.match(n)
            if not m:
                continue
            try:
                data = json.loads(self._zf.read(n).decode("utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                out.setdefault(f"{m.group(1)}/{m.group(2)}", {}).update(
                    {str(k): str(v) for k, v in data.items()}
                )
        return out

    def lang(self, ns: str, code: str = "en_us") -> dict[str, str]:
        key = f"assets/{ns}/lang/{code}.json"
        if key not in self._zf.namelist():
            return {}
        try:
            data = json.loads(self._zf.read(key).decode("utf-8"))
        except Exception:
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    # ---- 元数据 ----
    def meta(self) -> ModMeta:
        for cand in ("META-INF/mods.toml", "mods.toml"):
            if cand in self._zf.namelist():
                txt = self._zf.read(cand).decode("utf-8", "replace")
                d = _toml_lite(txt)
                mods = d.get("mods") or [{}]
                first = mods[0] if mods else {}
                return ModMeta(
                    mod_id=first.get("modId", ""),
                    name=first.get("displayName", ""),
                    version=first.get("version", ""),
                    author=first.get("authors", "") or first.get("author", ""),
                    raw=d,
                )
        # Fabric 风格兜底
        if "fabric.mod.json" in self._zf.namelist():
            try:
                d = json.loads(self._zf.read("fabric.mod.json").decode("utf-8"))
                return ModMeta(
                    mod_id=d.get("id", ""),
                    name=d.get("name", ""),
                    version=d.get("version", ""),
                    author=", ".join(d.get("authors") or []),
                    raw=d,
                )
            except Exception:
                pass
        return ModMeta()

    # ---- 硬编码 ----
    def classes(self, prefixes: tuple[str, ...] = ()) -> list[str]:
        out = [
            n
            for n in self._zf.namelist()
            if n.endswith(".class")
            and not n.startswith(("META-INF/", "org/", "net/", "com/google/"))
        ]
        if prefixes:
            out = [n for n in out if n.startswith(prefixes)]
        return out

    def hardcoded(
        self,
        prefixes: tuple[str, ...] = (),
        min_length: int = 1,
        skip_internal: bool = True,
    ) -> dict[str, list[str]]:
        """扫 class 常量池，返回 ``{字面量: [出现它的 class...]}``。

        只认 ``ldc`` 链上的 ``CONSTANT_String``，因此天然排除类名与描述符。
        """
        found: dict[str, list[str]] = {}
        for name in self.classes(prefixes):
            try:
                raw = self._zf.read(name)
                c = cf.parse(raw)
            except Exception:
                continue
            internal = cf.class_internal_name(raw, c) or ""
            for s in c.all_strings():
                if len(s) < min_length:
                    continue
                if skip_internal and _looks_internal(s, internal):
                    continue
                found.setdefault(s, []).append(name)
        return found


_INTERNAL_HINT = re.compile(
    r"^(?:[a-z][a-z0-9_]*/)+[A-Za-z0-9_$]+$"  # 斜杠内部名
    r"|^\(.*\).*"  # 方法描述符
    r"|^\[+[LZBSCIJFD]"  # 数组描述符
    r"|^(?:assets|data|config|kubejs|patchouli_books)/"  # 资源路径
)


def _looks_internal(s: str, own_class: str = "") -> bool:
    """启发式判断字符串是否为内部名/描述符/资源路径而非玩家可见文本。"""
    if s == own_class:
        return True
    if _INTERNAL_HINT.match(s):
        return True
    if "." in s and s.replace(".", "").isalnum() and " " not in s and len(s) > 6:
        # 形如 com.example.Foo 或 en_us.json 的点分类名
        if re.match(r"^[a-zA-Z_$][\w$]*(\.[a-zA-Z_$][\w$]*)+$", s):
            return True
    return False


# --------------------------------------------------------------------------- #
# 便捷入口
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=8)
def _reader_for_bytes(key: str, data: bytes) -> JarReader:
    return JarReader(data, label=key)


def reader_from_zip(zf: zipfile.ZipFile, member: str) -> JarReader:
    """从整合包 zip 里取出嵌套 jar 并构造 reader（带缓存）。"""
    info = zf.getinfo(member)
    key = f"{getattr(zf, 'filename', '')}!{member}!{info.file_size}"
    return _reader_for_bytes(key, zf.read(member))


def find_mod_jar(zf: zipfile.ZipFile, name_hint: str) -> str | None:
    """在 zip 的 mods/ 下按文件名片段找 jar（返回后缀匹配中版本最高的那个）。"""
    cands = [
        n
        for n in zf.namelist()
        if n.startswith("mods/")
        and n.lower().endswith(".jar")
        and name_hint.lower() in n.rsplit("/", 1)[-1].lower()
    ]
    if not cands:
        return None
    from tools.cnrebase.packs import _version_key

    return sorted(cands, key=_version_key, reverse=True)[0]
