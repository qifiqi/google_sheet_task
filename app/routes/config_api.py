"""配置管理 API。

配置读取/更新经 config_manager（缓存与负缓存刷新语义留在该层）。
"""
from flask import Blueprint, request

from app.exceptions import BadRequestError, NotFoundError, ServiceError
from app.services.config_manager import get_config_manager
from app.utils.api_response import success
from app.schemas.config import ConfigBatchSchema, SystemConfigUpdateSchema
from app.utils.auth import login_required
from app.utils.request_parsing import parse_body
from app.utils.logger import get_logger

logger = get_logger(__name__)

config_api_bp = Blueprint('config_api', __name__)


@config_api_bp.route('/config', methods=['GET'])
@login_required
def get_config():
    """获取系统配置"""
    config_manager = get_config_manager()
    configs = config_manager.get_all_configs(force_refresh=True)
    return success(data={"config": configs})


@config_api_bp.route('/config', methods=['POST'])
@login_required
def update_config():
    """更新系统配置"""
    data = parse_body(ConfigBatchSchema).root
    if not data:
        raise BadRequestError("请求数据为空")

    logger.info(f"接收到配置更新请求: {len(data)} 个配置项, keys={list(data.keys())}")

    config_manager = get_config_manager()
    updated = config_manager.update_configs(data)
    if updated:
        logger.info("配置更新成功，缓存已刷新")
        return success(message="配置更新成功，已立即生效")
    raise ServiceError("配置更新失败")


@config_api_bp.route('/config/validate', methods=['GET'])
@login_required
def validate_config():
    """验证配置状态"""
    config_manager = get_config_manager()

    rows = config_manager.get_db_config_rows()
    db_configs = {row["key"]: row["value"] for row in rows}

    cache_configs = config_manager.get_cache_snapshot()
    gs_config = config_manager.get_google_sheet_config()

    return success(data={
        "validation": {
            "database_configs": db_configs,
            "cache_configs": cache_configs,
            "google_sheet_config": gs_config,
            "cache_size": len(cache_configs),
            "db_size": len(db_configs),
        }
    })


@config_api_bp.route('/system-configs', methods=['GET'])
@login_required
def list_system_configs():
    """获取 system_configs 配置列表"""
    return success(data={"configs": get_config_manager().get_db_config_rows()})


@config_api_bp.route('/system-configs/<string:key>', methods=['PUT'])
@login_required
def update_system_config(key):
    """更新单条配置"""
    data = parse_body(SystemConfigUpdateSchema).root

    fields = {}
    if 'value' in data:
        fields["value"] = data['value']
    if 'description' in data:
        fields["description"] = data['description']

    updated = get_config_manager().update_config_row(key, fields)
    if updated is None:
        raise NotFoundError("配置不存在")

    return success(data={"config": updated})

