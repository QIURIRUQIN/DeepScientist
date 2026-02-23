from typing_extensions import TypedDict
from typing import List, Dict, Any, Optional
from loguru import logger
import os

from langchain_core.messages import ToolMessage
from langchain_core.messages.utils import count_tokens_approximately

from tools.rag import vector_search

class State(TypedDict):
    # for all
    messages: list # 所有的信息

    # for literature search
    original_query: str # 用户的原始输入
    refined_query: str # 经过 deepseek 润色之后的 query
    paper_urls: list # 文献的 url list
    downloaded_papers: list # 下载的文献的路径 list
    save_path: str

    # for literature parsing
    parsed_multimodal_content: List[Dict[str, Any]]
    report_draft: Dict[str, str]
    structured_methodology: List[Dict[str, Any]]
    methodology_path: Optional[str]
    errors: List[str]
    processed_papers: set
    current_paper: str

    # for AIScientist
    # question: str
    literature_summary: Dict[str, Any]
    methodology_summary: Dict[str, Any]
    new_idea: str
    motivation: str
    download_path: str
    dataset: str
    dataset_url: str
    subplans: dict # 生成代码的子计划

    # for data analysis
    load_result: dict
    column_meaning: dict
    column_statistics: dict
    final_report: str
    final_data_report: str

    # for code generation
    methods_description: str
    critique_feedback: str
    iteration_count: int
    generated_code: str
    execution_result: Dict[str, Any]
    execution_success: bool
    error_message: str
    quality_score: float
    final_output: Dict[str, Any]       # 最终输出
    output_figures: list          # 输出图表路径
    output_tables: list           # 输出表格路径
    performance_metrics: Dict[str, float]  # 性能指标
    input_data_path: str # 数据的地址，可能有可能没有，可能是 .csv 格式，也可能不是

    # for latex writer
    summary: str
    topic: str
    latex_draft: str
    latex_evaluation: str
    latex_revision: str
    results: str
    revision_count: int

    # Tools info
    literature_tool_call_counter: int
    dataset_tool_call_counter: int

def react_pre_model_wrapper(vector_search_question: str):
    """
    创建一个预处理模型的包装器，用于在将消息传递给模型之前进行处理
    
    Args:
        vector_search_question: 用于向量搜索的问题
        
    Returns:
        一个预处理函数，用于处理状态中的消息
    """
    def react_pre_model_hook(state):
        """
        在模型调用前处理状态中的消息，特别是处理过长的工具消息
        """
        logger.info(f"React pre model hook called with llm input message len {len(state['messages'])}")
        # 如果工具返回信息太多，用向量搜索
        max_tool_token_cnt = int(os.environ.get("MAX_TOOL_TOKEN_CNT", 2000))
        for message_i, message in enumerate(state["messages"]):
            # 如果 MEssage 是 ToolMessage 类型就进入分支 
            if isinstance(message, ToolMessage):
                token_cnt = count_tokens_approximately([message])
                if token_cnt > max_tool_token_cnt * 2:
                    short_message = vector_search_match_type(message, vector_search_question, token_cnt=max_tool_token_cnt)
                    logger.info(f"Message is too long ({token_cnt}), "
                                f"use vector search to summarize to ({count_tokens_approximately([short_message])})")
                    state["messages"][message_i] = short_message
        return state

    return react_pre_model_hook


def vector_search_match_type(message: str, query: str, token_cnt: int = 10000):
    """
    根据消息类型执行向量搜索并保持消息类型一致
    
    Args:
        message: 原始消息
        query: 查询语句
        token_cnt: 最大token数量
        
    Returns:
        处理后的消息，保持原始消息类型
    """
    message_type = type(message)
    short_messages = vector_search([message], query, token_cnt=token_cnt)
    # 合并
    all_content = [message.content for message in short_messages]
    if message_type == ToolMessage:
        return message_type(content="\n".join(all_content), tool_call_id=message.tool_call_id, name=message.name, status=message.status)
    else:
        return message_type("\n".join(all_content))
