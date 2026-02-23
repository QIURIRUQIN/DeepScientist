import os
import sys
import json
from pathlib import Path

from langgraph.graph import START, END, StateGraph
from tools.code_generation_tools import CodeExecutorTool, CodeGeneratorTool, QualityCriticTool
from utils.file_utils import load_prompt_template

from utils.state import State
from tools.timing import get_timing_logger, time_node

max_iterations = 1
min_quality_score = 0.88

def code_generation_node(state: State) -> State:
    print("\n🧠 Step 1: Code Generation - Reasoning and generating code...")
    
    # 加载prompt
    prompt_template = load_prompt_template("code_generation_v3.md")
    
    # 获取反馈
    feedback = state.get("critique_feedback", "")
    iteration = state.get("iteration_count", 0)
    previous_code = state.get("generated_code", "")

    # 上一次执行的完整结果
    execution_result = state.get("execution_result", {})
    full_error = execution_result.get("error", "")     # 错误信息
    traceback = execution_result.get("traceback", "")  # 完整的错误跟踪
    
    # 提示词
    # final_data_report 在数据分析阶段生成，若缺失则降级为空字符串，避免 KeyError
    final_data_report = state.get("final_data_report", "")

    full_prompt = prompt_template.format(
        methods_description=state["subplans"], # 生成代码的计划
        data_info=state["dataset"],
        feedback=feedback,
        previous_code=previous_code,
        final_data_report=final_data_report,
        execution_error=full_error,
        execution_traceback=traceback,
        iteration=iteration
    )
    
    # 代码生成工具
    code_tool = CodeGeneratorTool()
    generated_code = code_tool.generate_code(full_prompt)
    
    # 更新状态
    state["generated_code"] = generated_code
    state["iteration_count"] = iteration + 1
    
    print(f"\n✅ Generated code (iteration {state['iteration_count']})")
    return state 

def experiment_execution_node(state: State) -> State:
    print("\n⚡ Step 2: Experiment Execution - Running code...")
    
    # 代码执行工具
    executor_tool = CodeExecutorTool()
    
    # 执行代码
    # 需要在 AIScientist 中下载对应的数据
    dataset_path = state.get("download_path", "/Users/chongyanghe/Desktop/DeepScientist/outputs/dataset")
    input_data_path = os.path.join(dataset_path, state["dataset_url"].split("/")[-1])
    dataPath = ""
    if input_data_path: 
        for file in os.listdir(input_data_path):
            dataPath = os.path.join(input_data_path, file)
            if os.path.isfile(dataPath):
                break
    else:
        raise FileNotFoundError(f"input_data_path is NULL!")
    execution_result = executor_tool.execute_code(
        code=state["generated_code"],
        data_path=dataPath
    )
    
    # 更新状态
    state["execution_result"] = execution_result
    state["execution_success"] = execution_result["success"]
    state["error_message"] = execution_result.get("error", "")
    
    if execution_result["success"]:
        print("\n✅ Code executed successfully")

        state.update({
            "output_figures": execution_result.get("figures", []),
            "output_tables": execution_result.get("tables", []),
            "performance_metrics": execution_result.get("metrics", {})
        })
    else:
        print(f"\n❌ Code execution failed: {execution_result['error']}")
    
    return state

def critique_node(state: State) -> State:
    print("\n🔍 Step 3: Quality Critique - Evaluating results...")
    
    critic_tool = QualityCriticTool()
    
    # 评估实验质量
    critique_result = critic_tool.evaluate_experiment(
        methods=state["methods_description"],
        code=state["generated_code"],
        result=state["execution_result"],
        iteration=state["iteration_count"]
    )
    
    # 累积反馈
    previous_feedback = state.get("critique_feedback", "")
    new_feedback = critique_result.get("feedback", "no feedback")
    
    if previous_feedback:
        cumulative_feedback = f"{previous_feedback}\n\n--- Iteration {state['iteration_count']} ---\n{new_feedback}"
    else:
        cumulative_feedback = f"--- Iteration {state['iteration_count']} ---\n{new_feedback}"
    
    # 更新状态
    state["critique_feedback"] = cumulative_feedback
    state["quality_score"] = critique_result.get("quality_score", 0)
    
    print(f"\n📊 Quality score: {critique_result.get('quality_score', 0):.2f}")
    print(f"💡 New feedback: {new_feedback}")
    
    return state

