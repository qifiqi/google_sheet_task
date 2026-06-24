import time

from flask import Blueprint, redirect, request, jsonify, url_for

from app.models import GoogleSheetToken, GoogleSheetTableType, db
from app.services.google_sheet_registry_service import get_google_sheet_registry_service
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_token_service import get_google_sheet_token_service, RANDOM_TOKEN_VALUE
from app.utils.auth import login_required, permission_required
from app.utils.logger import get_logger

logger = get_logger(__name__)

google_sheet_api_bp = Blueprint('google_sheet_api', __name__)

_worksheets_cache = {}
_WORKSHEETS_CACHE_TTL = 5 * 24 * 60 * 60


def _get_worksheets_with_cache(spreadsheet_id: str, token_file: str, proxy_url: str | None):
    """内部工具：带缓存获取 worksheet 列表"""
    try:
        cache_key = (spreadsheet_id, token_file, proxy_url or '')
        now = time.time()
        cached = _worksheets_cache.get(cache_key)
        if cached:
            ts, cached_data = cached
            if now - ts < _WORKSHEETS_CACHE_TTL:
                logger.debug(f"命中工作表列表缓存: spreadsheet_id={spreadsheet_id}")
                resp = {
                    "status": "success",
                    "title": cached_data.get("title", ""),
                    "worksheets": cached_data.get("worksheets", []),
                    "cached": True,
                }
                return resp, 200

        data = GoogleSheetService.get_worksheets(spreadsheet_id, token_file, proxy_url)

        try:
            _worksheets_cache[cache_key] = (now, data)
        except Exception as e:
            logger.warning(f"更新工作表缓存失败: {e}")

        resp = {
            "status": "success",
            "title": data.get("title", ""),
            "worksheets": data.get("worksheets", []),
        }
        return resp, 200
    except Exception as e:
        logger.error(f"获取工作表列表失败: {str(e)}")
        return {"status": "error", "message": str(e)}, 500


