import os
import sys
import logging
from typing import Dict, Any

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END, START
import dotenv
dotenv.load_dotenv()

from utils.state import State
from tools.pdf_parser_tools import PDFParserTool
from tools.summary_tools import SummaryWriterTool
from tools.methodology_tools import MethodologyWriterTool
from utils.node import SimpleToolNode
from utils.tool_utils import route_by_tool_call_summary, route_methodology_workflow, route_pdf_parser_workflow
from tools.chatbot import create_simple_chatbot, create_methodology_chatbot, create_pdf_parser_chatbot
from tools.timing import get_timing_logger, time_node

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/pdfParser.md"), "r", encoding="utf-8") as f:
    pdf_parser_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/paperSummary.md"), "r", encoding="utf-8") as f:
    summary_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/methodologySummary.md"), "r", encoding="utf-8") as f:
    methodology_prompt_template = f.read()

logger = logging.getLogger(__name__)

def ensure_dirs():
    dirs = [
        "../outputs/reports",
        "../outputs/methods",
        "../outputs/pdf",
        "../outputs/markdown"
    ]
    for dir in dirs:
        os.makedirs(dir, exist_ok=True)

# def state_to_dict(state: State) -> Dict[str, Any]:
#     """Convert State object to dictionary for LangGraph compatibility."""
#     return {
#         "pdf_files": state.pdf_files,
#         "parsed_multimodal_content": state.parsed_multimodal_content,
#         "report_draft": state.report_draft,
#         "structured_methodology": state.structured_methodology,
#         "methodology_path": state.methodology_path,
#         "errors": state.errors,
#         "messages": [],                  # Add messages list for LangGraph
#         "processed_papers": set(),  # Track processed papers
#         "current_paper": {}              # Current paper context for tools
#     }

# def dict_to_state(state_dict: Dict[str, Any]) -> State:
#     """Convert dictionary back to State object."""
#     state = State()
#     for key, value in state_dict.items():
#         if key != "messages" and hasattr(state, key):
#             setattr(state, key, value)
#     return state


