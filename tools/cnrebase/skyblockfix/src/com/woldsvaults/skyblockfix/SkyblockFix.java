package com.woldsvaults.skyblockfix;

import net.minecraftforge.fml.common.Mod;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Wolds Vaults CN — SkyblockAddon behavior fixes.
 *
 * Fixes several gameplay bugs in skyblockaddon 8.2 without touching its classes:
 *  1. One-island-per-player: a player who is already a member OR owner of any island
 *     can no longer run {@code /island create} (the previous check relied on a 12h
 *     cache that kept a stale "no island" answer after being invited).
 *  2. Island grid moved far from spawn so player islands no longer overlap the
 *     vault's own resource island at world spawn.
 *  3. The spawn island (vault resource island) can only be broken by OPs.
 *  4. Building outside a player's own island bounding box is blocked (no bridging
 *     back toward spawn).
 *  5. Respawning after create / accepting an invite defaults to the island spawn.
 */
@Mod("woldsvaults_skyblock_fix")
public class SkyblockFix {
    private static final Logger LOGGER = LogManager.getLogger();

    public SkyblockFix() {
        SkyblockFixConfig.load();
        LOGGER.info("Wolds Vaults SkyblockAddon fix loaded.");
    }
}
