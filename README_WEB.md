# DeepScientist Web 应用使用指南

这是一个基于 React 前端和 Flask 后端的 Web 应用，用于调用 DeepScientist AI Agent。

## 项目结构

```
DeepScientist/
├── backend/
│   ├── app.py              # Flask 后端应用
│   └── requirements.txt    # Python 依赖
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/     # React 组件
│   │   ├── services/       # API 服务
│   │   └── App.tsx         # 主应用组件
│   ├── package.json        # Node.js 依赖
│   └── tsconfig.json       # TypeScript 配置
└── run_graph.py            # AI Agent 主函数
```

## 安装和运行

### 1. 后端设置

```bash
# 进入后端目录
cd backend

# 安装 Python 依赖
pip install -r requirements.txt

# 运行 Flask 服务器
python app.py
```

后端服务将在 `http://localhost:5000` 启动。

### 2. 前端设置

```bash
# 进入前端目录
cd frontend

# 安装 Node.js 依赖
npm install

# 启动开发服务器
npm start
```

前端应用将在 `http://localhost:3000` 启动。

### 3. 环境变量（可选）

如果需要修改后端 API 地址，可以在 `frontend` 目录下创建 `.env` 文件：

```
REACT_APP_API_URL=http://localhost:5000
```

## 使用说明

1. **启动服务**：先启动后端服务，再启动前端服务
2. **访问应用**：在浏览器中打开 `http://localhost:3000`
3. **输入研究问题**：在表单中输入您的研究问题
4. **配置参数**（可选）：
   - 研究主题：默认为 "agent"
   - 研究方法：默认为 "LLM, Agent, Tool, Memory"
5. **运行 Agent**：点击"运行 AI Agent"按钮
6. **查看结果**：处理完成后，结果将显示在页面上

## API 接口

### 健康检查
- **GET** `/api/health`
- 返回服务状态

### 运行 Agent
- **POST** `/api/run-agent`
- 请求体：
  ```json
  {
    "original_query": "您的研究问题",
    "topic": "agent",
    "methodology": "LLM, Agent, Tool, Memory",
    "results": "",
    "messages": []
  }
  ```
- 返回：包含处理结果的 JSON 对象

## 注意事项

1. AI Agent 处理可能需要较长时间，请耐心等待
2. 确保后端服务正常运行，前端才能正常工作
3. 如果遇到跨域问题，确保 Flask-CORS 已正确安装
4. 处理大型任务时，可能需要调整超时设置

## 故障排除

### 后端无法启动
- 检查 Python 版本（建议 3.8+）
- 确保所有依赖已安装
- 检查端口 5000 是否被占用

### 前端无法连接后端
- 确认后端服务正在运行
- 检查 `.env` 文件中的 API URL 配置
- 查看浏览器控制台的错误信息

### Agent 处理超时
- 可以在 `frontend/src/services/api.ts` 中调整 `timeout` 值
- 检查后端日志查看具体错误信息
