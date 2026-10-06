package com.woldsvaults.skyblockfix.mixin;

import com.woldsvaults.skyblockfix.SkyblockFixConfig;
import net.minecraft.core.BlockPos;
import net.minecraft.resources.ResourceKey;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import yorickbm.skyblockaddon.core.util.geometry.Vec3i;
import yorickbm.skyblockaddon.islands.ForgeIsland;

/**
 * Makes the player's spawn (respawn) point default to the island spawn.
 *
 * {@code teleportTo} is the single entry point used both after a successful
 * {@code /island create} and after accepting an island invite, so injecting at its tail
 * covers both paths without touching the invokedynamic lambdas inside the commands.
 */
@Mixin(value = ForgeIsland.class, remap = false)
public abstract class MixinForgeIslandRespawn {

    @Inject(method = "teleportTo", at = @At("TAIL"), remap = false)
    private void woldsvaults$setRespawn(Entity entity, CallbackInfo ci) {
        if (!SkyblockFixConfig.setRespawnOnIsland) {
            return;
        }
        if (!(entity instanceof ServerPlayer)) {
            return;
        }
        ServerPlayer player = (ServerPlayer) entity;
        Level level = player.getLevel();
        if (level == null || level.dimension() != Level.OVERWORLD) {
            return;
        }
        Vec3i spawn = ((ForgeIsland) (Object) this).getSpawn();
        BlockPos pos = new BlockPos(spawn.getX(), spawn.getY(), spawn.getZ());
        ResourceKey<Level> dim = level.dimension();
        // setRespawnPosition(ResourceKey, BlockPos, angle, forced, sendMessage)
        player.setRespawnPosition(dim, pos, 0.0f, true, false);
    }
}
