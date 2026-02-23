import pandas as pd
from copy import deepcopy
from loguru import logger
import os

result_dir = os.path.dirname(__file__)

def create_agent(
    llm,
    prompt: str,
    agent_class: str
):
    def format_prompt(state: dict) -> str:
        # 格式化 prompt
        this_prompt = deepcopy(prompt)
        if agent_class == "latex_writer":
            img_names = os.listdir(os.path.join(result_dir, "..", "results/figures"))
            table_names = os.listdir(os.path.join(result_dir, "..", "results/tables"))

            results = {}
            for filename in table_names:
                file_path = os.path.join(result_dir, "..", "results/tables", filename)
                results[filename] = pd.read_csv(file_path)

            state["summary"] = str(state["literature_summary"])[:4000] + str(state["methodology_summary"])[:2000]
            this_prompt = this_prompt.replace("{topic}", state.get("topic", ""))
            this_prompt = this_prompt.replace("{new_idea}", state.get("new_idea", ""))
            this_prompt = this_prompt.replace("{motivation}", state.get("motivation", ""))
            this_prompt = this_prompt.replace("{references}", str(state.get("paper_urls", "")))
            this_prompt = this_prompt.replace("{subplans}", str(state.get("subplans", "")))
            this_prompt = this_prompt.replace("{methodology}", state.get("methods_description", ""))
            this_prompt = this_prompt.replace("{summary}", state.get("summary", ""))
            this_prompt = this_prompt.replace("{final_data_report}", str(state.get("final_data_report", ""))[:2000])
            this_prompt = this_prompt.replace("{output_figures}", str(img_names))
            this_prompt = this_prompt.replace("{output_tables}", str(table_names))
            this_prompt = this_prompt.replace("{results}", str(results))

        elif agent_class == "latex_evaluator":
            if "latex_revision" in state:
                this_prompt = this_prompt.replace("{latex_code}", state.get("latex_revision", ""))
            else:
                this_prompt = this_prompt.replace("{latex_code}", state.get("latex_draft", ""))

        elif agent_class == "latex_rewriter":
            this_prompt = this_prompt.replace("{latex_code}", state.get("latex_draft", ""))
            this_prompt = this_prompt.replace("{revised_suggestion}", state.get("latex_evaluation", ""))

        return this_prompt
    
    def chatbot(state: dict) -> str:
        this_prompt = format_prompt(state)

        response = llm.invoke(this_prompt)
        logger.info(f"[{agent_class}] Response: {response.content[:100]}")
        print(f"[{agent_class}] Response: {response.content[:100]}")
        
        if agent_class == "latex_writer":
            state["latex_draft"] = response.content
        elif agent_class == "latex_evaluator":
            state["latex_evaluation"] = response.content
        elif agent_class == "latex_rewriter":
            state["revision_count"] += 1
            state["latex_revision"] = response.content

        return state

    return chatbot