def should_continue(state: State) -> str:
    if state["execution_success"] and state.get("quality_score", 0) >= min_quality_score:
        return "accept"
    elif state["iteration_count"] >= max_iterations:
        return "max_iterations_reached"
    else:
        return "continue"

def finalize_output(state: State) -> State:
    print("\n🎯 Finalizing output...")
    
    # 准备最终输出
    state["final_output"] = {
        "code": state["generated_code"],
        "execution_result": state["execution_result"],
        "quality_score": state["quality_score"],
        "iterations": state["iteration_count"],
        "figures": state.get("output_figures", []),
        "tables": state.get("output_tables", []),
        "metrics": state.get("performance_metrics", {})
    }
    
    print(f"✅ Experiment completed after {state['iteration_count']} iterations")
    print(f"📈 Final quality score: {state['quality_score']:.2f}")
    
    return state

def handle_max_iterations(state: State) -> State:
    print("⚠️ Maximum iterations reached, using best available result")
    return finalize_output(state)

def build_code_experiment_subgraph():
    timing_logger, log_file = get_timing_logger(
        log_dir="./outputs/logs/codeGenerator",
        agent_name='codeGenerator'
    )
    timing_logger.info("="*60)
    timing_logger.info("Initialize codeGenerator subgraph")
    timing_logger.info("="*60)

    workflow = StateGraph(State)

    code_generation_node_ = time_node("codeGenerator", "code_generation", timing_logger)(code_generation_node)
    experiment_execution_node_ = time_node("codeGenerator", "experiment_execution", timing_logger)(experiment_execution_node)
    critique_node_ = time_node("codeGenerator", "quality critique", timing_logger)(critique_node)
    finalize_output_ = time_node("codeGenerator", "finalize output", timing_logger)(finalize_output)
    handle_max_iterations_ = time_node("codeGenerator", "handle max iter", timing_logger)(handle_max_iterations)
    
    # 节点
    workflow.add_node("code_generation", code_generation_node_)
    workflow.add_node("experiment_execution", experiment_execution_node_)
    workflow.add_node("quality_critique", critique_node_)
    workflow.add_node("finalize", finalize_output_)
    workflow.add_node("handle_max_iterations", handle_max_iterations_)
    
    # 设置入口
    workflow.set_entry_point("code_generation")
    
    # 添加边
    workflow.add_edge("code_generation", "experiment_execution")
    workflow.add_edge("experiment_execution", "quality_critique")
    
    # 条件边
    workflow.add_conditional_edges(
        "quality_critique",
        should_continue,
        {
            "accept": "finalize",
            "continue": "code_generation", 
            "max_iterations_reached": "handle_max_iterations"
        }
    )
    
    workflow.add_edge("finalize", END)
    workflow.add_edge("handle_max_iterations", END)
    
    return workflow.compile()

if __name__ == "__main__":
    graph = build_code_experiment_subgraph()
    init_state= {
    "methods_description": "Implementing a risk-managed sparse index tracking framework using market-graph clustering and turnover sparsity optimization. The methodology includes: 1) Market graph construction based on absolute correlation coefficients between S&P 500 assets; 2) Graph clustering using RatioCut spectral relaxation with constrained K-means to form dynamic asset clusters; 3) Portfolio optimization with market-graph neutrality constraints, intra-cluster sparsity constraints, turnover sparsity regularization, and weight bounds; 4) Implementation of Primal-Dual Splitting (PDS) algorithm for solving the non-convex optimization problem; 5) Evaluation using rolling-window backtesting with multiple benchmark comparisons and comprehensive performance metrics.",
    "data_info": "S&P 500 constituent daily returns data (2012-2022). The dataset includes adjusted closing prices for 463 assets with complete coverage over the study period. Data spans two time periods: September 2012 - October 2017 and November 2017 - August 2022. Daily returns are calculated as percentage changes in adjusted closing prices.",
    "research_question": "How does market-graph clustering compare to traditional sector classification for sparse index tracking? What is the trade-off between tracking accuracy, turnover sparsity, and computational efficiency in risk-managed portfolio optimization?"
}
    final_state = graph.invoke(init_state)
    print("Graph structure:", final_state.get("generated_code", " "))
