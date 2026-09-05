#!/usr/bin/env python3
"""
补充 permission 表的 route_path 列。
直接运行：python scripts/add_permission_route_path.py
"""
import sys
from pathlib import Path
from sqlalchemy import inspect, text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    inspector = inspect(db.engine)
    columns = {c['name'] for c in inspector.get_columns('permission')}

    if 'route_path' in columns:
        print("route_path 列已存在，无需迁移。")
    else:
        db.session.execute(text(
            "ALTER TABLE permission ADD COLUMN route_path VARCHAR(200)"
        ))
        db.session.commit()
        print("已添加 route_path 列。")

    # 顺手把 PERMISSIONS 里的 route_path 值回填进去
    from app.config import PERMISSIONS
    from app.models import Permission

    updated = 0
    for group, code, name, route_path in PERMISSIONS:
        perm = Permission.query.filter_by(code=code).first()
        if perm and perm.route_path != route_path:
            perm.route_path = route_path
            updated += 1
    db.session.commit()
    print(f"已回填 {updated} 条权限的 route_path。")
    print("完成。")
