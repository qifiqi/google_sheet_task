#!/bin/bash

# 切换到脚本所在目录
cd "$(dirname "$0")" || exit 1

title="Google Validator Launcher"
echo -e "\033]0;$title\007"

export FLASK_DEBUG="false"
PYTHON_CMD=""

# 查找 Python 解释器
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
elif [ -f "env/bin/python" ]; then
    PYTHON_CMD="env/bin/python"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
elif command -v py &> /dev/null; then
    PYTHON_CMD="py -3"
else
    echo "[ERROR] Python was not found."
    echo "Install Python or create .venv, venv, or env first."
    read -p "Press Enter to exit..."
    exit 1
fi

# 检查 run.py 是否存在
if [ ! -f "run.py" ]; then
    echo "[ERROR] run.py was not found in the current directory."
    read -p "Press Enter to exit..."
    exit 1
fi

# 创建必要目录
mkdir -p logs data

# 输出信息
echo "[INFO] Workdir: $(pwd)"
echo "[INFO] Python: $PYTHON_CMD"
echo "[INFO] APP_ENV=$APP_ENV"
echo "[INFO] FLASK_DEBUG=$FLASK_DEBUG"
echo "[INFO] Starting application..."
echo

# 运行应用（传递所有参数）
$PYTHON_CMD run.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo
    echo "[ERROR] Startup failed. Exit code: $EXIT_CODE"
    read -p "Press Enter to exit..."
fi

exit $EXIT_CODE