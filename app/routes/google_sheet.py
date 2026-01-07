from flask import Blueprint, render_template, request, jsonify, url_for, redirect, flash
import json
from app.services.task_manager import task_manager
from app.services.config_manager import get_config_manager
from app.utils.logger import get_logger
from app.models import TaskTemplate

logger = get_logger(__name__)

google_sheet_bp = Blueprint('google_sheet', __name__)

@google_sheet_bp.route('/')
def index():
    """Google Sheet参数批量校验首页

    使用 query 参数 version 区分不同版本：
    - version=c4 -> C4 模板
    - version=c5 -> C5 模板
    - 其它 / 无 -> 默认模板
    """
    version = request.args.get('version')

    if version == 'c5':
        return render_template('google_sheet_c5/index.html', version='c5')
    if version == 'c4':
        return render_template('google_sheet_c4/index.html', version='c4')
    return render_template('google_sheet/index.html', version=None)

@google_sheet_bp.route('/create')
def create():
    """创建Google Sheet任务页面"""
    template_id = request.args.get('template_id')
    version = request.args.get('version')
    template = None
    
    if template_id:
        try:
            template = TaskTemplate.query.get(int(template_id))
            if template:
                logger.info(f"加载模板 {template_id}: {template.name}")
                template_data = template.to_dict()
                
                # 确保配置是字典格式
                if isinstance(template_data['config'], str):
                    try:
                        template_data['config'] = json.loads(template_data['config'])
                    except json.JSONDecodeError:
                        logger.error(f"模板配置解析失败: {template_data['config']}")
                        template_data['config'] = {}
                
                # 修改模板名称，表明这是从模板创建的
                template_data['name'] = f"{template_data['name']} - 从模板创建"

                if version == 'c5':
                    return render_template(
                        'google_sheet_c5/create.html',
                        template=template_data,
                        template_id=template_id,
                        version='c5',
                    )
                if version == 'c4':
                    return render_template(
                        'google_sheet_c4/create.html',
                        template=template_data,
                        template_id=template_id,
                        version='c4',
                    )
                return render_template(
                    'google_sheet/create.html',
                    template=template_data,
                    template_id=template_id,
                    version=None,
                )
            else:
                logger.warning(f"模板不存在: {template_id}")
                flash('模板不存在', 'error')
        except Exception as e:
            logger.error(f"加载模板失败: {str(e)}")
            flash('加载模板失败: ' + str(e), 'error')
    if version == 'c5':
        return render_template('google_sheet_c5/create.html', version='c5')
    if version == 'c4':
        return render_template('google_sheet_c4/create.html', version='c4')
    return render_template('google_sheet/create.html', version=None)

@google_sheet_bp.route('/detail')
def detail():
    """任务详情页面"""
    version = request.args.get('version')

    if version == 'c5':
        return render_template('google_sheet_c5/detail.html', version='c5')
    if version == 'c4':
        return render_template('google_sheet_c4/detail.html', version='c4')
    return render_template('google_sheet/detail.html', version=None)

@google_sheet_bp.route('/create-restart/<task_id>')
def create_restart(task_id):
    """重启任务页面，预填充原任务的配置

    支持通过 ?version=c4 或 ?version=c5 区分使用 C4/C5 版本的创建页面。
    """
    from app.services.task_manager import task_manager

    version = request.args.get('version')

    # 获取原任务
    task = task_manager.get_task_status(task_id)
    if not task:
        logger.error(f"原任务不存在: {task_id}")
        # 原任务不存在时，同样根据 version 渲染对应的空创建页
        if version == 'c5':
            return render_template('google_sheet_c5/create.html', version='c5')
        if version == 'c4':
            return render_template('google_sheet_c4/create.html', version='c4')
        return render_template('google_sheet/create.html', version=None)

    # 将原任务配置传递给模板
    if version == 'c5':
        return render_template(
            'google_sheet_c5/create.html',
            restart_config=task['config'],
            original_task_id=task_id,
            version='c5',
        )

    if version == 'c4':
        return render_template(
            'google_sheet_c4/create.html',
            restart_config=task['config'],
            original_task_id=task_id,
            version='c4',
        )

    return render_template(
        'google_sheet/create.html',
        restart_config=task['config'],
        original_task_id=task_id,
        version=None,
    )
