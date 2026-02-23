from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langgraph.graph import StateGraph, START, END
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field
import arxiv
import requests
import time
from pathlib import Path
import os
from langchain.chat_models import init_chat_model
import dotenv
from loguru import logger
from tools.timing import get_timing_logger, time_node
dotenv.load_dotenv(dotenv_path="/Users/chongyanghe/Desktop/DeepScientist/.env")

from utils.state import State

# ===================== 1. 第一个 Agent: Query Refinement Agent =====================
class QueryRefinementAgent:
    """Agent 1: 查询优化（翻译+增强）"""
    
    def __init__(self, model_name: str = "deepseek-reasoner", temperature: float = 0.7):
        self.llm = init_chat_model(
                    model_name,
                    base_url=os.environ.get("OPENAI_BASE_URL", ""),
                    model_provider="openai",
                    extra_body={"chat_template_kwargs": {"enable_thinking": True}}
                )
        # 读取 prompt 文件（兼容路径不存在的情况，内置默认 prompt）
        prompt_path = Path(os.path.dirname(__file__)) / ".." / "prompt" / "queryTranslation.md"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                prompt_template = f.read()
        else:
            # 默认 prompt（如果文件不存在）
            prompt_template = """
            Please optimize the following query statement to be suitable for the ArXiv academic 
            search (if it is already in English, enhance the keywords): 
            Query statement: {query}
            """
        self.prompt_template = PromptTemplate.from_template(prompt_template)

    def refine_query(self, state: State) -> State:
        """
        接收状态对象，优化查询后返回更新的状态
        """
        # 从 state 中提取初始查询
        original_query = state["original_query"]
        # 调用 LLM 优化查询
        prompt = self.prompt_template.format(query=original_query)
        response = self.llm.invoke(prompt)
        # 提取优化后的查询（关键：AIMessage 需要取 content 属性）
        refined_query = response.content.strip()
        # 更新 state 并返回
        state["refined_query"] = refined_query

        return state

# ===================== 2. 第二个 Agent: Search Agent (ArXiv 搜索) =====================
class SearchAgent:
    """Agent 2: 论文搜索（ArXiv）"""
    
    def __init__(self, model_name: str = "deepseek-chat", temperature: float = 0.7):
        self.llm = init_chat_model(
                    model_name,
                    base_url=os.environ.get("OPENAI_BASE_URL", ""),
                    model_provider="openai",
                    extra_body={"chat_template_kwargs": {"enable_thinking": True}}
                )

    def search_papers(self, state: State) -> State:
        """
        接收状态对象，搜索论文后返回更新的状态
        """
        # 从 state 中提取优化后的查询
        refined_query = state["refined_query"]
        logger.info(f"🔍 使用优化后查询进行 ArXiv 搜索：{refined_query}")
        # 调用 ArXiv API 搜索论文
        paper_urls = self._search_arxiv(refined_query)
        # 更新 state 并返回
        state["paper_urls"] = paper_urls
        return state

    def _search_arxiv(self, query: str) -> list:
        """ArXiv 底层搜索逻辑"""
        urls = []
        try:
            search = arxiv.Search(
                query=query,
                max_results=1, # 可修改
                sort_by=arxiv.SortCriterion.Relevance,
                sort_order=arxiv.SortOrder.Descending
            )
            for result in search.results():
                urls.append(result.pdf_url)
        except Exception as e:
            print(f"ArXiv 搜索失败：{e}")
        return urls

