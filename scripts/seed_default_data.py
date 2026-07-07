#!/usr/bin/env python3
"""Seed default configuration, RBAC, navigation and scheduled tasks."""
import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db
from app.seed_data import seed_default_data
from app.startup import (
    ensure_backtest_runtime_schema,
    ensure_google_sheet_token_schema,
    ensure_navigation_menu_schema,
    ensure_scheduled_task_schema,
    ensure_stock_metadata_schema,
    ensure_task_result_return_schema,
    ensure_task_result_schema,
    ensure_task_result_summary_index_schema,
    ensure_task_schema,
    ensure_user_schema,
    ensure_xpl_analysis_job_schema,
)


def prepare_schema():
    db.create_all()
    ensure_google_sheet_token_schema()
    ensure_user_schema()
    ensure_task_schema()
    ensure_task_result_schema()
    ensure_scheduled_task_schema()
    ensure_task_result_return_schema()
    ensure_task_result_summary_index_schema()
    ensure_xpl_analysis_job_schema()
    ensure_stock_metadata_schema()
    ensure_backtest_runtime_schema()
    ensure_navigation_menu_schema()


def parse_args():
    parser = argparse.ArgumentParser(
        description='Initialize default SystemConfig, RBAC, navigation menu and scheduled tasks.',
    )
    parser.add_argument(
        '--skip-schema',
        action='store_true',
        help='Do not create/repair tables before seeding.',
    )
    parser.add_argument(
        '--skip-scheduler',
        action='store_true',
        help='Do not create the default scheduled cleanup task.',
    )
    return parser.parse_args()


def main():
    args = parse_args()
    app = create_app()
    with app.app_context():
        if not args.skip_schema:
            prepare_schema()
        seed_default_data(app, include_scheduler=not args.skip_scheduler)
    print('默认配置、权限、导航菜单和定时任务初始化完成')


if __name__ == '__main__':
    main()
