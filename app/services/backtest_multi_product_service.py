"""Multi-product backtest task service and preview helpers."""

from __future__ import annotations

import json
import math
import re
import traceback
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from flask import current_app
from sqlalchemy import text

from app.extensions import db
from app.models import Task, TaskResult, TaskResultReturn
from app.services.backtest_training_service import BacktestTrainingService
from app.services.config_manager import get_config_manager
from app.services.xpl_service import xpl_analyzer
from app.utils.db_retry import db_retry_manager, safe_db_operation
from app.utils.task_error_utils import build_task_error_message, unwrap_exception


BACKTEST_MULTI_PRODUCT_TASK_TYPE = "backtest_multi_product"
RATIO_BASE = Decimal("100")

SUMMARY_ROW_DEFS = [
    ("绝对收益", "年化收益", "index_annualized_return", "start_annualized_return", "percent"),
    ("绝对收益", "盈利年份百分比", "index_profit_annual", "start_profit_annual", "percent"),
    ("绝对收益", "月盈利百分比", "index_profit_monthly_percentage", "start_profit_monthly_percentage", "percent"),
    ("绝对收益", "平均月收益率", "index_avg_monthly_return", "start_avg_monthly_return", "percent"),
    ("绝对收益", "月收益率波动率", "index_monthly_return_volatility", "start_monthly_return_volatility", "percent"),
    ("相对收益", "年化超额收益", None, "annualized_return_diff", "percent"),
    ("相对收益", "跑赢年份(百分比)", None, "outperform_year", "percent"),
    ("相对收益", "月超额收益胜率", None, "monthly_excess_return_percentage", "percent"),
    ("相对收益", "平均月超额", None, "avg_monthly_excess_return", "percent"),
    ("相对收益", "月超额波动率", None, "monthly_excess_volatility", "percent"),
    ("回撤", "年最大超额回撤", None, "year_max_excess_drawdown", "percent"),
    ("回撤", "超额回撤胜率", None, "excess_drawdown_winning_rate", "percent"),
    ("回撤", "年最大回撤", None, "start_max_drawdown", "percent"),
    ("回撤", "最大修复天数", None, "start_maximum_number_of_backtest_repair_days", "number"),
    ("回撤", "超额最大修复天数", None, "excess_maximum_number_of_backtest_repair_days", "number"),
    ("比率", "夏普比率", "index_sharpe_ratio", "start_sharpe_ratio", "number"),
    ("比率", "卡玛比率", "index_kama_ratio", "start_kama_ratio", "number"),
    ("比率", "所提诺比率", "index_sotino_ratio", "start_sotino_ratio", "number"),
    ("夏普", "超额夏普", None, "excess_sharp", "number"),
    ("所提诺", "超额所提诺比率", None, "excess_of_promissory_note", "number"),
]


def normalize_market_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"en", "us", "usa"}:
        return "en"
    return "cn"


def normalize_price_mode(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"kp_price", "sp_price"}:
        return normalized
    return "sp_price"


def parse_ratio(value: Any) -> Decimal:
    raw = str(value if value is not None else "").strip().replace("%", "")
    if not raw:
        raise ValueError("产品比例不能为空")
    try:
        ratio = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"产品比例不是有效数字: {value}") from exc
    if ratio < 0:
        raise ValueError("产品比例不能小于 0")
    return ratio


