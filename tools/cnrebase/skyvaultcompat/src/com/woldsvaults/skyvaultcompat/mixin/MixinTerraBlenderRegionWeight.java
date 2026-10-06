package com.woldsvaults.skyvaultcompat.mixin;

import com.woldsvaults.skyvaultcompat.SkyVaultProbe;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/**
 * Redirects TerraBlender's registration of {@code vanilla_overworld_region_weight}.
 *
 * Teralith's own {@code MixinTerrablenderConfig} pushes that weight to 0 whenever its
 * {@code terrablender_compatibility} option is enabled, which is what makes a Sky Vaults
 * / SkyblockBuilder world come out as Teralith terrain. When the running world is one of
 * those vault worlds we return a high weight instead, so the vault keeps its own terrain.
 *
 * Two redirectors are declared because the method is called {@code addNumber} in
 * TerraBlender 1.2.0.x but {@code create} in some builds; both use {@code require = 0},
 * so if neither matches the mixin simply does nothing instead of breaking the server.
 */
@Mixin(targets = "terrablender.config.TerraBlenderConfig", remap = false)
public abstract class MixinTerraBlenderRegionWeight {

    /**
     * Raw-typed call to the original method.
     *
     * {@code Config#addNumber} is {@code <T extends Number & Comparable<T>> T}, and a raw
     * type only exists for generic classes, so the erasure cannot be requested directly.
     * Casting the arguments to an unbounded type variable is the standard way to reach
     * the erased {@code (String, String, Number, Number, Number)} descriptor, which is
     * exactly what the redirector's own signature sees at runtime.
     */
    @SuppressWarnings("unchecked")
    private static <T extends Number & Comparable<T>> Number callOriginal(
            Object cfg, String description, String entryName,
            Number defaultValue, Number min, Number max) {
        T a = (T) defaultValue;
        T b = (T) min;
        T c = (T) max;
        return ((terrablender.config.Config) cfg).addNumber(description, entryName, a, b, c);
    }

    @Redirect(
            method = "<init>",
            at = @At(
                    value = "INVOKE",
                    target = "Lterrablender/config/Config;addNumber(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Number;Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;",
                    remap = false),
            require = 0)
    private Number woldsvaults$forceWeight_addNumber(
            Object config, String description, String entryName,
            Number defaultValue, Number min, Number max) {
        if (SkyVaultProbe.shouldForceVanillaOverworldRegion(entryName, defaultValue)) {
            return Integer.valueOf(SkyVaultProbe.forceWeight());
        }
        return callOriginal(config, description, entryName, defaultValue, min, max);
    }

    @Redirect(
            method = "<init>",
            at = @At(
                    value = "INVOKE",
                    target = "Lterrablender/config/Config;create(Ljava/lang/String;Ljava/lang/String;Ljava/lang/Number;Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/Number;",
                    remap = false),
            require = 0)
    private Number woldsvaults$forceWeight_create(
            Object config, String description, String entryName,
            Number defaultValue, Number min, Number max) {
        if (SkyVaultProbe.shouldForceVanillaOverworldRegion(entryName, defaultValue)) {
            return Integer.valueOf(SkyVaultProbe.forceWeight());
        }
        return callOriginal(config, description, entryName, defaultValue, min, max);
    }
}
