#!/usr/bin/env python3
import os

from app import create_app
from app.startup import bootstrap_app, register_cli, register_shell_context
from app.utils.logger import get_logger


app = create_app()
register_shell_context(app)
register_cli(app)


if __name__ == '__main__':
    logger = get_logger('app')
    try:
        bootstrap_app(app)
        debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes', 'on')
        app.run(debug=debug_mode, host='0.0.0.0', port=os.getenv('PORT', 5000))
    except Exception as exc:
        logger.error(f'启动失败: {exc}', exc_info=True)
