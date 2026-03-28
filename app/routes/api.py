import time

from flask import Blueprint, request, jsonify, Response
import json
import queue
from app.services.task_manager import task_manager
from app.services.config_manager import get_config_manager
from app.models import Task, TaskLog, TaskTemplate, TaskResult, SystemConfig, GoogleSheetToken, GoogleSheet, db, GoogleSheetTableType
from app.utils.logger import get_logger
from flask import current_app
from app.services.google_sheet_service import GoogleSheetService
from app.services.google_sheet_token_service import get_google_sheet_token_service, RANDOM_TOKEN_VALUE
from app.services.google_sheet_registry_service import get_google_sheet_registry_service

logger = get_logger(__name__)

# Google Sheet 工作表列表简单内存缓存
_worksheets_cache = {}
# 缓存默认过期时间（秒），5 天
_WORKSHEETS_CACHE_TTL = 5 * 24 * 60 * 60

api_bp = Blueprint('api', __name__)

# 任务相关API
@api_bp.route('/tasks', methods=['GET', 'POST'])
def tasks():
    """获取任务列表 / 创建任务

    - GET: 返回全部任务，支持task_type过滤
    - POST: 创建任务，仅当body中包含config时
    """
    try:
        if request.method == 'GET':
            task_type = request.args.get('task_type')
            page = request.args.get('page', type=int)
            per_page = request.args.get('per_page', type=int)
            task_status = request.args.get('status')
            keyword = request.args.get('keyword', '', type=str)

            use_pagination = page is not None or per_page is not None or bool(task_status) or bool(keyword)
            if use_pagination:
                data = task_manager.get_tasks_paginated(
                    page=page or 1,
                    per_page=per_page or 10,
                    task_type=task_type,
                    status=task_status,
                    keyword=keyword,
                )
                return jsonify({
                    "status": "success",
                    "tasks": data["tasks"],
                    "pagination": data["pagination"],
                    "statistics": data["statistics"],
                })

            tasks = task_manager.get_all_tasks(task_type=task_type)
            return jsonify({"status": "success", "tasks": tasks})

        data = request.get_json() or {}

        # 兼容：创建任务
        config = data.get('config')
        if config:
            name = data.get('name', '未命名任务')
            description = data.get('description', '')
            task_type = data.get('task_type', 'google_sheet')
            response, status_code = task_manager.create_and_start_task(name, description, task_type, config)
            return jsonify(response), status_code

        return jsonify({"status": "error", "message": "任务配置为空"}), 400

    except ValueError as e:
        logger.warning(f"处理任务接口校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"处理任务接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route('/tasks/batch-create', methods=['POST'])
def batch_create_tasks():
    """C31 批量创建接口。

    当前仅打印收到的参数，并最小映射到原有 C3 单任务创建流程。
    后续再补真正的批量拆分逻辑。
    """
    try:
        data = request.get_json() or {}
        logger.info("C31 batch create request: %s", json.dumps(data, ensure_ascii=False, default=str))

        response, status_code = task_manager.batch_create_and_start_task(data)
        if status_code == 200:
            response["debug_message"] = "已调用原有 C3 创建流程；当前仍为占位版批量接口"
        return jsonify(response), status_code

    except ValueError as e:
        logger.warning(f"批量创建接口校验失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"批量创建接口失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取任务详情"""
    try:
        task = task_manager.get_task_status(task_id)
        if not task:
            return jsonify({"status": "error", "message": "任务不存在"}), 404
        
        return jsonify({"status": "success", "task": task})
    except Exception as e:
        logger.error(f"获取任务详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/config', methods=['PUT'])
def update_task_config(task_id):
    """更新任务配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400
        
        config = data.get('config')
        if not config:
            return jsonify({"status": "error", "message": "配置信息不能为空"}), 400
        
        name = data.get('name')
        description = data.get('description')
        
        result = task_manager.update_task_config(task_id, config, name, description)
        
        if result["status"] == "success":
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        logger.error(f"更新任务配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消任务"""
    try:
        success = task_manager.cancel_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "任务已取消"})
        else:
            return jsonify({"status": "error", "message": "取消任务失败"}), 400
    except Exception as e:
        logger.error(f"取消任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除任务"""
    try:
        success = task_manager.delete_task(task_id)
        if success:
            return jsonify({"status": "success", "message": "任务已删除"})
        else:
            return jsonify({"status": "error", "message": "删除任务失败"}), 400
    except Exception as e:
        logger.error(f"删除任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/logs', methods=['GET'])
def get_task_logs(task_id):
    """获取任务日志"""
    try:
        logs = task_manager.get_task_logs(task_id)
        return jsonify({"status": "success", "logs": logs})
    except Exception as e:
        logger.error(f"获取任务日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/results', methods=['GET'])
def get_task_results(task_id):
    """获取任务结果"""
    try:
        page = request.args.get('page', type=int)
        per_page = request.args.get('per_page', type=int)

        if page is not None and per_page is not None:
            data = task_manager.get_task_results(task_id, page=page, per_page=per_page)
            return jsonify({
                "status": "success",
                "results": data["items"],
                "total": data["total"],
                "pages": data["pages"],
                "current_page": data["current_page"],
                "per_page": data["per_page"],
                "total_success": data.get("total_success"),
                "total_failed": data.get("total_failed"),
            })

        results = task_manager.get_task_results(task_id)
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        logger.error(f"获取任务结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/status-check', methods=['GET'])
def check_task_status(task_id):
    """检查任务本地状态"""
    try:
        status_check = task_manager.check_local_task_status(task_id)
        return jsonify({"status": "success", "status_check": status_check})
    except Exception as e:
        logger.error(f"检查任务状态失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/stop-confirmation', methods=['GET'])
def get_task_stop_confirmation(task_id):
    """确认任务是否已经完全停止"""
    try:
        task = Task.query.get(task_id)
        if not task:
            return jsonify({"status": "error", "message": "任务不存在"}), 404

        status_check = task_manager.check_local_task_status(task_id)
        thread = task_manager.running_tasks.get(task_id)
        stop_event = task_manager.task_stop_events.get(task_id)
        thread_alive = bool(thread and thread.is_alive())
        stop_requested = bool(stop_event and stop_event.is_set())
        stop_confirmed = (task.status != 'running') and (not thread_alive)

        return jsonify({
            "status": "success",
            "task_id": task_id,
            "db_status": task.status,
            "thread_alive": thread_alive,
            "memory_running": status_check.get("memory_running", thread_alive),
            "stop_requested": stop_requested,
            "stop_confirmed": stop_confirmed,
            "current_step": task.current_step,
            "total_steps": task.total_steps,
            "status_check": status_check,
            "checked_at": time.time(),
        })
    except Exception as e:
        logger.error(f"获取任务停止确认失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route('/tasks/<task_id>/restart', methods=['POST'])
def restart_task(task_id):
    """重启任务"""
    try:
        data = request.get_json() or {}
        resume_from_checkpoint = data.get('resume_from_checkpoint', True)
        
        result = task_manager.restart_task(task_id, resume_from_checkpoint)
        if result["status"] == "success":
            return jsonify(result)
        else:
            return jsonify(result), 400
    except Exception as e:
        logger.error(f"重启任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/create-restart', methods=['POST'])
def create_restart_task_api(task_id):
    """基于原任务创建新的重启任务"""
    try:
        new_task_id = task_manager.create_restart_task(task_id)
        
        # 自动启动新任务
        if task_manager.start_task(new_task_id):
            return jsonify({
                "status": "success", 
                "new_task_id": new_task_id,
                "message": "重启任务创建并启动成功"
            })
        else:
            return jsonify({
                "status": "success", 
                "new_task_id": new_task_id,
                "message": "重启任务创建成功，但启动失败"
            })
    except Exception as e:
        logger.error(f"创建重启任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/events')
def task_events_stream(task_id):
    """SSE事件流，用于任务状态更新和确认请求"""
    def event_stream():
        if task_id not in task_manager.task_events:
            yield f"data: {json.dumps({'type': 'error', 'data': 'Task not found'})}\n\n"
            return
        
        event_queue = task_manager.task_events[task_id]
        
        try:
            while True:
                # 从事件队列获取事件
                try:
                    event = event_queue.get(timeout=1)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue.Empty:
                    # 超时，发送心跳
                    yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                
                # 检查事件队列是否还存在（任务管理器会清理完成的队列）
                if task_id not in task_manager.task_events:
                    break
                
        except GeneratorExit:
            pass
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return Response(event_stream(), mimetype='text/event-stream')

@api_bp.route('/tasks/<task_id>/confirm', methods=['POST'])
def confirm_task(task_id):
    """确认任务继续执行"""
    try:
        data = request.get_json()
        confirmed = data.get('confirmed', False) if data else False
        
        if task_id in task_manager.task_events:
            task_manager.task_events[task_id].put({
                "type": "confirmation",
                "data": {
                    "confirmed": confirmed
                }
            })
            return jsonify({"status": "success", "message": "确认已发送"})
        else:
            return jsonify({"status": "error", "message": "任务事件队列不存在"}), 400
    except Exception as e:
        logger.error(f"确认任务失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 配置相关API
@api_bp.route('/config', methods=['GET'])
def get_config():
    """获取系统配置"""
    try:
        config_manager = get_config_manager()
        # 强制刷新缓存，确保获取最新配置
        config_manager.refresh_cache()
        configs = config_manager.get_all_configs()
        logger.debug(f"返回配置数据: {configs}")
        return jsonify({"status": "success", "config": configs})
    except Exception as e:
        logger.error(f"获取配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/config', methods=['POST'])
def update_config():
    """更新系统配置"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400
        
        logger.info(f"接收到配置更新请求: {data}")
        
        config_manager = get_config_manager()
        success = config_manager.update_configs(data)
        if success:
            # 强制刷新缓存，确保配置立即生效
            config_manager.refresh_cache()
            logger.info("配置更新成功，缓存已刷新")
            return jsonify({"status": "success", "message": "配置更新成功，已立即生效"})
        else:
            return jsonify({"status": "error", "message": "配置更新失败"}), 500
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/config/validate', methods=['GET'])
def validate_config():
    """验证配置状态"""
    try:
        config_manager = get_config_manager()
        
        # 获取数据库中的配置
        from app.models import SystemConfig
        db_configs = {}
        configs = SystemConfig.query.all()
        for config in configs:
            db_configs[config.key] = config.value
        
        # 获取缓存中的配置
        cache_configs = config_manager._cache.copy()
        
        # 获取Google Sheet配置
        gs_config = config_manager.get_google_sheet_config()
        
        return jsonify({
            "status": "success",
            "validation": {
                "database_configs": db_configs,
                "cache_configs": cache_configs,
                "google_sheet_config": gs_config,
                "cache_size": len(cache_configs),
                "db_size": len(db_configs)
            }
        })
    except Exception as e:
        logger.error(f"验证配置失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/system-configs', methods=['GET'])
def list_system_configs():
    """获取 system_configs 配置列表（包含 key/value/description）"""
    try:
        configs = SystemConfig.query.order_by(SystemConfig.key.asc()).all()
        return jsonify({
            "status": "success",
            "configs": [c.to_dict() for c in configs]
        })
    except Exception as e:
        logger.error(f"获取 system_configs 列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/system-configs/<string:key>', methods=['PUT'])
def update_system_config(key):
    """更新单条配置（仅允许更新 value / description）"""
    try:
        data = request.get_json() or {}

        if 'value' not in data and 'description' not in data:
            return jsonify({"status": "error", "message": "缺少需要更新的字段"}), 400

        cfg = SystemConfig.query.filter_by(key=key).first()
        if not cfg:
            return jsonify({"status": "error", "message": "配置不存在"}), 404

        if 'value' in data:
            cfg.value = data.get('value')
        if 'description' in data:
            cfg.description = data.get('description')

        db.session.commit()

        try:
            get_config_manager().refresh_cache()
        except Exception as e:
            logger.warning(f"更新配置后刷新缓存失败: {e}")

        return jsonify({"status": "success", "config": cfg.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新 system_config 失败: key={key}, err={str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/tasks/<task_id>/system-logs', methods=['GET'])
def get_task_system_logs(task_id):
    """获取任务相关的系统日志"""
    try:
        import os
        import re
        from app.config import Config
        
        # 获取查询参数
        limit = request.args.get('limit', 200, type=int)
        level_filter = request.args.get('level', '')
        
        log_file = Config.LOG_FILE
        task_logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                
                # 解析日志格式
                log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'
                
                # 生成任务相关的搜索模式
                task_patterns = [
                    f"[Task-{task_id[:8]}]",  # 任务日志前缀
                    f"任务 {task_id}",        # 中文任务标识
                    task_id                    # 完整任务ID
                ]
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 检查是否包含任务相关信息
                    contains_task_info = any(pattern in line for pattern in task_patterns)
                    if not contains_task_info:
                        continue
                        
                    match = re.match(log_pattern, line)
                    if match:
                        timestamp_str, source, level, message = match.groups()
                        
                        # 转换时间格式
                        try:
                            from datetime import datetime
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                            iso_timestamp = timestamp.isoformat()
                        except:
                            iso_timestamp = timestamp_str
                        
                        log_entry = {
                            'timestamp': iso_timestamp,
                            'level': level.lower(),
                            'message': message.strip(),
                            'source': source.strip(),
                            'task_id': task_id
                        }
                        
                        # 应用级别过滤器
                        if level_filter and log_entry['level'] != level_filter.lower():
                            continue
                            
                        task_logs.append(log_entry)
                
                # 按时间正序排列
                task_logs.sort(key=lambda x: x['timestamp'])
                
                # 限制结果数量
                task_logs = task_logs[-limit:]
        
        return jsonify({
            "status": "success", 
            "logs": task_logs,
            "task_id": task_id,
            "total_found": len(task_logs)
        })
    except Exception as e:
        logger.error(f"获取任务系统日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/logs', methods=['GET'])
def get_logs():
    """获取系统日志"""
    try:
        import os
        import re
        from app.config import Config
        
        # 获取查询参数
        limit = request.args.get('limit', 100, type=int)
        level_filter = request.args.get('level', '')
        search = request.args.get('search', '')
        date_filter = request.args.get('date', '')
        task_id_filter = request.args.get('task_id', '')  # 新增任务ID过滤
        
        log_file = Config.LOG_FILE
        parsed_logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 读取最后的日志行
                recent_lines = lines[-limit*3:] if len(lines) > limit*3 else lines
                
                # 解析日志格式: 2025-09-28 20:53:48,938 - __main__ - INFO - 消息
                log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'
                
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    match = re.match(log_pattern, line)
                    if match:
                        timestamp_str, source, level, message = match.groups()
                        
                        # 转换时间格式
                        try:
                            from datetime import datetime
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                            iso_timestamp = timestamp.isoformat()
                        except:
                            iso_timestamp = timestamp_str
                        
                        log_entry = {
                            'timestamp': iso_timestamp,
                            'level': level.lower(),
                            'message': message.strip(),
                            'source': source.strip()
                        }
                        
                        # 应用过滤器
                        if level_filter and log_entry['level'] != level_filter.lower():
                            continue
                        if search and search.lower() not in log_entry['message'].lower():
                            continue
                        if date_filter and not iso_timestamp.startswith(date_filter):
                            continue
                        # 新增任务ID过滤器
                        if task_id_filter:
                            task_pattern = f"[Task-{task_id_filter[:8]}]"
                            if task_pattern not in log_entry['message'] and task_id_filter not in log_entry['message']:
                                continue
                            
                        parsed_logs.append(log_entry)
                    else:
                        # 如果无法解析，保留原始格式
                        parsed_logs.append({
                            'timestamp': '',
                            'level': 'info',
                            'message': line,
                            'source': 'unknown'
                        })
                
                # 按时间倒序排列，最新的在前
                parsed_logs.reverse()
                
                # 限制结果数量
                parsed_logs = parsed_logs[:limit]
        
        return jsonify({"status": "success", "logs": parsed_logs})
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Google Sheet相关API
def _get_worksheets_with_cache(spreadsheet_id: str, token_file: str, proxy_url: str | None):
    """内部工具：带缓存获取 worksheet 列表和 spreadsheet 标题"""
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

@api_bp.route('/google-sheet/worksheets', methods=['POST'])
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

@api_bp.route('/google-sheets', methods=['GET', 'POST'])
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


@api_bp.route('/google-sheets/<int:sheet_id>', methods=['GET', 'PUT', 'DELETE'])
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

# 模板相关API
@api_bp.route('/templates', methods=['GET'])
def get_templates():
    """获取所有任务模板"""
    try:
        # 可选按 task_type 过滤（例如 task_type=google_sheet_C4 仅返回 C4 模板）
        task_type = request.args.get('task_type')

        templates = TaskTemplate.query.order_by(TaskTemplate.created_at.desc()).all()

        if task_type:
            filtered = []
            for t in templates:
                try:
                    cfg = json.loads(t.config) if isinstance(t.config, str) else t.config
                except Exception:
                    continue
                if isinstance(cfg, dict) and cfg.get('task_type') == task_type:
                    filtered.append(t)
            templates = filtered

        return jsonify({
            "status": "success",
            "templates": [template.to_dict() for template in templates]
        })
    except Exception as e:
        logger.error(f"获取模板列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/templates', methods=['POST'])
def create_template():
    """创建新任务模板"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400
        
        if 'name' not in data:
            return jsonify({"status": "error", "message": "模板名称不能为空"}), 400
            
        if 'config' not in data:
            return jsonify({"status": "error", "message": "配置信息不能为空"}), 400
            
        # 验证配置是否为有效的JSON
        try:
            if isinstance(data['config'], str):
                config_json = json.loads(data['config'])
                config_str = json.dumps(config_json)
            else:
                config_str = json.dumps(data['config'])
        except json.JSONDecodeError:
            return jsonify({"status": "error", "message": "配置信息不是有效的JSON格式"}), 400
        
        template = TaskTemplate(
            name=data['name'],
            description=data.get('description', ''),
            config=config_str
        )
        
        db.session.add(template)
        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": "模板创建成功",
            "template": template.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"创建模板失败: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"创建模板失败: {str(e)}"
        }), 500

@api_bp.route('/templates/<int:template_id>', methods=['GET'])
def get_template(template_id):
    """获取模板详情"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404
        
        return jsonify(template.to_dict())
    except Exception as e:
        logger.error(f"获取模板详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/templates/<int:template_id>', methods=['PUT'])
def update_template(template_id):
    """更新任务模板"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "请求数据为空"}), 400
        
        template.name = data['name']
        template.description = data.get('description', template.description)
        template.config = json.dumps(data['config']) if isinstance(data['config'], (dict, list)) else data['config']
        
        db.session.commit()
        
        return jsonify({"status": "success", "template": template.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error(f"更新模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/templates/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    """删除任务模板"""
    try:
        template = TaskTemplate.query.get(template_id)
        if not template:
            return jsonify({"status": "error", "message": "模板不存在"}), 404
        
        db.session.delete(template)
        db.session.commit()
        
        return jsonify({"status": "success", "message": "模板已删除"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除模板失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 任务结果相关API
@api_bp.route('/results', methods=['GET'])
def get_results():
    """获取任务结果列表（支持分页和筛选）"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        task_id = request.args.get('task_id', None)
        
        query = TaskResult.query
        
        if task_id:
            query = query.filter_by(task_id=task_id)
        
        pagination = query.order_by(TaskResult.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        results = [result.to_dict() for result in pagination.items]
        
        return jsonify({
            "results": results,
            "total": pagination.total,
            "pages": pagination.pages,
            "current_page": page
        })
    except Exception as e:
        logger.error(f"获取结果列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/results/<int:result_id>', methods=['GET'])
def get_result(result_id):
    """获取任务结果详情"""
    try:
        result = TaskResult.query.get(result_id)
        if not result:
            return jsonify({"status": "error", "message": "结果不存在"}), 404
        
        return jsonify(result.to_dict())
    except Exception as e:
        logger.error(f"获取结果详情失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/results/<int:result_id>', methods=['DELETE'])
def delete_result(result_id):
    """删除任务结果"""
    try:
        result = TaskResult.query.get(result_id)
        if not result:
            return jsonify({"status": "error", "message": "结果不存在"}), 404
        
        db.session.delete(result)
        db.session.commit()
        
        return jsonify({"status": "success", "message": "结果已删除"})
    except Exception as e:
        db.session.rollback()
        logger.error(f"删除结果失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/logs/latest', methods=['GET'])
def get_latest_logs():
    """获取最新的日志（用于实时更新）"""
    try:
        import os
        import re
        from app.config import Config
        
        # 获取查询参数
        since = request.args.get('since', '')  # 获取指定时间之后的日志
        limit = request.args.get('limit', 50, type=int)
        
        log_file = Config.LOG_FILE
        latest_logs = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                # 只读取最后的一些行以提高性能
                recent_lines = lines[-limit*2:] if len(lines) > limit*2 else lines
                
                # 解析日志格式
                log_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - ([^-]+) - (\w+) - (.+)'
                
                for line in recent_lines:
                    line = line.strip()
                    if not line:
                        continue
                        
                    match = re.match(log_pattern, line)
                    if match:
                        timestamp_str, source, level, message = match.groups()
                        
                        # 转换时间格式
                        try:
                            from datetime import datetime
                            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
                            iso_timestamp = timestamp.isoformat()
                        except:
                            iso_timestamp = timestamp_str
                        
                        # 如果指定了since参数，只返回该时间之后的日志
                        if since and iso_timestamp <= since:
                            continue
                        
                        log_entry = {
                            'timestamp': iso_timestamp,
                            'level': level.lower(),
                            'message': message.strip(),
                            'source': source.strip()
                        }
                        
                        latest_logs.append(log_entry)
                
                # 按时间正序排列（最新的在后面）
                latest_logs.sort(key=lambda x: x['timestamp'])
                
                # 限制结果数量
                latest_logs = latest_logs[-limit:]
        
        return jsonify({"status": "success", "logs": latest_logs})
    except Exception as e:
        logger.error(f"获取最新日志失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route('/google-sheet-tokens', methods=['GET'])
def list_google_sheet_tokens():
    """获取Google Sheet Token列表"""
    try:
        return jsonify({
            "status": "success",
            "random_value": RANDOM_TOKEN_VALUE,
            "tokens": get_google_sheet_token_service().list_tokens(),
            "summary": get_google_sheet_token_service().get_usage_summary()
        })
    except Exception as e:
        logger.error(f"获取Google Sheet Token列表失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['GET', 'PUT'])
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
        for key in ('name', 'token_context', 'is_active'):
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


@api_bp.route('/google-sheet-tokens/import', methods=['POST'])
def import_google_sheet_token():
    """Add or import a Google Sheet token."""
    try:
        data = request.get_json() or {}
        token_file = (data.get('token_file') or '').strip()
        token_context = data.get('token_context')
        name = (data.get('name') or '').strip() or None
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

@api_bp.route('/google-sheet-tokens/<int:token_id>', methods=['DELETE'])
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

@api_bp.route('/database/status', methods=['GET'])
def get_database_status():
    """获取数据库状态"""
    try:
        from app.utils.db_monitor import DatabaseMonitor
        report = DatabaseMonitor.get_full_report()
        return jsonify({"status": "success", "report": report})
    except Exception as e:
        logger.error(f"获取数据库状态失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/database/vacuum', methods=['POST'])
def vacuum_database():
    """压缩数据库"""
    try:
        from app.utils.db_monitor import DatabaseMonitor
        result = DatabaseMonitor.vacuum_database()
        if result.get('success'):
            return jsonify({"status": "success", "result": result})
        else:
            return jsonify({"status": "error", "message": result.get('message', result.get('error'))}), 400
    except Exception as e:
        logger.error(f"压缩数据库失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@api_bp.route('/database/suggestions', methods=['GET'])
def get_optimization_suggestions():
    """获取数据库优化建议"""
    try:
        from app.utils.db_monitor import DatabaseMonitor
        suggestions = DatabaseMonitor.suggest_optimizations()
        return jsonify({"status": "success", "suggestions": suggestions})
    except Exception as e:
        logger.error(f"获取优化建议失败: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500
