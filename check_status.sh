#!/bin/bash

# DeepScientist 状态检查脚本

echo "🔍 DeepScientist 服务状态检查"
echo "=================================="
echo ""

# 检查后端服务
echo "1️⃣  检查后端服务..."
if curl -s http://localhost:5000/api/health > /dev/null 2>&1; then
    echo "   ✅ 后端服务正在运行"
    echo "   响应:"
    curl -s http://localhost:5000/api/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:5000/api/health
else
    echo "   ❌ 后端服务未运行或无法访问"
    echo "   请确保后端服务已启动: ./start_backend.sh"
fi
echo ""

# 检查 Python 依赖
echo "2️⃣  检查 Python 依赖..."
cd "$(dirname "$0")"
if python3 -c "import langgraph; import langchain; import flask; print('✅ 核心依赖已安装')" 2>/dev/null; then
    echo "   ✅ 核心依赖已安装"
else
    echo "   ❌ 缺少核心依赖"
    echo "   请运行: pip install langgraph langchain flask flask-cors"
fi
echo ""

# 检查模块导入
echo "3️⃣  检查模块导入..."
if python3 -c "import sys; sys.path.insert(0, '.'); from run_graph import build_graph, main; print('✅ run_graph 模块可以正常导入')" 2>/dev/null; then
    echo "   ✅ run_graph 模块可以正常导入"
else
    echo "   ❌ run_graph 模块导入失败"
    echo "   错误信息:"
    python3 -c "import sys; sys.path.insert(0, '.'); from run_graph import build_graph, main" 2>&1 | head -5
    echo ""
    echo "   💡 解决方案:"
    echo "      ./install_dependencies.sh"
    echo "      或"
    echo "      cd backend && pip install -r requirements.txt"
fi
echo ""

# 检查前端服务
echo "4️⃣  检查前端服务..."
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "   ✅ 前端服务正在运行"
else
    echo "   ⚠️  前端服务未运行（这是正常的，如果还没启动）"
    echo "   启动命令: ./start_frontend.sh"
fi
echo ""

echo "=================================="
echo "检查完成！"
echo ""
echo "如果看到错误，请按照上述提示解决。"
