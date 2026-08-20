KLINE_ADJUSTMENT_FORWARD = "forward"
KLINE_ADJUSTMENT_BACK = "back"
KLINE_ADJUSTMENT_NONE = "none"

DEFAULT_KLINE_ADJUSTMENT = KLINE_ADJUSTMENT_FORWARD

_ALIASES = {
    "": DEFAULT_KLINE_ADJUSTMENT,
    "1": KLINE_ADJUSTMENT_FORWARD,
    "qfq": KLINE_ADJUSTMENT_FORWARD,
    "front": KLINE_ADJUSTMENT_FORWARD,
    "forward": KLINE_ADJUSTMENT_FORWARD,
    "before": KLINE_ADJUSTMENT_FORWARD,
    "前复权": KLINE_ADJUSTMENT_FORWARD,
    "2": KLINE_ADJUSTMENT_BACK,
    "hfq": KLINE_ADJUSTMENT_BACK,
    "back": KLINE_ADJUSTMENT_BACK,
    "backward": KLINE_ADJUSTMENT_BACK,
    "after": KLINE_ADJUSTMENT_BACK,
    "后复权": KLINE_ADJUSTMENT_BACK,
    "0": KLINE_ADJUSTMENT_NONE,
    "bfq": KLINE_ADJUSTMENT_NONE,
    "none": KLINE_ADJUSTMENT_NONE,
    "raw": KLINE_ADJUSTMENT_NONE,
    "unadjusted": KLINE_ADJUSTMENT_NONE,
    "不复权": KLINE_ADJUSTMENT_NONE,
}

_EASTMONEY_FQT = {
    KLINE_ADJUSTMENT_FORWARD: "1",
    KLINE_ADJUSTMENT_BACK: "2",
    KLINE_ADJUSTMENT_NONE: "0",
}

_YAHOO_ADJUST_FLAGS = {
    KLINE_ADJUSTMENT_FORWARD: {"auto_adjust": True, "back_adjust": False},
    KLINE_ADJUSTMENT_BACK: {"auto_adjust": False, "back_adjust": True},
    KLINE_ADJUSTMENT_NONE: {"auto_adjust": False, "back_adjust": False},
}


def normalize_kline_adjustment(value):
    """将复权模式别名归一为系统支持的标准值。"""
    normalized = str(value if value is not None else "").strip().lower()
    return _ALIASES.get(normalized, DEFAULT_KLINE_ADJUSTMENT)


def eastmoney_fqt(value):
    """将标准复权模式转换为东方财富接口的 fqt 参数。"""
    return _EASTMONEY_FQT[normalize_kline_adjustment(value)]


def yahoo_adjust_flags(value):
    """将标准复权模式转换为 Yahoo 数据处理开关。"""
    return dict(_YAHOO_ADJUST_FLAGS[normalize_kline_adjustment(value)])
