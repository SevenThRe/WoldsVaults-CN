#!/usr/bin/env python3
"""Rebuild skyblockaddon-8.2-CN.jar with COMPLETE translation of the
permission registries, remaining GUI text, and the server-side lang file.

WHY
---
The previous CN jar translated the GUI chrome (返回/上一页/标题) and shipped
``lang/zh_cn.json``, but in-game the permission menus were still English:

1. **Permission items** (names like "Pickup/Drop Items", lore "Click to
   toggle...", "♦ Status: ") live in ``assets/skyblockaddon/registries/
   permissions/*.json`` as literal text — never translated.
2. **The mod never reads ``zh_cn.json``.** ``ResourceManager.commonSetup``
   copies ``lang/en_us.json`` (hardcoded) to ``config/skyblockaddon/
   language.json`` with REPLACE_EXISTING on every startup and loads THAT.
   Server-side resolution goes through ``SkyBlockAddonLanguage``
   (a plain map lookup), so Chinese must be written into ``en_us.json``.
3. The ``%group_category%`` title word ("General") is computed in code from
   ``category_id`` (capitalize), not from any lang file — we replace the
   title template in our own GUI file instead (zero risk).

Extraction semantics (verified via javap), i.e. why replacing the jar is
enough on the server — no manual config cleanup needed:

* ``language.json``, all ``guis/*.json`` → generateFile = REPLACE_EXISTING
  on every startup;
* ``registries/permissions`` + ``registries/groups`` → extractResourceDirectory
  → extractSingleFile → generateFile (REPLACE_EXISTING) on every startup.

SAFETY (same philosophy as skyblockaddon_cn.py):
* entry set identical to the official jar (nothing added/removed/dropped
  except the one zh_cn.json language file carried from the previous CN);
* every .class byte-identical to the official jar;
* every transformed JSON keeps the exact structure fingerprint (shape);
* lang key set unchanged (values swapped to Chinese);
* after translation, no unwhitelisted Latin text may remain in the files
  we touch — a missed string fails the build loudly.
"""
import json
import sys
import zipfile

from tools.cnrebase import sba_translations as T


