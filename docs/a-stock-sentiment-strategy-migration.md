# stock-panel 原生情绪策略报告

> 13 个定义固化在仓库本地 YAML，生成器不读取同级工程。生成策略不自动加入当前策略池。

| 源策略 | 目标策略 | 原状态 | 作用域 | 依赖数 | 最新候选 | 适配说明 |
|---|---|---|---|---:|---:|---|
| limit_pullback | custom_ass_limit_pullback | 停用 | research | 4 | 6 | evidence_rules 输出命中与缺口，不参与硬过滤；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| limit_reversal | custom_ass_limit_reversal | 停用 | research | 4 | 0 | evidence_rules 输出命中与缺口，不参与硬过滤；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| default | custom_ass_default | 停用 | research | 14 | 394 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| short_term_alpha | custom_ass_short_term_alpha | 停用 | research | 12 | 14 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| momentum_repair | custom_ass_momentum_repair | 停用 | research | 6 | 0 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| trend_follow | custom_ass_trend_follow | 停用 | research | 12 | 16 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| first_board_launch | custom_ass_first_board_launch | 启用 | production | 18 | 0 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；evidence_rules 输出命中与缺口，不参与硬过滤；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；源端三段移动止盈已映射到统一分级退出配置；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| ultra_short_board | custom_ass_ultra_short_board | 停用 | research | 13 | 9 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| weak_to_strong | custom_ass_weak_to_strong | 启用 | production | 16 | 3 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；evidence_rules 输出命中与缺口，不参与硬过滤；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；源端三段移动止盈已映射到统一分级退出配置；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行；已接入目标日前20个交易日历史龙头池时点门控 |
| mainline_leader | custom_ass_mainline_leader | 启用 | production | 16 | 0 | evidence_rules 输出命中与缺口，不参与硬过滤；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；源端三段移动止盈已映射到统一分级退出配置；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| capital_resonance | custom_ass_capital_resonance | 停用 | research | 12 | 151 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| defensive_quality | custom_ass_defensive_quality | 停用 | research | 10 | 68 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |
| weak_market_probe | custom_ass_weak_market_probe | 停用 | research | 11 | 7 | priority_filters 已按优先级执行 min_keep/max_drop_ratio 放宽；盘中 entry mode/deadline 尚未执行，当前为盘后候选版；市场状态/情绪阶段保留为元数据，显式市场硬条件照常执行 |

## 验收结论

- 已生成并成功加载 13 个自定义策略。
- 生产策略重点验收数：3。
- required/exclusion/veto 与源阈值一致；评分负权重转换为 stock-panel 的 low 方向。
- priority_filters 在评分后按源端 min_keep/max_drop_ratio 语义执行。
- evidence_rules 输出命中数、命中项和证据缺口；entry mode、confirmation deadline 尚未接入盘中执行。
- 源端三段移动止盈已进入策略定义；回测和模拟执行使用同一分级阈值选择规则。

## 历史数据覆盖

- 股票因子与策略上下文均已同步 349 个交易日，范围为 2025-06-03 至 2026-11-06，共 1,910,222 个股票日样本。
- 历史龙头池按目标日前 20 个交易日计算，导出 349 个交易日、52,232 条资格记录；首日无前序窗口，因此落地 348 个非空 Parquet 分区。
- 龙头池分区采用整日替换写入，股票退出资格池后不会被旧分区残留误判。

## 生产策略候选对照

对照日期：2026-11-06。以下验证包含硬过滤、否决、评分与优先过滤，但不包含分钟入场确认。

| 策略 | 源系统候选数 | stock-panel 候选数 | 结果 |
|---|---:|---:|---|
| first_board_launch | 0 | 0 | 一致 |
| weak_to_strong | 3 | 3 | 一致 |
| mainline_leader | 0 | 0 | 一致 |

## 执行适配状态

- 三段移动止盈已经接入策略定义、独立回测、组合撮合和模拟盘；退出阶段按持仓期间峰值收益选择。
- 分钟入场仍保持失败闭合。源系统确认器依赖集合竞价、板块同步、成交额节奏和确认质量；这些字段尚未进入 stock-panel 分钟数据契约，因此不会使用普通 OHLC 生成伪等价买点。