@google_sheet_api_bp.route('/google-sheet/worksheets', methods=['POST'])
@login_required
@permission_required('google_sheet:view')
def get_worksheets():
    """获取Google Sheet中的所有工作表名称"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400

        spreadsheet_id = data.get('spreadsheet_id')
        token_file = 'data/token.json'
        proxy_url = data.get('proxy_url')

        if not spreadsheet_id:
            return jsonify({"status": "error", "message": "缺少spreadsheet_id参数"}), 400

        result, status_code = _get_worksheets_with_cache(spreadsheet_id, token_file, proxy_url)
        return jsonify(result), status_code
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"获取工作表列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheets', methods=['GET', 'POST'])
@login_required
@permission_required('google_sheet:view', 'google_sheet:manage')
def google_sheets():
    """Google Sheet 配置表列表/创建"""
    try:
        service = get_google_sheet_registry_service()

        if request.method == 'GET':
            include_inactive = request.args.get('include_inactive', '0') in ('1', 'true', 'True')
            only_available = request.args.get('only_available', '0') in ('1', 'true', 'True')
            task_id = request.args.get('task_id', '', type=str) or None
            table_type = GoogleSheetTableType.normalize(request.args.get('table_type'))
            return jsonify({
                "status": "success",
                "items": service.list_sheets(
                    include_inactive=include_inactive,
                    only_available=only_available,
                    task_id=task_id,
                    table_type=table_type,
                )
            })

        data = request.get_json() or {}
        item = service.create_sheet(
            spreadsheet_id=data.get('spreadsheet_id', ''),
            name=data.get('name'),
            table_type=data.get('table_type'),
            remark=data.get('remark'),
            is_active=data.get('is_active', True),
        )
        return jsonify({
            "status": "success",
            "message": "Google Sheet 创建成功",
            "item": item
        })
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"处理 Google Sheet 列表接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheets/<int:sheet_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
@permission_required('google_sheet:view', 'google_sheet:manage')
def google_sheet_detail(sheet_id):
    """Google Sheet 配置详情"""
    try:
        service = get_google_sheet_registry_service()

        if request.method == 'GET':
            item = service.get_sheet(sheet_id)
            if not item:
                return jsonify({"status": "error", "message": "Google Sheet 不存在"}), 404
            return jsonify({"status": "success", "item": item})

        if request.method == 'PUT':
            data = request.get_json() or {}
            payload = {}
            for key in ('spreadsheet_id', 'name', 'remark', 'table_type'):
                if key in data:
                    payload[key] = data.get(key)
            if 'is_active' in data:
                payload['is_active'] = data.get('is_active')
            item = service.update_sheet(sheet_id, **payload)
            return jsonify({"status": "success", "message": "Google Sheet 更新成功", "item": item})

        service.delete_sheet(sheet_id)
        return jsonify({"status": "success", "message": "Google Sheet 删除成功"})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"处理 Google Sheet 详情接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheet-tokens', methods=['GET'])
@login_required
@permission_required('google_sheet:view')
def list_google_sheet_tokens():
    """获取Google Sheet Token列表"""
    try:
        task_type = request.args.get('task_type')
        return jsonify({
            "status": "success",
            "random_value": RANDOM_TOKEN_VALUE,
            "tokens": get_google_sheet_token_service().list_tokens(task_type=task_type),
            "summary": get_google_sheet_token_service().get_usage_summary()
        })
    except Exception as e:
        logger.error(f"获取Google Sheet Token列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['GET', 'PUT'])
@login_required
@permission_required('google_sheet:view', 'google_sheet:manage')
def google_sheet_token_detail(token_id):
    """获取或更新 Google Sheet Token"""
    try:
        token_service = get_google_sheet_token_service()

        if request.method == 'GET':
            include_context = request.args.get('include_context', '0') in ('1', 'true', 'True')
            return jsonify({
                "status": "success",
                "token": token_service.get_token(token_id, include_context=include_context)
            })

        data = request.get_json() or {}
        payload = {}
        for key in ('name', 'token_context', 'is_active', 'task_type'):
            if key in data:
                payload[key] = data.get(key)
        if 'max_usage_count' in data:
            payload['max_usage_count'] = data.get('max_usage_count')

        token = token_service.update_token(token_id, **payload)
        return jsonify({
            "status": "success",
            "message": "Token更新成功",
            "token": token
        })
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logger.error(f"处理Google Sheet Token详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheet-tokens/import', methods=['POST'])
@login_required
@permission_required('google_sheet:manage')
def import_google_sheet_token():
    """Add or import a Google Sheet token"""
    try:
        data = request.get_json() or {}
        token_file = (data.get('token_file') or '').strip()
        token_context = data.get('token_context')
        name = (data.get('name') or '').strip() or None
        task_type = data.get('task_type')
        max_usage_count = data.get('max_usage_count')
        if max_usage_count not in (None, ''):
            max_usage_count = int(max_usage_count)
        else:
            max_usage_count = None

        token, created = get_google_sheet_token_service().import_token(
            token_context=token_context,
            token_file=token_file,
            name=name,
            max_usage_count=max_usage_count,
            task_type=task_type,
        )
        return jsonify({
            "status": "success",
            "message": "Token新增成功" if created else "Token更新成功",
            "token": token,
        })
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Add Google Sheet token failed: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['DELETE'])
@login_required
@permission_required('google_sheet:manage')
def delete_google_sheet_token(token_id):
    """删除 Google Sheet Token"""
    try:
        token = GoogleSheetToken.query.get(token_id)
        if not token:
            return jsonify({"status": "error", "message": "Token不存在"}), 404

        db.session.delete(token)
        db.session.commit()
        return jsonify({"status": "success", "message": "Token删除成功"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除Google Sheet Token失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@google_sheet_api_bp.route("/<task_id>/export", methods=["GET"])
@login_required
@permission_required('task:view')
def export_global_preview(task_id):
    """兼容旧导出路径，实际导出逻辑在 task_api.export_task_results。"""
    return redirect(url_for("task_api.export_task_results", task_id=task_id))
