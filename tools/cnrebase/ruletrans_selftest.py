# -*- coding: utf-8 -*-
"""``ruletrans`` 的纯逻辑自检（不依赖真实语料，秒级）。

为什么单独留一份：这里验的是组合法的**判据**，而不是「今天跑了多少条」——
一旦判据错，整批译文会以看似合理的方式静默走样：

* 后缀投票在证据不足时**必须弃权**（票数 < 3，或最高票并列）；
* 有足够且唯一证据时**必须学到**正确的构件；
* 组合拼接**必须在词边界**上进行、且拼接处不加空格；
* 多级构件（``Vertical Slab`` 未被整体学到）**必须能拆成两级**拼出来；
* 质量闸门**必须**拦下含 ASCII 字母残留 / 占位符 / 与英文逐字相同的结果。

打印每项 ``PASS/FAIL`` 与总结，返回 0（全过）或 1。
"""
from __future__ import annotations

from tools.cnrebase import ruletrans as rt


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


def run() -> int:
    r = _Report()

    # ------------------------------------------------------------------ #
    print("=" * 78)
    print("1. learn_shapes：证据不足必须弃权（票数 < 3）")
    print("=" * 78)
    terms = {
        "Stone Slab": "石头台阶",
        "Oak Slab": "橡木台阶",
        "Stone": "石头",
        "Oak": "橡木",
    }
    targets = ["Stone Slab", "Oak Slab", "Iron Slab", "Brick Slab", "Tuff Slab"]
    shapes, detail = rt.learn_shapes(targets, terms, min_freq=2, min_votes=3)
    r.say("Slab" not in shapes,
          "只有 2 票时 Slab 不被采信", f"shapes={shapes}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("2. learn_shapes：票数达标且唯一最高时学到构件")
    print("=" * 78)
    terms2 = dict(terms)
    terms2["Iron Slab"] = "铁台阶"
    terms2["Iron"] = "铁"
    shapes2, detail2 = rt.learn_shapes(targets, terms2, min_freq=2, min_votes=3)
    r.say(shapes2.get("Slab") == "台阶",
          "3 票唯一最高 -> Slab=台阶", f"{shapes2.get('Slab')!r} {detail2.get('Slab')}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("3. learn_shapes：最高票并列时仍弃权")
    print("=" * 78)
    terms3 = {
        "Stone Slab": "石头台阶",
        "Oak Slab": "橡木台阶",
        "Brick Slab": "砖平板",
        "Iron Slab": "铁平板",   # 与「台阶」平分
        "Stone": "石头", "Oak": "橡木", "Brick": "砖", "Iron": "铁",
    }
    shapes3, _d3 = rt.learn_shapes(
        ["Stone Slab", "Oak Slab", "Brick Slab", "Tuff Slab"], terms3,
        min_freq=2, min_votes=2)
    r.say("Slab" not in shapes3,
          "并列最高票（2 vs 2）不采信", f"shapes={shapes3}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("4. 组合拼接：<原子材质> + <构件>，拼接处不加空格")
    print("=" * 78)
    t = rt.Translator(terms={"Sandstone": "砂岩"}, shapes={"Slab": "台阶"},
                      materials={"Stone": "石头"})
    zh, how, _v = t.translate("Stone Slab")
    r.say(zh == "石头台阶", "Stone Slab -> 石头台阶", f"{zh!r} via {how}")
    zh, how, _v = t.translate("Stone Vertical Slab")
    r.say(zh is None, "未学到的构件不可凭空生成", f"{zh!r}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("5. 多级构件：Vertical Slab 拆两级")
    print("=" * 78)
    t2 = rt.Translator(terms={}, shapes={"Vertical": "竖直", "Slab": "台阶"},
                       materials={"Stone": "石头"})
    zh, how, _v = t2.translate("Stone Vertical Slab")
    r.say(zh == "石头竖直台阶", "Stone Vertical Slab -> 石头竖直台阶", f"{zh!r} via {how}")
    r.say(how == "l2", "走的是两级构件分支", f"{how!r}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("6. 材质前缀可拼合：Black Sandstone Slab")
    print("=" * 78)
    t3 = rt.Translator(terms={"Sandstone": "砂岩"}, shapes={"Slab": "台阶"},
                       materials={"Black": "黑色"})
    zh, how, _v = t3.translate("Black Sandstone Slab")
    r.say(zh == "黑色砂岩台阶", "Black Sandstone Slab -> 黑色砂岩台阶", f"{zh!r} via {how}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("7. 质量闸门：ASCII 字母 / 占位符 / 逐字相同")
    print("=" * 78)
    r.say(rt.check_quality("Foo Bar", "Foo Bar") == "ascii", "含 ASCII 字母被拦")
    r.say(rt.check_quality("Ashpen Slab", "Ashpen台阶") == "ascii", "英文残留被拦")
    r.say(rt.check_quality("Hello %s", "你好") == "placeholder", "占位符被拦")
    r.say(rt.check_quality("Foo", "Foo") is not None, "逐字相同被拦")
    r.say(rt.check_quality("Stone Slab", "石头台阶") is None, "合法结果放行")
    r.say(rt.check_quality("ME", "ME") is None, "白名单 ME 放行")
    r.say(rt.check_quality("Stone Slab", "石头台阶", used_votes=[2]) == "low-votes",
          "参与部件票数 < 3 被拦")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("8. 可重复性：同输入两次学习结果一致")
    print("=" * 78)
    s_a, _ = rt.learn_shapes(targets, terms2, min_freq=2, min_votes=3)
    s_b, _ = rt.learn_shapes(targets, terms2, min_freq=2, min_votes=3)
    r.say(s_a == s_b == {"Slab": "台阶"}, "两次学习完全一致", f"{s_a}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("9. G1「块」守卫：非 Block 结尾的复合材质不得以「块」收尾")
    print("=" * 78)
    kept, gdrops = rt.apply_guards(
        {"Exposed Copper": "斑驳的铜块", "Stone Block": "石头块", "Foo": "块"},
        {"Stone": "石头"}, {"Block": "块"}, {})
    dropped_set = {e: why for e, why in gdrops}
    r.say(dropped_set.get("Exposed Copper") == "G1-block",
          "斑驳的铜块（非 Block）被 G1 拦下", str(dropped_set.get("Exposed Copper")))
    r.say("Stone Block" in kept, "Stone Block（Block 结尾 + 可拼出）放行", str(kept))
    r.say("Exposed Copper" not in kept, "被拦条目未保留")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("10. G2 构件后缀压过原版：Brick 作后缀译「砖」，不吃原版「红砖」")
    print("=" * 78)
    t_g2 = rt.Translator(
        terms={}, shapes=dict(rt.SHAPE_SEEDS),
        materials={}, vanilla={"Brick": "红砖", "Tuff": "凝灰岩"})
    zh, how, _v = t_g2.translate("Tuff Brick")
    r.say(zh == "凝灰岩砖", "Tuff Brick -> 凝灰岩砖（非凝灰岩红砖）", f"{zh!r} via {how}")
    r.say("Brick" in rt.SHAPE_SEEDS and rt.SHAPE_SEEDS["Brick"] == "砖",
          "SHAPE_SEEDS 显式登记 Brick=砖")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("11. G3 复合可导出守卫：拼不出的复合材质丢弃，拼得出的保留")
    print("=" * 78)
    _k, g3 = rt.apply_guards({"Foo Bar": "甲乙丙"}, {}, {}, {})
    r.say(any(e == "Foo Bar" and why == "G3-not-composable" for e, why in g3),
          "Foo Bar（原子拼不出）被 G3 拦下", str(g3))
    kept2, g3b = rt.apply_guards(
        {"Black Sandstone": "黑色砂岩", "Black": "黑色"},
        {"Sandstone": "砂岩"}, {}, {})
    r.say(kept2.get("Black Sandstone") == "黑色砂岩" and not g3b,
          "Black Sandstone（可拼出）保留", f"{kept2} {g3b}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("12. G4 自一致守卫：同一短语独立成条与嵌入更长短语须同译")
    print("=" * 78)
    t_g4 = rt.Translator(
        terms={"Tuff": "凝灰岩"},
        shapes={"Brick Vertical Slab": "砖竖直台阶", "Brick": "砖", "Slab": "台阶"},
        materials={"Tuff Brick": "凝灰岩红砖"},  # 污染源（应被 G4 抓出）
        vanilla={}, corrections={})
    acc = [
        ("k1", "Tuff Brick", "凝灰岩红砖", "atom"),
        ("k2", "Tuff Brick Slab", "凝灰岩红砖台阶", "l1-atomic"),
        ("k3", "Tuff Brick Vertical Slab", "凝灰岩砖竖直台阶", "l1-atomic"),
    ]
    conf = rt._detect_conflicts(
        acc, t_g4, ["Tuff Brick", "Tuff Brick Slab", "Tuff Brick Vertical Slab"])
    r.say("Tuff Brick" in conf,
          "Tuff Brick 两处译法不一致被抓出", str(conf))
    clean = rt._detect_conflicts(
        [("k1", "Tuff Brick", "凝灰岩砖", "shape")], t_g4,
        ["Tuff Brick", "Tuff Brick Slab"])
    r.say(clean == {}, "仅一条、无对照时不误报", str(clean))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("13. 输出唯一性：按 key 去重 + 重复 key 断言（合并前防歧义）")
    print("=" * 78)
    rows = [
        ("block.x.slab", "X Slab", "X台阶", "l1-atomic"),
        ("block.x.slab", "X Slab", "X台阶", "l1-atomic"),   # 同一 key 重复
        ("item.x.slab", "X Slab", "X台阶", "l1-atomic"),     # 同 en 不同 key：必须各自保留
    ]
    deduped = rt._dedupe_by_key(rows)
    r.say([x[0] for x in deduped] == ["block.x.slab", "item.x.slab"],
          "同 key 去重、同 en 不同 key（block./item.）保留",
          str([x[0] for x in deduped]))
    rt._assert_unique_keys(deduped, "t")
    r.say(True, "去重后断言「无重复 key」通过")
    threw = False
    try:
        rt._assert_unique_keys(rows, "t")
    except ValueError:
        threw = True
    r.say(threw, "发现重复 key 时断言抛错（宁停不脏）")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("14. G4 豁免：整条已人工校正者不再被判自相矛盾")
    print("=" * 78)
    t_g4b = rt.Translator(
        terms={}, shapes={}, materials={}, vanilla={},
        corrections={"Mangrove Boat": "红树船",
                     "Mangrove Boat with Chest": "红树运输船"})
    acc2 = [
        ("k1", "Mangrove Boat", "红树船", "correction"),
        ("k2", "Mangrove Boat with Chest", "红树运输船", "correction"),
    ]
    conf2 = rt._detect_conflicts(
        acc2, t_g4b, ["Mangrove Boat", "Mangrove Boat with Chest"])
    r.say(conf2 == {},
          "整条校正的短语不再触发矛盾（红树船 vs 红树运输船）", str(conf2))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("15. 通用规则：含 corrections 词素则禁用 term-table 整条捷径（须词边界）")
    print("=" * 78)
    t15 = rt.Translator(
        terms={"Mangrovexyz Door": "伪红木门", "Mangrove Door": "红木门"},
        shapes={"Door": "门"}, materials={}, vanilla={},
        corrections={"Mangrove": "红树"})
    zh, how, _v = t15.translate("Mangrove Door")
    r.say(zh == "红树门" and how == "compose-corr",
          "Mangrove Door 走组合 -> 红树门（不吃 term-table 红木门）", f"{zh!r} via {how}")
    zh2, how2, _v = t15.translate("Mangrovexyz Door")
    r.say(zh2 == "伪红木门" and how2 == "atom",
          "子串反例：Mangrovexyz 不触发（仍走 term-table 整条）", f"{zh2!r} via {how2}")
    t15b = rt.Translator(
        terms={"Mangrove Door": "红木门"}, shapes={"Door": "门"}, materials={},
        vanilla={}, corrections={"Mangrove": "红树"},
        enforce_corrections_compose=False)
    zh3, how3, _v = t15b.translate("Mangrove Door")
    r.say(zh3 == "红木门" and how3 == "atom",
          "开关关闭 -> 退回 term-table 整条（可对照爆炸半径）", f"{zh3!r} via {how3}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("16. G5 括号禁令：输出含 [] 且 en 无 [] 则拒绝（en 自带则保留）")
    print("=" * 78)
    r.say(rt.check_quality("Small Iron Block Tiles", "[小型]铁块瓦") == "bracket",
          "真实反例 [小型]铁块瓦 被 G5 拦下", str(rt.check_quality("Small Iron Block Tiles", "[小型]铁块瓦")))
    r.say(rt.check_quality("Base Color [HEX]", "基本颜色 [十六进制]") is None,
          "en 自带方括号 -> 按原样保留放行")
    r.say(rt.check_quality("Stone", "石头") is None, "无括号正常放行")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("17. G6 单字母透传：en 的单字母 ASCII token 须原样出现在 zh")
    print("=" * 78)
    r.say(rt.check_quality("Small Filled Jars C", "[小型]满的玻璃罐℃") == "single-letter",
          "真实反例 C→℃ 被 G6 拦下",
          str(rt.check_quality("Small Filled Jars C", "[小型]满的玻璃罐℃")))
    r.say(rt.check_quality("Small Filled Jars A", "[小型]满的玻璃罐任") == "single-letter",
          "真实反例 A→任 被 G6 拦下")
    r.say(rt.check_quality("Variant A", "变体 A") is None,
          "en 单字母在 zh 中原样出现 -> 放行（豁免 ASCII）", str(rt.check_quality("Variant A", "变体 A")))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("18. G7 相邻重复词素：拼接出「相机相机」一律拒绝；材质含构件词素即丢")
    print("=" * 78)
    r.say(rt.check_quality("Polaroid Camera", "宝丽来相机相机") == "dup-morpheme",
          "真实反例 相机相机 被 G7 拦下", str(rt.check_quality("Polaroid Camera", "宝丽来相机相机")))
    r.say(rt.check_quality("Glass Jars", "玻璃玻璃罐") == "dup-morpheme",
          "真实反例 玻璃玻璃罐 被 G7 拦下")
    _k7, g7 = rt.apply_guards({"Polaroid": "宝丽来相机"}, {}, {"Camera": "相机"}, {})
    r.say("Polaroid" not in _k7 and any(w == "G7-material-shape" for _e, w in g7),
          "材质 Polaroid=宝丽来相机（含构件「相机」）被丢弃", str(g7))

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("19. G8 修饰词正规化：Small/Empty/Large/Tiny 走前置形容词，禁标记兜底")
    print("=" * 78)
    t_g8 = rt.Translator(terms={"Jars": "玻璃罐"}, shapes={}, materials={},
                         vanilla={}, corrections={})
    zh, how, _v = t_g8.translate("Empty Small Jars")
    r.say(zh == "空的小玻璃罐" and how == "modifier",
          "Empty Small Jars -> 空的小玻璃罐（前缀形容词）", f"{zh!r} via {how}")
    r.say(rt.check_quality("Empty Casing", "空弹壳") == "G8-modifier",
          "修饰词未落实为前置形容词 -> 拒绝", str(rt.check_quality("Empty Casing", "空弹壳")))
    r.say(rt.check_quality("Empty Small Jars", "空的小玻璃罐") is None,
          "正规前置形容词结果 -> 放行")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("20. 7 条短语须「经规则」得到正确译文（不依赖整条补丁，防规则退化）")
    print("=" * 78)
    rule_corr = {"Mangrove": "红树", "Quartz Pillar": "石英柱"}
    t_rule = rt.Translator(
        terms={"Mangrove Door": "红木门", "Mangrove Fence": "红木栅栏",
               "Mangrove Fence Gate": "红木栅栏门", "Mangrove Slab": "红木台阶",
               "Mangrove Stairs": "红木楼梯", "Mangrove Trapdoor": "红树林活板门",
               "Quartz Pillar Wall": "竖纹石英墙"},
        shapes={"Door": "门", "Fence": "栅栏", "Fence Gate": "栅栏门",
                "Slab": "台阶", "Stairs": "楼梯", "Trapdoor": "活板门", "Wall": "墙"},
        materials={}, vanilla={}, corrections=rule_corr)
    for en, exp in [
            ("Mangrove Door", "红树门"), ("Mangrove Fence", "红树栅栏"),
            ("Mangrove Fence Gate", "红树栅栏门"), ("Mangrove Slab", "红树台阶"),
            ("Mangrove Stairs", "红树楼梯"), ("Mangrove Trapdoor", "红树活板门"),
            ("Quartz Pillar Wall", "石英柱墙")]:
        zh, how, _v = t_rule.translate(en)
        r.say(zh == exp and how == "compose-corr",
              f"[规则] {en} -> {exp}", f"{zh!r} via {how}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("21. G9 弱词材质守卫：裸词 Light 不得泄漏成「光源方块」，仅后接颜色词作「淡」")
    print("=" * 78)
    t_g9 = rt.Translator(
        terms={"Light": "光源方块", "Green": "绿色", "Gray": "灰色",
               "Light Gray": "淡灰色"},
        shapes={"Cabinet": "柜"}, materials={}, vanilla={"Light": "光源方块"},
        corrections={})
    zh, how, _v = t_g9.translate("Light Green Cabinet")
    r.say(zh == "淡绿色柜", "Light Green Cabinet -> 淡绿色柜（不泄漏 光源方块）",
          f"{zh!r} via {how}")
    zh2, how2, _v = t_g9.translate("Light Cabinet")
    r.say(zh2 is None, "裸 Light + 构件 -> 未命中（黑名单生效，不再拼出 光源方块柜）",
          f"{zh2!r} via {how2}")
    zh3, how3, _v = t_g9.translate("Light Gray")
    r.say(zh3 == "淡灰色", "Light Gray 官方条目保持不变（不被覆盖）",
          f"{zh3!r} via {how3}")
    r.say("Light" in t_g9.weak_drops and "Light Green" in t_g9.weak_derived,
          "命中记录：裸词进 weak_drops、颜色对进 weak_derived",
          f"drops={t_g9.weak_drops} derived={sorted(t_g9.weak_derived)}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("22. Cut 译名一致：材质修饰位一律「切制」（不吃 term-table 的「剪切」）")
    print("=" * 78)
    t_cut = rt.Translator(
        terms={"Cut": "剪切", "Deepslate": "深层", "Andesite": "安山岩"},
        shapes={}, materials={"Polished": "磨制"}, vanilla={},
        corrections={"Cut": "切制", "Deepslate": "深板岩"})
    zh, how, _v = t_cut.translate("Polished Cut Deepslate")
    r.say(zh == "磨制切制深板岩",
          "真实反例 Polished Cut Deepslate -> 磨制切制深板岩（非 磨制剪切深板岩）",
          f"{zh!r} via {how}")
    # Cut 是「仅词素覆盖」校正：不得触发整条绕行，term-table 里正确的整条须保留
    t_cut2 = rt.Translator(
        terms={"Cut": "剪切", "Cut Copper Vertical Slab": "切制铜竖直台阶"},
        shapes={"Vertical Slab": "竖直台阶"}, materials={}, vanilla={},
        corrections={"Cut": "切制"})
    zh2, how2, _v = t_cut2.translate("Cut Copper Vertical Slab")
    r.say(zh2 == "切制铜竖直台阶" and how2 == "atom",
          "Cut 不触发绕行：Cut Copper Vertical Slab 仍走 term-table 整条",
          f"{zh2!r} via {how2}")

    # ------------------------------------------------------------------ #
    print()
    print("=" * 78)
    print("23. Acacia Leaf Hedge：整条校正 + 可作 Snowy 前缀（不出现多余的「木」）")
    print("=" * 78)
    t_ac = rt.Translator(
        terms={"Acacia": "金合欢木"}, shapes={},
        materials={"Snowy": "积雪的"}, vanilla={},
        corrections={"Acacia Leaf Hedge": "金合欢树叶篱笆", "Leaf Hedge": "树叶篱笆"})
    zh, how, _v = t_ac.translate("Acacia Leaf Hedge")
    r.say(zh == "金合欢树叶篱笆", "Acacia Leaf Hedge -> 金合欢树叶篱笆",
          f"{zh!r} via {how}")
    zh2, how2, _v = t_ac.translate("Snowy Acacia Leaf Hedge")
    r.say(zh2 == "积雪的金合欢树叶篱笆",
          "Snowy Acacia Leaf Hedge -> 积雪的金合欢树叶篱笆（整条校正作后缀生效）",
          f"{zh2!r} via {how2}")

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
