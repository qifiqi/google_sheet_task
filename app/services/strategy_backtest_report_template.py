"""量化策略回测报告 DOCX 模板。

本模块只负责将已经计算好的数据排版成报告，不计算 index_return、
start_return 或任何指标。xpl 在完成计算后，按 ``build_demo_report_data``
返回的结构组装数据，并调用 ``generate_strategy_backtest_report`` 即可。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


logger = logging.getLogger(__name__)
# 报告结构、样式和校验规则均由该 JSON 配置；渲染器只负责通用解释。
DEFAULT_TEMPLATE_PATH = Path(__file__).with_name("report_templates") / "strategy_backtest_report.json"


def build_demo_report_data(report_type: str = "RPT") -> dict[str, Any]:
    """返回完整的假数据结构，供 xpl 侧实现时直接复制字段格式。

    约定：所有指标均应在 xpl 中计算并格式化为展示文本（例如 ``"30.16%"``），
    本模块不会对它们进行计算或格式化。
    """
    def table(columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
        return {"columns": columns, "rows": rows}

    if report_type not in {"RPT", "ZRPT"}:
        raise ValueError("report_type 仅支持 RPT 或 ZRPT")

    # 此对象是 xpl 侧需要构造的完整数据协议示例，数值均为展示用假数据。
    report_data = {"report_type": report_type, "title": "量化策略回测绩效分析报告", "metadata": {
        "report_id": f"{report_type}-20260821",
        "model_version": "C7.0.2",
        "price_type": "收盘价|OHLC",
        "generated_at": "2026年08月21日",
        "date_range": "2020-08-21 至 2026-08-20",
        "total_trading_days": "1506 天",
        "risk_free_rate": "0.00%",
    }, "sections": [
        {
            "title": "一、收益类指标",
            "subsections": [
                {"title": "1.1 核心收益", "table": table(
                    ["指标", "指数", "策略", "超额(策略-指数)"],
                    [["累计回报率", "128.99%", "383.00%", "254.01%"],
                     ["年化收益率", "14.89%", "30.16%", "15.27%"],
                     ["年化波动率", "15.16%", "17.56%", "11.54%"]])},
                {"title": "1.2 分年度收益率", "table": table(
                    ["年份", "指数", "策略", "超额(策略-指数)"],
                    [["2020", "16.03%", "12.42%", "-3.61%"],
                     ["2021", "31.74%", "67.34%", "35.60%"],
                     ["2022", "-3.23%", "5.09%", "8.32%"],
                     ["2023", "4.68%", "20.36%", "15.68%"],
                     ["2024", "10.85%", "10.97%", "0.12%"],
                     ["2025", "4.57%", "27.12%", "22.55%"],
                     ["2026", "27.68%", "40.44%", "12.76%"]])},
                {"title": "1.3 滚动收益（月度窗口）", "table": table(
                    ["滚动周期", "指数平均收益", "策略平均收益", "策略胜率(跑赢指数)"],
                    [["3个月滚动", "3.57%", "7.02%", "66.7%"],
                     ["6个月滚动", "6.73%", "14.34%", "66.7%"],
                     ["12个月滚动", "10.66%", "25.66%", "64.7%"]])},
            ],
        },
        {
            "title": "二、风险类指标",
            "subsections": [
                {"title": "2.1 回撤指标", "table": table(
                    ["指标", "指数", "策略"],
                    [["最大回撤(MDD)", "-16.84%", "-19.87%"],
                     ["回撤持续时间(平均/天)", "17.2", "7.7"],
                     ["最大回撤修复天数(年度最大)", "173", "201"],
                     ["回撤发生次数(单日>5%)", "469", "308"]])},
                {"title": "2.2 分年度最大回撤", "table": table(
                    ["年份", "指数回撤", "策略回撤", "超额回撤(策略-指数)"],
                    [["2020", "-7.65%", "-13.00%", "-5.34%"],
                     ["2021", "-4.99%", "-10.08%", "-5.10%"],
                     ["2022", "-16.84%", "-19.87%", "-3.03%"],
                     ["2023", "-11.96%", "-6.27%", "5.70%"],
                     ["2024", "-7.95%", "-13.87%", "-5.92%"],
                     ["2025", "-14.02%", "-7.78%", "6.24%"],
                     ["2026", "-4.61%", "-6.41%", "-1.79%"]])},
            ],
        },
        {
            "title": "三、风险调整收益指标",
            "subsections": [{"table": table(
                ["指标", "指数", "策略", "超额"],
                [["夏普比率", "0.98", "1.59", "—"],
                 ["卡玛比率", "0.88", "1.52", "—"],
                 ["索提诺比率", "2.12", "3.14", "—"],
                 ["超额夏普比率", "—", "—", "1.12"],
                 ["超额索提诺比率", "—", "—", "1.30"],
                 ["信息比率", "—", "—", "2.09"],
                 ["收益回撤比", "0.88", "1.52", "—"]])}],
        },
        {
            "title": "四、月度收益分布",
            "subsections": [
                {"title": "4.1 月度统计总览", "table": table(
                    ["指标", "指数", "策略"],
                    [["总月数", "72", "72"], ["盈利月数", "44", "50"],
                     ["亏损月数", "28", "22"], ["月盈利百分比", "61.11%", "69.44%"],
                     ["平均月收益率", "1.23%", "2.29%"], ["月收益率标准差", "4.38%", "5.07%"],
                     ["最大单月收益", "13.17%", "16.43%"], ["最大单月亏损", "-7.96%", "-12.44%"],
                     ["月收益率偏度", "0.17", "-0.39"], ["月收益率峰度", "-0.03", "1.45"]])},
                {"title": "4.2 月度收益区间分布", "table": table(
                    ["收益区间", "指数(月数/占比)", "策略(月数/占比)"],
                    [["< -5%", "4 / 5.6%", "5 / 6.9%"], ["-5%~-2%", "14 / 19.4%", "5 / 6.9%"],
                     ["-2%~0%", "9 / 12.5%", "12 / 16.7%"], ["0%~2%", "12 / 16.7%", "7 / 9.7%"],
                     ["2%~5%", "19 / 26.4%", "25 / 34.7%"], ["5%~10%", "12 / 16.7%", "15 / 20.8%"],
                     [">10%", "2 / 2.8%", "3 / 4.2%"]])},
            ],
        },
        {
            "title": "五、日度收益分布",
            "subsections": [
                {"title": "5.1 日度统计总览", "table": table(
                    ["指标", "指数", "策略"],
                    [["总交易日", "1506", "1506"], ["盈利天数", "797", "809"],
                     ["亏损天数", "709", "697"], ["日盈利百分比", "52.92%", "53.72%"],
                     ["日均收益率", "0.059%", "0.112%"], ["日收益率标准差", "0.93%", "1.19%"],
                     ["最大单日收益", "6.38%", "9.07%"], ["最大单日亏损", "-5.42%", "-9.01%"],
                     ["日收益率偏度", "0.05", "-0.10"], ["日收益率峰度", "3.39", "9.11"]])},
                {"title": "5.2 盈亏比分析", "table": table(
                    ["指标", "指数", "策略"],
                    [["平均盈利日收益", "0.71%", "0.79%"], ["平均亏损日收益", "-0.69%", "-0.69%"],
                     ["盈亏比(平均盈利/平均亏损)", "1.04", "1.14"], ["单笔最大盈利/最大亏损", "1.18", "1.01"]])},
                {"title": "5.3 日度收益区间分布", "table": table(
                    ["收益区间", "指数(天数/占比)", "策略(天数/占比)"],
                    [["<-2%", "27 / 1.8%", "52 / 3.5%"], ["-2%~-1%", "129 / 8.6%", "80 / 5.3%"],
                     ["-1%~-0.2%", "408 / 27.1%", "310 / 20.6%"], ["-0.2%~0.2%", "302 / 20.1%", "532 / 35.3%"],
                     ["0.2%~1%", "446 / 29.6%", "302 / 20.1%"], ["1%~2%", "162 / 10.8%", "158 / 10.5%"],
                     [">2%", "32 / 2.1%", "72 / 4.8%"]])},
            ],
        },
        {
            "title": "六、超额收益分析",
            "subsections": [
                {"title": "6.1 超额收益统计", "table": table(
                    ["指标", "数值"],
                    [["累计超额(策略-指数)", "254.01%"], ["年化超额", "15.27%"],
                     ["月超额收益均值", "1.06%"], ["月超额收益中位数", "1.48%"],
                     ["月超额收益标准差", "3.33%"], ["月超额胜率(>0)", "66.67%"],
                     ["最大单月超额", "11.59%"]])},
                {"title": "6.2 超额收益区间分布", "table": table(
                    ["超额区间", "月数/占比"],
                    [["<-2%", "8 / 11.1%"], ["-2%~0%", "16 / 22.2%"], ["0%~2%", "15 / 20.8%"],
                     ["2%~5%", "28 / 38.9%"], [">5%", "5 / 6.9%"]])},
                {"title": "6.3 滚动超额胜率", "table": table(
                    ["滚动窗口", "平均超额", "正超额概率"],
                    [["1个月", "1.06%", "66.7%"], ["3个月", "7.02%", "66.7%"],
                     ["6个月", "14.34%", "66.7%"], ["12个月", "25.66%", "64.7%"]])},
            ],
        },
        {
            "title": "七、极端行情表现",
            "subsections": [
                {"title": "7.1 市场下跌阶段（指数月收益 < -2%）", "table": table(
                    ["指标", "指数", "策略", "超额"],
                    [["下跌月数", "18", "18", "—"], ["平均收益", "-4.19%", "-2.61%", "1.58%"],
                     ["中位收益", "-3.75%", "-1.81%", "2.22%"], ["策略跑赢次数", "—", "11", "61.1%"]])},
                {"title": "7.2 市场上涨阶段（指数月收益 > +2%）", "table": table(
                    ["指标", "指数", "策略", "超额"],
                    [["上涨月数", "33", "33", "—"], ["平均收益", "5.03%", "5.77%", "0.73%"],
                     ["中位收益", "4.53%", "5.13%", "0.78%"], ["策略跑赢次数", "—", "22", "66.7%"]])},
                {"title": "7.3 极端单日表现", "table": table(
                    ["指标", "指数", "策略"],
                    [["最大单日涨幅", "6.38%", "9.07%"], ["最大单日跌幅", "-5.42%", "-9.01%"],
                     ["涨幅>2%的天数", "32", "72"], ["跌幅>2%的天数", "27", "52"],
                     ["涨跌比(涨>2%/跌>2%)", "1.19", "1.38"]])},
            ],
        },
        {
            "title": "八、资金曲线特征",
            "subsections": [{"table": table(
                ["指标", "指数", "策略"],
                [["初始净值", "1.0000", "1.0000"], ["期末净值", "2.2899", "4.8300"],
                 ["净值创新高次数", "148", "297"], ["净值创新高频率", "9.8%", "19.7%"],
                 ["最大涨幅区间(连续)", "8.3%", "9.5%"], ["最大跌幅区间(连续)", "-13.0%", "-16.3%"],
                 ["创新高平均间隔(天)", "10.2", "5.1"]])}],
        },
    ], "charts": [
        {"title": "累计净值曲线", "image_path": "downloads\\策略回测报告图表\\累计净值曲线.png",
         "caption": "传入累计净值曲线 PNG 文件路径。"},
        {"title": "最大回撤曲线", "image_path": "downloads\\策略回测报告图表\\最大回撤曲线.png",
         "caption": "传入最大回撤曲线 PNG 文件路径。"},
        {"title": "超额收益曲线", "image_path": "downloads\\策略回测报告图表\\超额收益曲线.png",
         "caption": "传入累计超额收益曲线 PNG 文件路径。"},
        {"title": "分年度收益", "image_path": "downloads\\策略回测报告图表\\分年度收益.png",
         "caption": "传入分年度收益柱状图 PNG 文件路径。"},
        {"title": "日收益分布", "image_path": "downloads\\策略回测报告图表\\日收益分布.png",
         "caption": "传入日收益分布图 PNG 文件路径。"},
        {"title": "月度超额分布", "image_path": "downloads\\策略回测报告图表\\月度超额分布.png",
         "caption": "传入月度超额分布图 PNG 文件路径。"},
    ], "calculation_notes": [
        #     ("10.1 收益类指标", [
        #         "累计回报率：策略/指数在整个回测期间的总回报。",
        #         "年化收益率：将累计回报率按总交易日年化。",
        #         "年化波动率：使用月收益率标准差年化。",
        #         "分年度收益率：使用年末净值与年初净值计算。",
        #     ]),
        #     ("10.2 风险类指标", [
        #         "最大回撤(MDD)：从净值峰值到后续最低点的最大亏损幅度。",
        #         "回撤持续时间：净值低于历史前高的持续交易日。",
        #         "最大回撤修复天数：从回撤低点恢复至前高所需交易日。",
        #     ]),
        #     ("10.3 风险调整收益指标", [
        #         "夏普比率：单位总风险获得的超额收益。",
        #         "卡玛比率：年化收益率与最大回撤绝对值之比。",
        #         "索提诺比率：仅考虑下行风险的风险调整收益指标。",
        #     ]),
        #     ("10.4 月度与日度统计", [
        #         "月收益率：本月最后净值 / 上月最后净值 - 1。",
        #         "日收益率：当日净值 / 前日净值 - 1。",
        #         "盈亏比：平均盈利日收益率与平均亏损日收益率绝对值之比。",
        #     ]),
        #     ("10.5 超额收益分析", [
        #         "月超额收益：策略月收益率 - 指数月收益率。",
        #         "滚动超额胜率：指定滚动窗口内策略跑赢指数的月数占比。",
        #     ]),
        #     ("10.6 极端行情与资金曲线", [
        #         "下跌/上涨阶段：指数月收益率 < -2% 或 > +2%。",
        #         "净值创新高：当日净值超过此前所有历史前高。",
        #     ]),
    ], "conclusion": [
        "本策略在 2020年08月 至 2026年08月 的考察期内，累计回报率达 383.00%，年化收益率 30.16%，实现年化超额收益 15.27%。",
        "策略最大回撤为 -19.87%，夏普比率 1.72，卡玛比率 1.52，索提诺比率 1.76。",
    ], "weight_allocation": table(
        ["股票代码", "股票名", "权重"],
        [["600519", "贵州茅台", "100.00%"]] if report_type == "RPT" else [
            ["600519", "贵州茅台", "35.00%"],
            ["000858", "五粮液", "30.00%"],
            ["300750", "宁德时代", "35.00%"],
        ],
    )}
    # RPT 是单产品；ZRPT 默认提供多产品样例，业务侧可替换为实际权重。
    return report_data


def generate_strategy_backtest_report(
    report_data: dict[str, Any],
    output_path: str | Path,
    template_path: str | Path = DEFAULT_TEMPLATE_PATH,
) -> Path:
    """按 JSON 模板和已计算的数据生成 DOCX 报告。"""
    # 模板决定“渲染什么”，report_data 仅提供“渲染的数据”。
    template = _load_template(template_path)
    _validate_report_data(report_data, template)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = Document()
    _configure_document(document, template["styles"], report_data)
    _render_blocks(document, report_data, template, template["blocks"])

    document.save(output_path)
    logger.info("已生成策略回测报告: %s", output_path)
    return output_path


def _load_template(template_path: str | Path) -> dict[str, Any]:
    path = Path(template_path)
    if not path.is_file():
        raise ValueError(f"报告 JSON 模板不存在: {path}")
    try:
        with path.open(encoding="utf-8") as template_file:
            return json.load(template_file)
    except json.JSONDecodeError as error:
        raise ValueError(f"报告 JSON 模板格式无效: {path}") from error


def _validate_report_data(report_data: dict[str, Any], template: dict[str, Any]) -> None:
    validation = template["validation"]
    required_keys = set(validation["required_fields"])
    missing_keys = required_keys - report_data.keys()
    if missing_keys:
        raise ValueError(f"report_data 缺少字段: {', '.join(sorted(missing_keys))}")

    if report_data["report_type"] not in set(validation["report_types"]):
        raise ValueError(f"report_type 仅支持 {'、'.join(validation['report_types'])}")

    metadata_keys = set(validation["required_metadata_fields"])
    missing_metadata = metadata_keys - report_data["metadata"].keys()
    if missing_metadata:
        raise ValueError(f"metadata 缺少字段: {', '.join(sorted(missing_metadata))}")

    # 条件校验（例如 RPT 单产品、ZRPT 多产品）由 JSON 配置驱动。
    for condition in validation.get("conditions", []):
        if _resolve_value(report_data, condition["field"]) != condition["equals"]:
            continue
        for field in condition.get("required_fields", []):
            if not _resolve_optional_value(report_data, field):
                raise ValueError(f"{report_data['report_type']} 报告必须传入 {field}")
        for field in condition.get("forbidden_fields", []):
            if _resolve_optional_value(report_data, field):
                raise ValueError(f"{report_data['report_type']} 报告不应传入 {field}")
        row_count_rule = condition.get("table_row_count")
        if row_count_rule:
            table_data = _resolve_value(report_data, row_count_rule["field"])
            if len(table_data.get("rows", [])) != row_count_rule["equals"]:
                raise ValueError(
                    f"{report_data['report_type']} 报告的 {row_count_rule['field']} "
                    f"必须包含 {row_count_rule['equals']} 行"
                )

    weight_allocation = report_data.get("weight_allocation")
    if weight_allocation:
        _validate_table_data(weight_allocation, "weight_allocation")

    for section in report_data["sections"]:
        if not section.get("title") or not section.get("subsections"):
            raise ValueError("每个 section 必须包含 title 和非空的 subsections")
        for subsection in section["subsections"]:
            table = subsection.get("table")
            _validate_table_data(table, subsection.get("title", section["title"]))


def _validate_table_data(table_data: dict[str, Any] | None, table_name: str) -> None:
    if not table_data or not table_data.get("columns"):
        raise ValueError(f"{table_name} 必须包含 table.columns")
    column_count = len(table_data["columns"])
    if any(len(row) != column_count for row in table_data.get("rows", [])):
        raise ValueError(f"表格列数不一致: {table_name}")


def _render_blocks(
    document: Document,
    report_data: dict[str, Any],
    template: dict[str, Any],
    blocks: list[dict[str, Any]],
) -> None:
    for block in blocks:
        block_type = block["type"]
        # 每一种 block 都对应 JSON 中的一种声明式报告组件。
        if block_type == "conditional":
            condition = block["when"]
            if _resolve_value(report_data, condition["field"]) == condition["equals"]:
                _render_blocks(document, report_data, template, block["blocks"])
        elif block_type == "title":
            title = document.add_paragraph(style="Title")
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER
            title.add_run(str(_resolve_value(report_data, block["source"])))
        elif block_type == "metadata":
            _add_metadata(document, report_data, template)
        elif block_type == "heading":
            document.add_heading(block["text"], level=block["level"])
        elif block_type == "text":
            document.add_paragraph(block["text"])
        elif block_type == "table":
            _add_table(
                document,
                _resolve_value(report_data, block["source"]),
                template["styles"]["table"],
                header_fill=block.get("header_fill", True),
            )
        elif block_type == "sections":
            for section in _resolve_value(report_data, block["source"]):
                document.add_heading(section["title"], level=1)
                for subsection in section["subsections"]:
                    if subsection.get("title"):
                        document.add_heading(subsection["title"], level=2)
                    _add_table(document, subsection["table"], template["styles"]["table"])
        elif block_type == "charts":
            for chart in _resolve_value(report_data, block["source"]):
                document.add_heading(chart["title"], level=2)
                _add_chart(document, chart, template["styles"]["chart"])
        elif block_type == "notes":
            for title, notes in _resolve_value(report_data, block["source"]):
                document.add_heading(title, level=2)
                for note in notes:
                    document.add_paragraph(note)
        elif block_type == "paragraphs":
            for paragraph in _resolve_value(report_data, block["source"]):
                document.add_paragraph(paragraph)
        else:
            raise ValueError(f"不支持的报告 JSON 区块类型: {block_type}")


def _resolve_value(data: dict[str, Any], source: str) -> Any:
    value: Any = data
    # 支持 metadata.report_id 这类点路径，避免将字段位置固化在 Python 中。
    for key in source.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"report_data 缺少 JSON 模板需要的字段: {source}")
        value = value[key]
    return value


def _resolve_optional_value(data: dict[str, Any], source: str) -> Any:
    try:
        return _resolve_value(data, source)
    except ValueError:
        return None


def _configure_document(document: Document, styles: dict[str, Any], report_data: dict[str, Any]) -> None:
    document_style = styles["document"]
    section = document.sections[0]
    section.page_width = Inches(document_style["page_width_inches"])
    section.page_height = Inches(document_style["page_height_inches"])
    margins = document_style["margins_inches"]
    section.left_margin = Inches(margins["left"])
    section.right_margin = Inches(margins["right"])
    section.top_margin = Inches(margins["top"])
    section.bottom_margin = Inches(margins["bottom"])

    normal = document.styles["Normal"]
    normal.font.name = document_style["font_name"]
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), document_style["font_name"])
    normal.font.size = Pt(document_style["normal_font_size"])
    normal.paragraph_format.space_after = Pt(document_style["normal_space_after_pt"])
    normal.paragraph_format.line_spacing = document_style["normal_line_spacing"]

    # 标题样式与“标题不单独留在页尾”的规则均从 JSON 读取。
    for style_name, style_config in styles["headings"].items():
        style = document.styles[style_name]
        style.font.name = document_style["font_name"]
        style._element.rPr.rFonts.set(qn("w:eastAsia"), document_style["font_name"])
        style.font.size = Pt(style_config["font_size"])
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(style_config["color"])
        style.paragraph_format.space_before = Pt(style_config["space_before_pt"])
        style.paragraph_format.space_after = Pt(style_config["space_after_pt"])
        style.paragraph_format.keep_with_next = style_config.get("keep_with_next", False)

    footer = section.footer.paragraphs[0]
    footer_style = styles["footer"]
    footer.alignment = _alignment(footer_style["alignment"])
    footer_run = footer.add_run(footer_style["text"].format(**report_data))
    footer_run.font.name = document_style["font_name"]
    footer_run._element.rPr.rFonts.set(qn("w:eastAsia"), document_style["font_name"])
    footer_run.font.size = Pt(footer_style["font_size"])
    footer_run.font.color.rgb = RGBColor.from_string(footer_style["color"])


def _add_metadata(document: Document, report_data: dict[str, Any], template: dict[str, Any]) -> None:
    metadata_style = template["styles"]["metadata"]
    for field in template["metadata_fields"]:
        paragraph = document.add_paragraph()
        paragraph.alignment = _alignment(metadata_style["alignment"])
        paragraph.add_run(f"{field['label']}：{_resolve_value(report_data, field['source'])}")


def _add_table(
    document: Document,
    table_data: dict[str, Any],
    table_style: dict[str, Any],
    header_fill: bool = True,
) -> None:
    table = document.add_table(rows=1, cols=len(table_data["columns"]))
    table.style = table_style["style"]
    table.autofit = True
    # Word 需要在 OOXML 中显式标记，才能在表格跨页时重复第一行表头。
    if table_style.get("repeat_header_row", False):
        _set_row_repeat_as_header(table.rows[0])
    # 防止同一数据行内容被拆到两页；长表仍可在行与行之间分页。
    if not table_style.get("allow_row_break_across_pages", True):
        for row in table.rows:
            _set_row_cant_split(row)
    header_cells = table.rows[0].cells
    for cell, value in zip(header_cells, table_data["columns"]):
        _set_cell_text(
            cell,
            str(value),
            table_style,
            bold=True,
            color=table_style["header_font_color"] if header_fill else None,
        )
        if header_fill:
            _set_cell_shading(cell, table_style["header_fill"])

    for row_index, values in enumerate(table_data.get("rows", [])):
        cells = table.add_row().cells
        if not table_style.get("allow_row_break_across_pages", True):
            _set_row_cant_split(table.rows[-1])
        for cell, value in zip(cells, values):
            _set_cell_text(cell, str(value), table_style)
            if row_index % 2:
                _set_cell_shading(cell, table_style["alternate_fill"])

    document.add_paragraph()


def _set_cell_text(
    cell: Any,
    text: str,
    table_style: dict[str, Any],
    bold: bool = False,
    color: str | None = None,
) -> None:
    paragraph = cell.paragraphs[0]
    paragraph.alignment = _alignment(table_style["alignment"])
    run = paragraph.add_run(text)
    run.bold = bold
    run.font.name = table_style["font_name"]
    run._element.rPr.rFonts.set(qn("w:eastAsia"), table_style["font_name"])
    run.font.size = Pt(table_style["font_size"])
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _set_cell_shading(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _set_row_repeat_as_header(row: Any) -> None:
    """标记首行为 Word 跨页表格的重复表头。"""
    properties = row._tr.get_or_add_trPr()
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    properties.append(repeat_header)


def _set_row_cant_split(row: Any) -> None:
    """保持单个表格行完整，避免一行内容被断在两页。"""
    properties = row._tr.get_or_add_trPr()
    properties.append(OxmlElement("w:cantSplit"))


def _add_chart(document: Document, chart: dict[str, Any], chart_style: dict[str, Any]) -> None:
    image_path = chart.get("image_path")
    if image_path:
        path = Path(image_path)
        if not path.is_file():
            raise ValueError(f"图表文件不存在: {path}")
        document.add_picture(str(path), width=Inches(chart_style["width_inches"]))
        document.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        placeholder = document.add_paragraph("【图表待传入】")
        placeholder.alignment = WD_ALIGN_PARAGRAPH.CENTER
        placeholder.runs[0].font.color.rgb = RGBColor(128, 128, 128)

    if chart.get("caption"):
        caption = document.add_paragraph(chart["caption"])
        caption.alignment = _alignment(chart_style["caption_alignment"])
        caption.runs[0].italic = True
        caption.runs[0].font.size = Pt(chart_style["caption_font_size"])


def _alignment(value: str) -> WD_ALIGN_PARAGRAPH:
    alignments = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
    }
    if value not in alignments:
        raise ValueError(f"不支持的文本对齐方式: {value}")
    return alignments[value]


def _main() -> None:
    parser = argparse.ArgumentParser(description="生成量化策略回测报告 DOCX 模板示例")
    parser.add_argument(
        "--output",
        default="downloads/策略回测报告模板示例.docx",
        help="输出 DOCX 路径",
    )
    args = parser.parse_args()
    generate_strategy_backtest_report(build_demo_report_data(), args.output)


if __name__ == "__main__":
    _main()
