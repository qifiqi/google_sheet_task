# -*- coding: utf-8 -*-
"""批量注册老路由表（DEFAULT_NAVIGATION_MENU）到远程 SysModel/ModifyOrAdd"""
import requests

URL = "https://stockapi.stplan.cn/api/SysModel/ModifyOrAdd"

HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6ImZ1cWluZyIsInVzZXJpZCI6IjI4MDU2NiIsIm5iZiI6MTc4ODg2OTM0NiwiZXhwIjoxNzg5NDc0MTQ2LCJpc3MiOiJEYXRhIiwiYXVkIjoiQWxsIn0.QIbcA7Q92q1WObh8FTELWhYPyYjBMIh7MO955bSzPrc",
    "User-Id": "280566",
    "User-Name": "fuqing",
    "Model-Code": "ModelManage",
    "Current-IP": "8.219.233.41",
    "Origin": "http://172.18.20.14:5500",
    "Referer": "http://172.18.20.14:5500/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
}

# (model_name, model_link)，来自 app/navigation.py 的 DEFAULT_NAVIGATION_MENU
ITEMS = [
    # ("任务管理", "tasks","/admin/tasks"),
    # ("任务模板", "templates","/admin/templates"),
    # ("任务结果","results", "/admin/results"),
    # ("单模型汇总", "model_summary","/admin/model-summary"),
    # ("东方财富 K 线", "eastmoney_kline","/admin/eastmoney-kline"),
    # ("单品全局预览", "/global-preview/single_product"),
    # ("定时任务", "scheduler","/admin/scheduler"),
    # ("系统配置","config", "/admin/config"),
    # ("Google Sheet 管理","sheets", "/admin/google-sheets"),
    # ("路由表管理", "/admin/navigation"),
    # ("系统日志", "/admin/logs"),
    # ("用户管理", "/admin/users"),
    # ("角色管理", "/admin/roles"),
    ("Google Sheet C3","c3", "/google-sheet/?version=c3"),
    ("Google Sheet C4","c4", "/google-sheet/?version=c4"),
    ("Google Sheet C5","c5", "/google-sheet/?version=c5"),
    ("Google Sheet C7","c7", "/google-sheet/?version=c7"),
    ("单品数据回测","backtest_single_product", "/backtest-training/list"),
    ("多品数据回测","backtest_multi_product", "/backtest-multi-product/list"),
    # ("夏普率计算", "/xpl"),
    ("V2 回测数据分析","backtest_v2", "/xpl/v2"),
]


# DEFAULT_NAVIGATION_MENU = [
#     {"key": "task", "label": "任务模块", "children": [
#         {"key": "tasks", "label": "任务管理", "path": "/admin/tasks", "permission": "page:admin:tasks"},
#         {"key": "templates", "label": "任务模板", "path": "/admin/templates", "permission": "page:admin:templates"},
#         {"key": "results", "label": "任务结果", "path": "/admin/results", "permission": "page:admin:results"},
#     ]},
#     {"key": "data", "label": "数据模块", "children": [
#         {"key": "model_summary", "label": "单模型汇总", "path": "/admin/model-summary", "permission": "page:admin:model_summary"},
#         {"key": "eastmoney_kline", "label": "东方财富 K 线", "path": "/admin/eastmoney-kline"},
#     ]},
#     {"key": "scheduler_group", "label": "调度模块", "children": [
#         {"key": "scheduler", "label": "定时任务", "path": "/admin/scheduler", "permission": "page:admin:scheduler"},
#     ]},
#     {"key": "system", "label": "系统模块", "children": [
#         {"key": "config", "label": "系统配置", "path": "/admin/config", "permission": "page:admin:config"},
#         {"key": "sheets", "label": "Google Sheet 管理", "path": "/admin/google-sheets", "permission": "page:admin:google_sheets"},
#         {"key": "navigation", "label": "路由表管理", "path": "/admin/navigation", "permission": "page:admin:navigation"},
#         {"key": "logs", "label": "系统日志", "path": "/admin/logs", "permission": "page:admin:logs"},
#         {"key": "users", "label": "用户管理", "path": "/admin/users", "permission": "page:admin:users"},
#         {"key": "roles", "label": "角色管理", "path": "/admin/roles", "permission": "page:admin:roles"},
#     ]},
#     {"key": "business", "label": "业务模块", "children": [
#         {"key": "c3", "label": "Google Sheet C3", "path": "/google-sheet/?version=c3", "permission": "page:google_sheet:c3"},
#         {"key": "c4", "label": "Google Sheet C4", "path": "/google-sheet/?version=c4", "permission": "page:google_sheet:c4"},
#         {"key": "c5", "label": "Google Sheet C5", "path": "/google-sheet/?version=c5", "permission": "page:google_sheet:c5"},
#         {"key": "c7", "label": "Google Sheet C7", "path": "/google-sheet/?version=c7", "permission": "page:google_sheet:c7"},
#         {"key": "backtest_single_product", "label": "单品数据回测", "path": "/backtest-training/list", "permission": "page:backtest:list"},
#         {"key": "backtest_multi_product", "label": "多品数据回测", "path": "/backtest-multi-product/list", "permission": "page:backtest_multi_product:list"},
#         {"key": "xpl", "label": "夏普率计算", "path": "/xpl"},
#         {"key": "xpl_v1", "label": "V1 回测数据分析", "path": "/xpl/v1"},
#     ]},
# ]
#

for name, code,link in ITEMS:
    payload = {
        "model_name": name,
        "model_code": code,
        "model_link": link,
        "file": "",
        "model_icon": "",
        "parent_model_id": "119",
        "order_num": "0",
        "model_type": "0",
        "sys_type": 1,
    }
    r = requests.post(URL, headers=HEADERS, json=payload, timeout=15)
    print(name, link, r.status_code, r.text)
