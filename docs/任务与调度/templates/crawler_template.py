"""独立爬虫模板。

本地运行：
    python crawler_template.py --config-file config.json

平台运行：
    worker 通过 importlib 加载本文件，并调用 run(config, context)。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)


class CrawlerError(Exception):
    """可被平台识别的业务异常。"""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _get_logger(context: Any) -> logging.Logger:
    """本地运行使用模块 logger，平台运行使用任务 logger。"""
    return getattr(context, "logger", logger)


def crawl_symbol(symbol: str, context: Any = None) -> dict[str, Any]:
    """抓取单个标的；在此替换为真实网络请求、解析和入库逻辑。"""
    task_logger = _get_logger(context)
    normalized_symbol = str(symbol or "").strip()
    if not normalized_symbol:
        raise CrawlerError("INVALID_SYMBOL", "股票代码不能为空")

    task_logger.info("开始抓取股票代码: %s", normalized_symbol)

    # TODO: 在这里实现真实爬取。
    # 网络超时时可使用：
    # raise CrawlerError("UPSTREAM_TIMEOUT", "上游行情服务请求超时", retryable=True)

    return {"symbol": normalized_symbol, "status": "success"}


def run(config: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """平台约定入口：成功返回 JSON 可序列化结果，失败直接抛出异常。"""
    symbols = config.get("symbols")
    if not isinstance(symbols, list) or not symbols:
        raise CrawlerError("INVALID_CONFIG", "config.symbols 必须是非空数组")

    results = [crawl_symbol(symbol, context) for symbol in symbols]
    _get_logger(context).info("爬虫执行完成，成功处理 %s 个标的", len(results))
    return {"processed_count": len(results), "results": results}


def _load_local_config(config_file: str) -> dict[str, Any]:
    """读取本地测试配置。"""
    path = Path(config_file)
    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if not isinstance(config, dict):
        raise CrawlerError("INVALID_CONFIG", "配置文件根节点必须是 JSON 对象")
    return config


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="独立爬虫模板本地运行入口")
    parser.add_argument("--config-file", required=True, help="UTF-8 编码的 JSON 配置文件")
    args = parser.parse_args()

    try:
        output = run(_load_local_config(args.config_file))
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except CrawlerError as exc:
        logger.error("爬虫失败: code=%s retryable=%s message=%s", exc.code, exc.retryable, exc)
        raise SystemExit(1) from exc
