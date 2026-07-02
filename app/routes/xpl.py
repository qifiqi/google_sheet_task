from flask import Blueprint, render_template, request, jsonify, url_for, redirect, flash, current_app, send_file
from app.utils.logger import get_logger
from app.services.xpl_service import xpl_analyzer

logger = get_logger(__name__)

xpl_bp = Blueprint('xpl', __name__)

@xpl_bp.route('/')
def index():
    """Excel数据分析工具首页"""
    return render_template('xpl/index.html')


@xpl_bp.route('/v1', methods=['GET'])
def index_v1():
    """V1：Google Sheet 分析页面"""
    return render_template('xpl/v1.html')

@xpl_bp.route('/analyze', methods=['POST'])
def analyze_data():
    """
    API接口：分析Excel数据
    
    请求体 (JSON):
    {
        "data": "2023-01-01 0.01\n2023-01-02 0.02\n...",
        "time_format": "YYYY-MM-DD"
    }
    
    返回 (JSON):
    {
        "status": "success/error",
        "message": "描述信息",
        "results": [{"date": "2023-01-01", "return": 0.01, ...}],
        "metrics": {"total_return": 0.1, ...}
    }
    """
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空',
                'results': [],
                'metrics': {}
            }), 400
            
        # 获取参数
        input_data = data.get('data', '')
        time_format = data.get('time_format', 'auto')
        logger.debug("收到XPL分析请求: time_format=%s, data_length=%s", time_format, len(input_data))
        
        # 调用服务层进行分析
        result = xpl_analyzer.analyze(
            data=input_data,
            time_format=time_format
        )
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"处理分析请求时出错: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'处理请求时出错: {str(e)}',
            'results': [],
            'metrics': {}
        }), 500


@xpl_bp.route('/export', methods=['POST'])
def export_file():
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空',
            }), 400

        filename = data.get('filename')
        file,file_type = xpl_analyzer.export_file(data)

        # 发送文件
        return send_file(
            file,
            mimetype=file_type,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        logger.error(f"导出文件时出错: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'处理请求时出错: {str(e)}',
        }), 500


@xpl_bp.route('/v1/analyze', methods=['POST'])
def analyze_data_v1():
    """
    API接口：分析Excel数据

    请求体 (JSON):
    {
        'google_sheet_url':'',
        'google_sheet_name':''
    }

    返回 (JSON):
    {
        "status": "success/error",
        "message": "描述信息",
        "results": {"total_return": 0.1, ...}
    }
    """
    try:
        # 获取请求数据
        data = request.get_json()
        if not data:
            return jsonify({
                'status': 'error',
                'message': '请求体不能为空',
                'results': [],
                'metrics': {}
            }), 400

        # 获取参数
        spreadsheet_id = data.get('spreadsheet_id', '')
        google_sheet_url = data.get('google_sheet_url', '')
        google_sheet_name = data.get('google_sheet_name', 'auto')

        # 调用服务层进行分析
        result = xpl_analyzer.analyze_v1(
            spreadsheet_id=spreadsheet_id,
            google_sheet_name=google_sheet_name
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"处理分析请求时出错: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'处理请求时出错: {str(e)}',
            'results': [],
            'metrics': {}
        }), 500
