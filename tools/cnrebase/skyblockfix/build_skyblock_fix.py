#!/usr/bin/env python3
"""Build the standalone "skyblockaddon fix" mod jar.

Uses the mojmap jar to compile with official MC names, then reobfuscates back to SRG
with ForgeAutoRenamingTool so it runs on a Forge 1.18.2 server. Mixins target
skyblockaddon's own (unobfuscated) classes with remap=false, so FART leaves those
member names untouched while still remapping the net.minecraft.* calls inside.

All fixes are runtime-tunable via config/woldsvaults-skyblock-fix.json.

Usage:
    python build_skyblock_fix.py <out.jar>
"""
import os
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")
RES = os.path.join(HERE, "resources")

JAVAC = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\javac.exe"
JAVA17 = r"C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot\bin\java.exe"

GRADLE = r"C:\Users\ASUS\.gradle\caches\forge_gradle"
MOJMAP = os.path.join(
    GRADLE,
    r"minecraft_user_repo\net\minecraftforge\forge\1.18.2-40.3.11_mapped_official_1.18.2",
    "forge-1.18.2-40.3.11_mapped_official_1.18.2-recomp.jar",
)
FART = os.path.join(
    GRADLE,
    r"maven_downloader\net\minecraftforge\ForgeAutoRenamingTool\1.0.6",
    "ForgeAutoRenamingTool-1.0.6-all.jar",
)
MAP = os.path.join(
    GRADLE,
    r"minecraft_user_repo\de\oceanlabs\mcp\mcp_config\1.18.2-20220404.173914",
    "srg_to_official_1.18.2.tsrg",
)

MCLIB = r"E:\Game Files (x86)\Minecraft\.minecraft\libraries"
# skyblockaddon itself (provides yorickbm.skyblockaddon.* for the mixin targets)
SKYBLOCKADDON = r"E:\WoldsVaults-0.34.1-CN-Server\mods\skyblockaddon-8.2.jar"
# our CN mod (LiteralTranslator is a mixin target of MixinLiteralGuiL10n)
CN_MOD = (r"E:\Game Files (x86)\Minecraft\.minecraft\versions"
          r"\Wold's Vaults 汉化版\mods\woldsvaults_cn-1.0.17-0.34.1-universal.jar")

CP = [
    MOJMAP,
    SKYBLOCKADDON,
    CN_MOD,
    os.path.join(MCLIB, r"net\minecraftforge\javafmllanguage\1.18.2-40.3.11\javafmllanguage-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\fmlcore\1.18.2-40.3.11\fmlcore-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\fmlloader\1.18.2-40.3.11\fmlloader-1.18.2-40.3.11.jar"),
    os.path.join(MCLIB, r"net\minecraftforge\eventbus\5.0.3\eventbus-5.0.3.jar"),
    os.path.join(MCLIB, r"org\spongepowered\mixin\0.8.5\mixin-0.8.5.jar"),
    os.path.join(MCLIB, r"com\google\guava\guava\31.0.1-jre\guava-31.0.1-jre.jar"),
    os.path.join(MCLIB, r"com\google\code\gson\gson\2.8.7\gson-2.8.7.jar"),
    os.path.join(MCLIB, r"org\apache\logging\log4j\log4j-api\2.17.0\log4j-api-2.17.0.jar"),
    os.path.join(MCLIB, r"com\mojang\brigadier\1.0.18\brigadier-1.0.18.jar"),
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
    for p in (MOJMAP, FART, MAP):
        if not os.path.exists(p):
            raise SystemExit("missing build tool: " + p)

    classes = os.path.join(HERE, "build", "classes")
    os.makedirs(classes, exist_ok=True)
    cmd = [JAVAC, "-nowarn", "-proc:none", "-encoding", "UTF-8",
           "--release", "17",
           "-classpath", os.pathsep.join(CP), "-d", classes] + sources()
    print("compiling %d source files" % len(sources()))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        return r.returncode
    if r.stderr.strip():
        print("javac warnings:\n" + r.stderr.strip()[:2000])

    # ---- raw jar (mods.toml + mixins.json + classes) ----
    raw_jar = os.path.join(HERE, "build", "mod-raw.jar")
    with zipfile.ZipFile(raw_jar, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(classes):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, classes).replace(os.sep, "/"))
        for root, _dirs, files in os.walk(RES):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, RES).replace(os.sep, "/"))
        # MANIFEST with MixinConfigs — required for the mixins to load at all
        manifest = (
            "Manifest-Version: 1.0\n"
            "MixinConfigs: woldsvaults_skyblock_fix.mixins.json\n"
        )
        z.writestr("META-INF/MANIFEST.MF", manifest)
    print("raw jar:", raw_jar, os.path.getsize(raw_jar), "bytes")

    # ---- reobf (mojmap -> SRG) ----
    cmd = [JAVA17, "-jar", FART, "--input", raw_jar, "--output", out_jar,
           "--map", MAP, "--reverse", "--ann-fix", "--ids-fix", "--lib", MOJMAP]
    print("reobfuscating ...")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        return r.returncode
    print(r.stderr.strip()[:2000] if r.stderr.strip() else "reobf ok")

    # ---- verify ----
    with zipfile.ZipFile(out_jar) as z:
        names = z.namelist()
        assert "META-INF/mods.toml" in names, "mods.toml missing"
        assert "woldsvaults_skyblock_fix.mixins.json" in names, "mixins.json missing"
        mf = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
        assert "MixinConfigs" in mf and "woldsvaults_skyblock_fix.mixins.json" in mf, \
            "manifest lost MixinConfigs!"
        for need in (
            "com/woldsvaults/skyblockfix/SkyblockFix.class",
            "com/woldsvaults/skyblockfix/SkyblockFixConfig.class",
            "com/woldsvaults/skyblockfix/SpatialProtectionEvents.class",
            "com/woldsvaults/skyblockfix/IslandDeleteCommand.class",
            "com/woldsvaults/skyblockfix/mixin/MixinIslandManager.class",
            "com/woldsvaults/skyblockfix/mixin/MixinIslandGridOrigin.class",
            "com/woldsvaults/skyblockfix/mixin/MixinForgeIslandRespawn.class",
            "com/woldsvaults/skyblockfix/mixin/MixinLiteralGuiL10n.class",
        ):
            assert need in names, "missing " + need
        # strip the fernflower metadata FART may inject
    clean = out_jar
    if "fernflower_abstract_parameter_names.txt" in names:
        clean = out_jar + ".clean"
        with zipfile.ZipFile(out_jar) as zin, zipfile.ZipFile(clean, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.filename == "fernflower_abstract_parameter_names.txt":
                    continue
                zout.writestr(info, zin.read(info.filename))
        os.replace(clean, out_jar)

    print("wrote %s: %d bytes" % (out_jar, os.path.getsize(out_jar)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
