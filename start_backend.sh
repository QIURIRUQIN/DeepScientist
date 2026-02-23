#!/bin/bash

# DeepScientist 后端启动脚本

echo "🚀 启动 DeepScientist 后端服务..."
echo ""

# 进入后端目录
cd "$(dirname "$0")/backend"

# 检查是否安装了依赖
if [ ! -d "venv" ]; then
    echo "📦 检测到首次运行，建议创建虚拟环境..."
    echo "   运行: python3 -m venv venv"
    echo "   然后: source venv/bin/activate"
    echo ""
fi

# 检查 requirements.txt 是否存在
if [ ! -f "requirements.txt" ]; then
    echo "❌ 错误: 找不到 requirements.txt"
    exit 1
fi

# 安装依赖（如果需要）
echo "📦 检查 Python 依赖..."
pip install -q -r requirements.txt 2>/dev/null || {
    echo "⚠️  依赖安装可能有问题，继续尝试启动..."
}

echo ""
echo "✅ 启动 Flask 服务器..."
echo "   后端服务地址: http://localhost:5000"
echo "   按 Ctrl+C 停止服务"
echo ""

# 启动 Flask 应用
python app.py
