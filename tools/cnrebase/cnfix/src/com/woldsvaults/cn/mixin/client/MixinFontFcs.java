package com.woldsvaults.cn.mixin.client;

import com.woldsvaults.cn.LiteralTranslator;
import net.minecraft.util.FormattedCharSequence;
import net.minecraft.network.chat.Style;
import net.minecraft.network.chat.TextComponent;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyVariable;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 1006a：tooltip 标题（技能名/天赋名）与数字模板串的兜底翻译。
 *
 * 证据链：天赋 tooltip 标题显示 "Hexbreaker"（侧栏同一名显示"破咒者"），
 * 说明它既不是 new TextComponent（会被 TextComponentMixin 拦截），
 * 也不走 draw(String)（会被 FontMixin 拦截），
 * 而是 Component/FormattedText → getVisualOrderText() → FormattedCharSequence
 * → Font.drawInternal(m_92726_) 绘制。
 *
 * 本 mixin 钩 Font.m_92726_（FCS 绘制链最底层，drawInBatch(FCS) 也走它），
 * 在参数入口把 FCS 还原成字符串：无 CJK 时过 LiteralTranslator + 数字模板正则，
 * 有变化则替换为译文的 FCS。
 */
@Mixin(net.minecraft.client.gui.Font.class)
public abstract class MixinFontFcs {

    private static final Pattern P_RANK_LINE = Pattern.compile(
            "^Rank (\\d+)/(\\d+)\\s+-\\s+(\\d+)/(\\d+) skill points$");
    private static final Pattern P_NEXT_RANK = Pattern.compile(
            "^Next [Rr]ank: (\\d+) skill points?$");
    private static final Pattern P_UNLOCK = Pattern.compile(
            "^Unlocks rank (\\d+)$");
    private static final Pattern P_ROW_UNLOCKED = Pattern.compile(
            "^Row unlocked: (\\d+)/(\\d+) skill points spent in talents$");
    private static final Pattern P_REQUIRES_MORE = Pattern.compile(
            "^Requires (\\d+) more skill points spent in talents$");
    private static final Pattern P_GROUP_POINTS = Pattern.compile(
            "^(.+?): (\\d+)/(\\d+) group points$");

    // m_92726_ = drawInternal(FCS,f,f,i,Matrix4f,Z)  ← draw(PoseStack,FCS)/drawShadow 走它
    // m_92733_ = drawInBatch(FCS,f,f,i,Z,Matrix4f,MultiBufferSource,Z,i,i) ← tooltip(ClientTextTooltip) 走它
    @ModifyVariable(method = {"m_92726_", "m_92733_"}, at = @At("HEAD"), argsOnly = true, ordinal = 0, remap = false)
    private FormattedCharSequence woldsvaultsCn$translateFcs(FormattedCharSequence fcs) {
        if (fcs == null) {
            return null;
        }
        String s;
        try {
            StringBuilder sb = new StringBuilder(64);
            fcs.accept((index, style, codePoint) -> {
                sb.appendCodePoint(codePoint);
                return true;
            });
            s = sb.toString();
        } catch (Throwable t) {
            return fcs;
        }
        if (s.isEmpty() || woldsvaultsCn$hasCjk(s)) {
            return fcs; // 已含中文 = 已本地化，不碰（避免样式丢失与误替换）
        }
        String tr = null;
        try {
            tr = LiteralTranslator.translate(s);
        } catch (Throwable ignored) {
        }
        if (tr == null || tr.equals(s)) {
            tr = woldsvaultsCn$patterns(s);
        }
        if (tr == null || tr.equals(s)) {
            return fcs;
        }
        try {
            return new TextComponent(tr).getVisualOrderText();
        } catch (Throwable t) {
            return fcs;
        }
    }

    private static String woldsvaultsCn$patterns(String s) {
        Matcher m = P_RANK_LINE.matcher(s);
        if (m.matches()) {
            return "等级 " + m.group(1) + "/" + m.group(2) + " - " + m.group(3) + "/" + m.group(4) + " 技能点";
        }
        m = P_NEXT_RANK.matcher(s);
        if (m.matches()) {
            return "下一级：" + m.group(1) + " 技能点";
        }
        m = P_UNLOCK.matcher(s);
        if (m.matches()) {
            return "解锁等级 " + m.group(1);
        }
        m = P_ROW_UNLOCKED.matcher(s);
        if (m.matches()) {
            return "已解锁行：天赋已投入 " + m.group(1) + "/" + m.group(2) + " 技能点";
        }
        m = P_REQUIRES_MORE.matcher(s);
        if (m.matches()) {
            return "天赋还需投入 " + m.group(1) + " 技能点";
        }
        m = P_GROUP_POINTS.matcher(s);
        if (m.matches()) {
            return m.group(1) + "：" + m.group(2) + "/" + m.group(3) + " 组点数";
        }
        return s;
    }

    private static boolean woldsvaultsCn$hasCjk(String s) {
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if ((c >= 0x4E00 && c <= 0x9FFF) || (c >= 0x3400 && c <= 0x4DBF)
                    || (c >= 0x3000 && c <= 0x30FF) || (c >= 0xFF00 && c <= 0xFFEF)) {
                return true;
            }
        }
        return false;
    }
}
