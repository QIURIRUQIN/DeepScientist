import os
import dotenv
from loguru import logger

from langchain.chat_models import init_chat_model
from langgraph.graph import START, END, StateGraph
from langchain_community.tools.tavily_search import TavilySearchResults

from tools.timing import get_timing_logger, time_node
from tools.paper_search_tool import searhArxivTool
from utils.state import State
from tools.chatbot_for_latexWriter import create_agent
dotenv.load_dotenv()

# 写 latex
with open(os.path.join(os.path.dirname(__file__), '../prompt/latex_writer.md'), 'r') as f:
    latexWriter_prompt = f.read()
# 检查 latex
with open(os.path.join(os.path.dirname(__file__), '../prompt/latex_evaluator.md'), 'r') as f:
    latexEvaluate_prompt = f.read()
# 润色 latex
with open(os.path.join(os.path.dirname(__file__), '../prompt/latex_rewriter.md'), 'r') as f:
    latexRewriter_prompt = f.read()

def build_latex_writer_agent() -> StateGraph:
    """Build LaTeX Writer Agent."""
    # 初始化 Agent\

    timing_logger, log_file = get_timing_logger(
        log_dir="./outputs/logs/latexWriter",
        agent_name='latexWriter'
    )
    timing_logger.info("="*60)
    timing_logger.info("Initialize latexWriter subgraph")
    timing_logger.info("="*60)

    """写 latex 初稿的 agent"""
    latexWriter_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-reasoner"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )
    """评估 latex 质量的 agent"""
    latexEvaluator_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-chat"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )
    """润色 latex 的 agent"""
    latexRewriter_llm = init_chat_model(
        os.environ.get("MODEL", "deepseek-reasoner"),
        base_url=os.environ.get("OPENAI_BASE_URL", ""),
        model_provider="openai",
        extra_body={"chat_template_kwargs": {"enable_thinking": True}}
    )

    # literature_search_tools = [
    #     searhArxivTool(),
    # ]
    # latexWriter_llm = latexWriter_llm.bind_tools(literature_search_tools)
    latexWriter_agent = create_agent(
        llm=latexWriter_llm,
        prompt=latexWriter_prompt,
        agent_class="latex_writer"
    )
    latexEvaluator_agent = create_agent(
        llm=latexEvaluator_llm,
        prompt=latexEvaluate_prompt,
        agent_class="latex_evaluator"
    )
    latexRewriter_agent = create_agent(
        llm=latexRewriter_llm,
        prompt=latexRewriter_prompt,
        agent_class="latex_rewriter"
    )

    latexWriter_agent = time_node('latexWriter', "latex_writer", timing_logger)(latexWriter_agent)
    latexEvaluator_agent = time_node('latexEvaluator', "latex_evaluator", timing_logger)(latexEvaluator_agent)
    latexRewriter_agent = time_node('latexRewriter', "latex_rewriter", timing_logger)(latexRewriter_agent)

    def router_by_quality(state: State) -> State:
        if "CONTINUE" in state["latex_evaluation"]:
            logger.info("Latex quality is low, need revision.")
            return "NEXT"
        else:
            return "RETURN"
        
    def router_by_revision_count(state: State) -> State:
        if state["revision_count"] < 1:
            logger.info(f"Revision count is {state['revision_count']}, need further revision.")
            return "RETURN"
        else:
            logger.info(f"Revision count is {state['revision_count'] }, reach max revision count.")
            return "NEXT"

    graph = StateGraph(State)

    graph.add_node("latex_writer", latexWriter_agent)
    graph.add_node("latex_evaluator", latexEvaluator_agent)
    graph.add_node("latex_rewriter", latexRewriter_agent)

    graph.add_edge(START, "latex_writer")
    graph.add_edge("latex_writer", "latex_evaluator")
    graph.add_conditional_edges("latex_evaluator", router_by_quality, {
        "RETURN": "latex_rewriter",
        "NEXT": END
    })
    graph.add_conditional_edges("latex_rewriter", router_by_revision_count, {
        "RETURN": "latex_evaluator",
        "NEXT": END
    })

    return graph.compile()

if __name__ == "__main__":
    init_state = State(
        topic="A Novel Approach to Image Classification Using Deep Learning",
        methodology="We propose a convolutional neural network architecture that leverages residual connections and attention mechanisms to improve classification accuracy on benchmark datasets.",
        results="Our model achieves state-of-the-art performance on CIFAR-10 and ImageNet datasets, outperforming existing methods by a significant margin.",
        revision_count=0,
        new_idea="A Novel Approach to Image Classification Using Deep Learning",
        motivation="To improve the accuracy and efficiency of image classification tasks in computer vision applications.",
        downloaded_papers="CoT, ToT, ReAct",
        subplans={"Plan A": "Design the model architecture", "Plan B": "Train the model", "Plan C": "Evaluate the model"},
    )

    latex_writer_agent = build_latex_writer_agent()
    final_state = latex_writer_agent.invoke(init_state)

    print("Final LaTeX Draft:")
    print(final_state["latex_revision"])

    with open("./res.md", "r") as f:
        f.write(final_state["latex_revision"])
