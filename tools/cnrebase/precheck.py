# -*- coding: utf-8 -*-
"""``config_extra`` 预检：改译料层的「新增配置键」后，先花几秒确认形态不会被打回。

门禁【2】【3】的「预置 JSON 结构无退化」做的是**叶子路径集合**比对
（源包 vs 产物，要求「源 ⊆ 产物」）。``config_extra`` 会替换或新增键，
一旦把源里的对象段压成单段 —— 例如把
``[{"text": "…"}, {"text": "…", "color": "gold"}]`` 写成 ``[{"text": "…"}]``
—— 叶子路径就少一条 ``.color``，**8 分钟后构建才失败**。

本模块在几秒内跑同一套判定（同一份 ``_json_leaves`` / ``_merge_extra_keys``），
把这类错误提前到「改完立刻知道」。

用法::

    python -m tools.cnrebase.precheck \\
        --client "C:/Users/ASUS/Downloads/Wold's Vaults-0.34.1.zip" \\
        --server "C:/Users/ASUS/Downloads/official-wolds-vaults-server-pack-0-34-1.zip" \\
        --corpus translations/cn-rebase
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import zipfile
from pathlib import Path

from .build import EXTRA_OVERWRITE, _merge_extra_keys
from .corpus import Corpus
from .verify import _json_leaves

#: 客户端包内 config 的存放前缀（服务端包同理）。
PREFIXES = ("overrides/", "config/", "")


def _find_member(z: zipfile.ZipFile, target: str) -> str | None:
    names = set(z.namelist())
    for pre in PREFIXES:
        if pre + target in names:
            return pre + target
    return None


def check_pack(path: Path, extras: dict[str, object], label: str) -> tuple[int, int]:
    """返回 ``(检查数, 失败数)``。"""
    print(f"\n=== {label} :: {path.name} ===")
    n_checked = n_bad = 0
    with zipfile.ZipFile(path) as z:
        for target, frag in sorted(extras.items()):
            member = _find_member(z, target)
            if member is None:
                print(f"  --  {target}（源包无此文件，跳过）")
                continue
            raw = z.read(member)
            src = json.loads(raw.decode("utf-8"))
            merged = copy.deepcopy(src)
            overwrite = target in EXTRA_OVERWRITE
            added, skipped = _merge_extra_keys(merged, frag, overwrite=overwrite)
            ls = _json_leaves(raw) or set()
            lo = _json_leaves(
                json.dumps(merged, ensure_ascii=False).encode("utf-8")) or set()
            gone = sorted(ls - lo)
            n_checked += 1
            if gone:
                n_bad += 1
                print(f"  ✗  {target}")
                print(f"       叠加 {added} 键（overwrite={overwrite}）"
                      f" 跳过 {len(skipped)}")
                print(f"       丢 {len(gone)}/{len(ls)} 个叶子：{gone[:6]}")
            else:
                print(f"  ok {target}  叠加 {added} 键"
                      f"（overwrite={overwrite}）跳过 {len(skipped)}"
                      f"  叶子 {len(ls)} → {len(lo)}")
            if skipped:
                print(f"       跳过明细（前 3）：{skipped[:3]}")
    return n_checked, n_bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="config_extra 结构预检")
    ap.add_argument("--client", help="客户端源包 zip")
    ap.add_argument("--server", help="服务端源包 zip")
    ap.add_argument("--corpus", default="translations/cn-rebase")
    args = ap.parse_args(argv)

    corpus = Corpus.load(Path(args.corpus))
    extras = corpus.extra_config
    if not extras:
        print("译料层没有 config_extra 片段，无事可做。")
        return 0
    print(f"config_extra 目标 {len(extras)} 个：")
    for t in extras:
        print(f"   {t}  （overwrite={t in EXTRA_OVERWRITE}）")

    total = bad = 0
    for path, label in ((args.client, "客户端"), (args.server, "服务端")):
        if not path:
            continue
        p = Path(path)
        if not p.is_file():
            print(f"\n[跳过] {label}源包不存在: {p}")
            continue
        c, b = check_pack(p, extras, label)
        total += c
        bad += b

    print(f"\n预检结果：检查 {total} 处，结构退化 {bad} 处")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
