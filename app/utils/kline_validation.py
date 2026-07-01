from typing import Any, Dict, Iterable, List, Optional


def require_kline_rows(
    stock_code: str,
    market_type: str,
    rows: Optional[Iterable[Dict[str, Any]]],
    *,
    context: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    latest_date: Optional[str] = None,
    min_rows: int = 1,
    price_field: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Validate K-line rows before writing them into Google Sheet."""
    row_list = list(rows or [])
    range_text = ""
    if start_date or end_date:
        range_text = f" 区间 [{start_date or '-'}, {end_date or '-'}]"
    latest_text = f"，最新K线日期为 {latest_date}" if latest_date else ""

    if not row_list:
        raise ValueError(
            f"股票{stock_code}({market_type}) {context}{range_text}没有可用K线数据{latest_text}"
        )

    if len(row_list) < min_rows:
        raise ValueError(
            f"股票{stock_code}({market_type}) {context}{range_text}K线数据量不足，"
            f"当前 {len(row_list)} 条，至少需要 {min_rows} 条{latest_text}"
        )

    for index, row in enumerate(row_list, start=1):
        if not row.get("stock_date"):
            raise ValueError(f"股票{stock_code}({market_type}) {context}第 {index} 条K线缺少日期")
        if price_field and row.get(price_field) in (None, ""):
            raise ValueError(
                f"股票{stock_code}({market_type}) {context}第 {index} 条K线缺少价格字段 {price_field}"
            )

    return row_list