def normalize_ratio_display(value: Any) -> str:
    ratio = parse_ratio(value)
    normalized = ratio.quantize(Decimal("0.0001")).normalize()
    text = format(normalized, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _normalize_sheet(product: dict[str, Any]) -> dict[str, str]:
    sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
    spreadsheet_id = str(sheet.get("spreadsheet_id") or product.get("spreadsheet_id") or "").strip()
    sheet_name = str(sheet.get("sheet_name") or product.get("sheet_name") or "data").strip()
    title = str(sheet.get("title") or product.get("title") or "").strip()
    if not spreadsheet_id:
        raise ValueError("每个产品都必须配置 Google Sheet 链接")
    return {
        "spreadsheet_id": spreadsheet_id,
        "sheet_name": sheet_name or "data",
        "title": title,
    }


def normalize_multi_product_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        raise ValueError("多品数据回测 config 必须是 JSON 对象")

    start_date = str(config.get("start_date") or "").strip()
    end_date = str(config.get("end_date") or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_date):
        raise ValueError("请填写有效的 K 线开始日期")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_date):
        raise ValueError("请填写有效的 K 线结束日期")
    if start_date > end_date:
        raise ValueError("K 线开始日期不能晚于结束日期")

    products = config.get("products")
    if not isinstance(products, list) or len(products) < 2:
        raise ValueError("多品数据回测至少需要 2 个产品")

    normalized_products = []
    expected_parameter_count = None
    for index, product in enumerate(products, start=1):
        if not isinstance(product, dict):
            raise ValueError(f"产品 {index} 配置格式不正确")
        stock_code = str(product.get("stock_code") or "").strip().upper()
        if not stock_code:
            raise ValueError(f"产品 {index} 缺少股票代码")
        parameters = product.get("parameters")
        if not isinstance(parameters, list) or not parameters:
            raise ValueError(f"产品 {index} 至少需要一行参数")
        for row_index, row in enumerate(parameters, start=1):
            if not isinstance(row, list) or not any(str(item).strip() for item in row):
                raise ValueError(f"产品 {index} 第 {row_index} 行参数为空")
        if expected_parameter_count is None:
            expected_parameter_count = len(parameters)
        elif len(parameters) != expected_parameter_count:
            raise ValueError("所有产品的参数行数必须一致，才能按行号对齐")

        normalized_products.append({
            **product,
            "product_index": index - 1,
            "product_name": str(product.get("product_name") or product.get("name") or stock_code).strip(),
            "stock_code": stock_code,
            "market_type": normalize_market_type(product.get("market_type")),
            "price_mode": normalize_price_mode(product.get("price_mode") or config.get("price_mode")),
            "kline_adjustment": product.get("kline_adjustment") or config.get("kline_adjustment") or "forward",
            "ratio": normalize_ratio_display(product.get("ratio")),
            "sheet": _normalize_sheet(product),
            "parameters": parameters,
        })

    return {
        **config,
        "start_date": start_date,
        "end_date": end_date,
        "products": normalized_products,
    }


def _parse_json(raw: Any, default: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw) if raw else default
    except (TypeError, json.JSONDecodeError):
        return default


def _all_entry(items: Any, key_name: str = "year") -> dict[str, Any]:
    if not isinstance(items, list):
        return {}
    for item in items:
        if isinstance(item, dict) and str(item.get(key_name)) == "all":
            return item
    return {}


def _extract_result_core(task_result: TaskResult) -> dict[str, Any]:
    payload = _parse_json(task_result.result, {})
    if not isinstance(payload, dict) or not payload:
        return {}

    prioritized_keys = ("calculate_metrics", "weighted_calculate_metrics")
    for value in payload.values():
        if not isinstance(value, dict):
            continue
        if any(key in value for key in prioritized_keys):
            return value

    first_value = next(iter(payload.values()), {})
    return first_value if isinstance(first_value, dict) else {}


