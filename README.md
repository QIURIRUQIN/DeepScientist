# DeepScientist Web 应用运行指南

## 📋 前置要求

1. **Python 3.8+** 已安装
2. **Node.js 16+** 和 **npm** 已安装
3. 项目所需的所有 Python 依赖已安装（用于运行 AI Agent）

## 🚀 快速启动

### 方法一：手动启动（推荐用于开发）

#### 步骤 1：启动后端服务

打开第一个终端窗口：

```bash
# 进入项目根目录
cd /Users/chongyanghe/Desktop/DeepScientist

# 进入后端目录
cd backend

# 安装后端依赖（如果还没安装）
pip install -r requirements.txt

# 启动 Flask 服务器
python app.py
```

看到以下输出表示后端启动成功：
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

**保持这个终端窗口打开！**

#### 步骤 2：启动前端服务

打开第二个终端窗口：

```bash
# 进入项目根目录
cd /Users/chongyanghe/Desktop/DeepScientist

# 进入前端目录
cd frontend

# 安装前端依赖（首次运行需要）
npm install

# 启动 React 开发服务器
npm start
```

看到以下输出表示前端启动成功：
```
Compiled successfully!

You can now view deep-scientist-frontend in the browser.

  Local:            http://localhost:3000
```

#### 步骤 3：访问应用

浏览器会自动打开，或手动访问：**http://localhost:3000**

---

### 方法二：使用启动脚本（macOS/Linux）

我为您创建了启动脚本，可以更方便地启动服务。

#### 启动后端：
```bash
chmod +x start_backend.sh
./start_backend.sh
```

#### 启动前端：
```bash
chmod +x start_frontend.sh
./start_frontend.sh
```

---

## 🔍 验证服务是否正常运行

### 检查后端服务

在浏览器中访问：**http://localhost:5000/api/health**

应该看到：
```json
{"status": "ok", "message": "AI Agent服务运行正常"}
```

### 检查前端服务

访问：**http://localhost:3000**

应该看到 DeepScientist AI Agent 的界面，并且状态栏显示"服务正常"。

---

## 📝 使用应用

1. **输入研究问题**：在"研究问题"文本框中输入您的问题
2. **配置参数**（可选）：
   - 研究主题：默认为 "agent"
   - 研究方法：默认为 "LLM, Agent, Tool, Memory"
3. **点击"运行 AI Agent"**按钮
4. **等待处理**：AI Agent 处理可能需要几分钟时间
5. **查看结果**：处理完成后，结果会显示在页面上

---

## ⚠️ 常见问题

### 问题 1：后端启动失败

**错误**：`ModuleNotFoundError: No module named 'flask'`

**解决**：
```bash
pip install -r backend/requirements.txt
```

### 问题 2：前端启动失败

**错误**：`command not found: npm`

**解决**：安装 Node.js
- macOS: `brew install node`
- 或从 https://nodejs.org/ 下载安装

### 问题 3：端口被占用

**错误**：`Address already in use`

**解决**：
- 后端端口 5000 被占用：修改 `backend/app.py` 中的 `port=5000` 为其他端口
- 前端端口 3000 被占用：React 会自动提示使用其他端口

### 问题 4：前端无法连接后端

**错误**：状态栏显示"服务异常"

**解决**：
1. 确认后端服务正在运行（检查终端窗口）
2. 确认后端地址是 `http://localhost:5000`
3. 如果后端使用了其他端口，修改 `frontend/src/services/api.ts` 中的 `API_BASE_URL`

### 问题 5：Agent 处理超时

**解决**：
- 这是正常的，AI Agent 处理可能需要较长时间（几分钟到十几分钟）
- 可以在 `frontend/src/services/api.ts` 中增加 `timeout` 值（当前为 5 分钟）

---

## 🛑 停止服务

- **停止后端**：在运行后端的终端窗口按 `Ctrl + C`
- **停止前端**：在运行前端的终端窗口按 `Ctrl + C`

---

## 📦 生产环境部署

### 构建前端

```bash
cd frontend
npm run build
```

构建后的文件在 `frontend/build` 目录中。

### 运行后端（生产模式）

修改 `backend/app.py` 最后一行：
```python
app.run(debug=False, host='0.0.0.0', port=5000)
```

---

## 💡 提示

- 开发时保持两个终端窗口都打开
- 修改前端代码后，页面会自动刷新
- 修改后端代码后，需要重启后端服务
- 查看浏览器控制台（F12）可以查看详细的错误信息
