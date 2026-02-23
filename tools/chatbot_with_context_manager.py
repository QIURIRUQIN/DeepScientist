
from typing_extensions import Literal
from loguru import logger
import time
import traceback
from copy import deepcopy
import traceback
import os
import pandas as pd
import json
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph.state import CompiledStateGraph
from langchain_core.load import dumps, loads

from utils.config import Config
from utils.state import State
from utils.frontend_utils import frontend_add_message, frontend_add_tool_call
from tools.rag import vector_search
from utils.track_node_call import track_node_call

def chatbot_with_context_manager(
    config: Config, llm: BaseChatModel, prompt: str,
    context_manage: Literal["token_cnt", "token_cnt_large", "last_message", "last_tool_message", "vector_search"] = "vector_search",
    only_last_human_message: bool = False,
    calling_subgraph: str = ""
):
    """
    创建一个带上下文管理功能的聊天机器人
    
    :param config: 配置对象
    :type config: Config
    :param llm: 语言模型
    :type llm: BaseChatModel
    :param prompt: 提示词
    :type prompt: str
    :param context_manage: 上下文管理策略
    :type context_manage: Literal["token_cnt", "token_cnt_large", "last_message", "last_tool_message", "vector_search"]
    :param only_last_human_message: 是否只保留最后一条人类信息
    :type only_last_human_message: bool
    :param calling_subgraph: 说明
    :type calling_subgraph: str

    :returns 聊天机器人函数
    """

    def detect_error_message(state: State):
        if ("messages" in state) and (len(state["messages"]) > 0):
            last_message = state["messages"][-1]

            if isinstance(last_message, ToolMessage):
                if "error" in last_message.status:
                    return last_message
                
        return False
    
    def clamp_token_cnt(messages: list[dict], max_token_cnt: int):
        token_cnt = 0
        context_messages = []

        for message in messages[::-1]:
            token_cnt += count_tokens_approximately([message])
            if token_cnt > max_token_cnt:
                break

            context_messages.insert(0, message)
        
        return context_messages
    
    def call_react(state: State, message_to_llm: list):
        tool_call_interval = 5
        for _ in range(5):
            try:
                if calling_subgraph == "literature_search":
                    if "literature_tool_call_counter" not in state:
                        state["literature_tool_call_counter"] = 0

                elif calling_subgraph == "dataset_search":
                    if "dataset_tool_call_counter" not in state:
                        state["dataset_tool_call_counter"] = 0

                for event in llm.stream({"messages": message_to_llm}, config={"recursion_limit": 100}):
                    node_name = list(event.keys())[0]
                    new_state = event[node_name]

                    all_messages = new_state["messages"]
                    if len(all_messages) > 0:
                        show_message = all_messages[-1]
                        frontend_add_message(show_message, config)

                        if isinstance(show_message, AIMessage):
                            if show_message.tool_calls:
                                for tool_call in show_message.tool_calls:
                                    frontend_add_tool_call(tool_call["name"], tool_call["args"], config)

                    logger.info(f"Streaming: {node_name}, "
                                f"wait for {tool_call_interval} seconds, "
                                f"token cnt: {count_tokens_approximately(all_messages)}")    
                    
                    if node_name == "tools":
                        if calling_subgraph == "literature_search":
                            state["literature_tool_call_counter"] += 1
                        elif calling_subgraph == "dataset_search":
                            state["dataset_tool_call_counter"] += 1
                        time.sleep(tool_call_interval)

            except Exception as e:
                logger.warning(f"React LLM error: {e}")
                logger.warning(traceback.format_exc())
                logger.warning("Retrying...")
                tool_call_interval = min(tool_call_interval * 2, 60)
                time.sleep(10)
            else:
                break
            
        state["messages"] += all_messages
        return state

    def format_prompt(state: State):
        literature_summary = state.get("literature_summary", " ")
        methodology_summary = state.get("methodology_summary", " ")
        new_idea = state.get("new_idea", " ")
        dataset = state.get("dataset", " ")
        subplans = state.get("subplans", " ")
        dataset_url = state.get("dataset_url", " ")

        this_prompt = deepcopy(prompt)

        # generate new idea
        if calling_subgraph in ["idea_generation", "literature_search"]:
            if "{literature_summaries}" in this_prompt:
                try:
                    if len(literature_summary) > 32000 * 4:
                        logger.warning("data show is too long, clamping with vector search")
                        literature_summary = vector_search(literature_summary, prompt, token_cnt=32000)
                    this_prompt = this_prompt.replace("{literature_summaries}", str(literature_summary))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

            if "{methodology_summaries}" in this_prompt:
                try:
                    if len(methodology_summary) > 32000 * 4:
                        logger.warning("data show is too long, clamping with vector search")
                        methodology_summary = vector_search(methodology_summary, prompt, token_cnt=32000)
                    this_prompt = this_prompt.replace("{methodology_summaries}", str(methodology_summary))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

            if "{new_research_idea}" in this_prompt:
                try:
                    if len(new_idea) > 4000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        new_idea = vector_search(new_idea, prompt, token_cnt=4000)
                    this_prompt = this_prompt.replace("{new_research_idea}", str(new_idea))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

        elif calling_subgraph == "dataset_search":
            if "{new_research_idea}" in this_prompt:
                try:
                    if len(new_idea) > 4000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        new_idea = vector_search(new_idea, prompt, token_cnt=4000)
                    this_prompt = this_prompt.replace("{new_research_idea}", str(new_idea))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

        elif calling_subgraph == "plan_generation":
            if "{new_research_idea}" in this_prompt:
                try:
                    if len(new_idea) > 4000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        new_idea = vector_search(new_idea, prompt, token_cnt=4000)
                    this_prompt = this_prompt.replace("{new_research_idea}", str(new_idea))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

            if "{dataset}" in this_prompt:
                try:
                    if len(dataset) > 32000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        dataset = vector_search(dataset, prompt, token_cnt=32000)
                    this_prompt = this_prompt.replace("{dataset}", str(dataset))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

            if "{dataset_url}" in this_prompt:
                try:
                    if len(dataset_url) > 32000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        dataset_url = vector_search(dataset_url, prompt, token_cnt=32000)
                    this_prompt = this_prompt.replace("{dataset_url}", str(dataset_url))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())
        
        elif calling_subgraph == "code_generation":
            if "{subplans}" in this_prompt:
                try:
                    if len(subplans) > 32000 * 4:
                        logger.warning("new idea is too long, clamping with vector search")
                        subplans = vector_search(subplans, prompt, token_cnt=32000)
                    this_prompt = this_prompt.replace("{subplans}", str(subplans))
                
                except Exception as e:
                    logger.warning("Error occurred when fortmatting data show", str(e))
                    logger.warning(traceback.format_exc())

        return this_prompt
    
    @track_node_call(subgraph_name=calling_subgraph)
    def chatbot(state: State):
        this_prompt = format_prompt(state)

        logger.info(f"Context management: {context_manage}")
        if context_manage == "last_message":
            logger.info("Only keep the last message")
            message_to_llm = state["messages"][-1:]
        elif context_manage == "last_tool_message":
            logger.info("Keep to the last tool message")
            last_tool_message_index = 0
            for msg_i in range(len(state["messages"]) - 1, -1, -1):
                if isinstance(state["messages"][msg_i], ToolMessage):
                    last_tool_message_index = msg_i
                    break
            message_to_llm = state["messages"][last_tool_message_index:]
        elif context_manage == "vector_search":
            logger.info("Using vector search for context management")
            message_to_llm = vector_search(state["messages"], this_prompt, token_cnt=10000)
        elif context_manage == "token_cnt_large":
            max_context_token_cnt_large = int(os.environ.get("MAX_CONTEXT_TOKEN_CNT_LARGE", 96000))
            logger.info(f"Use max_context_token_cnt_large: {max_context_token_cnt_large}")
            message_to_llm = clamp_token_cnt(state["messages"], max_context_token_cnt_large)
        else:
            max_context_token_cnt_large = int(os.environ.get("MAX_CONTEXT_TOKEN_CNT_LARGE", 96000))
            logger.info(f"Use max_context_token_cnt_large: {max_context_token_cnt_large}")
            message_to_llm = clamp_token_cnt(state["messages"], max_context_token_cnt_large)

        last_error_message = detect_error_message(state)
        if last_error_message:
            logger.warning("Error message detected, do not add prompt to context.")
            message_to_llm.append(HumanMessage(content=this_prompt))
            message_to_llm.append(last_error_message)
        else:
            state["messages"].append(HumanMessage(content=this_prompt))
            message_to_llm.append(state["messages"][-1])

            logger.info(f"Prompt: {this_prompt[:1000]}...")

        if only_last_human_message:
            if isinstance(message_to_llm[-1], HumanMessage):
                last_human_message = message_to_llm[-1]
                message_no_human = [msg for msg in message_to_llm if not isinstance(msg, HumanMessage)]
                message_no_human = message_no_human + [last_human_message]
                logger.info("Only keep the last human message")

        logger.info(f"Message count to LLM: {len(message_to_llm)}, token count: {count_tokens_approximately(message_to_llm)}")
        time_stamp = pd.Timestamp.now().strftime("%Y%m%d%H%M%S")
        save_path = os.path.join(config.save_path, "llm_calls", f"{time_stamp}.json")
        os.makedirs(os.path.dirname(save_path), exist_ok=True)

        with open(save_path, "w") as f:
            f.write(dumps(message_to_llm, indent=4))

        # with open(save_path, "r") as f:
        #     message_to_llm = loads(f.read())

        if isinstance(llm, CompiledStateGraph):
            assert "pre_model_hook" in llm.nodes, "React LLM graph must have a pre_model_hook node"
            state = call_react(state, message_to_llm)
        else:
            for try_i in range(10):
                try:
                    if calling_subgraph == "dataset_search":
                        response = llm.invoke(this_prompt)
                    else:
                        response = llm.invoke(message_to_llm)
                    state["messages"].append(response)
                    frontend_add_message(state["messages"][-1], config)
                    if calling_subgraph == "idea_generation":
                        try:
                            parsed = json.loads(response.content)
                            print(f"response content: {response.content}")
                            state["topic"] = parsed["topic"]
                            state["new_idea"] = parsed["new_idea"]
                            state["motivation"] = parsed["motivation"]
                            state["methods_description"] = parsed["methods_description"]
                        except:
                            print(f"response content: {response.content}")
                            state["topic"] = response.content
                            state["new_idea"] = response.content
                            state["motivation"] = response.content
                            state["methods_description"] = response.content
                    elif calling_subgraph == "dataset_search":
                        state["dataset"] = response.content
                    elif calling_subgraph == "plan_generation":
                        state["subplans"] = response.content
                        state["methods_description"] = state.get("methods_description", " ") + response.content
                    break
                except Exception as e:
                    logger.warning(f"Error when calling llm: {e}")
                    logger.warning(traceback.format_exc())
                    logger.warning("Retrying...")
                    time.sleep(5)

        with open(save_path, "w") as f:
            f.write(dumps(message_to_llm + [state["messages"][-1]], indent=4))

        return state
    
    return chatbot
