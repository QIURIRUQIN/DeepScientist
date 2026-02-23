import time
import json
import logging
import os
from datetime import datetime
from functools import wraps
from typing import Callable, Dict, Any

_timing_stats = {}
_timing_logger = None

def get_timing_logger(log_dir: str = "./outputs/logs", agent_name: str = "workflow"):
    """
    获取或创建一个时间记录logger
    
    Args:
        log_dir: 日志保存目录
        agent_name: agent名称，用于区分不同的logger
    
    Returns:
        logger实例和日志文件路径
    """
    global _timing_logger
    
    os.makedirs(log_dir, exist_ok=True)
    
    logger_name = f"timing_logger_{agent_name}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.handlers = [] 
    logger.propagate = False
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    log_file = os.path.join(log_dir, f"timing_{agent_name}_{timestamp}.log")
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    return logger, log_file

def time_node(agent_name: str, node_name: str, logger: logging.Logger = None):
    """
    装饰器：为节点函数添加时间记录
    
    Args:
        agent_name: agent名称（如 "paperSearcher", "AIScientist"）
        node_name: 节点名称（如 "refine_query", "search_papers"）
        logger: 可选的logger实例，如果不提供则使用全局logger
    
    Usage:
        @time_node("paperSearcher", "refine_query", logger)
        def refine_query(state):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(state):
            # 使用提供的logger或全局logger
            log = logger or _timing_logger
            
            start_time = time.time()
            if log:
                log.info(f"[{agent_name}] 开始执行节点: {node_name}")
            
            try:
                result = func(state)
                elapsed = time.time() - start_time
                
                if log:
                    log.info(f"[{agent_name}] 节点 {node_name} 执行完成，耗时: {elapsed:.2f}秒")
                
                # 记录到统计数据
                key = f"{agent_name}.{node_name}"
                if key not in _timing_stats:
                    _timing_stats[key] = []
                
                _timing_stats[key].append({
                    "start_time": datetime.fromtimestamp(start_time).isoformat(),
                    "elapsed_seconds": round(elapsed, 2)
                })
                
                return result
                
            except Exception as e:
                elapsed = time.time() - start_time
                if log:
                    log.error(f"[{agent_name}] 节点 {node_name} 执行失败: {str(e)}, 耗时: {elapsed:.2f}秒")
                raise e
        
        return wrapper
    return decorator

def save_timing_stats(log_dir: str = "./outputs/results", agent_name: str = "workflow"):
    """
    保存时间统计数据到JSON文件
    
    Args:
        log_dir: 保存目录
        agent_name: agent名称
    """
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stats_file = os.path.join(log_dir, f"timing_stats_{agent_name}_{timestamp}.json")
    
    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(_timing_stats, f, indent=2, ensure_ascii=False)
    
    return stats_file

def get_timing_stats() -> Dict[str, Any]:
    """获取当前的时间统计数据"""
    return _timing_stats.copy()

def clear_timing_stats():
    """清除时间统计数据"""
    global _timing_stats
    _timing_stats = {}

# 向后兼容的旧函数
def setup_runtiem_logger(log_dir: str):
    """向后兼容的logger设置函数"""
    return get_timing_logger(log_dir)

def time_subgraph(subgraph, node, logger):
    """向后兼容的subgraph时间记录函数"""
    def wrapper(state):
        st = time.time()
        logger.info(f"Starting {node} subgraph")
        try:
            result = subgraph(state)
            elapsed = time.time() - st
            logger.info(f"Finished {node} subgraph in {elapsed:.2f} seconds")
            return result
        except Exception as e:
            elapsed = time.time() - st
            logger.error(f"Error in {node} subgraph: {e}")
            logger.error(f"Time taken: {elapsed:.2f} seconds")
            raise e
    return wrapper