import os
from typing import Callable, Optional, Dict, Any
from loguru import logger

from langgraph.graph import START, END, StateGraph
from langchain_core.load import dumps, loads

from agents.paperSearcher import build_literature_search_subgraph
from agents.paperReader import build_literature_parse_subgraph
from agents.AIScientist import build_AIScientist_subgraph
from agents.dataAnalyser import build_data_analysis_subgraph
from agents.codeGenerator import build_code_experiment_subgraph
from agents.latexWriter import build_latex_writer_agent
from utils.state import State
from utils.config import Config
from utils.workflow_tracer import get_workflow_tracer, reset_workflow_tracer
from pathlib import Path

def build_graph_with_progress(progress_callback: Optional[Callable[[str, str, Optional[Dict]], None]] = None):
    """构建带进度回调的图"""
    filePath = os.path.dirname(__file__)
    pdf_dir = os.path.join(filePath, "./outputs/papers")
    md_output_dir = os.path.join(filePath, "./outputs/markdown")
    reports_save_path = os.path.join(filePath, "./outputs/reports")
    methods_save_path = os.path.join(filePath, "./outputs/methods")

    config = Config(
        save_path=os.path.join(filePath, "./outputs/results"),
        question="please generate a new idea from existing paper summary",
        thread_id="1"
    )
    
    # 构建子图
    if progress_callback:
        progress_callback("literature_search", "running", {"message": "正在构建文献搜索子图..."})
    literature_search = build_literature_search_subgraph()
    
    if progress_callback:
        progress_callback("literature_parser", "running", {"message": "正在构建文献解析子图..."})
    literature_parser = build_literature_parse_subgraph(
        pdf_dir=pdf_dir, md_output_dir=md_output_dir,
        reports_save_path=reports_save_path, methods_save_path=methods_save_path
    )
    
    if progress_callback:
        progress_callback("AIScientist", "running", {"message": "正在构建AI科学家子图..."})
    AIScientist = build_AIScientist_subgraph(config=config)
    
    if progress_callback:
        progress_callback("data_analyser", "running", {"message": "正在构建数据分析子图..."})
    data_analyser = build_data_analysis_subgraph()
    
    if progress_callback:
        progress_callback("code_experiment", "running", {"message": "正在构建代码实验子图..."})
    code_experiment = build_code_experiment_subgraph()
    
    if progress_callback:
        progress_callback("latex_writer", "running", {"message": "正在构建LaTeX写作子图..."})
    latex_writer = build_latex_writer_agent()

    graph = StateGraph(State)

    graph.add_node("literature_search", literature_search)
    graph.add_node("literature_parser", literature_parser)
    graph.add_node("AIScientist", AIScientist)
    graph.add_node("data_analyser", data_analyser)
    graph.add_node("code_experiment", code_experiment)
    graph.add_node("latex_writer", latex_writer)

    graph.add_edge(START, "literature_search")
    graph.add_edge("literature_search", "literature_parser")
    graph.add_edge("literature_parser", "AIScientist")
    graph.add_edge("AIScientist", "data_analyser")
    graph.add_edge("data_analyser", "code_experiment")
    graph.add_edge("code_experiment", "latex_writer")
    graph.add_edge("latex_writer", END)

    graph = graph.compile()

    return graph

def _extract_paper_paths(downloaded_papers: list) -> list:
    """从downloaded_papers中提取论文路径信息"""
    paper_paths = []
    for paper in downloaded_papers:
        if isinstance(paper, (str, os.PathLike, Path)):
            paper_paths.append(str(paper))
        elif isinstance(paper, dict):
            # 处理序列化的Path对象
            if "repr" in paper:
                # 从repr中提取路径
                repr_str = paper["repr"]
                if "PosixPath('" in repr_str:
                    path = repr_str.split("PosixPath('")[1].split("')")[0]
                    paper_paths.append(path)
                elif "Path('" in repr_str:
                    path = repr_str.split("Path('")[1].split("')")[0]
                    paper_paths.append(path)
                else:
                    paper_paths.append(str(paper))
            elif "path" in paper:
                paper_paths.append(str(paper["path"]))
            else:
                paper_paths.append(str(paper))
        else:
            paper_paths.append(str(paper))
    return paper_paths

