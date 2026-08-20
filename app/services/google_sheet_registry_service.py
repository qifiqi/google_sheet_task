from __future__ import annotations

from typing import Optional

from app.models import GoogleSheetTableType, google_sheet_registry_scope
from app.repositories.google_sheet_repository import GoogleSheetRepository

class GoogleSheetRegistryService:
    def __init__(self, repository: GoogleSheetRepository | None = None):
        """注入 Sheet 注册表仓储；运行占用事实由任务锁维护。"""
        self.repository = repository or GoogleSheetRepository()

    def list_sheets(self, include_inactive: bool = False, only_available: bool = False, task_id: str | None = None,
                    table_type: str | None = None):
        """读取远程注册表并按页面已有条件筛选展示结果。"""
        sheets = self.repository.list_page(
            page_size=1000,
        )["items"]
        normalized_table_type = GoogleSheetTableType.normalize(table_type)
        return [
            sheet
            for sheet in sheets
            if (not normalized_table_type or sheet.get("table_type") == normalized_table_type)
            and (include_inactive or sheet.get("is_active"))
            and (
                not only_available
                or not sheet.get("is_in_use")
                or (task_id and sheet.get("current_task_id") == task_id)
            )
        ]

    def get_sheet(self, sheet_id: int) -> Optional[dict]:
        """通过远程 CRUD 按主键读取一个 Sheet 注册记录。"""
        return self.repository.get(sheet_id)

    def create_sheet(self, spreadsheet_id: str, name: str | None = None, remark: str | None = None,
                     is_active: bool = True, table_type: str | None = None):
        """校验同类表唯一性后，调用远程 CRUD 创建注册记录。"""
        spreadsheet_id = (spreadsheet_id or '').strip()
        if not spreadsheet_id:
            raise ValueError("spreadsheet_id 不能为空")

        normalized_table_type = GoogleSheetTableType.normalize(table_type, GoogleSheetTableType.C3.value)
        if not normalized_table_type:
            raise ValueError("table_type 无效")

        # 服务端尚无复合条件去重接口，暂在单页注册表数据中完成兼容校验。
        existing = next(
            (
                sheet
                for sheet in self.repository.list_page(page_size=1000)["items"]
                if sheet.get("spreadsheet_id") == spreadsheet_id
                and sheet.get("registry_scope") == google_sheet_registry_scope(normalized_table_type)
            ),
            None,
        )
        if existing:
            raise ValueError("该 spreadsheet_id 已存在于同类表类型中")

        return self.repository.save({
            "spreadsheet_id": spreadsheet_id,
            "name": (name or spreadsheet_id).strip(),
            "table_type": normalized_table_type,
            "registry_scope": google_sheet_registry_scope(normalized_table_type),
            "remark": (remark or '').strip() or None,
            "is_active": bool(is_active),
        })

    def update_sheet(self, sheet_id: int, **payload):
        """更新远程注册表记录，并校验同类表内的 spreadsheet_id 唯一性。"""
        sheet = self.repository.get(sheet_id)
        if not sheet:
            raise ValueError("Google Sheet 不存在")

        spreadsheet_id = sheet["spreadsheet_id"]
        if 'spreadsheet_id' in payload:
            spreadsheet_id = (payload.get('spreadsheet_id') or '').strip()
            if not spreadsheet_id:
                raise ValueError("spreadsheet_id 不能为空")

        table_type = sheet["table_type"]
        if 'table_type' in payload:
            table_type = GoogleSheetTableType.normalize(payload.get('table_type'))
            if not table_type:
                raise ValueError("table_type 无效")

        # 排除当前记录后，再检查更新后的复合唯一性约束。
        existing = next(
            (
                item
                for item in self.repository.list_page(page_size=1000)["items"]
                if item.get("spreadsheet_id") == spreadsheet_id
                and item.get("registry_scope") == google_sheet_registry_scope(table_type)
                and item.get("id") != sheet_id
            ),
            None,
        )
        if existing:
            raise ValueError("该 spreadsheet_id 已存在于同类表类型中")

        updated = dict(sheet)
        updated.update({
            "spreadsheet_id": spreadsheet_id,
            "table_type": table_type,
            "registry_scope": google_sheet_registry_scope(table_type),
        })
        if 'name' in payload:
            updated["name"] = (payload.get('name') or '').strip() or spreadsheet_id
        if 'remark' in payload:
            updated["remark"] = (payload.get('remark') or '').strip() or None
        if 'is_active' in payload:
            updated["is_active"] = bool(payload.get('is_active'))
        return self.repository.save(updated)

    def delete_sheet(self, sheet_id: int):
        """删除未被任务占用的远程注册表记录。"""
        sheet = self.repository.get(sheet_id)
        if not sheet:
            raise ValueError("Google Sheet 不存在")
        if sheet.get("is_in_use"):
            raise ValueError("该 Google Sheet 正在被任务使用，无法删除")

        self.repository.delete(sheet_id)

    def acquire_for_task(self, sheet_id: int, task_id: str):
        """兼容旧入口：仅校验 Sheet；互斥由 BacktestSheetRunLock 负责。"""
        sheet = self.repository.get(int(sheet_id))
        if not sheet:
            raise ValueError("所选 Google Sheet 不存在")
        if not sheet.get("is_active"):
            raise ValueError("所选 Google Sheet 未启用")
        # is_in_use/current_task_id 只是页面派生展示，不能作为并发互斥事实。
        return sheet

    def release_for_task(self, task_id: str):
        """兼容旧入口；实际释放由任务运行锁在收尾阶段完成。"""
        return False


google_sheet_registry_service = GoogleSheetRegistryService()


def get_google_sheet_registry_service() -> GoogleSheetRegistryService:
    """返回共享的 Sheet 注册表服务实例。"""
    return google_sheet_registry_service
