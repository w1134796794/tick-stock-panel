"""原生因子与策略上下文字段注册表。"""

from __future__ import annotations

from pathlib import Path

from app.factors.ext_factors import ensure_synced, ext_column_name
from app.services.ext_data import ExtConfig, ExtConfigStore, ExtField

CONFIG_ID = "a_stock_sentiment_factors"
STRATEGY_CONTEXT_CONFIG_ID = "a_stock_sentiment_strategy_context"
LEADER_POOL_CONFIG_ID = "a_stock_sentiment_leader_pool"

GROUP_TECHNICAL = "扩展·技术量价"
GROUP_LIMIT_UP = "扩展·涨停与接力"
GROUP_SECTOR = "扩展·板块与主线"
GROUP_CAPITAL = "扩展·资金流与交易"
GROUP_BEHAVIOR = "扩展·情绪与行为"
GROUP_LEADER = "扩展·龙虎榜与龙头"
GROUP_MARKET = "扩展·市场环境"

STOCK_FACTOR_LABELS: tuple[tuple[str, str], ...] = (
    ("D1_n_day_high_low", "N日高低位"),
    ("D2_vol_price_coord", "量价配合度"),
    ("D3_seal_strength", "封板强度"),
    ("D4_turnover_health", "换手率健康度"),
    ("D5_ma_bull_align", "均线多头排列度"),
    ("stk_board_height", "连板高度梯队分"),
    ("stk_seal_time_quality", "封板时间质量分"),
    ("stk_float_mv_fit", "流通市值适配分"),
    ("E1_main_net_ratio", "主力净流入占比"),
    ("E2_retail_net_ratio", "散户净流入占比"),
    ("E3_large_buy_ratio", "大单买入占比"),
    ("E4_moneyflow_trend", "资金流向趋势"),
    ("stk_capital_flow_consensus", "多源资金流共识"),
    ("stk_intraday_seal_quality", "封板综合质量"),
    ("stk_first_board_sector_sync_score", "首板板块同步爆发"),
    ("stk_first_board_leadership_score", "首板先锋领先性"),
    ("stk_first_board_sector_pioneer_score", "首板题材集群强度"),
    ("stk_first_board_breadth_score", "首板题材跟涨宽度"),
    ("stk_first_board_amount_surge_score", "首板量价共振"),
    ("stk_first_board_new_theme_score", "首板新题材启动"),
    ("stk_first_board_resonance_score", "首板板块共振综合分"),
    ("stk_sector_rotation_momentum", "板块轮动动量"),
    ("stk_crowding_decay_5d", "近5日拥挤衰减"),
    ("stk_relative_strength_sector", "个股相对板块强度"),
    ("stk_behavior_attention", "个股注意形成"),
    ("stk_behavior_acceleration", "个股一致加速"),
    ("stk_behavior_divergence", "个股分歧释放"),
    ("stk_behavior_repair", "个股弱转强修复"),
    ("stk_behavior_decay", "个股拥挤衰退"),
    ("stk_capital_flow_persistence", "资金流持续性"),
    ("stk_attention_consensus", "双平台热度共识"),
    ("stk_attention_crowding_risk", "热度拥挤风险"),
    ("stk_kpl_leader_quality", "开盘啦龙头身份证据"),
    ("stk_mainline_leader_identity", "主线龙头身份"),
    ("stk_margin_acceleration", "融资净买入加速度"),
    ("stk_block_trade_risk", "大宗交易折价风险"),
    ("stk_lhb_net_buy_score", "龙虎榜净买入强度"),
    ("stk_lhb_institution_score", "机构净买入强度"),
    ("stk_lhb_institution_consensus", "机构席位共识"),
    ("stk_lhb_repeat_persistence", "龙虎榜资金持续性"),
    ("stk_lhb_sector_resonance", "龙虎榜板块共振"),
    ("stk_lhb_crowding_risk", "龙虎榜拥挤风险"),
)
STOCK_FACTOR_IDS = tuple(key for key, _ in STOCK_FACTOR_LABELS)
FACTOR_GROUPS: dict[str, str] = {
    **dict.fromkeys((
        "D1_n_day_high_low",
        "D2_vol_price_coord",
        "D4_turnover_health",
        "D5_ma_bull_align",
        "stk_float_mv_fit",
    ), GROUP_TECHNICAL),
    **dict.fromkeys((
        "D3_seal_strength",
        "stk_board_height",
        "stk_seal_time_quality",
        "stk_intraday_seal_quality",
        "stk_first_board_sector_sync_score",
        "stk_first_board_leadership_score",
        "stk_first_board_sector_pioneer_score",
        "stk_first_board_breadth_score",
        "stk_first_board_amount_surge_score",
        "stk_first_board_new_theme_score",
        "stk_first_board_resonance_score",
    ), GROUP_LIMIT_UP),
    **dict.fromkeys((
        "stk_sector_rotation_momentum",
        "stk_relative_strength_sector",
    ), GROUP_SECTOR),
    **dict.fromkeys((
        "E1_main_net_ratio",
        "E2_retail_net_ratio",
        "E3_large_buy_ratio",
        "E4_moneyflow_trend",
        "stk_capital_flow_consensus",
        "stk_capital_flow_persistence",
        "stk_margin_acceleration",
        "stk_block_trade_risk",
    ), GROUP_CAPITAL),
    **dict.fromkeys((
        "stk_crowding_decay_5d",
        "stk_behavior_attention",
        "stk_behavior_acceleration",
        "stk_behavior_divergence",
        "stk_behavior_repair",
        "stk_behavior_decay",
        "stk_attention_consensus",
        "stk_attention_crowding_risk",
    ), GROUP_BEHAVIOR),
    **dict.fromkeys((
        "stk_kpl_leader_quality",
        "stk_mainline_leader_identity",
        "stk_lhb_net_buy_score",
        "stk_lhb_institution_score",
        "stk_lhb_institution_consensus",
        "stk_lhb_repeat_persistence",
        "stk_lhb_sector_resonance",
        "stk_lhb_crowding_risk",
    ), GROUP_LEADER),
}

