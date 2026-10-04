# -*- coding: utf-8 -*-
"""``langpack`` 的纯逻辑自检（不依赖完整构建，秒级）。

为什么单独留一份：这里验的是**反向**不变量 —— 不是「译文写进去了吗」，
而是「会不会把模组自带的中文弄丢」「zip 会不会被改坏」这类一旦出错就静默
发生、且要等玩家进游戏才暴露的约束：

* :func:`langpack.merge_files` 必须**后层覆盖前层**、且按命名空间分组 ——
  对应运行时「getResources 列表按序 put、后加载包优先」这条真实语义，
  也是「模组自带为底、我方译文按 key 叠加」的落点；
* :func:`langpack.build_resource_pack` 产出必须是合法资源包（含 ``pack.mcmeta``
  且语言表能原样解析回来）；
* :func:`langpack.patch_jar` 必须在「写回语言表」的同时**字节保真**地搬运其余条目
  （CRC 不变、条目数只在新建时 +1），并且原有的键不能被顶掉；
* :func:`langpack.load_lang_zip` 必须丢掉空值 / 非字符串值。

打印每项 ``PASS/FAIL`` 与总结，返回 0（全过）或 1。
"""
from __future__ import annotations

import hashlib
import json
import tempfile
import zipfile
from pathlib import Path

from tools.cnrebase import langpack