def build_literature_parse_subgraph(pdf_dir: str = "../outputs/pdf",
                                    md_output_dir: str = "../outputs/markdown",
                                    reports_save_path: str = "../outputs/reports/",
                                    methods_save_path: str = "../outputs/methods/") -> StateGraph:
    """
    Build a subgraph for literature parsing, including PDF parsing, summary generation, and methodology extraction.
    
    Args:
        deepseek_api_key: API key for DeepSeek models
        glm_api_key: API key for GLM models
        pdf_dir: Directory containing PDF files to parse
        md_output_dir: Directory for markdown output
    
    Returns:
        Compiled StateGraph
    """
    ensure_dirs()
    
    timing_logger, log_file = get_timing_logger(
        log_dir="./outputs/logs/paperReader",
        agent_name='paperReader'
    )
    timing_logger.info("="*60)
    timing_logger.info("Initialize paperReader subgraph")
    timing_logger.info("="*60)

    # Initialize LLMs
    pdf_parser_llm = init_chat_model(
        model=os.environ.get("MODEL", "deepseek-chat"),
        base_url=os.environ.get("OPENAI_BASE_URL", " "),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    
    summary_llm = init_chat_model(
        model=os.environ.get("MODEL", "deepseek-reasoner"),
        base_url=os.environ.get("OPENAI_BASE_URL", " "),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}},
    )
    
    methodology_multimodal_llm = init_chat_model(
        model=os.environ.get("MODEL", "glm-4.6v"),
        base_url=os.environ.get("ZHIPU_URL", " "),
        model_provider="openai",
        api_key=os.environ.get("ZHIPU_API_KEY", " "),
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )
    
    # tools
    pdf_parser_tools = [PDFParserTool(pdf_dir=pdf_dir, md_output_dir=md_output_dir)]
    summary_tools = [SummaryWriterTool(save_path=reports_save_path, file_name="report_draft.md")]
    methodology_tools = [MethodologyWriterTool(save_path=methods_save_path)]
    
    # Bind tools to LLMs
    pdf_parser_llm = pdf_parser_llm.bind_tools(pdf_parser_tools, tool_choice="pdf_parser_tool")
    summary_llm = summary_llm.bind_tools(summary_tools)
    methodology_llm = methodology_multimodal_llm
    
    # Create chatbot and tool nodes
    pdf_parser_chatbot = create_pdf_parser_chatbot(pdf_parser_llm, pdf_parser_prompt_template, pdf_dir=pdf_dir)
    pdf_parser_tool_node = SimpleToolNode(pdf_parser_tools)
    
    summary_chatbot = create_simple_chatbot(summary_llm, summary_prompt_template)
    summary_tool_node = SimpleToolNode(summary_tools)
    
    methodology_chatbot = create_methodology_chatbot(
            llm_with_tools=methodology_llm, 
            prompt_template=methodology_prompt_template, 
            md_output_dir=md_output_dir,
            methods_save_path=methods_save_path
        )    
    methodology_tool_node = SimpleToolNode(methodology_tools) 

    pdf_parser_chatbot = time_node("paperReader", "pdf_parser_chatbot", timing_logger)(pdf_parser_chatbot)
    pdf_parser_tool_node = time_node("paperReader", "pdf_parser_tool", timing_logger)(pdf_parser_tool_node)
    summary_chatbot = time_node("paperReader", "summary_chatbot", timing_logger)(summary_chatbot)
    summary_tool_node = time_node("paperReader", "summrt_tool", timing_logger)(summary_tool_node)
    methodology_chatbot = time_node("paperReader", "methodology_chatbot", timing_logger)(methodology_chatbot)
    methodology_tool_node = time_node("paperReader", "methodology_tool", timing_logger)(methodology_tool_node)

    
    # Build the graph
    graph = StateGraph(State)
    
    # Add nodes
    graph.add_node("pdf_parser_chatbot", pdf_parser_chatbot)
    graph.add_node("pdf_parser_tool_node", pdf_parser_tool_node)
    graph.add_node("summary_chatbot", summary_chatbot)
    graph.add_node("summary_tool_node", summary_tool_node)
    graph.add_node("methodology_chatbot", methodology_chatbot)
    graph.add_node("methodology_tool_node", methodology_tool_node)
    
    # Add edges
    graph.add_edge(START, "pdf_parser_chatbot")
    graph.add_conditional_edges(
        "pdf_parser_chatbot",
        route_pdf_parser_workflow,
        {
            "TOOLS": "pdf_parser_tool_node",
            "CONTINUE": "pdf_parser_chatbot",
            "END": "summary_chatbot"  # After PDF parsing, go to summary
        }
    )
    graph.add_conditional_edges(
        "pdf_parser_tool_node",
        route_pdf_parser_workflow,
        {
            "TOOLS": "pdf_parser_tool_node",
            "CONTINUE": "pdf_parser_chatbot",
            "END": "summary_chatbot"  # After PDF parsing, go to summary
        }
    )
    graph.add_conditional_edges(
        "summary_chatbot",
        route_by_tool_call_summary,
        {
            "TOOLS": "summary_tool_node",
            "CONTINUE": "summary_chatbot",
            "END": "methodology_chatbot"  # After summary, go to methodology
        }
    )
    graph.add_conditional_edges(
        "summary_tool_node",
        route_by_tool_call_summary,
        {
            "TOOLS": "summary_tool_node",
            "CONTINUE": "summary_chatbot",
            "END": "methodology_chatbot"  # After summary, go to methodology
        }
    )
    graph.add_conditional_edges(
        "methodology_chatbot",
        route_methodology_workflow,
        {
            "TOOLS": "methodology_tool_node",
            "CONTINUE": "methodology_chatbot",
            "END": END
        }
    )
    # graph.add_conditional_edges(
    #     "methodology_tool_node",
    #     route_methodology_workflow,
    #     {
    #         "TOOLS": "methodology_tool_node",
    #         "CONTINUE": "methodology_chatbot",
    #         "END": END
    #     }
    # )

    graph.add_conditional_edges(
        "methodology_tool_node",
        route_methodology_workflow,
        {
            "TOOLS": END,
            "CONTINUE": END,
            "END": END
        }
    )
    
    return graph.compile()

if __name__ == "__main__":
    
    pdf_path = "../data/pdf/"
    md_out_path = "../res/markdown/"
    
    # Build and run the complete workflow graph (includes PDF parsing, summary, and methodology)
    graph = build_literature_parse_subgraph(
        pdf_dir=pdf_path,
        md_output_dir=md_out_path
    )
    
    init_state = {""}
    config = {"recursion_limit": 10}
    result_dict = graph.invoke(init_state, config=config)
    logger.info("🎉 工作流完成: PDF解析 -> Summary生成 -> Methodology提取")
