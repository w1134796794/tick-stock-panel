# stock-panel 原生因子迁移清单（99 项）

> 固化口径：`backend/app/integrations/a_stock_sentiment/config/factors.yaml`。股票 42 项、板块 17 项、市场 40 项。
> 股票 42 项由本地 OHLCV、截面和增强数据插件重算；插件证据缺失时保持 null。

| # | 注册键 | 展示 ID | 名称 | 层级 | 源数据 | 迁移状态 |
|---:|---|---|---|---|---|---|
| 1 | multi_index_trend | multi_index_trend | 多指数加权趋势评分 | 市场 | index_daily | 待市场级消费契约 |
| 2 | A1_index_intraday_volatility | A1 | 指数日内振幅 | 市场 | index_daily | 待市场级消费契约 |
| 3 | A2_index_consecutive_direction | A2 | 指数连续涨跌方向 | 市场 | index_daily | 待市场级消费契约 |
| 4 | A3_style_deviation | A3 | 大小盘风格偏离度 | 市场 | index_daily | 待市场级消费契约 |
| 5 | total_amount | total_amount | 全市场成交额 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 6 | volume_ratio | volume_ratio | 量比 | 市场 | index_daily | 待市场级消费契约 |
| 7 | A4_amount_change_ratio | A4 | 成交额环比变化率 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 8 | up_down_ratio | up_down_ratio | 涨跌比 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 9 | A5_limit_down_count | A5 | 跌停家数 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 10 | up_count | up_count | 上涨家数 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 11 | prev_limit_up_gap_up | prev_limit_up_gap_up | 昨日涨停高开比例 | 市场 | limit_up_pool | 待市场级消费契约 |
| 12 | prev_limit_up_positive | prev_limit_up_positive | 昨日涨停收红比例 | 市场 | limit_up_pool | 待市场级消费契约 |
| 13 | prev_first_board_gap_up | prev_first_board_gap_up | 昨日首板高开比例 | 市场 | limit_up_pool | 待市场级消费契约 |
| 14 | prev_first_board_positive | prev_first_board_positive | 昨日首板收红比例 | 市场 | limit_up_pool | 待市场级消费契约 |
| 15 | A6_blasted_next_day_performance | A6 | 炸板股次日表现 | 市场 | limit_up_pool | 待市场级消费契约 |
| 16 | limit_up_count | limit_up_count | 涨停家数 | 市场 | limit_up_pool | 待市场级消费契约 |
| 17 | max_board_height | max_board_height | 最高连板高度 | 市场 | limit_up_pool | 待市场级消费契约 |
| 18 | broken_rate | broken_rate | 炸板率 | 市场 | limit_up_pool | 待市场级消费契约 |
| 19 | nuclear_button_count | nuclear_button_count | 核按钮数量 | 市场 | limit_up_pool | 待市场级消费契约 |
| 20 | prev_limit_up_premium | prev_limit_up_premium | 昨日涨停溢价 | 市场 | limit_up_pool | 待市场级消费契约 |
| 21 | mkt_profit_effect_score | mkt_profit_effect_score | 市场赚钱效应 | 市场 | stock_daily_silver,limit_up_pool_silver,limit_down_pool_silver | 待市场级消费契约 |
| 22 | mkt_promotion_trend_score | mkt_promotion_trend_score | 连板接力趋势 | 市场 | limit_up_pool_silver | 待市场级消费契约 |
| 23 | echelon_integrity | echelon_integrity | 连板梯队完整性 | 市场 | limit_up_pool | 待市场级消费契约 |
| 24 | continuous_rate | continuous_rate | 连板率 | 市场 | limit_up_pool | 待市场级消费契约 |
| 25 | limit_down_ratio | limit_down_ratio | 跌停/涨停比 | 市场 | limit_up_pool | 待市场级消费契约 |
| 26 | win_rate | win_rate | T+1胜率 | 市场 | limit_up_pool | 待市场级消费契约 |
| 27 | avg_profit | avg_profit | 平均赢面 | 市场 | limit_up_pool | 待市场级消费契约 |
| 28 | B1_first_board_ratio | B1 | 首板/连板比 | 市场 | limit_up_pool | 待市场级消费契约 |
| 29 | B2_one_word_board_ratio | B2 | 一字板占比 | 市场 | limit_up_pool | 待市场级消费契约 |
| 30 | B3_tail_board_ratio | B3 | 尾盘板占比 | 市场 | limit_up_pool | 待市场级消费契约 |
| 31 | B4_extreme_reversal_count | B4 | 地天板/天地板数量 | 市场 | all_stocks_daily | 待市场级消费契约 |
| 32 | B5_avg_seal_ratio | B5 | 涨停股平均封单比 | 市场 | limit_up_pool | 待市场级消费契约 |
| 33 | sector_pct_change | sector_pct_change | 板块涨跌幅 | 板块 | ths_index | 待板块扩展表 |
| 34 | sector_amount | sector_amount | 板块成交额 | 板块 | ths_index | 待板块扩展表 |
| 35 | sector_limit_up_count | sector_limit_up_count | 板块涨停家数 | 板块 | limit_up_pool | 待板块扩展表 |
| 36 | sector_limit_up_ratio | sector_limit_up_ratio | 板块涨停占比 | 板块 | limit_up_pool | 待板块扩展表 |
| 37 | sector_momentum | sector_momentum | 板块动量得分 | 板块 | ths_index | 待板块扩展表 |
| 38 | C1_avg_seal_time | C1 | 板块内涨停股平均封板时间 | 板块 | limit_up_pool | 待板块扩展表 |
| 39 | C2_leader_follower_seal_ratio | C2 | 龙头/跟风封单比 | 板块 | limit_up_pool | 待板块扩展表 |
| 40 | C3_sector_next_day_premium | C3 | 板块涨停股次日平均溢价 | 板块 | limit_up_pool | 待板块扩展表 |
| 41 | C4_sector_net_capital_flow | C4 | 板块资金净流入 | 板块 | all_stocks_daily | 待板块扩展表 |
| 42 | C5_sector_rotation_speed | C5 | 板块轮动速度 | 板块 | persistence_history | 待板块扩展表 |
| 43 | D1_n_day_high_low | D1 | N日高低位 | 股票 | stock_daily | 本地原生/插件 |
| 44 | D2_vol_price_coord | D2 | 量价配合度 | 股票 | stock_daily | 本地原生/插件 |
| 45 | D3_seal_strength | D3 | 封板强度 | 股票 | limit_up_pool | 本地原生/插件 |
| 46 | D4_turnover_health | D4 | 换手率健康度 | 股票 | stock_daily | 本地原生/插件 |
| 47 | D5_ma_bull_align | D5 | 均线多头排列度 | 股票 | stock_daily | 本地原生/插件 |
| 48 | stk_board_height | D6 | 连板高度梯队分 | 股票 | limit_up_pool | 本地原生/插件 |
| 49 | stk_seal_time_quality | D7 | 封板时间质量分 | 股票 | limit_up_pool | 本地原生/插件 |
| 50 | stk_float_mv_fit | D8 | 流通市值适配分 | 股票 | limit_up_pool | 本地原生/插件 |
| 51 | E1_main_net_ratio | E1 | 主力净流入占比 | 股票 | moneyflow_summary | 本地原生/插件 |
| 52 | E2_retail_net_ratio | E2 | 散户净流入占比 | 股票 | moneyflow_summary | 本地原生/插件 |
| 53 | E3_large_buy_ratio | E3 | 大单买入占比 | 股票 | moneyflow_summary | 本地原生/插件 |
| 54 | E4_moneyflow_trend | E4 | 资金流向趋势 | 股票 | moneyflow_summary | 本地原生/插件 |
| 55 | first_board_sector_resonance_ratio | FBM1 | 首板板块共振占比 | 市场 | limit_up_pool+sector_daily+sector_membership | 待市场级消费契约 |
| 56 | first_board_cluster_count | FBM2 | 首板集群板块数 | 市场 | limit_up_pool+sector_membership | 待市场级消费契约 |
| 57 | first_board_follow_through_ratio | FBM3 | 首板题材延续率 | 市场 | limit_up_pool+sector_daily+sector_membership | 待市场级消费契约 |
| 58 | stk_capital_flow_consensus | SIG1 | 多源资金流共识 | 股票 | stock_capital_flow_silver | 本地原生/插件 |
| 59 | stk_intraday_seal_quality | D9 | 封板综合质量 | 股票 | limit_up_pool | 本地原生/插件 |
| 60 | stk_first_board_sector_sync_score | FB1 | 首板板块同步爆发 | 股票 | limit_up_pool+factor_sector_wide+stock_daily | 本地原生/插件 |
| 61 | stk_first_board_leadership_score | FB2 | 首板先锋领先性 | 股票 | limit_up_pool+sector_membership | 本地原生/插件 |
| 62 | stk_first_board_sector_pioneer_score | FB3 | 首板题材集群强度 | 股票 | limit_up_pool+sector_membership | 本地原生/插件 |
| 63 | stk_first_board_breadth_score | FB4 | 首板题材跟涨宽度 | 股票 | stock_daily+sector_membership | 本地原生/插件 |
| 64 | stk_first_board_amount_surge_score | FB5 | 首板量价共振 | 股票 | factor_sector_wide+stock_daily | 本地原生/插件 |
| 65 | stk_first_board_new_theme_score | FB6 | 首板新题材启动 | 股票 | factor_stock_wide+limit_up_pool | 本地原生/插件 |
| 66 | stk_first_board_resonance_score | FB7 | 首板板块共振综合分 | 股票 | factor_stock_wide | 本地原生/插件 |
| 67 | stk_sector_rotation_momentum | D10 | 板块轮动动量 | 股票 | factor_sector_wide | 本地原生/插件 |
| 68 | stk_crowding_decay_5d | D11 | 近5日拥挤衰减 | 股票 | limit_up_pool | 本地原生/插件 |
| 69 | stk_relative_strength_sector | D12 | 个股相对板块强度 | 股票 | stock_daily+sector_membership | 本地原生/插件 |
| 70 | sec_behavior_attention | BH1 | 板块注意形成 | 板块 | sector_daily_silver | 待板块扩展表 |
| 71 | sec_behavior_acceleration | BH2 | 板块一致加速 | 板块 | factor_sector_wide | 待板块扩展表 |
| 72 | sec_behavior_divergence | BH3 | 板块分歧释放 | 板块 | factor_sector_wide | 待板块扩展表 |
| 73 | sec_behavior_repair | BH4 | 板块弱转强修复 | 板块 | factor_sector_wide | 待板块扩展表 |
| 74 | sec_behavior_decay | BH5 | 板块拥挤衰退 | 板块 | factor_sector_wide | 待板块扩展表 |
| 75 | stk_behavior_attention | BH6 | 个股注意形成 | 股票 | factor_stock_wide | 本地原生/插件 |
| 76 | stk_behavior_acceleration | BH7 | 个股一致加速 | 股票 | factor_stock_wide | 本地原生/插件 |
| 77 | stk_behavior_divergence | BH8 | 个股分歧释放 | 股票 | factor_stock_wide | 本地原生/插件 |
| 78 | stk_behavior_repair | BH9 | 个股弱转强修复 | 股票 | factor_stock_wide | 本地原生/插件 |
| 79 | stk_behavior_decay | BH10 | 个股拥挤衰退 | 股票 | factor_stock_wide | 本地原生/插件 |
| 80 | stk_capital_flow_persistence | SIG2 | 资金流持续性 | 股票 | stock_capital_flow_silver | 本地原生/插件 |
| 81 | stk_attention_consensus | SIG3 | 双平台热度共识 | 股票 | stock_attention_silver | 本地原生/插件 |
| 82 | stk_attention_crowding_risk | SIG4 | 热度拥挤风险 | 股票 | stock_attention_silver | 本地原生/插件 |
| 83 | stk_kpl_leader_quality | SIG5 | 开盘啦龙头身份证据 | 股票 | stock_leader_signal_silver | 本地原生/插件 |
| 84 | stk_mainline_leader_identity | SIG5B | 主线龙头身份 | 股票 | factor_stock_wide | 本地原生/插件 |
| 85 | stk_margin_acceleration | SIG6 | 融资净买入加速度 | 股票 | stock_margin_silver | 本地原生/插件 |
| 86 | stk_block_trade_risk | SIG7 | 大宗交易折价风险 | 股票 | stock_event_silver | 本地原生/插件 |
| 87 | sec_capital_flow_score | SIG8 | 板块资金流强度 | 板块 | sector_capital_flow_silver | 待板块扩展表 |
| 88 | sec_flow_price_resonance | SIG9 | 板块量价资金共振 | 板块 | sector_capital_flow_silver | 待板块扩展表 |
| 89 | stk_lhb_net_buy_score | LHB1 | 龙虎榜净买入强度 | 股票 | top_list | 本地原生/插件 |
| 90 | stk_lhb_institution_score | LHB2 | 机构净买入强度 | 股票 | top_inst | 本地原生/插件 |
| 91 | stk_lhb_institution_consensus | LHB3 | 机构席位共识 | 股票 | top_inst | 本地原生/插件 |
| 92 | stk_lhb_repeat_persistence | LHB5 | 龙虎榜资金持续性 | 股票 | top_list | 本地原生/插件 |
| 93 | stk_lhb_sector_resonance | LHB6 | 龙虎榜板块共振 | 股票 | factor_lhb_sector_wide | 本地原生/插件 |
| 94 | stk_lhb_crowding_risk | LHB7 | 龙虎榜拥挤风险 | 股票 | top_inst | 本地原生/插件 |
| 95 | E3_north_flow | E3 | 北向资金净流入 | 市场 | moneyflow_hsgt | 待市场级消费契约 |
| 96 | E4_margin_change_ratio | E4 | 融资余额变化率 | 市场 | margin | 待市场级消费契约 |
| 97 | F1_cycle_duration | F1_cycle_duration | 情绪周期持续性 | 市场 | emotion_history | 待市场级消费契约 |
| 98 | F2_market_emotion_divergence | F2_market_emotion_divergence | 大盘-情绪背离度 | 市场 | composite | 待市场级消费契约 |
| 99 | F3_signal_win_rate | F3 | 昨日信号今日胜率 | 市场 | pattern_signals | 待市场级消费契约 |

## 本地重算命令

在 `backend/` 目录执行：

```powershell
# 最新交易日
.\.venv\Scripts\python.exe scripts/compute_a_stock_sentiment_factors.py

# 历史回补（闭区间，ISO 日期）
.\.venv\Scripts\python.exe scripts/compute_a_stock_sentiment_factors.py --start 2025-01-01 --end 2025-12-31
```

最终因子 ID 为 `ext_a_stock_sentiment_factors_<注册键>`。

## 当前批次结论

- 股票 42 项与策略上下文 20 项已进入原生每日重算管道。
- D1–D5 使用本地日线与标准分钟表；E1–E4 使用已注册 moneyflow 插件。
- 龙虎榜读取本地缓存；两融、大宗、热度等增强证据通过受控插件契约接入，缺失不伪造。
- 历史龙头池由本地交易日历和前 20 个交易日因子滚动生成。
- 板块 17 项与市场 40 项仍保留在后续批次，不冒充股票级字段。