# ===================== 3. 第三个 Agent: Downloader Agent (论文下载) =====================
class DownloaderAgent:
    """Agent 3: 论文下载（PDF）"""
    
    def __init__(self, download_dir: str = os.path.join(os.path.dirname(__file__), "../outputs/papers"), max_papers: int = 10):
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_papers = max_papers
    
    def download_papers(self, state: State) -> State:
        """
        接收状态对象，下载论文后返回更新的状态
        """
        # 从 state 中提取论文 URL 列表
        paper_urls = state["paper_urls"]
        # 下载论文
        downloaded_papers = self._download_papers(paper_urls)
        # 更新 state 并返回
        state["downloaded_papers"] = downloaded_papers

        return state

    def _download_papers(self, paper_urls: list) -> list:
        """底层下载逻辑"""
        downloaded_papers = []
        for url in paper_urls[:self.max_papers]:
            try:
                # 避免请求过快被封
                time.sleep(1)
                response = requests.get(url, timeout=10)
                response.raise_for_status()  # 抛出 HTTP 错误
                # 生成本地文件名
                filename = url.split("/")[-1] + ".pdf"
                filepath = self.download_dir / filename
                # 写入文件
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                # 记录下载结果
                # downloaded_papers.append({
                #     "url": url,
                #     "file_path": str(filepath),
                #     "status": "success"
                # })
                downloaded_papers.append(filepath)
                print(f"成功下载：{filepath}")
            except Exception as e:
                print(f"下载失败 {url}：{e}")
                # downloaded_papers.append({
                #     "url": url,
                #     "file_path": "",
                #     "status": f"failed: {str(e)}"
                # })

        return downloaded_papers

# ===================== 5. 创建 LangGraph 工作流 =====================
def build_literature_search_subgraph():
    """创建并编译 langgraph 工作流"""
    timing_logger, log_file = get_timing_logger(
        log_dir="./outputs/logs/paperSearcher",
        agent_name='paperSearcher'
    )
    timing_logger.info("="*60)
    timing_logger.info("Initialize paperSearcher subgraph")
    timing_logger.info("="*60)

    # 初始化 Agent 实例
    refine_agent = QueryRefinementAgent()
    search_agent = SearchAgent()
    download_agent = DownloaderAgent()

    refine_query_timed = time_node("paperSearcher", "refine_query", timing_logger)(refine_agent.refine_query)
    search_papers_timed = time_node("paperSearcher", "search_papers", timing_logger)(search_agent.search_papers)
    download_papers_timed = time_node("paperSearcher", "download_papers", timing_logger)(download_agent.download_papers)

    # 初始化 StateGraph（绑定状态类）
    graph = StateGraph(State)

    # 添加节点（核心：节点是接收 state 并返回 state 的函数）
    graph.add_node("refine_query", refine_query_timed)
    graph.add_node("search_papers", search_papers_timed)
    graph.add_node("download_papers", download_papers_timed)

    # 设置工作流边（定义执行顺序）
    graph.add_edge(START, "refine_query")          # 开始 → 优化查询
    graph.add_edge("refine_query", "search_papers") # 优化查询 → 搜索论文
    graph.add_edge("search_papers", "download_papers") # 搜索论文 → 下载论文
    graph.add_edge("download_papers", END)         # 下载论文 → 结束

    graph = graph.compile()

    # 编译工作流
    return graph

# # ===================== 6. 执行工作流 =====================
# def build_literature_search_subgraph(original_query: str):
#     """
#     执行工作流
#     :param original_query: 用户初始查询语句
#     :return: 最终状态（包含下载结果）
#     """
#     # 创建工作流
#     sub_graph_1 = create_workflow()
#     # 初始化 state（将初始 query 存入 state）
#     initial_state = {"original_query": original_query}
#     # 运行工作流（传入初始 state）
#     final_state = sub_graph_1.invoke(initial_state)
#     return final_state

# ===================== 7. 测试运行 =====================
if __name__ == "__main__":
    # 示例查询
    user_query = "Quantum computing advancements"
    # 执行工作流
    result = build_literature_search_subgraph(user_query)
    
    # 打印结果
    print("="*50)
    print(f"初始查询：{result.original_query}")
    print(f"优化后查询：{result.refined_query}")
    print(f"搜索到的论文 URL：{result.paper_urls}")
    print("下载结果：")
    for paper in result.downloaded_papers:
        print(f"- {paper['url']} → {paper['status']} ({paper['file_path']})")
    print("="*50)