STRATEGY_CONTEXT_LABELS: tuple[tuple[str, str], ...] = (
    ("board_height", "官方连板高度"),
    ("limit_progress", "涨停进度"),
    ("mkt_broken_rate", "市场炸板率"),
    ("mkt_limit_down_count", "市场跌停家数"),
    ("mkt_limit_up_count", "市场涨停家数"),
    ("mkt_market_score", "市场综合分"),
    ("stk_amount_ratio_5d", "成交额相对5日"),
    ("stk_board_position", "打板身位"),
    ("stk_limit_pullback", "涨停回踩结构"),
    ("stk_limit_reversal", "跌停反包结构"),
    ("stk_liquidity_percentile", "流动性分位"),
    ("stk_new_high_20d", "20日强势位置"),
    ("stk_pct_chg_1d", "当日涨跌幅强度"),
    ("stk_pullback_contraction", "回踩缩量程度"),
    ("stk_reversal_recovery", "跌幅收复程度"),
    ("stk_sector_mainline_score", "主线强度"),
    ("stk_sector_persistence_score", "板块持续性"),
    ("stk_sector_resonance_score", "板块共振"),
    ("stk_vol_ratio_5d", "成交量相对5日"),
    ("tech_score", "技术综合分"),
)
STRATEGY_CONTEXT_IDS = tuple(key for key, _ in STRATEGY_CONTEXT_LABELS)
STRATEGY_CONTEXT_GROUPS: dict[str, str] = {
    **dict.fromkeys((
        "stk_amount_ratio_5d",
        "stk_liquidity_percentile",
        "stk_new_high_20d",
        "stk_pct_chg_1d",
        "stk_pullback_contraction",
        "stk_vol_ratio_5d",
        "tech_score",
    ), GROUP_TECHNICAL),
    **dict.fromkeys((
        "board_height",
        "limit_progress",
        "stk_board_position",
        "stk_limit_pullback",
        "stk_limit_reversal",
        "stk_reversal_recovery",
    ), GROUP_LIMIT_UP),
    **dict.fromkeys((
        "stk_sector_mainline_score",
        "stk_sector_persistence_score",
        "stk_sector_resonance_score",
    ), GROUP_SECTOR),
    **dict.fromkeys((
        "mkt_broken_rate",
        "mkt_limit_down_count",
        "mkt_limit_up_count",
        "mkt_market_score",
    ), GROUP_MARKET),
}


def _config(
    config_id: str,
    label: str,
    fields: tuple[tuple[str, str], ...],
    groups: dict[str, str],
    existing: ExtConfig | None,
) -> ExtConfig:
    return ExtConfig(
        id=config_id,
        label=label,
        mode="timeseries",
        fields=[
            ExtField(name, "float", title, factor_group=groups[name])
            for name, title in fields
        ],
        description="由 stock-panel 本地行情、截面及数据源插件按交易日原生重算。",
        symbol_map={"type": "computed", "from": "code", "method": "append_exchange"},
        code_map={"type": "mapped", "col": "code"},
        created_at=existing.created_at if existing else None,
        updated_at=existing.updated_at if existing else None,
    )


def register_native_tables(data_dir: Path) -> tuple[ExtConfig, ExtConfig]:
    store = ExtConfigStore(Path(data_dir))
    old_factor = store.get(CONFIG_ID)
    old_context = store.get(STRATEGY_CONTEXT_CONFIG_ID)
    factor = _config(
        CONFIG_ID,
        "A股情绪原生因子",
        STOCK_FACTOR_LABELS,
        FACTOR_GROUPS,
        old_factor,
    )
    context = _config(
        STRATEGY_CONTEXT_CONFIG_ID,
        "A股情绪策略上下文",
        STRATEGY_CONTEXT_LABELS,
        STRATEGY_CONTEXT_GROUPS,
        old_context,
    )
    if old_factor is None or old_factor.to_dict() != factor.to_dict():
        store.upsert(factor)
    if old_context is None or old_context.to_dict() != context.to_dict():
        store.upsert(context)
    ensure_synced(Path(data_dir))
    return factor, context


def registered_factor_ids() -> tuple[str, ...]:
    return tuple(ext_column_name(CONFIG_ID, item) for item in STOCK_FACTOR_IDS)


def strategy_context_factor_ids() -> tuple[str, ...]:
    return tuple(ext_column_name(STRATEGY_CONTEXT_CONFIG_ID, item) for item in STRATEGY_CONTEXT_IDS)


def config_dir() -> Path:
    return Path(__file__).with_name("config")
