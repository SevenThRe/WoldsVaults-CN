package com.woldsvaults.skyblockfix;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.IntegerArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.UuidArgument;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.TextComponent;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.common.Mod.EventBusSubscriber.Bus;
import yorickbm.skyblockaddon.capabilities.SkyblockAddonWorldProvider;
import yorickbm.skyblockaddon.configs.SkyblockAddonConfig;
import yorickbm.skyblockaddon.core.islands.Island;
import yorickbm.skyblockaddon.core.islands.IslandManager;
import yorickbm.skyblockaddon.core.util.geometry.Vec3i;
import yorickbm.skyblockaddon.islands.ForgeIsland;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

/**
 * Adds real "delete" commands on top of skyblockaddon's leave/purge.
 *
 * <p>skyblockaddon has no way to actually remove an island: {@code leave} only
 * transfers/clears ownership, and {@code admin purge} only removes islands whose
 * {@code isAbandoned()} is true (no owner AND no members) and whose modified-chunk
 * list is non-empty. Worse, an island's terrain blocks are written directly into
 * the world's region files and are never removed by any data cleanup.</p>
 *
 * <p>Commands provided (all OP-only except the first):</p>
 * <ul>
 *   <li>{@code /island delete} — delete the island you belong to.</li>
 *   <li>{@code /island admin delete &lt;uuid&gt;} — delete any island by id.</li>
 *   <li>{@code /island admin deleteall} — wipe every island (terrain + registry +
 *       islanddata nbt) and reset the spawn grid far away, for a clean restart.</li>
 *   <li>{@code /island admin cleararea &lt;x&gt; &lt;z&gt;} — clear one island-sized
 *       column at arbitrary coordinates (orphan slabs left by older deletes).</li>
 * </ul>
 *
 * <p>The terrain band cleared is derived from skyblockaddon's
 * {@code island.spawn.height} config (the template occupies
 * {@code [height, height+16]}), NOT from the island center: the center is the
 * spawn-top position ({@code height+11} or so), so clearing around it left an
 * 8-layer floating slab below and reached into the vault resource-island layer
 * (Y128+) when islands were stacked at origin.</p>
 */
@Mod.EventBusSubscriber(modid = "woldsvaults_skyblock_fix", bus = Bus.FORGE)
public final class IslandDeleteCommand {

    // The island template is 11 wide (X -5..+5) and 12 deep (Z -6..+6) around the
    // anchor; clear a slightly larger footprint to absorb rounding.
    private static final int CLEAR_HALF_X = 8;
    private static final int CLEAR_HALF_Z = 8;
    private static final int DEFAULT_SPAWN_HEIGHT = 110;

    private IslandDeleteCommand() {
    }

    @SubscribeEvent
    public static void onRegisterCommands(RegisterCommandsEvent event) {
        CommandDispatcher<CommandSourceStack> d = event.getDispatcher();
        register(d, "island");
        register(d, "is");
    }

    private static void register(CommandDispatcher<CommandSourceStack> d, String root) {
        d.register(
            Commands.literal(root)
                .then(Commands.literal("delete")
                    .requires(src -> src.getEntity() instanceof ServerPlayer)
                    .executes(IslandDeleteCommand::deleteOwn))
                .then(Commands.literal("admin")
                    .requires(src -> src.hasPermission(2))
                    .then(Commands.literal("delete")
                        .then(Commands.argument("uuid", UuidArgument.uuid())
                            .executes(ctx -> deleteById(ctx, UuidArgument.getUuid(ctx, "uuid")))))
                    .then(Commands.literal("deleteall")
                        .executes(IslandDeleteCommand::deleteAll))
                    .then(Commands.literal("cleararea")
                        .then(Commands.argument("x", IntegerArgumentType.integer())
                            .then(Commands.argument("z", IntegerArgumentType.integer())
                                .executes(ctx -> clearArea(ctx,
                                        IntegerArgumentType.getInteger(ctx, "x"),
                                        IntegerArgumentType.getInteger(ctx, "z")))))))
        );
    }

    // ---------------------------------------------------------------- delete

    private static int deleteOwn(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack src = ctx.getSource();
        if (!(src.getEntity() instanceof ServerPlayer)) {
            src.sendFailure(new TextComponent("该命令只能由玩家执行。"));
            return 0;
        }
        ServerPlayer player = (ServerPlayer) src.getEntity();
        Island island = IslandManager.getInstance().getIslandByEntityUUID(player.getUUID());
        if (island == null) {
            src.sendFailure(new TextComponent("你没有属于自己的岛屿。"));
            return 0;
        }
        return deleteIsland(src, player, island, true);
    }

