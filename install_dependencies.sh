#!/bin/bash

# DeepScientist 依赖安装脚本

echo "📦 开始安装 DeepScientist 项目依赖..."
echo ""

# 进入项目根目录
cd "$(dirname "$0")"

# 检查是否有虚拟环境
if [ -d "venv" ]; then
    echo "✅ 检测到虚拟环境，正在激活..."
    source venv/bin/activate
fi

# 安装后端依赖
echo ""
echo "📦 安装后端依赖..."
cd backend
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "✅ 后端依赖安装成功！"
else
    echo "❌ 后端依赖安装失败，请检查错误信息"
    exit 1
fi

cd ..

# 测试导入
echo ""
echo "🧪 测试导入..."
python3 -c "from run_graph import build_graph, main; print('✅ 导入成功')" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 所有依赖安装完成！"
    echo ""
    echo "现在可以运行："
    echo "  ./start_backend.sh   # 启动后端"
    echo "  ./start_frontend.sh  # 启动前端"
else
    echo ""
    echo "⚠️  导入测试失败，可能还需要安装其他依赖"
    echo "请查看 '安装依赖说明.md' 获取更多帮助"
    exit 1
fi