def main_with_progress(
    original_query: str = "",
    messages: list = [],
    topic: str = "agent",
    results: str = "we found that agents are progressing rapidly",
    methodology: str = "LLM, Agent, Tool, Memory",
    progress_callback: Optional[Callable[[str, str, Optional[Dict]], None]] = None
):
    """带进度回调的main函数"""
    # 初始化轨迹记录器
    filePath = os.path.dirname(__file__)
    log_dir = os.path.join(filePath, "./outputs/logs/workflow_traces")
    tracer = get_workflow_tracer(log_dir=log_dir)
    
    # 构建图
    if progress_callback:
        progress_callback("init", "running", {"message": "正在初始化工作流..."})
    
    graph = build_graph_with_progress(progress_callback)
    
    initial_state = {
        "original_query": original_query,
        "messages": messages,
        "topic": topic,
        "results": results,
        "save_path": "/Users/chongyanghe/Desktop/DeepScientist/outputs/results",
        "download_path": "/Users/chongyanghe/Desktop/DeepScientist/outputs/dataset",
        "dataset": "finance",
        "methods_description": "LLM, Agent, Tool, Memory",
        "iteration_count": 0,
        "input_data_path": "result.csv",
        "revision_count": 0,
        "quality_score": 0.9
    }
    
    # 开始记录轨迹
    tracer.start_run(initial_state, original_query)
    
    # 定义步骤映射
    step_mapping = {
        "literature_search": "文献搜索",
        "literature_parser": "文献解析",
        "AIScientist": "AI科学家分析",
        "data_analyser": "数据分析",
        "code_experiment": "代码实验",
        "latex_writer": "LaTeX文档生成"
    }
    
    # 使用stream模式执行，以便捕获中间状态
    try:
        # 执行工作流，使用stream来捕获每个节点的输出
        # graph.stream() 返回的是字典，格式为 {node_name: state}
        final_state = None
        last_step_name = None
        consecutive_empty_outputs = 0
        max_empty_outputs = 3  # 允许最多3次空输出，然后认为工作流结束
        recorded_node_starts = set()  # 跟踪已记录开始的节点，避免重复记录
        
        recursion_cfg = {"recursion_limit": 100}
        for output in graph.stream(initial_state, config=recursion_cfg):
            # output 是一个字典，例如 {"literature_search": {...state...}}
            if not output:
                consecutive_empty_outputs += 1
                # 如果连续多次空输出，可能工作流已结束
                if consecutive_empty_outputs >= max_empty_outputs:
                    logger.info("检测到连续空输出，工作流可能已结束")
                    break
                continue
            
            consecutive_empty_outputs = 0  # 重置计数器
            
            # 获取节点名称和状态
            step_name = list(output.keys())[0]
            state = output[step_name]
            last_step_name = step_name
            
            # 记录节点开始执行（如果还没有记录过）
            if step_name not in recorded_node_starts:
                logger.info(f"[节点开始] {step_name} (subgraph)")
                tracer.log_node_start(step_name, "subgraph")
                recorded_node_starts.add(step_name)
            
            # 更新进度，传递详细的状态信息
            if progress_callback:
                step_display_name = step_mapping.get(step_name, step_name)
                
                # 提取关键信息用于日志展示
                log_data = {
                    "message": f"{step_display_name}完成",
                    "state_keys": list(state.keys()) if isinstance(state, dict) else []
                }
                
                # 根据步骤提取特定信息
                if step_name == "literature_search" and isinstance(state, dict):
                    # 文献搜索阶段：提取论文URL和查询信息
                    log_data["paper_urls"] = state.get("paper_urls", [])
                    log_data["refined_query"] = state.get("refined_query", "")
                    log_data["original_query"] = state.get("original_query", "")
                    log_data["downloaded_papers"] = _extract_paper_paths(state.get("downloaded_papers", []))
                
                elif step_name == "literature_parser" and isinstance(state, dict):
                    # 文献解析阶段：提取解析结果
                    parsed_content = state.get("parsed_multimodal_content", [])
                    log_data["parsed_papers"] = [
                        {
                            "pdf_path": item.get("pdf_path", ""),
                            "status": item.get("status", "unknown"),
                            "figures_count": len(item.get("figures", [])),
                            "markdown_path": item.get("markdown_path", "")
                        }
                        for item in parsed_content
                    ]
                    log_data["parsed_count"] = len([p for p in parsed_content if p.get("status") == "success"])
                    log_data["total_papers"] = len(parsed_content)
                    
                    # 文献解析完成后，下一个节点是 AIScientist，立即记录其开始
                    # 因为子图执行时，主图可能不会立即产生输出
                    if "AIScientist" not in recorded_node_starts:
                        logger.info("[节点开始] AIScientist (subgraph)")
                        tracer.log_node_start("AIScientist", "subgraph")
                        recorded_node_starts.add("AIScientist")
                        if progress_callback:
                            progress_callback("AIScientist", "running", {"message": "AI科学家分析中..."})
                
                elif step_name == "AIScientist" and isinstance(state, dict):
                    # AI科学家阶段：提取新想法和数据集信息
                    log_data["new_idea"] = state.get("new_idea", "")
                    log_data["motivation"] = state.get("motivation", "")
                    log_data["dataset"] = state.get("dataset", "")
                    log_data["dataset_url"] = state.get("dataset_url", "")
                
                elif step_name == "data_analyser" and isinstance(state, dict):
                    # 数据分析阶段：提取分析结果
                    log_data["data_report"] = state.get("final_data_report", "")
                    log_data["column_count"] = len(state.get("column_meaning", {}))
                
                elif step_name == "code_experiment" and isinstance(state, dict):
                    # 代码实验阶段：提取代码执行信息
                    log_data["iteration_count"] = state.get("iteration_count", 0)
                    log_data["quality_score"] = state.get("quality_score", 0)
                    log_data["execution_success"] = state.get("execution_success", False)
                    log_data["output_figures_count"] = len(state.get("output_figures", []))
                
                elif step_name == "latex_writer" and isinstance(state, dict):
                    # LaTeX写作阶段：提取文档信息
                    log_data["revision_count"] = state.get("revision_count", 0)
                    log_data["latex_revision"] = state.get("latex_revision", "")[:500] if state.get("latex_revision") else ""  # 只取前500字符预览
                    # 检查是否达到最大修订次数，如果是，工作流应该结束了
                    revision_count = state.get("revision_count", 0)
                    if revision_count >= 1:
                        logger.info(f"LaTeX写作完成，修订次数：{revision_count}，工作流即将结束")
                        # 不立即break，让stream自然结束，但记录状态
                
                progress_callback(step_name, "completed", log_data)
            
            # 记录节点执行完成
            tracer.log_node_end(step_name, "completed", state_snapshot=state)
            tracer.log_progress(step_name, "completed", log_data)
            
            final_state = state
            
            # 注意：不要在这里break，让stream自然结束
            # latex_writer是子图，内部可能有多个节点，需要等待子图完全结束
        
        # 如果stream正常结束但没有final_state，尝试获取最终状态
        if final_state is None:
            logger.warning("Stream结束但未获取到最终状态，尝试使用invoke获取")
            # 如果stream失败，回退到invoke
            if progress_callback:
                progress_callback("fallback", "running", {"message": "使用标准模式执行..."})
            try:
                final_state = graph.invoke(initial_state, config=recursion_cfg)
            except Exception as e:
                logger.error(f"Invoke也失败: {e}")
                raise
        
        # 确保发送完成回调
        if progress_callback:
            # 如果最后一步是latex_writer，确保提取最终结果
            if last_step_name == "latex_writer" and isinstance(final_state, dict):
                final_log_data = {
                    "message": "所有步骤完成",
                    "revision_count": final_state.get("revision_count", 0),
                    "latex_revision": final_state.get("latex_revision", "")[:500] if final_state.get("latex_revision") else ""
                }
                progress_callback("complete", "completed", final_log_data)
            else:
                progress_callback("complete", "completed", {"message": "所有步骤完成"})
        
        logger.info("工作流执行完成")
        
        # 结束轨迹记录
        tracer.end_run(final_state, success=True)
        
        return final_state
        
    except Exception as e:
        # 记录错误
        if last_step_name:
            tracer.log_node_end(last_step_name, "failed", error=str(e))
        tracer.end_run(final_state if 'final_state' in locals() else None, success=False)
        
        if progress_callback:
            progress_callback("error", "error", {"message": f"执行出错: {str(e)}"})
        raise
    finally:
        # 重置轨迹记录器，为下次运行做准备
        reset_workflow_tracer()
