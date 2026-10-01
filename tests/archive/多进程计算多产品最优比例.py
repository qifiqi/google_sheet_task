import csv
import json
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from itertools import product

from tqdm import tqdm

from app.services.performance_analysis.analyzer import performance_analyzer
from app.services.performance_analysis.portfolio_combiner import combine_product_returns


# ==================== 子进程全局 ====================
_WC = {}


def _wc_init(products):
    _WC["products"] = products


def _wc_worker(weights):
    """子进程：算一个权重组合，返回 (data, md_start, ar_start, weights) 或 None。"""
    products = _WC["products"]

    if not any(weights):
        return None

    active_products = [p for p, w in zip(products, weights) if w]
    active_weights = [w for w in weights if w]

    returns = combine_product_returns(active_products, weights=active_weights)
    if len(returns) < 2:
        return None

    metrics = performance_analyzer._weight_combination_v1(returns)
    index_annualized_rates = metrics["index_annualized_rates"]
    start_annualized_rates = metrics["start_annualized_rates"]
    index_maximum_drawdown = metrics["index_maximum_drawdown"]
    start_maximum_drawdown = metrics["start_maximum_drawdown"]

    annualized_rates_start = start_annualized_rates[0].get("annualized_return")
    maximum_drawdown_start = (
        start_maximum_drawdown.get("total_maximum_drawdown", {}).get("drawdown")
    )

    data = {
        "annualized_rates": {
            "index": index_annualized_rates[0].get("annualized_return"),
            "start": annualized_rates_start,
        },
        "year_max_drawdown": {
            "index": index_maximum_drawdown.get("total_maximum_drawdown", {}).get("drawdown"),
            "start": maximum_drawdown_start,
        },
        "stocks": [
            {
                "result_id": p["result_id"],
                "stock_code": p["stock_code"],
                "stock_name": p["stock_name"],
                "ratio": w,
            }
            for p, w in zip(products, weights)
        ],
    }
    return data, maximum_drawdown_start, annualized_rates_start, weights


# ==================== 主逻辑 ====================
def weight_combination():
    """每只股票权重 0~30、步长 5，总和 ≤ 100，笛卡尔积枚举 + 多进程并发。"""
    products = json.loads(open("c7.0.3.json", "r").read())

    step = 5                 # 权重步长，单位 %
    single_cap = 30          # 单只股票权重上限
    max_weight = 100         # 总权重上限
    n = len(products)        # 股票数量

    # 每只股票的候选权重
    choices = list(range(0, single_cap + step, step))   # [0,5,10,15,20,25,30]

    # 笛卡尔积 + 过滤总和 ≤ 100 + 过滤全 0
    all_weights = [
        w for w in product(choices, repeat=n)
        if 0 < sum(w) <= max_weight
    ]
    print(f"股票数: {n}, 候选权重: {choices}")
    print(f"合法组合数: {len(all_weights)}")

    datas = [["权重", "权重和", "是否选中", "最大回撤", "年化收益率"]]

    n_proc = max(1, (mp.cpu_count() or 4) - 1)
    ctx = mp.get_context("spawn")

    with ProcessPoolExecutor(
        max_workers=n_proc,
        initializer=_wc_init,
        initargs=(products,),
        mp_context=ctx,
    ) as ex:
        it = ex.map(_wc_worker, all_weights, chunksize=32)

        for r in tqdm(it, total=len(all_weights)):
            if r is None:
                continue

            data, md_start, ar_start, weights = r
            weight_sum = sum(weights)

            # 选中条件：最大回撤 < 10% 且 年化 > 20%
            selected = (md_start * 100 < 10) and (ar_start * 100 > 20)

            datas.append([
                "|".join(f"{i['stock_code']}:{i['ratio']}" for i in data["stocks"]),
                weight_sum,
                1 if selected else 0,
                round(md_start * 100, 2),
                round(ar_start * 100, 2),
            ])

            if selected:
                print("|".join(f"{i['stock_code']}:{i['ratio']}" for i in data["stocks"]))

    with open("c7.0.3.csv", "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(datas)

    print(f"结果已写入 aaa.csv，共 {len(datas) - 1} 条")


if __name__ == "__main__":
    weight_combination()