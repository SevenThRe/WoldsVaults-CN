# -*- coding: utf-8 -*-
"""第三方模组语言通道的纯逻辑自检（不依赖完整构建，秒级）。

为什么单独留一份：下面这些**不变量**是构建门禁覆盖不到的 ——
门禁验的是「译料写进产物了吗」，而这里验的是「会不会把模组自带的中文弄丢」
「待译判据会不会静默失效」这类**反向**约束。二者缺一不可：

* :func:`vendor.build_lang` 必须以自带 ``zh_cn`` 为底 —— 语言文件是整文件覆盖
  语义，只写增量会把 ``mekanism`` 那 1446 键中文整片顶掉。
* :meth:`vendor.ModLang.fake` 的判据必须先剥 printf 占位符 ——
  ``" - %s (%s)"`` 里的 ``s`` 是格式符，不剥就会被当成实义字母（踩过）。
* :data:`vendor.LANG_CHANNEL_NS` 排除必须生效，否则本体 5 个命名空间会被两条
  通道分别写入。
* :func:`vendor.effective` 对没有译料的命名空间**不生成文件** —— 少一份文件就
  少一次同路径竞争。
* :func:`assets.save_langs` 的键必须是 ``ns/lang``，传裸命名空间要报错而不是
  静默产出名为 ``.json`` 的垃圾文件。
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from tools.cnrebase import assets, vendor


class _Report:
    def __init__(self) -> None:
        self.ok = True
        self.failed: list[str] = []

    def say(self, cond: bool, label: str, detail: str = "") -> None:
        print(f"  {'OK  ' if cond else 'FAIL'} {label}{('  ' + detail) if detail else ''}")
        if not cond:
            self.ok = False
            self.failed.append(label)


def run() -> int:
    r = _Report()

    print("=" * 78)
    print("1. build_lang：自带 zh 为底 + 译料覆盖其上")
    print("=" * 78)
    rec = vendor.ModLang(
        ns="compressium", jar="Compressium.jar", modid="compressium",
        en={"itemGroup.compressium": "Compressium", "block.compressium.a": "Cobble"},
        zh={"itemGroup.compressium": "Compressium", "block.compressium.a": "圆石"},
    )
    out = vendor.build_lang(rec, {"itemGroup.compressium": "压缩方块"})
    r.say(out["itemGroup.compressium"] == "压缩方块", "译料覆盖了自带的英文占位值")
    r.say(out["block.compressium.a"] == "圆石", "模组原有的中文被保留（没被顶掉）")
    r.say(len(out) == 2, "文件条目数不变", str(len(out)))

    print()
    print("=" * 78)
    print("2. 待译判据：伪翻译识别、无字母条目排除")
    print("=" * 78)
    r.say(rec.fake() == ["itemGroup.compressium"], "识别伪翻译（值 == 英文）",
          str(rec.fake()))
    r.say(rec.missing() == [], "无缺键", str(rec.missing()))
    rows = vendor.todo({"compressium": rec}, {})
    r.say(rows == [("compressium", "itemGroup.compressium", "Compressium")],
          "待译 = 伪翻译那一条", str(rows))
    rows2 = vendor.todo(
        {"compressium": rec}, {"compressium": {"itemGroup.compressium": "压缩方块"}})
    r.say(rows2 == [], "译料已有的不再列出")

    # 判据本身：占位符里的 s 不算实义字母
    r.say(vendor._has_letter("Inferium") is True, "有实义字母 → True")
    r.say(vendor._has_letter("1") is False, "纯数字 → False")
    r.say(vendor._has_letter(" - %s (%s)") is False,
          "只有占位符 → False（%s 的 s 不是实义字母）")
    r.say(vendor._has_letter("%s Crop") is True, "占位符之外的字母仍算 → True")
    r.say(vendor._has_letter("%1$s was trying to cross a wired fence") is True,
          "%1$s 形态的占位符被正确剥离")

    norec = vendor.ModLang(
        ns="x", en={"cropTier.x.1": "1", "tooltip.x.buff": " - %s (%s)"},
        zh={"cropTier.x.1": "1", "tooltip.x.buff": " - %s (%s)"},
    )
    r.say(norec.fake() == [], "值等于英文但无实义字母 → 不算伪翻译", str(norec.fake()))
    r.say(vendor.todo({"x": norec}, {}) == [],
          "这类条目不进待译清单（否则永远清不到零）")

    print()
    print("=" * 78)
    print("3. 通道边界：LANG_CHANNEL_NS 排除、effective 只处理有译料的")
    print("=" * 78)
    tv = {"the_vault": vendor.ModLang(ns="the_vault", en={"a": "A"}), "compressium": rec}
    r.say(vendor.todo(tv, {}) == [("compressium", "itemGroup.compressium", "Compressium")],
          "归语言表通道的命名空间被排除")
    r.say(vendor.effective(tv, {}) == {}, "无译料时不生成文件（避免无意义竞争）")
    eff = vendor.effective(tv, {"compressium": {"itemGroup.compressium": "压缩方块"}})
    r.say(set(eff) == {"compressium"}, "有译料时只生成该命名空间", str(list(eff)))
    r.say(eff["compressium"]["block.compressium.a"] == "圆石", "生成的文件仍以自带为底")

    print()
    print("=" * 78)
    print("4. save_langs 的落盘路径与键格式校验")
    print("=" * 78)
    with tempfile.TemporaryDirectory() as td:
        d = Path(td)
        n = assets.save_langs(d, {"compressium/zh_cn": {"k": "压缩"}})
        p = d / "assets" / "compressium" / "lang" / "zh_cn.json"
        r.say(n == 1, "返回写入文件数", str(n))
        r.say(p.is_file(), "路径形如 assets/<ns>/lang/zh_cn.json",
              str(p.relative_to(d)))
        r.say(json.loads(p.read_text(encoding="utf-8")) == {"k": "压缩"},
              "内容可解析")

        # 裸命名空间必须报错 —— 历史上会静默产出名为 `.json` 的垃圾文件
        # （文件名缺失、玩家侧加载不到，而构建全程不报错）。
        for bad_key in ("compressium", "/zh_cn", "compressium/", ""):
            try:
                assets.save_langs(d, {bad_key: {"k": "压缩"}})
                r.say(False, f"非法键 {bad_key!r} 应报错，却静默通过")
            except ValueError:
                r.say(True, f"非法键 {bad_key!r} 被拒")

        # 非法键不能留下垃圾文件
        leftovers = [x.name for x in (d / "assets").rglob("*.json")
                     if x.name != "zh_cn.json"]
        r.say(leftovers == [], "非法键没有产出垃圾文件", str(leftovers))

    print()
    print("=" * 78)
    if r.ok:
        print("自检结果：全部通过 ✓")
    else:
        print(f"自检结果：{len(r.failed)} 项失败 ✗")
        for f in r.failed:
            print(f"  - {f}")
    return 0 if r.ok else 1
