package com.woldsvaults.skyblockfix.mixin;

import com.woldsvaults.skyblockfix.SkyblockFixConfig;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;
import yorickbm.skyblockaddon.core.islands.Island;
import yorickbm.skyblockaddon.core.islands.IslandManager;

import java.util.UUID;

/**
 * Root-cause fix for "a member can still /island create a brand new island".
 *
 * {@code IslandManager.getIslandByEntityUUID} reads from a 12-hour LoadingCache
 * ({@code CACHE_islandByPlayerUUID}). When a player logs in, the cache is seeded with
 * {@code Optional.empty()} (no island). If that player is later invited into an island,
 * the membership is added to the island's member list but the cache is never
 * invalidated, so {@code /island create} keeps seeing the stale "no island" answer and
 * allows creating a fresh island.
 *
 * This injector re-scans the live island registry on every call (before the cached
 * lookup) using the same {@code isPartOf} predicate the cache loader itself uses, and
 * short-circuits with that island when it matches. It is a strict superset of the
 * cached result, so it cannot break a normal first-time create.
 */
@Mixin(value = IslandManager.class, remap = false)
public abstract class MixinIslandManager {

    @Inject(method = "getIslandByEntityUUID", at = @At("HEAD"), cancellable = true, remap = false)
    private void woldsvaults$rescanMembership(UUID uuid, CallbackInfoReturnable<Island> cir) {
        if (!SkyblockFixConfig.oneIslandPerPlayer) {
            return;
        }
        IslandManager self = (IslandManager) (Object) this;
        for (Island island : self.getIslands()) {
            if (island.isPartOf(uuid)) {
                cir.setReturnValue(island);
                return;
            }
        }
    }
}
