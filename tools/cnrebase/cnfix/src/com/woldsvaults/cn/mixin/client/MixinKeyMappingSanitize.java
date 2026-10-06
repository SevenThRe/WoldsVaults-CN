package com.woldsvaults.cn.mixin.client;

import net.minecraft.client.KeyMapping;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.TranslatableComponent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

import java.util.Locale;

/**
 * 1005r: 修复按键绑定名渲染成控制字符乱码（如 "SOH\\SOH]SOH"）的问题。
 *
 * <p>技能树 tooltip 的 "按键: X" 行、原版控件界面的键名，全部经过
 * {@code KeyMapping.m_90863_()}（getTranslatedKeyMessage）。实测该出口在
 * 某些绑定下返回的文本含 C0 控制字符（0x01 等），渲染成乱码；而所有静态
 * 数据源（vanilla en_us/zh_cn、我方语言包、TSV、config）都是干净的，
 * 说明损坏发生在运行时。在此唯一出口处拦截：检测到控制字符即用规范键名
 * （{@code key.keyboard.f1} → {@code F1}）重建友好显示。</p>
 */
@Mixin(KeyMapping.class)
public abstract class MixinKeyMappingSanitize {

    @Inject(method = "m_90863_", at = @At("RETURN"), cancellable = true, remap = false)
    private void woldsvaultsCn$sanitizeKeyName(CallbackInfoReturnable<Component> cir) {
        Component comp = cir.getReturnValue();
        if (comp == null) {
            return;
        }
        String s;
        try {
            s = comp.getString();
        } catch (Throwable t) {
            return;
        }
        if (s == null || s.isEmpty() || !hasCtrlChar(s)) {
            return;
        }
        String key = null;
        try {
            if (comp instanceof TranslatableComponent tc) {
                key = tc.getKey();
            }
        } catch (Throwable ignored) {
        }
        String friendly = friendlyOf(key);
        cir.setReturnValue(new net.minecraft.network.chat.TextComponent(
                friendly != null ? friendly : stripCtrl(s)));
    }

    private static boolean hasCtrlChar(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if ((c < 32 && c != '\t' && c != '\n' && c != '\r') || c == 0x7F) {
                return true;
            }
        }
        return false;
    }

    private static String stripCtrl(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c >= 32 || c == '\t' || c == '\n' || c == '\r') {
                sb.append(c);
            }
        }
        return sb.toString();
    }

    private static String friendlyOf(String key) {
        if (key == null) {
            return null;
        }
        if (key.startsWith("key.keyboard.")) {
            String r = key.substring("key.keyboard.".length());
            if (r.matches("f\\d+")) {
                return "F" + r.substring(1);
            }
            if (r.equals("grave.accent")) {
                return "`";
            }
            if (r.equals("space")) {
                return "Space";
            }
            if (r.equals("tab")) {
                return "Tab";
            }
            if (r.equals("caps.lock")) {
                return "Caps Lock";
            }
            if (r.equals("enter")) {
                return "Enter";
            }
            if (r.equals("left.shift")) {
                return "LShift";
            }
            if (r.equals("right.shift")) {
                return "RShift";
            }
            if (r.equals("left.control")) {
                return "LCtrl";
            }
            if (r.equals("right.control")) {
                return "RCtrl";
            }
            if (r.equals("left.alt")) {
                return "LAlt";
            }
            if (r.equals("right.alt")) {
                return "RAlt";
            }
            if (r.equals("up")) {
                return "\u2191";
            }
            if (r.equals("down")) {
                return "\u2193";
            }
            if (r.equals("left")) {
                return "\u2190";
            }
            if (r.equals("right")) {
                return "\u2192";
            }
            if (r.length() == 1) {
                return r.toUpperCase(Locale.ROOT);
            }
            String[] parts = r.split("\\.");
            StringBuilder sb = new StringBuilder();
            for (String p : parts) {
                if (p.isEmpty()) {
                    continue;
                }
                if (sb.length() > 0) {
                    sb.append(' ');
                }
                sb.append(Character.toUpperCase(p.charAt(0))).append(p.substring(1));
            }
            return sb.toString();
        }
        if (key.startsWith("key.mouse.")) {
            try {
                int idx = Integer.parseInt(key.substring("key.mouse.".length()));
                return "Mouse " + (idx + 1);
            } catch (NumberFormatException ignored) {
            }
        }
        return null;
    }
}