    private static int deleteById(CommandContext<CommandSourceStack> ctx, UUID id) {
        CommandSourceStack src = ctx.getSource();
        Island island = IslandManager.getInstance().getIslandByUUID(id);
        if (island == null) {
            src.sendFailure(new TextComponent("找不到岛屿: " + id));
            return 0;
        }
        ServerPlayer operator = src.getEntity() instanceof ServerPlayer ? (ServerPlayer) src.getEntity() : null;
        return deleteIsland(src, operator, island, true);
    }

    private static int deleteIsland(CommandSourceStack src, ServerPlayer operator, Island island,
                                    boolean teleportMembers) {
        if (!(island instanceof ForgeIsland)) {
            src.sendFailure(new TextComponent("该岛屿不是 ForgeIsland，无法删除。"));
            return 0;
        }
        MinecraftServer server = src.getServer();
        ServerLevel overworld = server.getLevel(Level.OVERWORLD);
        if (overworld == null) {
            src.sendFailure(new TextComponent("找不到主世界。"));
            return 0;
        }

        List<ServerPlayer> toTeleport = new ArrayList<>();
        if (teleportMembers) {
            collectOnlineMembers(server, island, toTeleport);
        }

        Vec3i center = island.getCenter();
        final int cx = center.getX();
        final int cz = center.getZ();

        // 1) Remove terrain blocks on the main thread (next tick).
        server.execute(() -> clearTerrain(overworld, cx, cz));

        // 2) Remove from in-memory registry + player/bbox caches.
        IslandManager.getInstance().clearIslandCache(island);

        // 3) Delete the world/islanddata/<uuid>.nbt file (may not exist yet if the
        //    world hasn't been saved since create — that warning is benign).
        overworld.getCapability(SkyblockAddonWorldProvider.SKYBLOCKADDON_WORLD_CAPABILITY)
                .ifPresent(cap -> cap.removeIslandNBT((ForgeIsland) island));

        // 4) Teleport the island's online members back to overworld spawn so they
        //    don't fall into the void.
        for (ServerPlayer sp : toTeleport) {
            teleportToSpawn(overworld, sp);
        }

        String who = operator != null ? operator.getName().getString() : "Console";
        src.sendSuccess(new TextComponent("已删除岛屿 " + island.getId() + "（" + who + " 操作）。"), true);
        return 1;
    }

    // ------------------------------------------------------------- deleteall

    private static int deleteAll(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack src = ctx.getSource();
        MinecraftServer server = src.getServer();
        ServerLevel overworld = server.getLevel(Level.OVERWORLD);
        if (overworld == null) {
            src.sendFailure(new TextComponent("找不到主世界。"));
            return 0;
        }

        List<Island> snapshot = new ArrayList<>(IslandManager.getInstance().getIslands());
        if (snapshot.isEmpty()) {
            src.sendSuccess(new TextComponent("当前没有任何岛屿。"), false);
            return 0;
        }

        // Collect online members of every island BEFORE removal, so everyone standing
        // on a doomed island gets yanked to spawn instead of falling into the void.
        Set<UUID> toTeleportIds = new LinkedHashSet<>();
        for (Island island : snapshot) {
            addIfOnline(server, toTeleportIds, island.getOwner());
            for (UUID m : island.getMembers()) {
                addIfOnline(server, toTeleportIds, m);
            }
        }

        int[][] centers = new int[snapshot.size()][2];
        for (int i = 0; i < snapshot.size(); i++) {
            Vec3i c = snapshot.get(i).getCenter();
            centers[i][0] = c.getX();
            centers[i][1] = c.getZ();
        }

        // 1) Terrain: a single main-thread task clearing every island's band.
        server.execute(() -> {
            for (int[] c : centers) {
                clearTerrain(overworld, c[0], c[1]);
            }
        });

        // 2) Registry + caches (clearIslandCache mutates the map, hence the snapshot).
        for (Island island : snapshot) {
            IslandManager.getInstance().clearIslandCache(island);
        }

        // 3) islanddata nbt files.
        overworld.getCapability(SkyblockAddonWorldProvider.SKYBLOCKADDON_WORLD_CAPABILITY)
                .ifPresent(cap -> {
                    for (Island island : snapshot) {
                        cap.removeIslandNBT((ForgeIsland) island);
                    }
                });

        // 4) Reset the spiral grid: empty island table, no reusable slots, and the
        //    next /island create lands at the far grid origin instead of wherever
        //    the old (possibly spawn-stacked) anchor was.
        IslandManager.getInstance().initializeData(List.of(), List.of(),
                new Vec3i(SkyblockFixConfig.gridOriginX, 0, SkyblockFixConfig.gridOriginZ));

        // 5) Teleport everyone back to spawn.
        for (UUID id : toTeleportIds) {
            ServerPlayer sp = server.getPlayerList().getPlayer(id);
            if (sp != null) {
                teleportToSpawn(overworld, sp);
            }
        }

        src.sendSuccess(new TextComponent("已删除全部 " + snapshot.size()
                + " 座岛屿并重置岛屿网格（下一座岛将生成在 " + SkyblockFixConfig.gridOriginX
                + "," + SkyblockFixConfig.gridOriginZ + " 附近）。"), true);
        return 1;
    }

