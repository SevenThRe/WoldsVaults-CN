package com.woldsvaults.skyblockfix.mixin;

import com.woldsvaults.cn.LiteralTranslator;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Translates the hardcoded the_vault skill/ability dialog labels that the literal
 * TSV cannot cover: {@code Upgrade (N)}, {@code Research (N)}, {@code All Levels},
 * {@code Level N}, {@code Level: N}, {@code Cost: N}, {@code Level requirement: N}.
 *
 * <p>These strings are built in
 * {@code iskallia.vault.client.gui...SkillDialog} / {@code AbilityDialog} with the
 * count/level spliced in at runtime, so the TSV's whole-string exact match always
 * misses. Injecting at the head of our own {@link LiteralTranslator#translate}
 * catches every path that feeds it (TextComponentMixin + FontMixin) with zero
 * changes to the CN jar.</p>
 */
@Mixin(value = LiteralTranslator.class, remap = false)
public abstract class MixinLiteralGuiL10n {

    private static final Pattern UPGRADE = Pattern.compile("^Upgrade \\((\\d+)\\)$");
    private static final Pattern RESEARCH = Pattern.compile("^Research \\((\\d+)\\)$");
    private static final Pattern LEVEL_N = Pattern.compile("^Level (\\d+)$");
    private static final Pattern LEVEL_COLON = Pattern.compile("^Level: (\\d+)$");
    private static final Pattern COST = Pattern.compile("^Cost: (\\d+)$");
    private static final Pattern LEVEL_REQ = Pattern.compile("^Level requirement: (\\d+)$");

    @Inject(method = "translate", at = @At("HEAD"), cancellable = true, remap = false)
    private static void woldsvaults$guiL10n(String text, CallbackInfoReturnable<String> cir) {
        if (text == null || text.isEmpty()) {
            return;
        }
        String t = text.trim();
        if (t.isEmpty()) {
            return;
        }
        String zh = null;
        switch (t) {
            case "All Levels":
                zh = "全部等级";
                break;
            case "Current":
                zh = "当前";
                break;
            case "Next":
                zh = "下一项";
                break;
            default:
                break;
        }
        if (zh == null) {
            Matcher m;
            if ((m = UPGRADE.matcher(t)).matches()) {
                zh = "升级 (" + m.group(1) + ")";
            } else if ((m = RESEARCH.matcher(t)).matches()) {
                zh = "研究 (" + m.group(1) + ")";
            } else if ((m = LEVEL_N.matcher(t)).matches()) {
                zh = "等级 " + m.group(1);
            } else if ((m = LEVEL_COLON.matcher(t)).matches()) {
                zh = "等级: " + m.group(1);
            } else if ((m = COST.matcher(t)).matches()) {
                zh = "花费: " + m.group(1);
            } else if ((m = LEVEL_REQ.matcher(t)).matches()) {
                zh = "等级要求: " + m.group(1);
            }
        }
        if (zh != null && !zh.equals(t)) {
            // Preserve any surrounding whitespace the caller passed in.
            cir.setReturnValue(text.contains(t) ? text.replace(t, zh) : zh);
        }
    }
}
