import os

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

# os.environ['HF_HUB_OFFLINE'] = '1'  # 强制离线模式
# os.environ['TRANSFORMERS_OFFLINE'] = '1' 

def build_graph():
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
    
    literature_search = build_literature_search_subgraph()
    literature_parser = build_literature_parse_subgraph(
        pdf_dir=pdf_dir, md_output_dir=md_output_dir,
        reports_save_path=reports_save_path, methods_save_path=methods_save_path
    )
    AIScientist = build_AIScientist_subgraph(config=config)
    data_analyser = build_data_analysis_subgraph()
    code_experiment = build_code_experiment_subgraph()
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

def main(
    original_query: str = "",
    messages: list = [],
    topic: str = "agent",
    results: str = "we found that agents are progressing rapidly",
    methodology: str = "LLM, Agent, Tool, Memory"
):
    graph = build_graph()
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
    final_state = graph.invoke(initial_state)

    return final_state

if __name__ == "__main__":
    # 创建 init_state
    original_query = input("请输入您的研究问题：")

    final_state = main(
        original_query=original_query,
        messages=[]
    )
    with open("./state.json", "w") as f:
        f.write(dumps(final_state, indent=4))

    # 输出/储存结果
    print(final_state["latex_revision"])
    with open("./state.json", "w") as f:
            f.write(dumps(final_state, indent=4))

    with open("./res.md", "w") as f:
            f.write(final_state["latex_revision"])
