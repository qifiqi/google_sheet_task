"""Google Sheet / Token 管理 API。

数据层说明：列表/详情/导入/删除全部经 google_sheet_registry_service /
google_sheet_token_service；路由层不直接感知 repository。

服务层仍以 ValueError 表达请求校验失败（400 语义），本层显式翻译为
BadRequestError；待服务层改抛语义异常后移除该翻译。
"""
from flask import Blueprint, request

from app.exceptions import BadRequestError, NotFoundError
from app.services.google_sheet_registry_service import (
    get_google_sheet_registry_service,
    get_worksheets_with_cache,
)
from app.services.google_sheet_token_service import get_google_sheet_token_service, RANDOM_TOKEN_VALUE
from app.utils.api_response import success
from app.schemas.google_sheet import TokenImportSchema
from app.utils.auth import login_required
from app.utils.request_parsing import parse_body

google_sheet_api_bp = Blueprint('google_sheet_api', __name__)


@google_sheet_api_bp.route('/google-sheet/worksheets', methods=['POST'])
@login_required
def get_worksheets():
    """获取Google Sheet中的所有工作表名称"""
    data = request.get_json()
    if not data:
        raise BadRequestError("请求数据为空")

    spreadsheet_id = data.get('spreadsheet_id')
    token_file = 'data/token.json'
    proxy_url = data.get('proxy_url')

    if not spreadsheet_id:
        raise BadRequestError("缺少spreadsheet_id参数")

    try:
        result = get_worksheets_with_cache(spreadsheet_id, token_file, proxy_url)
    except ValueError as e:
        raise BadRequestError(str(e))
    return success(data=result)


@google_sheet_api_bp.route('/google-sheets', methods=['GET', 'POST'])
@login_required
def google_sheets():
    """Google Sheet 配置表列表/创建"""
    service = get_google_sheet_registry_service()

    if request.method == 'GET':
        include_inactive = request.args.get('include_inactive', '0') in ('1', 'true', 'True')
        only_available = request.args.get('only_available', '0') in ('1', 'true', 'True')
        task_id = request.args.get('task_id', '', type=str) or None
        table_type = _normalize_table_type(request.args.get('table_type'))
        return success(data={
            "items": service.list_sheets(
                include_inactive=include_inactive,
                only_available=only_available,
                task_id=task_id,
                table_type=table_type,
            )
        })

    data = request.get_json() or {}
    try:
        item = service.create_sheet(
            spreadsheet_id=data.get('spreadsheet_id', ''),
            name=data.get('name'),
            table_type=data.get('table_type'),
            remark=data.get('remark'),
            is_active=data.get('is_active', True),
        )
    except ValueError as e:
        raise BadRequestError(str(e))
    return success(data={"item": item}, message="Google Sheet 创建成功")


def _normalize_table_type(raw):
    return GoogleSheetTableType.normalize(raw)


@google_sheet_api_bp.route('/google-sheets/<int:sheet_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
def google_sheet_detail(sheet_id):
    """Google Sheet 配置详情"""
    service = get_google_sheet_registry_service()

    if request.method == 'GET':
        item = service.get_sheet(sheet_id)
        if not item:
            raise NotFoundError("Google Sheet 不存在")
        return success(data={"item": item})

    if request.method == 'PUT':
        data = request.get_json() or {}
        payload = {}
        for key in ('spreadsheet_id', 'name', 'remark', 'table_type'):
            if key in data:
                payload[key] = data.get(key)
        if 'is_active' in data:
            payload['is_active'] = data.get('is_active')
        try:
            item = service.update_sheet(sheet_id, **payload)
        except ValueError as e:
            raise BadRequestError(str(e))
        return success(data={"item": item}, message="Google Sheet 更新成功")

    try:
        service.delete_sheet(sheet_id)
    except ValueError as e:
        raise BadRequestError(str(e))
    return success(message="Google Sheet 删除成功")


@google_sheet_api_bp.route('/google-sheet-tokens', methods=['GET'])
@login_required
def list_google_sheet_tokens():
    """获取Google Sheet Token列表（只读；占用计数对账走 POST /reconcile）"""
    task_type = request.args.get('task_type')
    service = get_google_sheet_token_service()
    return success(data={
        "random_value": RANDOM_TOKEN_VALUE,
        "tokens": service.list_tokens(task_type=task_type),
        "summary": service.get_usage_summary(),
    })


@google_sheet_api_bp.route('/google-sheet-tokens/reconcile', methods=['POST'])
@login_required
def reconcile_google_sheet_tokens():
    """显式对账并修正 Token 占用计数（原 GET 隐式写库行为收敛至此）。"""
    get_google_sheet_token_service().reconcile_in_use_counts()
    return success(data=get_google_sheet_token_service().get_usage_summary(), message="Token 占用计数已对账")


@google_sheet_api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['GET', 'PUT'])
@login_required
def google_sheet_token_detail(token_id):
    """获取或更新 Google Sheet Token"""
    token_service = get_google_sheet_token_service()

    if request.method == 'GET':
        include_context = request.args.get('include_context', '0') in ('1', 'true', 'True')
        return success(data={
            "token": token_service.get_token(token_id, include_context=include_context)
        })

    data = request.get_json() or {}
    payload = {}
    for key in ('name', 'token_context', 'is_active', 'task_type'):
        if key in data:
            payload[key] = data.get(key)
    if 'max_usage_count' in data:
        payload['max_usage_count'] = data.get('max_usage_count')

    try:
        token = token_service.update_token(token_id, **payload)
    except ValueError as e:
        raise BadRequestError(str(e))
    return success(data={"token": token}, message="Token更新成功")


@google_sheet_api_bp.route('/google-sheet-tokens/import', methods=['POST'])
@login_required
def import_google_sheet_token():
    """Add or import a Google Sheet token"""
    data = parse_body(TokenImportSchema)
    token_file = (data.token_file or '').strip()
    token_context = data.token_context
    name = (data.name or '').strip() or None
    task_type = data.task_type
    max_usage_count = data.max_usage_count

    try:
        token, created = get_google_sheet_token_service().import_token(
            token_context=token_context,
            token_file=token_file,
            name=name,
            max_usage_count=max_usage_count,
            task_type=task_type,
        )
    except ValueError as e:
        raise BadRequestError(str(e))
    return success(
        data={"token": token},
        message="Token新增成功" if created else "Token更新成功",
    )


@google_sheet_api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['DELETE'])
@login_required
def delete_google_sheet_token(token_id):
    """删除 Google Sheet Token"""
    deleted = get_google_sheet_token_service().delete_token(token_id)
    if not deleted:
        raise NotFoundError("Token不存在")
    return success(message="Token删除成功")
