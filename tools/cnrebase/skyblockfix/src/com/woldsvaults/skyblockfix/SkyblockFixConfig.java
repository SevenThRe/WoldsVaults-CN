package com.woldsvaults.skyblockfix;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraftforge.fml.loading.FMLPaths;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Runtime-tunable flags, read from {@code config/woldsvaults-skyblock-fix.json}.
 * Missing file or missing keys fall back to the defaults below. Loaded once from the
 * mod constructor via {@link #load()}.
 */
public final class SkyblockFixConfig {
    public static boolean oneIslandPerPlayer = true;
    public static boolean moveIslandGridAwayFromSpawn = true;
    public static int gridOriginX = 100000;
    public static int gridOriginZ = 100000;
    public static boolean protectSpawnIsland = true;
    public static int spawnProtectRadius = 96;
    public static boolean blockBuildingOutsideIsland = true;
    public static boolean setRespawnOnIsland = true;

    private SkyblockFixConfig() {
    }

    public static void load() {
        Path path = FMLPaths.CONFIGDIR.get().resolve("woldsvaults-skyblock-fix.json");
        try {
            if (!Files.exists(path)) {
                return;
            }
            String text = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
            JsonObject o = JsonParser.parseString(text).getAsJsonObject();
            oneIslandPerPlayer = bool(o, "oneIslandPerPlayer", oneIslandPerPlayer);
            moveIslandGridAwayFromSpawn = bool(o, "moveIslandGridAwayFromSpawn", moveIslandGridAwayFromSpawn);
            gridOriginX = integer(o, "gridOriginX", gridOriginX);
            gridOriginZ = integer(o, "gridOriginZ", gridOriginZ);
            protectSpawnIsland = bool(o, "protectSpawnIsland", protectSpawnIsland);
            spawnProtectRadius = integer(o, "spawnProtectRadius", spawnProtectRadius);
            blockBuildingOutsideIsland = bool(o, "blockBuildingOutsideIsland", blockBuildingOutsideIsland);
            setRespawnOnIsland = bool(o, "setRespawnOnIsland", setRespawnOnIsland);
        } catch (Throwable t) {
            // never take the server down because of a malformed config
            System.err.println("[woldsvaults-skyblock-fix] config load failed, using defaults: " + t);
        }
    }

    private static boolean bool(JsonObject o, String k, boolean def) {
        return o.has(k) ? o.get(k).getAsBoolean() : def;
    }

    private static int integer(JsonObject o, String k, int def) {
        return o.has(k) ? o.get(k).getAsInt() : def;
    }
}
