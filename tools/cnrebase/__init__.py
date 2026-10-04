"""Wold's Vaults 汉化模组重基底流水线。

复用既有 woldsvaults_cn Mixin 模组，只替换载荷数据。

（历史：曾与 ``tools/i18n`` 的「资源包 + VaultPatcher 运行时字节码替换」
路线并列。那条通道因无法承载本项目的 AI 人工翻译流程，已于 2026-09-30
整体归档到 ``archive/i18n-vaultpatcher/``；其 ``classfile.py`` 被本包
需要，已内联为 ``tools/cnrebase/classfile.py``。）

后者是用户实际在用的方案：15 个自研 class 文件（6 个顶层类 + 3 个内部类 +
6 个 Mixin：3 个通用 + 3 个 client）与整合包版本无关，只读取三份载荷：

    assets/woldsvaults_cn/literal_zh_cn.tsv     硬编码字面量对照表
    assets/<ns>/lang/zh_cn.json                 语言文件
    assets/woldsvaults_cn/config_payload/       配置文本载荷 + 安装清单

因此「整合包发新版 → 出新汉化」的正确做法是版本重基底：继承 class 代码，
按新版本语料重建载荷，并收紧 mods.toml 的版本约束。

唯一的 class 例外是 ``patches``：母版作者在 ``WelcomeMessages`` 编译产物里
留了署名 / QQ 群号提示（mod 加载、服务端启动、玩家登录三处输出），
每次重基底都要用字节码补丁静默掉，否则会一路继承。

译料层
------
译文不写在载荷里，而存在 ``translations/cn-rebase/`` 三份 TSV（见 ``corpus``）。
载荷是每轮从源包重建的，写在里面的译文会被下一轮冲掉；译料层是**增量**，
每轮以「载荷（基线）+ 译料（叠加）」重建。回填走 ``apply-todo`` 子命令。

交付门禁
--------
``verify`` 子命令对 dist/ 下三件产物跑交付断言，全部以**母版模板**与
**源整合包**为参照系（不写死魔法数字）。条目数随场景浮动，以报告末尾
「结果: N 项全部通过」为准；缺源包时相关断言会登记为 SKIP，并在报告里
明示「另有 M 项跳过」。

CI 中 ``all`` 会连带执行，并带 ``--strict``：断言失败、或存在未执行的
SKIP，都返回非零、阻止发布。
"""

__all__ = ["fsutil", "assets", "packs", "mods", "classfile", "delta", "corpus",
           "build", "inject", "patches", "fetch", "report", "verify", "cli"]

from . import fsutil as _fsutil

# 本流水线要原地改写解压出来的模板文件；某些托管环境禁止对已存在文件
# 直接截断写，这里挂一层「临时文件 + 原子替换」的兜底。正常环境下不生效。
_fsutil.install()
