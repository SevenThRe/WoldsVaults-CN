package com.woldsvaults.skyvaultcompat;

import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.Level;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Decides whether TerraBlender's {@code vanilla_overworld_region_weight} has to be
 * forced up so that a "vault" world keeps its own terrain.
 *
 * Background
 * ----------
 * Teralith ships a compatibility mixin ({@code terralith-common.mixins.json} :
 * {@code MixinTerrablenderConfig}) that redirects
 * {@code terrablender.config.Config#addNumber(String, String, Number, Number, Number)}
 * and, when its {@code terrablender_compatibility} option is on, pushes
 * {@code vanilla_overworld_region_weight} to 0. That is correct for an ordinary
 * overworld but wrong for Wold's Vaults, whose Sky Vaults / SkyblockBuilder worlds
 * are built on the vanilla overworld generator: with the vanilla region disabled the
 * world comes out as Teralith terrain instead of the vault.
 *
 * A previous attempt at this fix shipped inside skyblockaddon-8.2-CN.jar. It worked,
 * but its helper class lived in {@code yorickbm.skyblockaddon.mixins.*}, which is a
 * declared mixin package - Mixin refuses to load such classes directly, so the server
 * died with {@code IllegalClassLoadError}. This is the same logic, ported to our own
 * package and our own mod, so no third-party mixin package is touched.
 */
public final class SkyVaultProbe {

    public static final String CONFIG_NAME = "vanilla_overworld_region_weight";
    public static final int DEFAULT_FORCE_WEIGHT = 100;

    private static final Logger LOGGER = LogManager.getLogger("woldsvaults_skyvault_compat");

    /** Generator class names that mean "this world is a vault / void island world". */
    private static final String[] VAULT_GENERATORS = {
            "VoidWorldType",                    // SkyblockBuilder's void world type
            "SkyblockNoiseBasedChunkGenerator", // SkyblockBuilder
            "SkyVaultsChunkGenerator",          // the_vault's own Sky Vaults
    };

    private static volatile MinecraftServer server;
    private static volatile Boolean cachedVaultWorld;
    private static volatile Boolean enabled = null;
    private static volatile int forceWeight = DEFAULT_FORCE_WEIGHT;

    private SkyVaultProbe() {
    }

    public static void onServerStarting(MinecraftServer srv) {
        server = srv;
        cachedVaultWorld = null;
    }

    public static void onServerStopped() {
        server = null;
        cachedVaultWorld = null;
    }

    /** Reads config/woldsvaults-skyvault-compat.json if present; otherwise defaults. */
    private static void loadConfig() {
        if (enabled != null) {
            return;
        }
        boolean en = true;
        int w = DEFAULT_FORCE_WEIGHT;
        try {
            // A dedicated server always runs inside its own directory, so the
            // relative config path is correct and avoids a hard fmlloader link.
            Path p = java.nio.file.Paths.get("config", "woldsvaults-skyvault-compat.json");
            if (Files.exists(p)) {
                String txt = new String(Files.readAllBytes(p), StandardCharsets.UTF_8);
                en = !txt.contains("\"enabled\"") || !txt.contains("false");
                java.util.regex.Matcher m = java.util.regex.Pattern
                        .compile("\"forceWeight\"\\s*:\\s*(\\d+)").matcher(txt);
                if (m.find()) {
                    w = Integer.parseInt(m.group(1));
                }
            }
        } catch (IOException | RuntimeException e) {
            LOGGER.warn("[skyvault-compat] could not read the config file: {}", e.toString());
        }
        enabled = en;
        forceWeight = w;
        LOGGER.info("[skyvault-compat] enabled={} forceWeight={}", en, w);
    }

    /**
     * @return true when the entry TerraBlender is registering is the vanilla overworld
     *         region weight AND the running world is a vault world.
     */
    public static boolean shouldForceVanillaOverworldRegion(String entryName, Object value) {
        try {
            loadConfig();
            if (!enabled) {
                return false;
            }
            if (!CONFIG_NAME.equals(entryName) || !(value instanceof Integer)) {
                return false;
            }
            return isVaultWorld();
        } catch (Throwable t) {
            LOGGER.warn("[skyvault-compat] guard failed, leaving TerraBlender untouched: {}",
                    t.toString());
            return false;
        }
    }

    /** Probes the overworld chunk generator; cached because it cannot change at runtime. */
    public static boolean isVaultWorld() {
        MinecraftServer srv = server;
        if (srv == null) {
            return false;
        }
        Boolean cached = cachedVaultWorld;
        if (cached != null) {
            return cached;
        }
        boolean vault = false;
        String genName = "unknown";
        try {
            ServerLevel overworld = srv.m_129880_(Level.f_46428_);
            if (overworld != null) {
                genName = overworld.m_7726_().m_8481_().getClass().getName();
                for (String marker : VAULT_GENERATORS) {
                    if (genName.contains(marker)) {
                        vault = true;
                        break;
                    }
                }
            }
        } catch (Throwable t) {
            LOGGER.warn("[skyvault-compat] world probe failed: {}", t.toString());
            return false;
        }
        cachedVaultWorld = vault;
        if (vault) {
            LOGGER.info("[skyvault-compat] vault world detected (generator={}), "
                    + "{} will be forced to {}", genName, CONFIG_NAME, forceWeight);
        } else {
            LOGGER.info("[skyvault-compat] normal world (generator={}), "
                    + "TerraBlender left as is", genName);
        }
        return vault;
    }

    public static int forceWeight() {
        loadConfig();
        return forceWeight;
    }
}
