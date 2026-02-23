# 读取 pdf
import dotenv
import os
from loguru import logger

from langchain.chat_models import init_chat_model
from langgraph.graph import StateGraph, END, START
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.chat_models import ChatTongyi

from utils.state import State
from tools.paper_search_tool import searhArxivTool
from utils.state import State, react_pre_model_wrapper
from tools.chatbot_with_context_manager import chatbot_with_context_manager
from tools.dataset_tools import create_kaggle_tool
from tools.timing import get_timing_logger, time_node

dotenv.load_dotenv()

# 加载 prompt
with open(os.path.join(os.path.dirname(__file__), "..", "prompt/ideaGen.md")) as f:
    ideaGen_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/literatureSearch.md")) as f:
    literatureSearch_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/dataSearch.md")) as f:
    dataSearch_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/planGen.md")) as f:
    planGen_prompt_template = f.read()

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/codeGen.md")) as f:
    codeGen_prompt_template = f.read()

# with open(os.path.join(os.path.dirname(__file__), "..", "prompt/dataAnalysis.md")) as f:
#     dataAnalysis_prompt_template = f.read()

def build_AIScientist_subgraph(config):
    """
    构建文献 AIScientist 子图，使用 ArXiv 搜索文献并通过嵌入模型进行RAG处理生成文献调研报告
    """

    timing_logger, log_file = get_timing_logger(
        log_dir="./outputs/logs/AIScientist",
        agent_name='AIScientist'
    )
    timing_logger.info("="*60)
    timing_logger.info("Initialize AIScientist subgraph")
    timing_logger.info("="*60)

    # Step_1: generate new idea from existing literature
    ideaGen_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-chat"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )

    # Step_2: search related literature
    literatureSearch_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-chat"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )

    # # Step_3: verify whether idea has been employed or not
    # ideaVerify_llm = init_chat_model(
    #     os.environ.get("MODEL", "deepseek-reasoner"),
    #     base_url=os.environ.get("BASE_URL", ""),
    #     model_provider="openai",
    #     extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    # )

    # Step_4: search relevant data to verify generated ideas
    # dataSearch_llm = init_chat_model(
    #     os.environ.get("MODEL", "deepseek-chat"),
    #     base_url=os.environ.get("OPENAI_BASE_URL", ""),
    #     model_provider="openai",
    #     extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    # )
    dataSearch_llm = ChatTongyi(
                model="qwen-plus",
                temperature=0.7,
                dashscope_api_key=os.environ.get("QWEN_API_KEY", " ")
            )
    # Step_5: generate specified plans including some subplans to generate code later
    planGen_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-chat"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )

    # Step_6: according to plans to generate code
    codeGen_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-reasoner"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )

    literature_search_tools = [
        searhArxivTool(),
    ]
    # llm_literature_search_react = create_react_agent(literatureSearch_llm, literature_search_tools, pre_model_hook=react_pre_model_wrapper(config.question))
    llm_literature_search_react = literatureSearch_llm.bind_tools(literature_search_tools)
    
    # dataset_search_tools = [
    #     TavilySearchResults(max_results=10)
    # ]
    # llm_dataset_search_react = create_react_agent(dataSearch_llm, dataset_search_tools, pre_model_hook=react_pre_model_wrapper(config.question))
    # dataSearch_llm = dataSearch_llm.bind_tools(dataset_search_tools)
    # planGen_llm = planGen_llm.bind_tools(dataset_search_tools)

    # 准备 llm
    idea_generation_chatbot = chatbot_with_context_manager(
        config, ideaGen_llm, ideaGen_prompt_template, context_manage="vector_search", calling_subgraph="idea_generation"
    )
    literature_search_chabot = chatbot_with_context_manager(
        config, llm_literature_search_react, literatureSearch_prompt_template, context_manage="vector_search", calling_subgraph="literature_search"
    )
    dataset_search_chatbot = chatbot_with_context_manager(
        config, dataSearch_llm, dataSearch_prompt_template, context_manage="vector_search", calling_subgraph="dataset_search"
    )
    plan_generation_chatbot = chatbot_with_context_manager(
        config, planGen_llm, planGen_prompt_template, context_manage="vector_search", calling_subgraph="plan_generation"
    )
    code_generation_chatbot = chatbot_with_context_manager(
        config, codeGen_llm, codeGen_prompt_template, context_manage="vector_search", calling_subgraph="code_generation"
    )

    def router_by_idea(state: State):
        if ("HIGH_SIMILARITY" in state["messages"][-1].content) and (state["literature_tool_call_counter"] <= 5):
            return "RETURN"
        else:
            return "CONTINUE"
        
    def load_summaries(state: State):
        state["literature_summary"] = dict()
        l_summary_path = os.path.join(os.path.dirname(__file__), "..", "outputs/reports")
        for file in os.listdir(l_summary_path):
            if file.endswith(".md"):
                with open(os.path.join(l_summary_path, file), "r") as f:
                    state["literature_summary"][file] = f.read()

        state["methodology_summary"] = dict()
        m_summary_path = os.path.join(os.path.dirname(__file__), "..", "outputs/methods")
        for file in os.listdir(m_summary_path):
            if file.endswith(".md"):
                with open(os.path.join(m_summary_path, file), "r") as f:
                    state["methodology_summary"][file] = f.read()

        return state
    
    dataset_downloader = create_kaggle_tool()

    load_summaries = time_node("AIScientist", "load_summaries", timing_logger)(load_summaries)
    idea_generation_chatbot_ = time_node("AIScientist", "idea_generation_chatbot", timing_logger)(idea_generation_chatbot)
    literature_search_chabot_ = time_node("AIScientist", "literature_search_chabot", timing_logger)(literature_search_chabot)
    dataset_search_chatbot_ = time_node("AIScientist", "data_search_chabot", timing_logger)(dataset_search_chatbot)
    plan_generation_chatbot_ = time_node("AIScientist", "plan_generation_chatbot", timing_logger)(plan_generation_chatbot)
    code_generation_chatbot_ = time_node("AIScientist", "code_generation_chatbot", timing_logger)(code_generation_chatbot)
    dataset_downloader_ = time_node("AIScientist", "dataset_downloader", timing_logger)(dataset_downloader)

        
    graph = StateGraph(State)

    graph.add_node("load_summaries", load_summaries)
    graph.add_node("idea_generation_chatbot", idea_generation_chatbot_)
    graph.add_node("literature_search_chabot", literature_search_chabot_)
    graph.add_node("dataset_search_chatbot", dataset_search_chatbot_)
    graph.add_node("dataset_downloader", dataset_downloader_)
    graph.add_node("plan_generation_chatbot", plan_generation_chatbot_)
    graph.add_node("code_generation_chatbot", code_generation_chatbot_)
    
    graph.add_edge(START, "load_summaries")
    graph.add_edge("load_summaries", "idea_generation_chatbot")
    graph.add_edge("idea_generation_chatbot", "literature_search_chabot")
    graph.add_conditional_edges("literature_search_chabot", router_by_idea, {"RETURN": "idea_generation_chatbot", "CONTINUE": "dataset_search_chatbot"})
    graph.add_edge("dataset_search_chatbot", "dataset_downloader")
    graph.add_edge("dataset_downloader", "plan_generation_chatbot")
    graph.add_edge("plan_generation_chatbot", "code_generation_chatbot")
    graph.add_edge("code_generation_chatbot", END)

    return graph.compile()

if __name__ == "__main__":
    with open(os.path.join(os.path.dirname(__file__), "..", "data/test.md")) as f:
        paper = f.read()

    initial_state = {"literature_summary": paper, 
                     "methodology_summary": paper,
                     "question": ""}

    graph = build_AIScientist_subgraph()
    graph.invoke(initial_state)