class _Report:
    """极简断言收集器，风格与 ``tools.cnrebase.selftest`` 保持一致。"""

    def __init__(self) -> None:
        self.ok = True
        self.failed: list[str] = []

    def say(self, cond: bool, label: str, detail: str = "") -> None:
        print(f"  {'PASS' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
        if not cond:
            self.ok = False
            self.failed.append(label)


def _make_jar(path: Path, entries: dict[str, bytes]) -> None:
    """造一个测试用 jar。"""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def _crc_map(path: Path) -> dict[str, int]:
    with zipfile.ZipFile(path) as zf:
        return {i.filename: i.CRC for i in zf.infolist()}


def _read_zip_json(path: Path, name: str) -> dict:
    with zipfile.ZipFile(path) as zf:
        return json.loads(zf.read(name).decode("utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run() -> int:
    r = _Report()

    # ------------------------------------------------------------------ #
    print("=" * 78)
    print("1. merge_files：后层覆盖前层 + 按命名空间分组")
    print("=" * 78)
    base = {"demo": {"a": "1", "b": "2"}, "other": {"x": "旧"}}
    top = {"demo": {"b": "3", "c": "4"}, "other": {"x": "新", "y": "加"}}
    m = langpack.merge_files(base, top)
    r.say(m["demo"] == {"a": "1", "b": "3", "c": "4"},
          "同名键取后到者、底层独有键保留", str(m["demo"]))
    r.say(m["other"] == {"x": "新", "y": "加"}, "跨命名空间独立合并", str(m["other"]))
    r.say(langpack.merge_files() == {}, "空输入 -> 空结果")
    r.say(len(m) == 2, "命名空间数量正确", str(list(m)))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("2. build_resource_pack：pack.mcmeta 合法 + 语言表可解析回原内容")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        out = d / "pack.zip"
        ns_lang = {"demo": {"k1": "值一", "k2": "值二"}, "solo": {"only": "唯一"}}
        dest = langpack.build_resource_pack(out, ns_lang, "测试语言包", pack_format=8)
        r.say(dest == out and out.is_file(), "产物已生成", str(dest))
        r.say(_read_zip_json(out, "assets/demo/lang/zh_cn.json") == ns_lang["demo"],
              "demo 语言表原样解析")
        r.say(_read_zip_json(out, "assets/solo/lang/zh_cn.json") == ns_lang["solo"],
              "solo 语言表原样解析")
        mc = _read_zip_json(out, "pack.mcmeta")
        r.say(isinstance(mc, dict) and "pack" in mc, "pack.mcmeta 含 pack 段", str(mc))
        r.say(mc["pack"].get("pack_format") == 8, "pack_format 正确",
              str(mc["pack"].get("pack_format")))
        r.say(mc["pack"].get("description") == "测试语言包", "description 用了给定名称")
        # 额外件
        out2 = d / "pack2.zip"
        langpack.build_resource_pack(out2, ns_lang, "带附件", extra_files={"pack.png": b"\x89PNG"})
        with zipfile.ZipFile(out2) as zf:
            r.say("pack.png" in zf.namelist(), "extra_files 被写入")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("3. patch_jar（已有 zh_cn）：条目数不变、非语言条目 CRC 不变、键不丢")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "existing.jar"
        dst = d / "existing.out.jar"
        lang_name = "assets/demo/lang/zh_cn.json"
        existing_lang = {"keep.1": "保留一", "override.me": "旧值"}
        _make_jar(src, {
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n",
            "com/example/Foo.class": bytes(range(256)) * 4,
            "data/foo/bar.json": b'{"x":1}',
            lang_name: langpack._lang_bytes(existing_lang),
        })
        before = _crc_map(src)
        non_lang = [n for n in before if n != lang_name]
        n = langpack.patch_jar(
            src, dst, {"demo": {"override.me": "新值", "new.key": "新增"}})
        after = _crc_map(dst)
        r.say(n == 1, "返回被写入的语言表文件数", str(n))
        r.say(len(after) == len(before) == 4, "条目数不变（替换而非新增）",
              f"{len(before)} -> {len(after)}")
        r.say(all(before[k] == after[k] for k in non_lang),
              "非语言条目 CRC 与源一致", str(non_lang))
        merged = _read_zip_json(dst, lang_name)
        r.say(merged.get("keep.1") == "保留一", "原有键没有丢", str(merged))
        r.say(merged.get("override.me") == "新值", "覆盖键取新值")
        r.say(merged.get("new.key") == "新增", "新键写入成功")
        r.say(len(merged) == 3, "合并后条目数正确", str(len(merged)))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("4. patch_jar（无 zh_cn）：条目数 +1 且内容正确")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "fresh.jar"
        dst = d / "fresh.out.jar"
        _make_jar(src, {
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\n",
            "com/example/Bar.class": b"\xca\xfe\xba\xbe",
        })
        n = langpack.patch_jar(src, dst, {"solo": {"a": "甲", "b": "乙"}})
        with zipfile.ZipFile(src) as zs, zipfile.ZipFile(dst) as zd:
            r.say(n == 1, "返回新建的文件数", str(n))
            r.say(len(zd.infolist()) == len(zs.infolist()) + 1, "条目数 +1",
                  f"{len(zs.infolist())} -> {len(zd.infolist())}")
        r.say(_read_zip_json(dst, "assets/solo/lang/zh_cn.json") == {"a": "甲", "b": "乙"},
              "新建语言表内容正确")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("5. load_lang_zip：丢弃空值 / 非字符串值")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        src = d / "messy.jar"
        raw = json.dumps({
            "good": "有效",
            "empty": "",
            "blank": "   ",
            "num": 5,
            "none": None,
            "nested": {"a": "b"},
        }, ensure_ascii=False)
        _make_jar(src, {"assets/demo/lang/zh_cn.json": raw.encode("utf-8")})
        got = langpack.load_lang_zip(src)
        r.say(got == {"demo": {"good": "有效"}}, "只留非空字符串值", str(got))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("6. 辅助：load_lang_dir / find_vendor_jars / conflicts")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        # load_lang_dir
        p = d / "assets" / "foo" / "lang" / "zh_cn.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('{"k": "值"}', encoding="utf-8")
        r.say(langpack.load_lang_dir(d) == {"foo": {"k": "值"}},
              "load_lang_dir 递归命中", str(langpack.load_lang_dir(d)))
        # find_vendor_jars
        mods = d / "mods"
        mods.mkdir()
        _make_jar(mods / "with.jar", {
            "assets/aaa/lang/zh_cn.json": b'{"a":"A"}',
            "assets/bbb/lang/zh_cn.json": b'{"b":"B"}',
        })
        _make_jar(mods / "without.jar", {"x.txt": b"hi"})
        vj = langpack.find_vendor_jars(mods)
        names = {q.name: nss for q, nss in vj.items()}
        r.say(names.get("with.jar") == {"aaa", "bbb"}, "自带 zh_cn 的命名空间集合",
              str(names.get("with.jar")))
        r.say(names.get("without.jar") == set(), "无 zh_cn 的 jar 映射到空集合")
        hit = langpack.conflicts(vj, {"bbb": {"b": "乙"}, "ccc": {"c": "丙"}})
        r.say(len(hit) == 1 and list(hit.values())[0] == {"bbb"},
              "conflicts 只报交集非空的 jar", str({q.name: n for q, n in hit.items()}))
        r.say(all(q.name != "without.jar" for q in hit), "无 zh_cn 的 jar 不进冲突")
        # 命名校验：本地烘焙包名不得含 I18n 的子串过滤器关键字
        r.say(langpack.pack_name_is_safe("CFPA-CN-Baked-1.18.2.zip") is True,
              "安全名通过", langpack.I18N_KEYWORD)
        r.say(langpack.pack_name_is_safe(
            "Minecraft-Mod-Language-Modpack-本地烘焙.zip") is False,
            "含关键字的包名被拒（否则会被 I18n 静默删除）")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("7. 路径穿越回归：非法命名空间必须被两个写侧入口拒绝")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        for ns in ("..", "../../evil", "a/b", ""):
            # (a) build_resource_pack 必须拒绝，且不落盘
            pack_out = d / "bad_pack.zip"
            try:
                langpack.build_resource_pack(pack_out, {ns: {"k": "v"}}, "x")
                r.say(False, f"build_resource_pack 应拒绝 ns={ns!r}，却通过")
            except ValueError:
                r.say(True, f"build_resource_pack 拒绝 ns={ns!r}")
            r.say(not pack_out.exists(), f"ns={ns!r} 未产出穿越产物（资源包）")

            # (b) patch_jar 必须拒绝，且不落盘
            src = d / "src.jar"
            _make_jar(src, {"x.txt": b"hi"})
            jar_dst = d / "bad_patch.jar"
            try:
                langpack.patch_jar(src, jar_dst, {ns: {"k": "v"}})
                r.say(False, f"patch_jar 应拒绝 ns={ns!r}，却通过")
            except ValueError:
                r.say(True, f"patch_jar 拒绝 ns={ns!r}")
            r.say(not jar_dst.exists(), f"ns={ns!r} 未产出穿越产物（jar）")

        # 合法命名空间不受影响
        ok = d / "ok.zip"
        langpack.build_resource_pack(ok, {"demo": {"k": "v"}}, "x")
        with zipfile.ZipFile(ok) as zf:
            names = zf.namelist()
        r.say(names == ["pack.mcmeta", "assets/demo/lang/zh_cn.json"],
              "合法 ns 正常产出（未误伤）", str(names))

        # 单元级：_check_ns 的接受/拒绝集合（含真实命名空间与边角）
        valid = ["the_vault", "woldsvaults", "kubejs", "qolhunters", "packmenu",
                 "ae2", "my-mod.v2", "a_b.c"]
        bad_unit = ["Demo", "demo\n", "demo x", ".", "..", "", "a/b", "../../evil"]
        ok_valid = True
        for g in valid:
            try:
                langpack._check_ns(g)
            except ValueError:
                ok_valid = False
        r.say(ok_valid, "_check_ns 接受全部合法命名空间", f"{len(valid)} 个")
        ok_bad = True
        for bad in bad_unit:
            try:
                langpack._check_ns(bad)
                ok_bad = False
            except ValueError:
                pass
        r.say(ok_bad, "_check_ns 拒绝大写/换行/空格/点/斜杠等非法名", f"{len(bad_unit)} 个")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("8. 可复现构建回归：同输入两次 build_resource_pack 逐字节一致")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        ns_lang = {"demo": {"k1": "值一", "k2": "值二"}, "solo": {"only": "唯一"}}
        extra = {"pack.png": b"\x89PNG\r\n\x1a\n"}
        a, b = d / "a.zip", d / "b.zip"
        langpack.build_resource_pack(a, ns_lang, "可复现", extra_files=dict(extra))
        langpack.build_resource_pack(b, ns_lang, "可复现", extra_files=dict(extra))
        ha, hb = _sha256(a), _sha256(b)
        r.say(ha == hb, "两次构建 sha256 相等（可复现）", f"{ha[:12]} vs {hb[:12]}")
        with zipfile.ZipFile(a) as zf:
            dts = {info.date_time for info in zf.infolist()}
        r.say(dts == {langpack._EPOCH_DT}, "所有条目时间戳为固定 epoch", str(dts))

    print()
    print("=" * 78)
    if r.ok:
        print("自检结果：全部通过 ✓")
    else:
        print(f"自检结果：{len(r.failed)} 项失败 ✗")
        for f in r.failed:
            print(f"  - {f}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    raise SystemExit(run())
