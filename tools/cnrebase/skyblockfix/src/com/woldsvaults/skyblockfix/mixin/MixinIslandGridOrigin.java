package com.woldsvaults.skyblockfix.mixin;

import com.woldsvaults.skyblockfix.SkyblockFixConfig;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;
import yorickbm.skyblockaddon.core.islands.IslandManager;
import yorickbm.skyblockaddon.core.util.geometry.Vec3i;

/**
 * Moves the first player island far away from world spawn.
 *
 * skyblockaddon's spiral grid starts at (0,0,0), and the_vault's sky_vaults world type
 * places a resource island at world spawn, so the first /island create lands directly
 * on top of it. Redirecting the constructor's {@code new Vec3i(0,0,0)} seed to a far
 * coordinate keeps every player island clear of the spawn island.
 *
 * Only the in-memory default is redirected; a world that already persisted
 * {@code lastIsland} into {@code capabilities.dat} keeps its existing value (new worlds
 * and fresh installs get the far start).
 */
@Mixin(value = IslandManager.class, remap = false)
public abstract class MixinIslandGridOrigin {

    @Redirect(
            method = "<init>",
            at = @At(value = "NEW", target = "yorickbm/skyblockaddon/core/util/geometry/Vec3i"),
            remap = false)
    private Vec3i woldsvaults$farOrigin(int x, int y, int z) {
        if (!SkyblockFixConfig.moveIslandGridAwayFromSpawn) {
            return new Vec3i(x, y, z);
        }
        // 100_000 blocks out keeps islands comfortably clear of the spawn island
        // while still using the existing 1000-block spiral spacing.
        return new Vec3i(SkyblockFixConfig.gridOriginX, 0, SkyblockFixConfig.gridOriginZ);
    }
}
