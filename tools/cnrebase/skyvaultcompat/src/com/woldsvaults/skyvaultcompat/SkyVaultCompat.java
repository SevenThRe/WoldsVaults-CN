package com.woldsvaults.skyvaultcompat;

import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.server.ServerStartingEvent;
import net.minecraftforge.event.server.ServerStoppedEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Wold's Vaults Sky Vaults & Teralith compatibility mod.
 *
 * Keeps the vault's own terrain when Teralith is installed by holding TerraBlender's
 * {@code vanilla_overworld_region_weight} up in vault worlds. See {@link SkyVaultProbe}.
 */
@Mod("woldsvaults_skyvault_compat")
public class SkyVaultCompat {

    public SkyVaultCompat() {
        MinecraftForge.EVENT_BUS.register(new ServerLifecycle());
    }

    private static final class ServerLifecycle {
        @SubscribeEvent
        public void onServerStarting(ServerStartingEvent event) {
            SkyVaultProbe.onServerStarting(event.getServer());
        }

        @SubscribeEvent
        public void onServerStopped(ServerStoppedEvent event) {
            SkyVaultProbe.onServerStopped();
        }
    }
}
