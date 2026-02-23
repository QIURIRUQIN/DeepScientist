from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
import os
import sys
import json
import time
from langchain_core.load import dumps, loads
import traceback

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 延迟导入，避免启动时就执行可能失败的操作
print("=" * 60)
print("🔍 正在检查依赖和导入模块...")
print("=" * 60)

_import_success = False
_import_error = None

try:
    print("📦 尝试导入 run_graph 模块...")
    from run_graph import build_graph, main
    from run_graph_with_progress import main_with_progress
    _import_success = True
    _import_error = None
    print("✅ run_graph 模块导入成功！")
except ImportError as e:
    _import_success = False
    _import_error = str(e)
    print("=" * 60)
    print("❌ 错误: 导入 run_graph 失败！")
    print(f"   错误信息: {e}")
    print("=" * 60)
    print("💡 解决方案:")
    print("   1. 安装缺失的依赖:")
    print("      cd backend && pip install -r requirements.txt")
    print("   2. 或运行安装脚本:")
    print("      ./install_dependencies.sh")
    print("=" * 60)
    traceback.print_exc()
except Exception as e:
    _import_success = False
    _import_error = str(e)
    print("=" * 60)
    print("❌ 错误: 导入 run_graph 时出现异常！")
    print(f"   错误信息: {e}")
    print("=" * 60)
    traceback.print_exc()
    print("=" * 60)

if _import_success:
    print("✅ 所有模块检查完成，服务可以正常使用")
else:
    print("⚠️  警告: 服务已启动，但 AI Agent 功能可能无法使用")
    print("   请检查上述错误信息并安装缺失的依赖")
print("=" * 60)
print()

app = Flask(__name__)
CORS(app)  # 允许跨域请求