    // ------------------------------------------------------------- cleararea

    private static int clearArea(CommandContext<CommandSourceStack> ctx, int x, int z) {
        CommandSourceStack src = ctx.getSource();
        MinecraftServer server = src.getServer();
        ServerLevel overworld = server.getLevel(Level.OVERWORLD);
        if (overworld == null) {
            src.sendFailure(new TextComponent("找不到主世界。"));
            return 0;
        }
        server.execute(() -> clearTerrain(overworld, x, z));
        src.sendSuccess(new TextComponent("已在 (" + x + ", " + z
                + ") 周围按岛屿尺寸清空地形（Y " + (spawnHeight() - 2) + "–" + (spawnHeight() + 17) + "）。"), true);
        return 1;
    }

    // ----------------------------------------------------------------- impl

    /**
     * Clears one island-sized block band around (cx, cz). The band is derived from
     * skyblockaddon's {@code island.spawn.height} — the template occupies
     * {@code [height, height+16]} — so the whole island goes and nothing above
     * (the vault resource-island layer at Y128+ when stacked at origin) is touched.
     */
    private static void clearTerrain(ServerLevel level, int cx, int cz) {
        int h = spawnHeight();
        int minY = h - 2;
        int maxY = h + 17;
        BlockState air = Blocks.AIR.defaultBlockState();
        for (int x = cx - CLEAR_HALF_X; x <= cx + CLEAR_HALF_X; x++) {
            for (int z = cz - CLEAR_HALF_Z; z <= cz + CLEAR_HALF_Z; z++) {
                for (int y = minY; y <= maxY; y++) {
                    BlockPos p = new BlockPos(x, y, z);
                    LevelChunk chunk = level.getChunk(x >> 4, z >> 4);
                    if (chunk != null && !chunk.getBlockState(p).isAir()) {
                        level.setBlock(p, air, 3);
                    }
                }
            }
        }
    }

    private static int spawnHeight() {
        try {
            return Integer.parseInt(SkyblockAddonConfig.getForKey("island.spawn.height"));
        } catch (NumberFormatException | NullPointerException e) {
            return DEFAULT_SPAWN_HEIGHT;
        }
    }

    private static void collectOnlineMembers(MinecraftServer server, Island island, List<ServerPlayer> out) {
        Set<UUID> ids = new LinkedHashSet<>();
        addIfOnline2(server, ids, island.getOwner());
        for (UUID m : island.getMembers()) {
            addIfOnline2(server, ids, m);
        }
        for (UUID id : ids) {
            ServerPlayer sp = server.getPlayerList().getPlayer(id);
            if (sp != null) {
                out.add(sp);
            }
        }
    }

    private static void addIfOnline(MinecraftServer server, Set<UUID> out, UUID id) {
        if (id != null && server.getPlayerList().getPlayer(id) != null) {
            out.add(id);
        }
    }

    private static void addIfOnline2(MinecraftServer server, Set<UUID> out, UUID id) {
        addIfOnline(server, out, id);
    }

    private static void teleportToSpawn(ServerLevel overworld, ServerPlayer player) {
        BlockPos spawn = overworld.getSharedSpawnPos();
        player.teleportTo(overworld, spawn.getX() + 0.5, spawn.getY() + 0.5, spawn.getZ() + 0.5,
                player.getYRot(), player.getXRot());
        player.displayClientMessage(new TextComponent("你的岛屿已被删除，你已回到出生点。"), false);
    }
}
