from flask import Flask, send_from_directory, request
from app.config import Config
from app.extensions import db, migrate
from app.routes import register_blueprints
import os
from pathlib import Path

def create_app():
    # 获取应用根目录
    current_dir = Path(__file__).parent.parent
    static_dir = current_dir / 'static'
    
    # 不再需要template_folder，因为使用Vue前端
    app = Flask(__name__, static_folder=str(static_dir))
                
    app.config.from_object(Config)
    
    # 初始化扩展
    db.init_app(app)
    migrate.init_app(app, db)
    
    # 注册蓝图
    register_blueprints(app)
    
    # Vue前端路由处理
    @app.route('/')
    def index():
        """主页重定向到Vue应用"""
        vue_dist_dir = static_dir / 'dist'
        if vue_dist_dir.exists() and (vue_dist_dir / 'index.html').exists():
            return send_from_directory(str(vue_dist_dir), 'index.html')
        else:
            # 如果Vue构建文件不存在，返回开发提示
            return '''
            <h1>Google Sheet 任务管理系统</h1>
            <p>Vue前端未构建，请运行以下命令：</p>
            <pre>
cd frontend
npm install
npm run build
            </pre>
            <p>或者在开发模式下运行：</p>
            <pre>
cd frontend
npm run dev
            </pre>
            <p>然后访问 <a href="http://localhost:8080">http://localhost:8080</a></p>
            '''
    
    @app.route('/<path:path>')
    def vue_app(path):
        """处理Vue应用的路由"""
        vue_dist_dir = static_dir / 'dist'
        
        # 如果是API请求，不处理
        if path.startswith('api/'):
            return '', 404
            
        # 检查是否是静态资源
        file_path = vue_dist_dir / path
        if file_path.exists() and file_path.is_file():
            return send_from_directory(str(vue_dist_dir), path)
        
        # 对于Vue路由，返回index.html
        if (vue_dist_dir / 'index.html').exists():
            return send_from_directory(str(vue_dist_dir), 'index.html')
        else:
            return index()  # 返回开发提示
    
    return app