@app.route('/', methods=['GET'])
def index():
    """根路径，提供 API 信息"""
    return jsonify({
        "service": "DeepScientist AI Agent API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "status": "/api/status",
            "run_agent": "/api/run-agent (POST)"
        },
        "message": "请访问前端应用: http://localhost:3000"
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    if not _import_success:
        return jsonify({
            "status": "error",
            "message": "AI Agent模块导入失败",
            "error": _import_error
        }), 500
    return jsonify({"status": "ok", "message": "AI Agent服务运行正常"})

def serialize_state(state):
    """序列化状态，将LangChain消息对象转换为可序列化的格式"""
    if not isinstance(state, dict):
        return state
    
    serialized = {}
    for key, value in state.items():
        if key == "messages" and isinstance(value, list):
            # 使用LangChain的dumps函数序列化消息列表
            try:
                # 尝试使用LangChain的序列化
                serialized[key] = loads(dumps(value))
            except Exception:
                # 如果失败，手动转换
                serialized_messages = []
                for msg in value:
                    if hasattr(msg, 'content'):
                        serialized_messages.append({
                            "type": type(msg).__name__,
                            "content": str(msg.content) if hasattr(msg, 'content') else str(msg)
                        })
                    else:
                        serialized_messages.append(str(msg))
                serialized[key] = serialized_messages
        elif isinstance(value, dict):
            # 递归处理嵌套字典
            serialized[key] = serialize_state(value)
        elif isinstance(value, list):
            # 处理列表，检查是否包含需要序列化的对象
            serialized_list = []
            for item in value:
                if hasattr(item, 'content') or hasattr(item, '__dict__'):
                    # 可能是LangChain对象
                    try:
                        serialized_list.append(loads(dumps(item)))
                    except Exception:
                        serialized_list.append(str(item))
                else:
                    serialized_list.append(item)
            serialized[key] = serialized_list
        else:
            # 尝试直接序列化，如果失败则转换为字符串
            try:
                # 检查是否是LangChain对象
                if hasattr(value, 'content') or hasattr(value, '__dict__'):
                    try:
                        serialized[key] = loads(dumps(value))
                    except Exception:
                        serialized[key] = str(value)
                else:
                    json.dumps(value)  # 测试是否可以序列化
                    serialized[key] = value
            except (TypeError, ValueError):
                serialized[key] = str(value)
    
    return serialized

def send_sse_event(event_type, data):
    """发送SSE事件"""
    # 如果数据中包含final_state，需要先序列化
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
        if "final_state" in data["data"]:
            try:
                data["data"]["final_state"] = serialize_state(data["data"]["final_state"])
            except Exception as e:
                print(f"⚠️  序列化final_state时出错: {e}")
                # 如果序列化失败，移除final_state或使用简化版本
                final_state = data["data"]["final_state"]
                data["data"]["final_state"] = {
                    "error": "无法序列化完整状态",
                    "keys": list(final_state.keys()) if isinstance(final_state, dict) else []
                }
    
    try:
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"
    except Exception as e:
        print(f"⚠️  序列化SSE数据时出错: {e}")
        # 返回错误信息
        error_data = {
            "error": f"序列化错误: {str(e)}",
            "event_type": event_type
        }
        return f"event: error\ndata: {json.dumps(error_data, ensure_ascii=False)}\n\n"

@app.route('/api/run-agent-stream', methods=['POST'])
def run_agent_stream():
    """运行AI Agent的流式接口（支持实时进度）"""
    def generate():
        try:
            # 检查模块是否成功导入
            if not _import_success:
                yield send_sse_event("error", {
                    "success": False,
                    "error": f"AI Agent模块未正确导入: {_import_error}",
                    "detail": "请检查后端日志以获取更多信息"
                })
                return
            
            data = request.get_json()
            
            # 获取请求参数
            original_query = data.get('original_query', '')
            messages = data.get('messages', [])
            topic = data.get('topic', 'agent')
            results = data.get('results', '')
            methodology = data.get('methodology', 'LLM, Agent, Tool, Memory')
            
            if not original_query:
                yield send_sse_event("error", {
                    "success": False,
                    "error": "original_query参数不能为空"
                })
                return
            
            # 定义工作流步骤
            workflow_steps = [
                {"id": "literature_search", "name": "文献搜索", "status": "pending"},
                {"id": "literature_parser", "name": "文献解析", "status": "pending"},
                {"id": "AIScientist", "name": "AI科学家分析", "status": "pending"},
                {"id": "data_analyser", "name": "数据分析", "status": "pending"},
                {"id": "code_experiment", "name": "代码实验", "status": "pending"},
                {"id": "latex_writer", "name": "LaTeX文档生成", "status": "pending"},
            ]
            
            # 发送开始事件
            yield send_sse_event("start", {
                "message": "开始运行 AI Agent",
                "query": original_query,
                "steps": workflow_steps
            })
            
            # 导入带进度回调的main函数
            from run_graph_with_progress import main_with_progress
            
            # 创建进度回调函数（使用生成器来发送事件）
            progress_queue = []
            
            def progress_callback(step_name, status, data=None):
                # 更新步骤状态
                for step in workflow_steps:
                    if step["id"] == step_name:
                        step["status"] = status
                        break
                
                # 将进度事件加入队列
                progress_queue.append({
                    "step": step_name,
                    "status": status,
                    "steps": workflow_steps.copy(),
                    "data": data or {}
                })
            
            # 运行agent（使用流式版本）
            print(f"🚀 开始运行 AI Agent（流式），查询: {original_query}")
            
            # 使用队列来在线程间通信
            import queue
            import threading
            
            progress_queue_thread = queue.Queue()
            result_queue = queue.Queue()
            
            def run_agent():
                try:
                    def thread_progress_callback(step_name, status, data=None):
                        # 将进度事件放入队列
                        progress_queue_thread.put({
                            "step": step_name,
                            "status": status,
                            "data": data or {}
                        })
                    
                    final_state = main_with_progress(
                        original_query=original_query,
                        messages=messages,
                        topic=topic,
                        results=results,
                        methodology=methodology,
                        progress_callback=thread_progress_callback
                    )
                    result_queue.put(("success", final_state))
                except Exception as e:
                    result_queue.put(("error", e))
            
            # 启动agent执行线程
            agent_thread = threading.Thread(target=run_agent, daemon=True)
            agent_thread.start()
            
            # 定期发送进度更新
            try:
                while agent_thread.is_alive() or not progress_queue_thread.empty():
                    # 发送队列中的进度事件
                    try:
                        while True:
                            event_data = progress_queue_thread.get_nowait()
                            # 更新步骤状态
                            step_id = event_data.get("step", "")
                            status = event_data.get("status", "")
                            
                            for step in workflow_steps:
                                if step["id"] == step_id:
                                    step["status"] = status
                                    break
                            
                            # 发送进度更新
                            yield send_sse_event("progress", {
                                "step": step_id,
                                "status": status,
                                "steps": workflow_steps.copy(),
                                "data": event_data.get("data", {})
                            })
                    except queue.Empty:
                        pass
                    
                    time.sleep(0.3)  # 每0.3秒检查一次
                
                # 等待线程完成并获取结果
                agent_thread.join(timeout=1)
                
                # 检查结果
                if not result_queue.empty():
                    result_type, result = result_queue.get()
                    
                    if result_type == "error":
                        raise result
                    
                    final_state = result
                    print("✅ AI Agent 运行完成")
                    
                    # 发送完成事件
                    yield send_sse_event("complete", {
                        "success": True,
                        "data": {
                            "latex_revision": final_state.get("latex_revision", ""),
                            "topic": final_state.get("topic", ""),
                            "results": final_state.get("results", ""),
                            "summary": final_state.get("summary", ""),
                            "new_idea": final_state.get("new_idea", ""),
                            "motivation": final_state.get("motivation", ""),
                            "final_state": final_state
                        }
                    })
                else:
                    raise Exception("Agent执行超时或未返回结果")
                
            except Exception as e:
                error_trace = traceback.format_exc()
                print(f"❌ 运行 AI Agent 时出错: {e}")
                yield send_sse_event("error", {
                    "success": False,
                    "error": str(e),
                    "traceback": error_trace if app.debug else None
                })
                
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"❌ 流式接口错误: {e}")
            yield send_sse_event("error", {
                "success": False,
                "error": str(e),
                "traceback": error_trace if app.debug else None
            })
    
    return Response(stream_with_context(generate()), mimetype='text/event-stream')