def _extract_return_date_from_result_payload(result_payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(result_payload, dict):
        return []
    direct_return_date = result_payload.get("_return_date")
    if isinstance(direct_return_date, list):
        return direct_return_date
    value = list(result_payload.values())[0] if result_payload else {}
    if not isinstance(value, dict):
        return []
    return_date = value.get("return_date")
    return return_date if isinstance(return_date, list) else []


def _safe_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    raw = str(value).strip().replace(",", "").replace("$", "")
    if not raw or raw == "-":
        return None
    try:
        if raw.endswith("%"):
            return float(raw[:-1]) / 100
        return float(raw)
    except ValueError:
        return None


def _fmt_value(value: Any, value_type: str) -> str:
    number = _safe_number(value)
    if number is None:
        return "" if value in (None, "") else str(value)
    if value_type == "percent":
        return f"{number:.2%}"
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_ratio_reference(value: Any) -> str:
    try:
        return f"{normalize_ratio_display(value)}%"
    except ValueError:
        return "-"


def _build_returns_json(return_date: list[dict[str, Any]]) -> str:
    dates = []
    index_returns = []
    start_returns = []
    for item in return_date:
        if not isinstance(item, dict):
            continue
        dates.append(item.get("date") or item.get("stock_date"))
        index_returns.append(item.get("index_return"))
        start_returns.append(item.get("start_return"))
    return json.dumps({
        "dates": dates,
        "index_returns": index_returns,
        "start_returns": start_returns,
    }, ensure_ascii=False, allow_nan=False)


def _parse_returns_json(raw: Any) -> list[dict[str, Any]]:
    payload = _parse_json(raw, {})
    if not isinstance(payload, dict):
        return []
    dates = payload.get("dates") or []
    index_returns = payload.get("index_returns") or []
    start_returns = payload.get("start_returns") or []
    return [
        {
            "date": date,
            "index_return": index_returns[index] if index < len(index_returns) else None,
            "start_return": start_returns[index] if index < len(start_returns) else None,
        }
        for index, date in enumerate(dates)
    ]


def _get_return_date_for_task_result(task_result: TaskResult) -> list[dict[str, Any]]:
    if task_result.return_series_id:
        return_series = db.session.get(TaskResultReturn, task_result.return_series_id)
        if return_series:
            return _parse_returns_json(return_series.returns_json)
    return _extract_return_date_from_result_payload(_parse_json(task_result.result, {}))


def _return_date_by_date(return_date: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    rows: dict[str, dict[str, float]] = {}
    for item in return_date:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or item.get("stock_date") or "").strip()
        index_return = _safe_number(item.get("index_return"))
        start_return = _safe_number(item.get("start_return"))
        if not date or index_return is None or start_return is None:
            continue
        rows[date] = {
            "index_return": index_return,
            "start_return": start_return,
        }
    return rows


def _build_portfolio_return_date(
    product_results: dict[int, dict[str, Any]],
    products: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    product_return_maps: list[tuple[dict[str, dict[str, float]], Decimal]] = []
    common_dates: set[str] | None = None

    for product in products:
        product_index = int(product["product_index"])
        product_result = product_results.get(product_index) or {}
        return_map = _return_date_by_date(product_result.get("return_date") or [])
        if not return_map:
            return []
        common_dates = set(return_map) if common_dates is None else common_dates & set(return_map)
        product_return_maps.append((return_map, parse_ratio(product.get("ratio")) / RATIO_BASE))

    if not common_dates:
        return []

    return_date = []
    for date in sorted(common_dates):
        index_total = Decimal("0")
        start_total = Decimal("0")
        for return_map, ratio in product_return_maps:
            row = return_map[date]
            index_total += Decimal(str(row["index_return"])) * ratio
            start_total += Decimal(str(row["start_return"])) * ratio
        return_date.append({
            "date": date,
            "index_return": float(index_total),
            "start_return": float(start_total),
        })
    return return_date


def _build_portfolio_metrics(
    product_results: dict[int, dict[str, Any]],
    products: list[dict[str, Any]],
) -> dict[str, Any]:
    return_date = _build_portfolio_return_date(product_results, products)
    if not return_date:
        return {}
    calculate_metrics = xpl_analyzer.get_calculate_metrics_v1(return_date)
    return calculate_metrics if isinstance(calculate_metrics, dict) else {}


def _derive_metrics(calculate_metrics: dict[str, Any]) -> dict[str, Any]:
    excess_all = _all_entry(calculate_metrics.get("excess_returns"))
    index_profit_monthly_all = _all_entry(calculate_metrics.get("index_profit_monthly"))
    start_profit_monthly_all = _all_entry(calculate_metrics.get("start_profit_monthly"))
    monthly_excess_percentage_all = _all_entry(
        calculate_metrics.get("monthly_excess_return_percentage")
    )
    index_kama_all = _all_entry(calculate_metrics.get("index_kama_ratio"))
    start_kama_all = _all_entry(calculate_metrics.get("start_kama_ratio"))
    index_sotino_all = _all_entry(calculate_metrics.get("index_sotino_ratio"))
    start_sotino_all = _all_entry(calculate_metrics.get("start_sotino_ratio"))
    index_sharpe_all = (calculate_metrics.get("index_sharpe_ratios") or {}).get("all") or {}
    start_sharpe_all = (calculate_metrics.get("start_sharpe_ratios") or {}).get("all") or {}
    monthly_excess_returns = calculate_metrics.get("monthly_excess_returns") or []
    monthly_excess_values = [
        item.get("monthly_excess_return_diff")
        for item in monthly_excess_returns
        if isinstance(item, dict) and item.get("monthly_excess_return_diff") is not None
    ]
    avg_monthly_excess_return = (
        sum(monthly_excess_values) / len(monthly_excess_values)
        if monthly_excess_values
        else None
    )
    total_max_drawdown = (
        (calculate_metrics.get("start_maximum_drawdown") or {}).get("total_maximum_drawdown")
        or {}
    )
    return {
        "index_annualized_return": excess_all.get("index_annualized_return"),
        "start_annualized_return": excess_all.get("start_annualized_return"),
        "annualized_return_diff": excess_all.get("annualized_return_diff"),
        "index_profit_annual": calculate_metrics.get("index_profit_annual"),
        "start_profit_annual": calculate_metrics.get("start_profit_annual"),
        "index_profit_monthly_percentage": index_profit_monthly_all.get("profit_monthly_percentage"),
        "start_profit_monthly_percentage": start_profit_monthly_all.get("profit_monthly_percentage"),
        "index_avg_monthly_return": index_sharpe_all.get("avg_monthly_return"),
        "start_avg_monthly_return": start_sharpe_all.get("avg_monthly_return"),
        "index_monthly_return_volatility": calculate_metrics.get("index_monthly_return_volatility"),
        "start_monthly_return_volatility": calculate_metrics.get("start_monthly_return_volatility"),
        "outperform_year": calculate_metrics.get("outperform_year"),
        "monthly_excess_return_percentage": monthly_excess_percentage_all.get("excess_return"),
        "avg_monthly_excess_return": avg_monthly_excess_return,
        "monthly_excess_volatility": calculate_metrics.get("monthly_excess_volatility"),
        "year_max_excess_drawdown": calculate_metrics.get("max_drawdown"),
        "excess_drawdown_winning_rate": calculate_metrics.get("excess_drawdown_winning_rate"),
        "start_max_drawdown": total_max_drawdown.get("drawdown"),
        "start_maximum_number_of_backtest_repair_days": calculate_metrics.get("start_maximum_number_of_backtest_repair_days"),
        "excess_maximum_number_of_backtest_repair_days": calculate_metrics.get("excess_maximum_number_of_backtest_repair_days"),
        "index_sharpe_ratio": index_sharpe_all.get("sharpe_ratio"),
        "start_sharpe_ratio": start_sharpe_all.get("sharpe_ratio"),
        "index_kama_ratio": index_kama_all.get("kama_ratio"),
        "start_kama_ratio": start_kama_all.get("kama_ratio"),
        "index_sotino_ratio": index_sotino_all.get("sotino_ratio"),
        "start_sotino_ratio": start_sotino_all.get("sotino_ratio"),
        "excess_sharp": calculate_metrics.get("excess_sharp"),
        "excess_of_promissory_note": calculate_metrics.get("excess_of_promissory_note"),
    }


class BacktestMultiProductService(BacktestTrainingService):
    """Multi-product backtest service with independent product sheets."""

    @staticmethod
    def _build_kline_signature(kline: list[dict[str, Any]]) -> dict[str, Any]:
        if not kline:
            return {}
        middle_index = len(kline) // 2
        return {
            "length": len(kline),
            "first": kline[0],
            "middle": kline[middle_index],
            "last": kline[-1],
        }

    @staticmethod
    def _build_sheet_cache_key(product: dict[str, Any]) -> str:
        sheet = product.get("sheet") if isinstance(product.get("sheet"), dict) else {}
        spreadsheet_id = str(sheet.get("spreadsheet_id") or "").strip()
        sheet_name = str(sheet.get("sheet_name") or "").strip()
        return f"{spreadsheet_id}::{sheet_name}"

    def _task_detail_url(self) -> str:
        return f"{current_app.config.get('BASE_URL')}/backtest-multi-product/detail/{self.task_id}"

    def execute_task(self):
        try:
            context_app = self.app or current_app
            with context_app.app_context():
                task = db.session.get(Task, self.task_id)
                self.task = task
                if not task:
                    self._log_error(f"任务 {self.task_id} 不存在")
                    return "error"
                if task.status == "cancelled" or self._is_cancel_requested():
                    self._log_info(f"任务 {self.task_id} 已被取消，停止执行")
                    return "cancelled"

                raw_config = _parse_json(task.config, {})
                config_data = {
                    **get_config_manager().get_google_sheet_config(),
                    **normalize_multi_product_config(raw_config),
                }
                self.task_name = task.name
                result = self._execute_products(task, config_data)
                if result == "completed":
                    self.task_ok_to_dd("多品数据回测任务执行完成")
                return result
        except Exception as exc:
            root = unwrap_exception(exc) or exc
            if self.task:
                self.task.error_message = build_task_error_message(exc)
                db.session.commit()
            self._log_error(f"执行多品数据回测任务失败: {self.task_id}, 错误: {root}")
            return "error"

    def _execute_products(self, task: Task, config_data: dict[str, Any]) -> str:
        products = config_data["products"]
        parameter_count = len(products[0]["parameters"])
        total_steps = parameter_count * len(products)
        task.total_steps = total_steps
        db_retry_manager.commit_with_retry(db.session)
        self._log_info(f"将执行 {parameter_count} 个参数方案、{len(products)} 个产品，共 {total_steps} 步")

        start_index = self._resolve_resume_start_index(task)
        sheet_kline_cache: dict[str, dict[str, Any]] = {}
        kline_cache: dict[int, dict[str, Any]] = {}
        success_count = start_index
        failed_count = 0
        processed_index = 0

        for product in products:
            for group_index in range(parameter_count):
                if self._is_cancel_requested():
                    return "cancelled"
                if processed_index < start_index:
                    processed_index += 1
                    continue

                result = safe_db_operation(lambda: db.session.execute(
                    text("SELECT status FROM tasks WHERE id = :task_id"),
                    {"task_id": self.task_id},
                ).fetchone())
                if not result or result.status == "cancelled":
                    self._log_warning("任务已被取消，停止执行")
                    return "cancelled"

                current_step = processed_index + 1
                product_index = int(product["product_index"])
                sheet_cache_key = self._build_sheet_cache_key(product)
                parameter = product["parameters"][group_index]
                product_config = self._build_product_config(config_data, product)
                self._init_google_sheet(product_config)
                kline_info = kline_cache.get(product_index)
                if not kline_info:
                    kline_info = self._build_product_kline(product, config_data)
                    kline_cache[product_index] = kline_info

                combination = {
                    "parameter": parameter,
                    "stock_code": product["stock_code"],
                    "year": kline_info["kline_key"],
                    "Kline_key": kline_info["kline_key"],
                    "kline_signature": kline_info["kline_signature"],
                    "product_index": product_index,
                    "product_name": product["product_name"],
                    "ratio": product["ratio"],
                    "parameter_group_index": group_index,
                }
                self._log_step(
                    current_step,
                    total_steps,
                    f"执行方案 {group_index + 1} / 产品 {product['product_name']}",
                )
                task.current_step = current_step
                db_retry_manager.commit_with_retry(db.session)

                try:
                    success, result_payload, return_date = self._execute_parameter_combination(
                        kline_info["column_A_length"],
                        combination,
                        sheet_kline_cache.setdefault(sheet_cache_key, {"combination": {}}),
                        product_config,
                        {kline_info["kline_key"]: kline_info["kline"]},
                    )
                    if not success:
                        failed_count += 1
                        self._log_warning(f"第 {current_step} 步执行失败")
                        return "error"

                    kline = kline_info["kline"]
                    self._save_task_result(current_step - 1, {
                        **combination,
                        "kline": [kline[0], kline[-1]],
                        "start_date": config_data["start_date"],
                        "end_date": config_data["end_date"],
                        "sheet": product["sheet"],
                    }, result_payload, True, return_date=return_date)
                    sheet_kline_cache[sheet_cache_key]["combination"] = combination
                    success_count += 1
                    self._log_info(f"第 {current_step} 步执行成功")
                except Exception as exc:
                    self._raise_retryable_network_error(exc, f"第 {current_step} 步网络请求失败")
                    failed_count += 1
                    self._log_error(f"第 {current_step} 步执行出错: {traceback.format_exc()}")
                    return "error"
                processed_index += 1

        self._log_info(f"多品数据回测完成，总成功: {success_count}, 总失败: {failed_count}")
        return "completed" if success_count else "error"

    def _save_task_result(
        self,
        step_index: int,
        parameters,
        result: dict[str, Any],
        success: bool,
        *,
        return_date: list[dict[str, Any]] | None = None,
    ):
        def save_result_operation():
            safe_parameters = self._sanitize_json_value(parameters)
            safe_result = self._sanitize_json_value(result)
            task_result = TaskResult(
                task_id=self.task_id,
                step_index=step_index,
                parameters=json.dumps(safe_parameters, allow_nan=False),
                result=json.dumps(safe_result, allow_nan=False),
                success=success,
            )
            db.session.add(task_result)
            db.session.flush()
            if return_date:
                return_series = TaskResultReturn(
                    task_id=self.task_id,
                    returns_json=_build_returns_json(return_date),
                )
                db.session.add(return_series)
                db.session.flush()
                task_result.return_series_id = return_series.id

            db.session.commit()

        try:
            context_app = self.app or current_app
            with context_app.app_context():
                safe_db_operation(save_result_operation)
        except Exception as exc:
            self._log_error(f"保存多品任务结果失败: {exc}")

    def _build_product_config(self, config_data: dict[str, Any], product: dict[str, Any]) -> dict[str, Any]:
        product_config = dict(config_data)
        product_config.update({
            "sheet": product["sheet"],
            "spreadsheet_id": product["sheet"]["spreadsheet_id"],
            "sheet_name": product["sheet"]["sheet_name"],
            "title": product["sheet"].get("title") or "",
            "stock_code": product["stock_code"],
            "market_type": product["market_type"],
            "kline_adjustment": product.get("kline_adjustment", "forward"),
        })
        return product_config

    def _build_product_kline(self, product: dict[str, Any], config_data: dict[str, Any]) -> dict[str, Any]:
        kline = self._get_kline_by_date_range(
            product["stock_code"],
            product["market_type"],
            config_data["start_date"],
            config_data["end_date"],
            price_mode=product.get("price_mode") or config_data.get("price_mode", "sp_price"),
            adjust_type=product.get("kline_adjustment", "forward"),
        )
        kline_key = f"{config_data['start_date']}~{config_data['end_date']}"
        return {
            "kline_key": kline_key,
            "kline": kline,
            "kline_signature": self._build_kline_signature(kline),
            "column_A_length": len(kline) + 20,
        }

    def _is_same_kline_source(self, combination: dict[str, Any], cached_combination: dict[str, Any]) -> bool:
        if combination.get("Kline_key") != cached_combination.get("Kline_key"):
            return False
        if combination.get("stock_code") != cached_combination.get("stock_code"):
            return False
        if combination.get("kline_signature") != cached_combination.get("kline_signature"):
            return False
        return True

    def _execute_parameter_combination(
        self,
        column_A_length,
        combination,
        cache_parameters,
        config_data: dict[str, Any],
        KLINE_DATA_MAP,
    ) -> tuple[bool, dict[str, Any]]:
        cached_combination = cache_parameters.get("combination") or {}
        if cached_combination and not self._is_same_kline_source(combination, cached_combination):
            cache_parameters["combination"] = {}
        return super()._execute_parameter_combination(
            column_A_length,
            combination,
            cache_parameters,
            config_data,
            KLINE_DATA_MAP,
        )

    def _get_kline_by_date_range(
        self,
        stock_code: str,
        market_type: str,
        start_date: str,
        end_date: str,
        *,
        price_mode: str = "sp_price",
        adjust_type: str | None = None,
    ) -> list[dict[str, Any]]:
        price_field = "stock_kp" if price_mode == "kp_price" else "stock_sp"
        market_type = normalize_market_type(market_type)
        start_year = int(start_date[:4])
        end_year = int(end_date[:4])
        year_count = max(1, end_year - start_year + 1)
        limit = max(300, year_count * (250 if market_type == "cn" else 252) + 120)

        if market_type == "cn":
            resolved_code, market = self._resolve_cn_stock_quote(stock_code)
            klines = self.dfcf_api.get_stock_kline_data(resolved_code, market, limit, adjust_type=adjust_type)
        else:
            klines = self.YF_api.get_kline_data(stock_code, "10y", adjust_type=adjust_type)

        if not klines:
            raise ValueError(f"股票 {stock_code} 没有 K 线数据")
        data_start_date = klines[0]["stock_date"]
        data_end_date = klines[-1]["stock_date"]
        if start_date < data_start_date or end_date > data_end_date:
            raise ValueError(
                f"股票{stock_code} 设定区间 [{start_date}, {end_date}] "
                f"不在K线数据范围 [{data_start_date}, {data_end_date}] 内"
            )
        kline = [
            {"stock_date": item["stock_date"], "stock_val": item[price_field]}
            for item in klines
            if start_date <= item["stock_date"] <= end_date
        ]
        if len(kline) < 100:
            raise ValueError(f"股票{stock_code} 数据量不足，K线数据量小于100条")
        return kline


def build_multi_product_global_preview_payload(
    task_id: str,
    ratios_override: list[Any] | None = None,
) -> dict[str, Any] | None:
    task = db.session.get(Task, task_id)
    if not task or task.task_type != BACKTEST_MULTI_PRODUCT_TASK_TYPE:
        return None
    config = normalize_multi_product_config(task.to_dict().get("config") or {})
    products = config["products"]
    if ratios_override is not None:
        if len(ratios_override) != len(products):
            raise ValueError("比例数量与产品数量不一致")
        for product, ratio in zip(products, ratios_override):
            product["ratio"] = normalize_ratio_display(
                ratio.get("ratio") if isinstance(ratio, dict) else ratio
            )
    results = (
        TaskResult.query
        .filter_by(task_id=task_id)
        .order_by(TaskResult.step_index.asc(), TaskResult.timestamp.asc(), TaskResult.id.asc())
        .all()
    )
    groups: OrderedDict[str, dict[str, Any]] = OrderedDict()
    success_count = 0
    failed_count = 0

    for result in results:
        parameters = _parse_json(result.parameters, {})
        group_index = int(parameters.get("parameter_group_index") or 0)
        group_key = str(group_index)
        group = groups.setdefault(group_key, {
            "group_key": group_key,
            "group_label": f"参数方案 {group_index + 1}",
            "parameter_group_index": group_index,
            "products": products,
            "product_results": {},
            "failed_results": 0,
        })
        product_index = int(parameters.get("product_index") or 0)
        if not result.success:
            failed_count += 1
            group["failed_results"] += 1
            continue
        success_count += 1
        core = _extract_result_core(result)
        calculate_metrics = core.get("calculate_metrics") if isinstance(core, dict) else {}
        group["product_results"][product_index] = {
            "result_id": result.id,
            "step_index": result.step_index,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
            "parameters": parameters,
            "metrics": _derive_metrics(calculate_metrics if isinstance(calculate_metrics, dict) else {}),
            "return_date": _get_return_date_for_task_result(result),
        }

    serialized_groups = []
    for group in groups.values():
        portfolio_metrics = _derive_metrics(_build_portfolio_metrics(group["product_results"], products))
        rows = []
        for category, metric, index_key, result_key, value_type in SUMMARY_ROW_DEFS:
            product_values = []
            for product in products:
                product_index = int(product["product_index"])
                product_result = group["product_results"].get(product_index) or {}
                metrics = product_result.get("metrics") or {}
                index_value = metrics.get(index_key) if index_key else None
                result_value = metrics.get(result_key) if result_key else None
                product_values.append({
                    "product_index": product_index,
                    "index_value": _fmt_value(index_value, value_type) if index_key else "-",
                    "result_value": _fmt_value(result_value, value_type),
                    "weighted_result_value": _format_ratio_reference(product.get("ratio")),
                    "raw_index_value": index_value,
                    "raw_result_value": result_value,
                    "raw_weighted_index_value": _safe_number(product.get("ratio")),
                    "raw_weighted_result_value": _safe_number(product.get("ratio")),
                })
            weighted_index_value = portfolio_metrics.get(index_key) if index_key else None
            weighted_result_value = portfolio_metrics.get(result_key) if result_key else None
            rows.append({
                "category": category,
                "metric": metric,
                "value_type": value_type,
                "product_values": product_values,
                "weighted_index_value": (
                    _fmt_value(weighted_index_value, value_type)
                    if index_key and weighted_index_value is not None
                    else "-"
                ),
                "weighted_result_value": (
                    _fmt_value(weighted_result_value, value_type)
                    if weighted_result_value is not None
                    else "-"
                ),
                "raw_weighted_index_value": weighted_index_value,
                "raw_weighted_result_value": weighted_result_value,
            })
        serialized_groups.append({
            **{key: value for key, value in group.items() if key != "product_results"},
            "rows": rows,
            "result_count": len(group["product_results"]),
        })

    return {
        "task": {
            "id": task.id,
            "name": task.name,
            "status": task.status,
            "start_date": config["start_date"],
            "end_date": config["end_date"],
        },
        "summary": {
            "total_results": len(results),
            "success_results": success_count,
            "failed_results": failed_count,
            "group_count": len(serialized_groups),
            "product_count": len(products),
        },
        "products": products,
        "groups": serialized_groups,
    }

