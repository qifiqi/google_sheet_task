from pathlib import Path

from app.services.strategy_backtest_report_service import strategy_backtest_report_service
from d import data

import pandas as pd
import json
from app.services.xpl_service import xpl_analyzer

parsed_data = xpl_analyzer._parse_input_data(data)


filename, buffer = strategy_backtest_report_service.generate_word({
    "report_type": "RPT-S",
    "returns": parsed_data,
    "filename": "单产品回测报告.docx",
    "metadata": {
        "model_version": "v2",
        "price_type": "收盘价",
    },
})

Path(filename).write_bytes(buffer.getvalue())