@app.route('/api/run-agent', methods=['POST'])
def run_agent():
    """运行AI Agent的主接口（兼容旧版本）"""
    try:
        # 检查模块是否成功导入
        if not _import_success:
            return jsonify({
                "success": False,
                "error": f"AI Agent模块未正确导入: {_import_error}",
                "detail": "请检查后端日志以获取更多信息"
            }), 500
        
        data = request.get_json()
        
        # 获取请求参数，设置默认值
        original_query = data.get('original_query', '')
        messages = data.get('messages', [])
        topic = data.get('topic', 'agent')
        results = data.get('results', '')
        methodology = data.get('methodology', 'LLM, Agent, Tool, Memory')
        
        if not original_query:
            return jsonify({
                "success": False,
                "error": "original_query参数不能为空"
            }), 400
        
        # 调用main函数运行agent
        print(f"🚀 开始运行 AI Agent，查询: {original_query}")
        final_state = main(
            original_query=original_query,
            messages=messages,
            topic=topic,
            results=results,
            methodology=methodology
        )
        print("✅ AI Agent 运行完成")
        
        # 返回结果
        return jsonify({
            "success": True,
            "data": {
                "latex_revision": final_state.get("latex_revision", ""),
                "topic": final_state.get("topic", ""),
                "results": final_state.get("results", ""),
                "summary": final_state.get("summary", ""),
                "new_idea": final_state.get("new_idea", ""),
                "motivation": final_state.get("motivation", ""),
                "final_state": final_state
            }
        })
        
    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"❌ 运行 AI Agent 时出错: {e}")
        print(f"错误详情:\n{error_trace}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": error_trace if app.debug else None
        }), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """获取服务状态"""
    return jsonify({
        "status": "running",
        "service": "AI Agent Web Service"
    })

if __name__ == '__main__':
    print()
    print("🚀 启动 Flask 服务器...")
    print(f"   后端服务地址: http://localhost:5000")
    print(f"   健康检查: http://localhost:5000/api/health")
    if not _import_success:
        print(f"   ⚠️  注意: AI Agent 模块未正确导入，请检查依赖")
    print("   按 Ctrl+C 停止服务")
    print()
    # 开发环境配置
    app.run(debug=True, host='0.0.0.0', port=5000)
