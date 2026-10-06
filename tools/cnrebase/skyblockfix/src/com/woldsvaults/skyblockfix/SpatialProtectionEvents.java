package com.woldsvaults.skyblockfix;

import com.woldsvaults.skyblockfix.SkyblockFixConfig;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TextComponent;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.LevelAccessor;
import net.minecraftforge.common.util.FakePlayer;
import net.minecraftforge.event.world.BlockEvent;
import net.minecraftforge.eventbus.api.EventPriority;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import yorickbm.skyblockaddon.core.islands.Island;
import yorickbm.skyblockaddon.core.islands.IslandManager;
import yorickbm.skyblockaddon.util.ForgeConverter;

/**
 * Enforces two spatial protections that skyblockaddon does not provide:
 *
 *  <ul>
 *    <li><b>Spawn island protection</b>: the vault's own resource island at world spawn
 *        can only be broken by operators.</li>
 *    <li><b>No bridging outside your island</b>: a player may only break/place blocks
 *        inside their own island's bounding box, so they cannot build a path back to
 *        spawn.</li>
 *  </ul>
 *
 * <p>Both protections are scoped to the overworld, because that is the only dimension where
 * islands exist. Applying them elsewhere compared vault coordinates against overworld data
 * and blocked legitimate play — most visibly it made the vault unminable for non-OP players.
 *
 * <p>Runs at LOW priority so skyblockaddon's own permission events (NORMAL) run first; we
 * only cancel what they already allowed through.
 */
@Mod.EventBusSubscriber(modid = "woldsvaults_skyblock_fix")
public final class SpatialProtectionEvents {
    private static final String MOD_ID = "woldsvaults_skyblock_fix";

    private SpatialProtectionEvents() {
    }

    @SubscribeEvent(priority = EventPriority.LOW)
    public static void onBlockBreak(BlockEvent.BreakEvent event) {
        Player player = event.getPlayer();
        if (player == null || player instanceof FakePlayer) {
            return;
        }
        BlockPos pos = event.getPos();
        LevelAccessor world = event.getWorld();
        ServerPlayer sp = player instanceof ServerPlayer ? (ServerPlayer) player : null;
        if (deny(player, sp, world, pos)) {
            event.setCanceled(true);
        }
    }

    @SubscribeEvent(priority = EventPriority.LOW)
    public static void onBlockPlace(BlockEvent.EntityPlaceEvent event) {
        Entity entity = event.getEntity();
        if (!(entity instanceof Player) || entity instanceof FakePlayer) {
            return;
        }
        Player player = (Player) entity;
        ServerPlayer sp = player instanceof ServerPlayer ? (ServerPlayer) player : null;
        LevelAccessor world = entity.getLevel();
        if (deny(player, sp, world, event.getPos())) {
            event.setCanceled(true);
        }
    }

    private static boolean deny(Player player, ServerPlayer sp, LevelAccessor worldAccess, BlockPos pos) {
        if (worldAccess.isClientSide()) {
            return false;
        }
        // OPs are never restricted.
        if (sp != null && sp.hasPermissions(2)) {
            return false;
        }

        // Islands only ever exist in the overworld. Both checks below compare block positions
        // against overworld data (shared spawn pos, island bounding boxes), so applying them in
        // any other dimension silently produced false positives:
        //   - in the_vault, getSharedSpawnPos() is still the OVERWORLD spawn, so the distance
        //     test happened to pass and every break was reported as "spawn island protected";
        //   - with an island, the bounding-box test rejected every break/place outside it.
        // Both made the vault unminable for non-OP players. Skip non-overworld dimensions.
        if (!(worldAccess instanceof final ServerLevel level)
                || level.dimension() != Level.OVERWORLD) {
            return false;
        }

        // 1) Spawn island protection: near world spawn, non-OP cannot break.
        if (SkyblockFixConfig.protectSpawnIsland) {
            BlockPos spawn = level.getSharedSpawnPos();
            int r = SkyblockFixConfig.spawnProtectRadius;
            int dx = pos.getX() - spawn.getX();
            int dz = pos.getZ() - spawn.getZ();
            if ((long) dx * dx + (long) dz * dz <= (long) r * r) {
                sendDeny(player, "spawn");
                return true;
            }
        }

        // 2) No building outside your own island.
        if (SkyblockFixConfig.blockBuildingOutsideIsland) {
            Island island = IslandManager.getInstance().getIslandByEntityUUID(player.getUUID());
            if (island == null) {
                return false; // no island: nothing to restrict against
            }
            if (!island.getIslandBoundingBox().isInside(
                    ForgeConverter.ForgeToInternalVec3i(pos))) {
                sendDeny(player, "island");
                return true;
            }
        }
        return false;
    }

    private static void sendDeny(Player player, String where) {
        String msg = where.equals("spawn")
                ? "你不能破坏出生岛屿。"
                : "你不能在自己的岛屿范围之外建造。";
        player.displayClientMessage(new TextComponent(msg), true);
    }
}
