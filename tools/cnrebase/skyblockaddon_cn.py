#!/usr/bin/env python3
"""Build a pure-localization Chinese jar for SkyBlockAddon 8.2.

WHY THIS TOOL EXISTS
--------------------
The first attempt (2026-10-03) shipped a "skyblockaddon-8.2-CN.jar" that was
NOT a localization jar. On top of the language file it also contained:

  * yorickbm/skyblockaddon/mixins/SkyVaultLevelType.class   (new level type)
  * yorickbm/skyblockaddon/mixins/TerralithRegionWeightMixin.class
  * mixins/terralith_region.mixin.json
  * yorickbm/skyblockaddon/islands/Hub*.class
  * yorickbm/skyblockaddon/SkyBlockAddon$TerralithGuard.class
  * a REBUILT SkyBlockAddon.class that references SkyVaultLevelType

and it had DROPPED assets/skyblockaddon/permissions.zip.

That class in a declared mixin package is fatal at runtime:

  java.lang.IllegalClassLoadError:
    yorickbm.skyblockaddon.mixins.SkyVaultLevelType is in a defined mixin
    package yorickbm.skyblockaddon.mixins.* owned by
    /mixins/skyblockaddon.mixin.json and cannot be referenced directly
      at yorickbm.skyblockaddon.SkyBlockAddon.<init>(SkyBlockAddon.java:69)

Mixin forbids loading classes that live in a mixin package directly, so the
server died during mod construction. The custom "sky vault" level type was
also scope creep: the Sky Vaults server preset only needs
    level-type=skyblockbuilder:skyblock
which the official pack's SkyblockBuilder already provides.

This builder is deliberately conservative - it can only ADD the zh_cn
language file and REPLACE data JSONs whose key structure is provably
identical to the original (pure text translation). Any structural change,
any new class and any new mixin config is impossible by construction.

Usage:
    python skyblockaddon_cn.py <original-skyblockaddon.jar> <out.jar>
"""
import json
import sys
import zipfile


def shape(obj):
    """Structure fingerprint: keys + types + list lengths, ignoring values."""
    if isinstance(obj, dict):
        return {k: shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return ["list%d" % len(obj)] + [shape(x) for x in obj[:3]]
    if isinstance(obj, str):
        return "str"
    return type(obj).__name__


def is_pure_translation(old_bytes: bytes, new_bytes: bytes) -> bool:
    try:
        a = json.loads(old_bytes.decode("utf-8-sig"))
        b = json.loads(new_bytes.decode("utf-8-sig"))
    except Exception:
        return False
    return shape(a) == shape(b)


def build(original: str, previous_cn: str, out_path: str) -> int:
    with zipfile.ZipFile(original) as zo, zipfile.ZipFile(previous_cn) as zc:
        old_names = set(zo.namelist())
        new_names = set(zc.namelist())

        added_classes = sorted(
            n for n in new_names - old_names if n.endswith(".class"))
        added_mixins = sorted(
            n for n in new_names - old_names
            if n.endswith(".json") and "mixin" in n.lower())
        dropped = sorted(old_names - new_names)
        if added_classes or added_mixins or dropped:
            print("previous CN jar was a functional mod (classes=%s, mixins=%s, "
                  "dropped=%s) - those are deliberately NOT carried over."
                  % (added_classes, added_mixins, dropped))

        # data files: same name, .json under assets/, pure translation only
        translated = []
        for name in sorted(old_names & new_names):
            if not name.startswith("assets/") or not name.endswith(".json"):
                continue
            a, b = zo.read(name), zc.read(name)
            if a != b and is_pure_translation(a, b):
                translated.append(name)

        lang = "assets/skyblockaddon/lang/zh_cn.json"
        if lang not in new_names:
            raise SystemExit("previous CN jar has no %s" % lang)

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as out:
            for info in zo.infolist():
                if info.filename in translated:
                    out.writestr(info.filename, zc.read(info.filename))
                else:
                    out.writestr(info, zo.read(info.filename))
            out.writestr(lang, zc.read(lang))

    # ---- verification -------------------------------------------------
    with zipfile.ZipFile(original) as zo, zipfile.ZipFile(out_path) as zn:
        on, nn = set(zo.namelist()), set(zn.namelist())
        assert not [n for n in nn - on if n.endswith(".class")], "no new class allowed"
        assert not [n for n in nn - on if "mixin" in n.lower()], "no new mixin config"
        assert on - nn == set(), "nothing may be dropped"
        assert nn - on == {lang}, "only the language file may be new"
        for name in on:
            if name in translated or name == lang:
                continue
            assert zo.read(name) == zn.read(name), "byte mismatch: " + name
        data = json.loads(zn.read(lang).decode("utf-8-sig"))
        zh = sum(1 for v in data.values()
                 if isinstance(v, str) and any("\u4e00" <= c <= "\u9fff" for c in v))

    print("translated data JSON : %d" % len(translated))
    for n in translated:
        print("    ", n)
    print("language file       : %s (%d keys, %d with Chinese)"
          % (lang, len(data), zh))
    print("entries             : %d -> %d" % (len(on), len(nn)))
    print("dropped files       : none")
    print("new classes/mixins  : none")
    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    return build(sys.argv[1], sys.argv[2], sys.argv[3])


if __name__ == "__main__":
    raise SystemExit(main())
