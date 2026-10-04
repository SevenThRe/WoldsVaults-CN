# 译料层（不要删）

这四份 TSV 是**本项目累积的译文**，是重基底构建的输入之一，不是导出物。
删掉它们，等价于把所有 AI 补译的内容丢掉，下一轮构建会重新把它们列为待译。

| 文件 | 列 | 对应通道 |
|---|---|---|
| `lang_zh.tsv` | `namespace` `key` `en` `zh` | 整合包本体语言文件 `assets/<ns>/lang/zh_cn.json` |
| `literal_zh_cn.tsv` | `en` `zh` | 硬编码字面量对照表（写入 jar 内 `literal_zh_cn.tsv`） |
| `config_zh.tsv` | `target` `pointer` `en` `zh` | 配置文本（按 JSON 指针回填） |
| `vendor_lang_zh.tsv` | `namespace` `key` `en` `zh` | **第三方模组**语言文件（以模组自带 zh 为底整份生成） |

`lang_zh.tsv` 与 `vendor_lang_zh.tsv` 结构相同，区别只在归属：前者是整合包
本体（`the_vault` / `woldsvaults` / `kubejs` …），后者是整合包自带的第三方
模组。分开存是为了让两类工作的进度各自可见。

`en` 列只作对照，构建时**不使用**——译文与键（或指针）绑定，
这样上游改了英文原文时，已有译文不会因为文本不匹配而失效。

写入请走 `python -m tools.cnrebase.cli apply-todo`，不要手改：
该命令会做占位符/样式码校验，并做转义与排序，手改容易破坏格式。

`pointer` 是 JSON 位置，形如 `/o:skills/i:3/o:name`：
`o:` 表示对象键、`i:` 表示数组下标，键内的 `/` 与 `~` 转义为 `~1` / `~0`。
回填**只覆盖已存在的叶子**，不会凭空新增字段——结构永远以新版 config 为准。
