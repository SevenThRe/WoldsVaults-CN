#!/usr/bin/env python3
"""Build the standalone "sky vault + Teralith compatibility" mod jar.

Why a separate jar instead of folding this into woldsvaults_cn?
    The previous version of this fix shipped inside skyblockaddon-8.2-CN.jar and its
    helper class ended up in a declared mixin package, which killed the server with
    IllegalClassLoadError. Keeping it standalone means (a) no third-party mixin package
    is ever touched and (b) the working localization jar stays untouched - if this mod
    misbehaves, deleting one file from mods/ is enough.

Compile classpath (all read-only):
    MC      : .minecraft/libraries/net/minecraft/client/1.18.2-20220404.173914/*-srg.jar
    Forge   : .minecraft/libraries/net/minecraftforge/forge/1.18.2-40.3.11/*-universal.jar
    Mixin   : .minecraft/libraries/org/spongepowered/mixin/0.8.5/mixin-0.8.5.jar
    TB      : <instance>/mods/TerraBlender-forge-1.18.2-1.2.0.126.jar  (redirector types)

Usage:
    python build_skyvault_compat.py <out.jar>
"""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
RES = os.path.join(HERE, "resources")

MCLIB = r"E:\Game Files (x86)\Minecraft\.minecraft\libraries"
INST = r"E:\Game Files (x86)\Minecraft\.minecraft\versions\Wold's Vaults 汉化版\mods"
JAVAC = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javac.exe"

CP = [
    os.path.join(MCLIB, r"net\minecraft\client\1.18.2-20220404.173914\client-1.18.2-20220404.173914-srg.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\forge\1.18.2-40.3.11\forge-1.18.2-40.3.11-universal.jar"),
    os.path.join(MCLIB, r"org\spongepowered\mixin\0.8.5\mixin-0.8.5.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\eventbus\5.0.3\eventbus-5.0.3.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\fmlloader\1.18.2-40.3.11\fmlloader-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\javafmllanguage\1.18.2-40.3.11\javafmllanguage-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\fmlcore\1.18.2-40.3.11\fmlcore-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"org\apache\logging\log4j\log4j-api\2.17.0\log4j-api-2.17.0.jar"),
    os.path.join(INST, "TerraBlender-forge-1.18.2-1.2.0.126.jar"),
]


def sources():
    out = []
    for root, _dirs, files in os.walk(SRC):
        for f in files:
            if f.endswith(".java"):
                out.append(os.path.join(root, f))
    return sorted(out)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_jar = sys.argv[1]
    for p in CP:
        if not os.path.exists(p):
            raise SystemExit("missing classpath entry: " + p)

    classes = os.path.join(HERE, "build", "classes")
    os.makedirs(classes, exist_ok=True)
    cmd = [JAVAC, "-nowarn", "-proc:none", "-encoding", "UTF-8",
           "-source", "17", "-target", "17",
           "-classpath", os.pathsep.join(CP), "-d", classes] + sources()
    print("compiling %d source files" % len(sources()))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        return r.returncode
    if r.stderr.strip():
        print("javac warnings:\n" + r.stderr.strip()[:2000])

    n = 0
    with zipfile.ZipFile(out_jar, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(classes):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, classes).replace(os.sep, "/"))
                n += 1
        for root, _dirs, files in os.walk(RES):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, RES).replace(os.sep, "/"))
                n += 1
        z.writestr("pack.mcmeta", '{\n  "pack": {\n    "description": "Sky Vaults - Teralith compatibility",\n'
                                 '    "pack_format": 8\n  }\n}\n')
        n += 1

    with zipfile.ZipFile(out_jar) as z:
        bad = z.testzip()
        assert bad is None, bad
        names = z.namelist()
    print("wrote %s: %d entries, %d bytes" % (out_jar, len(names), os.path.getsize(out_jar)))
    for need in ("META-INF/mods.toml",
                 "woldsvaults_skyvault_compat.mixins.json",
                 "com/woldsvaults/skyvaultcompat/SkyVaultCompat.class",
                 "com/woldsvaults/skyvaultcompat/SkyVaultProbe.class",
                 "com/woldsvaults/skyvaultcompat/mixin/MixinTerraBlenderRegionWeight.class",
                 "pack.mcmeta"):
        assert need in names, "missing " + need
    # the mixin config must be referenced (memory rule: a jar entry proves nothing)
    with zipfile.ZipFile(out_jar) as z:
        cfg = json.loads(z.read("woldsvaults_skyvault_compat.mixins.json").decode("utf-8"))
    assert cfg["mixins"] == ["MixinTerraBlenderRegionWeight"], cfg
    assert cfg["package"] == "com.woldsvaults.skyvaultcompat.mixin", cfg
    print("verified: mixin config references the compiled class")
    return 0


if __name__ == "__main__":
    import json  # noqa: E402  (used in main)
    raise SystemExit(main())