# --------------------------------------------------------------------------- #
def shape(obj):
    """Structure fingerprint: keys + types + list lengths, ignoring values."""
    if isinstance(obj, dict):
        return {k: shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return ["list%d" % len(obj)] + [shape(x) for x in obj[:3]]
    if isinstance(obj, str):
        return "str"
    return type(obj).__name__


def is_component(s: str) -> bool:
    """display_name 形态：JSON-in-string（{"text": ...}）。"""
    return s.startswith("{") and '"text"' in s


def translate_component(s: str, text_map: dict, name_map: dict) -> str:
    """翻译 display_name 组件串：解析内层 JSON，只换 text，原样重排。"""
    obj = json.loads(s)
    old = obj.get("text")
    new = name_map.get(old)
    if new is None:
        new = text_map.get(old, old)
    obj["text"] = new
    return json.dumps(obj, ensure_ascii=False)


def translate_registry(raw: bytes, fname: str, stats: dict) -> bytes:
    """翻译一个 registries/permissions/*.json。"""
    bom = raw.startswith(b"\xef\xbb\xbf")
    d = json.loads(raw.decode("utf-8-sig"))
    text_map = T.text_map()
    unknown: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k == "text" and isinstance(v, str):
                    if v in text_map:
                        o[k] = text_map[v]
                    elif _latin(v) and v not in T.ALLOWED_KEEP and "%" not in v:
                        unknown.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if isinstance(v, str) and is_component(v):
                    o[i] = translate_component(v, text_map, T.PERM_NAME)
                    stats["components"] += 1
                else:
                    walk(v)

    walk(d)

    # display_name 组件里漏翻的英文名也要报出来
    def scan_names(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "display_name" and isinstance(v, list):
                    for s in v:
                        if isinstance(s, str) and is_component(s):
                            t = json.loads(s).get("text", "")
                            if _latin(t) and t not in T.ALLOWED_KEEP and "%" not in t:
                                if not any("\u4e00" <= c <= "\u9fff" for c in t):
                                    unknown.append("(name) " + t)
                else:
                    scan_names(v)
        elif isinstance(o, list):
            for v in o:
                scan_names(v)

    scan_names(d)
    if unknown:
        raise SystemExit("%s: untranslated text:\n  %s"
                         % (fname, "\n  ".join(sorted(set(unknown)))))

    out = json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8")
    if bom:
        out = b"\xef\xbb\xbf" + out
    if shape(json.loads(raw.decode("utf-8-sig"))) != shape(d):
        raise SystemExit(fname + ": shape changed!")
    return out


def translate_gui(raw: bytes, fname: str, stats: dict) -> bytes:
    """翻译 GUI JSON：display_name 组件 + 纯文本 text + set_permission 标题。"""
    bom = raw.startswith(b"\xef\xbb\xbf")
    d = json.loads(raw.decode("utf-8-sig"))
    text_map = T.text_map()
    unknown: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if isinstance(v, str):
                    if k == "text" and v in text_map:
                        o[k] = text_map[v]
                    elif is_component(v):
                        o[k] = translate_component(v, text_map, T.PERM_NAME)
                        stats["components"] += 1
                    elif fname.endswith("set_permission.json") and k == "title":
                        pass  # 标题在下面统一处理
                else:
                    walk(v)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                if isinstance(v, str) and is_component(v):
                    o[i] = translate_component(v, text_map, T.PERM_NAME)
                    stats["components"] += 1
                else:
                    walk(v)

    walk(d)

    if fname.endswith("set_permission.json"):
        # 标题里的 %group_category% 是代码现算的英文（capitalize(category_id)），
        # 改模板为固定中文。需要在任意深度替换（title 是组件串列表）。
        hit = False

        def replace_deep(o):
            nonlocal hit
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    if isinstance(v, str):
                        if "%group_category%" in v:
                            o[k] = v.replace("%group_category%", "权限设置")
                            hit = True
                    else:
                        replace_deep(v)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    if isinstance(v, str):
                        if "%group_category%" in v:
                            o[i] = v.replace("%group_category%", "权限设置")
                            hit = True
                    else:
                        replace_deep(v)

        replace_deep(d)
        if not hit:
            raise SystemExit(fname + ": %group_category% template not found!")

    def residual(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "text" and isinstance(v, str):
                    if _latin(v) and v not in T.ALLOWED_KEEP and "%" not in v:
                        if not any("\u4e00" <= c <= "\u9fff" for c in v):
                            unknown.append(v)
                else:
                    residual(v)
        elif isinstance(o, list):
            for v in o:
                if isinstance(v, str) and is_component(v):
                    t = json.loads(v).get("text", "")
                    if _latin(t) and t not in T.ALLOWED_KEEP and "%" not in t:
                        if not any("\u4e00" <= c <= "\u9fff" for c in t):
                            unknown.append("(name) " + t)
                else:
                    residual(v)

    residual(d)
    if unknown:
        raise SystemExit("%s: untranslated text:\n  %s"
                         % (fname, "\n  ".join(sorted(set(unknown)))))

    out = json.dumps(d, ensure_ascii=False, indent=1).encode("utf-8")
    if bom:
        out = b"\xef\xbb\xbf" + out
    return out


def _latin(s: str) -> bool:
    return any(("a" <= c <= "z") or ("A" <= c <= "Z") for c in s)


# --------------------------------------------------------------------------- #
def build(cn_path: str, official_path: str, out_path: str) -> int:
    with zipfile.ZipFile(official_path) as zo, zipfile.ZipFile(cn_path) as zc:
        off_names = set(zo.namelist())
        cn_names = set(zc.namelist())
        assert cn_names - off_names == {"assets/skyblockaddon/lang/zh_cn.json"}, \
            "CN jar 应当只比官方多一份 zh_cn.json"

        # lang 键集合必须一致（值换成中文）
        en = json.loads(zo.read("assets/skyblockaddon/lang/en_us.json").decode("utf-8-sig"))
        zh = json.loads(zc.read("assets/skyblockaddon/lang/zh_cn.json").decode("utf-8-sig"))
        assert set(en.keys()) == set(zh.keys()), "zh_cn.json 键集合与 en_us 不一致"
        missing_zh = [k for k, v in zh.items()
                      if not any("\u4e00" <= c <= "\u9fff" for c in v)]
        if missing_zh:
            raise SystemExit("zh_cn.json 有未翻译键: %s" % missing_zh)

        stats = {"components": 0, "registries": 0, "guis": 0}
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out:
            for info in zc.infolist():
                name = info.filename
                data = zc.read(name)
                if name.startswith("assets/skyblockaddon/registries/permissions/") \
                        and name.endswith(".json"):
                    data = translate_registry(data, name, stats)
                    stats["registries"] += 1
                elif name == "assets/skyblockaddon/lang/en_us.json":
                    # 服务端只读这个文件（每次启动覆盖 config/skyblockaddon/
                    # language.json 后加载）。写入中文值；**不带 BOM**——
                    # Java 的 UTF-8 Reader 不剥 BOM，带 BOM 会让 Gson 解析失败。
                    data = json.dumps(zh, ensure_ascii=False, indent=1).encode("utf-8")
                elif name.startswith("assets/skyblockaddon/guis/") \
                        and name.endswith(".json"):
                    new = translate_gui(data, name, stats)
                    if new != data:
                        stats["guis"] += 1
                    data = new
                out.writestr(info, data)

    # ---- 验证 -----------------------------------------------------------
    with zipfile.ZipFile(official_path) as zo, zipfile.ZipFile(out_path) as zn:
        on, nn = set(zo.namelist()), set(zn.namelist())
        assert nn - on == {"assets/skyblockaddon/lang/zh_cn.json"}, "新增条目越界"
        assert on - nn == set(), "不允许删除条目"
        for n in on:
            if n.endswith(".class"):
                assert zo.read(n) == zn.read(n), "class 被改动: " + n

        changed = [n for n in on if zo.read(n) != zn.read(n)]
        for n in changed:
            assert n.startswith("assets/skyblockaddon/"), "非资产文件被改动: " + n
            if n.endswith(".json") and "lang/" not in n:
                a = json.loads(zo.read(n).decode("utf-8-sig"))
                b = json.loads(zn.read(n).decode("utf-8-sig"))
                assert shape(a) == shape(b), "结构变化: " + n

    print("permission registries translated : %d files" % stats["registries"])
    print("gui files updated                : %d files" % stats["guis"])
    print("text components translated       : %d" % stats["components"])
    print("lang/en_us.json                  : -> Chinese (%d keys)" % len(zh))
    print("changed files vs official        : %d + zh_cn.json" % len(changed))
    print("classes                          : byte-identical")
    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        print("usage: skyblockaddon_cn2.py <current-CN.jar> <official.jar> <out.jar>")
        return 2
    return build(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    raise SystemExit(main())
