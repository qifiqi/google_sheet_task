import re

from flask import Blueprint, current_app, jsonify, render_template, request

from app.utils.auth import login_required
from app.utils.dfcf_api import DFCJStockApi


eastmoney_kline_bp = Blueprint("eastmoney_kline", __name__)

_KLINE_TYPES = {"1", "5", "15", "30", "60", "101", "102", "103"}
_SECID_PATTERN = re.compile(r"^(?P<market>\d{1,3})\.(?P<code>[A-Za-z0-9._-]{1,20})$")


@eastmoney_kline_bp.route("/eastmoney-kline")
def index():
    return render_template("eastmoney_kline/index.html")


@eastmoney_kline_bp.route("/eastmoney-kline/api/klines", methods=["GET"])
@login_required
def get_klines():
    secid = (request.args.get("secid") or "").strip()
    match = _SECID_PATTERN.fullmatch(secid)
    if not match:
        return jsonify({"status": "error", "message": "证券标识格式无效"}), 400

    kline_type = (request.args.get("klt") or "101").strip()
    if kline_type not in _KLINE_TYPES:
        return jsonify({"status": "error", "message": "K线周期无效"}), 400

    try:
        limit = int(request.args.get("lmt") or 2000)
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "获取条数无效"}), 400
    if not 2 <= limit <= 10000:
        return jsonify({"status": "error", "message": "获取条数应为 2 至 10000 的整数"}), 400

    adjustment = (request.args.get("fqt") or "1").strip()
    if adjustment not in {"0", "1", "2"}:
        return jsonify({"status": "error", "message": "复权方式无效"}), 400

    try:
        rows = DFCJStockApi().get_stock_kline_data(
            match.group("code"),
            match.group("market"),
            limit,
            kline_type=kline_type,
            adjust_type=adjustment,
        )
        klines = [_serialize_kline(row, match.group("code")) for row in rows]
    except Exception:
        current_app.logger.exception("东方财富 K 线代理请求失败: secid=%s", secid)
        return jsonify({"status": "error", "message": "东方财富 K 线请求失败"}), 502

    if not klines:
        return jsonify({"status": "error", "message": "东方财富未返回有效K线数据"}), 502

    return jsonify({
        "status": "success",
        "data": {"klines": klines},
    })


def _serialize_kline(row, stock_code):
    volume = float(row["stock_cjl"])
    if str(stock_code).isdigit():
        volume /= 100
    fields = [
        row["stock_date"],
        row["stock_kp"],
        row["stock_sp"],
        row["stock_zg"],
        row["stock_zd"],
        volume,
        row["stock_cje"],
        row["stock_zf"],
        row["stock_zdf"],
        row["stock_zde"],
        row["stock_hsl"],
    ]
    return ",".join(str(value) for value in fields)
