"""
工作流轨迹记录工具
用于记录每次代码运行的完整轨迹，包括节点执行、状态变化、错误信息等
"""
import os
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from loguru import logger
from langchain_core.load import dumps, loads


class WorkflowTracer:
    """工作流轨迹记录器"""
    
    def __init__(self, log_dir: str = "./outputs/logs/workflow_traces", run_id: Optional[str] = None):
        """
        初始化轨迹记录器
        
        Args:
            log_dir: 日志保存目录
            run_id: 运行ID，如果不提供则自动生成
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # 生成运行ID
        if run_id is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            run_id = f"run_{timestamp}"
        self.run_id = run_id
        
        # 轨迹数据
        self.trace_data = {
            "run_id": self.run_id,
            "start_time": None,
            "end_time": None,
            "duration_seconds": None,
            "initial_state": {},
            "final_state": {},
            "nodes": [],  # 节点执行记录
            "errors": [],  # 错误记录
            "summary": {
                "total_nodes": 0,
                "successful_nodes": 0,
                "failed_nodes": 0,
                "total_duration": 0.0
            }
        }
        
        # 日志文件路径
        self.json_log_path = self.log_dir / f"trace_{self.run_id}.json"
        self.text_log_path = self.log_dir / f"trace_{self.run_id}.log"
        
        # 初始化文本日志
        self._init_text_logger()
        
    def _init_text_logger(self):
        """初始化文本日志记录器"""
        # 添加轨迹日志文件（不移除默认handler，避免影响其他日志）
        logger.add(
            str(self.text_log_path),
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
            level="DEBUG",
            encoding="utf-8",
            rotation="100 MB",
            retention="30 days"
        )
    
    def start_run(self, initial_state: Dict[str, Any], original_query: str = ""):
        """
        开始记录一次运行
        
        Args:
            initial_state: 初始状态
            original_query: 用户原始查询
        """
        self.trace_data["start_time"] = datetime.now().isoformat()
        self.trace_data["initial_state"] = self._serialize_state(initial_state)
        self.trace_data["original_query"] = original_query
        
        logger.info("=" * 80)
        logger.info(f"开始工作流执行 - Run ID: {self.run_id}")
        logger.info(f"用户查询: {original_query}")
        logger.info(f"开始时间: {self.trace_data['start_time']}")
        logger.info("=" * 80)
    
    def log_node_start(self, node_name: str, node_type: str = "node"):
        """
        记录节点开始执行
        
        Args:
            node_name: 节点名称
            node_type: 节点类型（node/subgraph）
        """
        node_record = {
            "node_name": node_name,
            "node_type": node_type,
            "start_time": datetime.now().isoformat(),
            "end_time": None,
            "duration_seconds": None,
            "status": "running",
            "state_snapshot": {},
            "error": None
        }
        
        self.trace_data["nodes"].append(node_record)
        self.trace_data["summary"]["total_nodes"] += 1
        
        logger.info(f"[节点开始] {node_name} ({node_type})")
    
    def log_node_end(self, node_name: str, status: str = "completed", 
                     state_snapshot: Optional[Dict[str, Any]] = None,
                     error: Optional[str] = None):
        """
        记录节点执行结束
        
        Args:
            node_name: 节点名称
            status: 状态（completed/failed/skipped）
            state_snapshot: 状态快照
            error: 错误信息（如果有）
        """
        # 找到对应的节点记录
        node_record = None
        for node in reversed(self.trace_data["nodes"]):
            if node["node_name"] == node_name and node["status"] == "running":
                node_record = node
                break
        
        if node_record is None:
            logger.warning(f"未找到节点 {node_name} 的开始记录")
            return
        
        # 更新节点记录
        node_record["end_time"] = datetime.now().isoformat()
        node_record["status"] = status
        node_record["state_snapshot"] = self._serialize_state(state_snapshot) if state_snapshot else {}
        
        # 计算执行时间
        start_time = datetime.fromisoformat(node_record["start_time"])
        end_time = datetime.fromisoformat(node_record["end_time"])
        duration = (end_time - start_time).total_seconds()
        node_record["duration_seconds"] = round(duration, 2)
        
        if error:
            node_record["error"] = error
            self.trace_data["errors"].append({
                "node": node_name,
                "time": node_record["end_time"],
                "error": error
            })
            self.trace_data["summary"]["failed_nodes"] += 1
            logger.error(f"[节点失败] {node_name} - 错误: {error} (耗时: {duration:.2f}秒)")
        else:
            self.trace_data["summary"]["successful_nodes"] += 1
            logger.info(f"[节点完成] {node_name} (耗时: {duration:.2f}秒)")
        
        self.trace_data["summary"]["total_duration"] += duration
    
    def log_state_change(self, node_name: str, state_key: str, old_value: Any, new_value: Any):
        """
        记录状态变化
        
        Args:
            node_name: 节点名称
            state_key: 状态键
            old_value: 旧值
            new_value: 新值
        """
        # 找到当前正在执行的节点
        current_node = None
        for node in reversed(self.trace_data["nodes"]):
            if node["node_name"] == node_name and node["status"] == "running":
                current_node = node
                break
        
        if current_node:
            if "state_changes" not in current_node:
                current_node["state_changes"] = []
            
            current_node["state_changes"].append({
                "key": state_key,
                "old_value": self._serialize_value(old_value),
                "new_value": self._serialize_value(new_value),
                "timestamp": datetime.now().isoformat()
            })
    
    def log_progress(self, step: str, status: str, data: Optional[Dict[str, Any]] = None):
        """
        记录进度信息
        
        Args:
            step: 步骤名称
            status: 状态（running/completed/error）
            data: 附加数据
        """
        progress_record = {
            "step": step,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "data": self._serialize_state(data) if data else {}
        }
        
        if "progress" not in self.trace_data:
            self.trace_data["progress"] = []
        self.trace_data["progress"].append(progress_record)
        
        logger.debug(f"[进度] {step} - {status}")
    
    def end_run(self, final_state: Optional[Dict[str, Any]] = None, success: bool = True):
        """
        结束记录一次运行
        
        Args:
            final_state: 最终状态
            success: 是否成功
        """
        self.trace_data["end_time"] = datetime.now().isoformat()
        self.trace_data["final_state"] = self._serialize_state(final_state) if final_state else {}
        self.trace_data["success"] = success
        
        # 计算总执行时间
        start_time = datetime.fromisoformat(self.trace_data["start_time"])
        end_time = datetime.fromisoformat(self.trace_data["end_time"])
        duration = (end_time - start_time).total_seconds()
        self.trace_data["duration_seconds"] = round(duration, 2)
        
        logger.info("=" * 80)
        logger.info(f"工作流执行结束 - Run ID: {self.run_id}")
        logger.info(f"结束时间: {self.trace_data['end_time']}")
        logger.info(f"总耗时: {duration:.2f}秒 ({duration/60:.2f}分钟)")
        logger.info(f"执行状态: {'成功' if success else '失败'}")
        logger.info(f"节点统计: 总计 {self.trace_data['summary']['total_nodes']} 个, "
                   f"成功 {self.trace_data['summary']['successful_nodes']} 个, "
                   f"失败 {self.trace_data['summary']['failed_nodes']} 个")
        logger.info("=" * 80)
        
        # 保存轨迹数据
        self.save_trace()
    
    def save_trace(self):
        """保存轨迹数据到JSON文件"""
        try:
            with open(self.json_log_path, 'w', encoding='utf-8') as f:
                json.dump(self.trace_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"轨迹数据已保存到: {self.json_log_path}")
        except Exception as e:
            logger.error(f"保存轨迹数据失败: {e}")
    
    def _serialize_state(self, state: Any) -> Any:
        """
        序列化状态对象，处理不可序列化的对象
        
        Args:
            state: 状态对象
            
        Returns:
            序列化后的状态
        """
        if state is None:
            return None
        
        try:
            # 尝试使用LangChain的序列化
            if isinstance(state, dict):
                serialized = {}
                for k, v in state.items():
                    try:
                        serialized[k] = self._serialize_value(v)
                    except Exception:
                        serialized[k] = str(v)
                return serialized
            elif isinstance(state, (list, tuple)):
                return [self._serialize_value(item) for item in state]
            else:
                return self._serialize_value(state)
        except Exception as e:
            logger.warning(f"序列化状态时出错: {e}")
            return str(state)
    
    def _serialize_value(self, value: Any) -> Any:
        """序列化单个值"""
        if value is None:
            return None
        elif isinstance(value, (str, int, float, bool)):
            return value
        elif isinstance(value, (list, tuple)):
            return [self._serialize_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, Path):
            return str(value)
        else:
            try:
                # 尝试使用LangChain的序列化
                return loads(dumps(value))
            except Exception:
                return str(value)
    
    def get_trace_summary(self) -> Dict[str, Any]:
        """获取轨迹摘要"""
        return {
            "run_id": self.run_id,
            "start_time": self.trace_data.get("start_time"),
            "end_time": self.trace_data.get("end_time"),
            "duration_seconds": self.trace_data.get("duration_seconds"),
            "success": self.trace_data.get("success", False),
            "summary": self.trace_data.get("summary", {}),
            "error_count": len(self.trace_data.get("errors", [])),
            "json_log_path": str(self.json_log_path),
            "text_log_path": str(self.text_log_path)
        }


# 全局轨迹记录器实例
_global_tracer: Optional[WorkflowTracer] = None


def get_workflow_tracer(log_dir: str = "./outputs/logs/workflow_traces", 
                       run_id: Optional[str] = None) -> WorkflowTracer:
    """
    获取全局工作流轨迹记录器
    
    Args:
        log_dir: 日志保存目录
        run_id: 运行ID
        
    Returns:
        WorkflowTracer实例
    """
    global _global_tracer
    if _global_tracer is None:
        _global_tracer = WorkflowTracer(log_dir=log_dir, run_id=run_id)
    return _global_tracer


def reset_workflow_tracer():
    """重置全局轨迹记录器"""
    global _global_tracer
    _global_tracer = None
