import os

from langgraph.graph import StateGraph, START, END
from langchain.chat_models import init_chat_model

from tools.data_analysis import LoadDataTool, ColumnMeaningTool, compute_column_statistics
from utils.state import State

with open(os.path.join(os.path.dirname(__file__), "..", "prompt/data_understading.md")) as f:
    dataUnderstanding_prompt = f.read()

def build_data_analysis_subgraph():

    # 1. 初始化工具实例
    load_data_tool = LoadDataTool()
    column_meaning_tool = ColumnMeaningTool()

    # 2. 定义节点函数（每个节点对应一个步骤）
    def load_data_node(state: State) -> State:
        """节点1：加载数据"""
        data_path = state.get("download_path", " ") + "/" + state.get("dataset_url", " ").split("/")[-1]
        load_result = load_data_tool.run({
            "data_path": data_path
        })
        state["load_result"] = load_result
        return state
    
    def analyze_column_meaning_node(state: State) -> State:
        """节点2：分析列含义"""
        load_result = state["load_result"]
        if not load_result["success"]:
            state["column_meaning"] = {"error": load_result["error"]}
            return state
        
        df = load_result["df"]
        meanings = {}
        for col in df.columns:
            series = df[col].dropna()

            result = column_meaning_tool.run({
                "column_name": col,
                "dtype": str(series.dtype),
                "nunique": series.nunique(),
                "sample_values": series.astype(str).head(5).tolist(),
            })

            meanings[col] = result

        state["column_meaning"] = meanings
        return state
    
    def get_column_statistics_node(state: State) -> State:
        """节点3：生成列统计"""
        load_result = state["load_result"]
        if not load_result["success"]:
            state["column_statistics"] = {"error": load_result["error"]}
            return state

        df = load_result["df"]
        state["column_statistics"] = compute_column_statistics(df)
        return state
    
    def generate_report_node(state: State) -> State:
        """节点4：生成最终报告"""
        # 提取状态中的数据
        load_result = state["load_result"]
        column_meaning = state["column_meaning"]
        column_stats = state["column_statistics"]

        # 校验前置步骤是否成功
        if not load_result["success"]:
            final_report = f"数据加载失败：{load_result['error']}"
            state["final_report"] = final_report
            return state

        # 初始化大模型
        llm = init_chat_model(
            os.environ.get("MODEL", "deepseek-reasoner"),
            base_url=os.environ.get("OPENAI_BASE_URL", ""),
            model_provider="openai",
            extra_body={"chat_template_kwargs": {"enable_thinking": True}}
        )
    
        # 格式化提示词参数
        basic_info = f"""
                - 文件路径：{load_result['data']['file_path']}
                - 文件名称：{load_result['data']['file_name']}
                - 数据行数：{load_result['data']['row_count']}
                - 数据列数：{load_result['data']['column_count']}
                - 重复行数量：{load_result['data']['duplicate_rows']}
                - 总缺失值数量：{sum(load_result['data']['missing_values'].values())}
        """

        this_prompt = dataUnderstanding_prompt.format(
            basic_info=basic_info,
            column_meaning=column_meaning,
            column_statistics=column_stats
        )

        # 执行提示词+LLM+输出解析
        response = llm.invoke(this_prompt)

        state["final_data_report"] = response.content

        return state
    
    graph = StateGraph(State)

    graph.add_node("load_data", load_data_node)
    graph.add_node("analyze_column_meaning", analyze_column_meaning_node)
    graph.add_node("get_column_statistics", get_column_statistics_node)
    graph.add_node("generate_report", generate_report_node)

    graph.add_edge(START, "load_data")
    graph.add_edge("load_data", "analyze_column_meaning")
    graph.add_edge("analyze_column_meaning", "get_column_statistics")
    graph.add_edge("get_column_statistics", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()

if __name__ == "__main__":
    pass
