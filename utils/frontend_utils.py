from langchain_core.messages import ToolMessage, HumanMessage, AIMessage
from typing import Union
from datetime import datetime
import pandas as pd
import os
import json
from loguru import logger

from utils.config import Config

current_node = ""
last_message = None

tool_show_message = {
    "search_academicPapers_from_AriXv": "Searching Arxiv for **{query}**",
    "tavily_search": "Searching on the web for **{query}**"
}

def _get_messages_file_path(config: Config):
    """获取消息文件路径"""
    streamlit_dir = os.path.join(config.save_path, "streamlit")
    os.makedirs(streamlit_dir, exist_ok=True)
    return os.path.join(streamlit_dir, "messages.json")

def _save_message(config: Config, message_data: dict):
    """保存消息到JSON文件，只保留最新的30条消息"""
    messages_file = _get_messages_file_path(config)
    message_file_all = messages_file.replace(".json", "_all.json")
    if not message_file_all:
        return
    
    messages = []
    if os.path.exists(message_file_all):
        try:
            with open(message_file_all, 'r') as f:
                messages = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read messages file: {e}")
            messages = []
    
    # 添加新消息
    messages.append(message_data)
    
    # 保存回文件
    try:
        with open(messages_file, 'w') as f:
            show_messages = messages[-30:] if len(messages) > 30 else messages
            json.dump(show_messages, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save message to file: {e}")
        
    try:
        with open(message_file_all, 'w') as f:
            json.dump(messages, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save message to file: {e}")

def frontend_add_message(new_message: Union[ToolMessage, HumanMessage, AIMessage], config: Config):
    if not config:
        return
    
    global current_node, last_message

    if new_message == last_message:
        return
    
    last_message = new_message[-1] if isinstance(new_message, list) else new_message
    if last_message.content.strip():
        if isinstance(last_message, ToolMessage):
            role = "tool"
            title = ""
            content = ""
            return
        elif isinstance(last_message, HumanMessage):
            role = "user"
            title = "Agent"
            content = last_message.content
        elif isinstance(last_message, AIMessage):
            role = "assistant"
            title = "deepseek-chat"
            content = last_message.content
        else:
            role = "assistant"
            title = ""
            content = last_message.content

        try:
            message_data = {
                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "type": "message",
                "role": role,
                "title": title,
                "content": new_message.content
            }
        except:
            message_data = {
                "timestamp": pd.Timestamp.now().strftime("%Y-%m-%d"),
                "type": "message",
                "role": role,
                "title": title,
                "content": content
            }
        _save_message(config, message_data)
    else:
        logger.warning("Empty message content...", new_message)

def frontend_add_tool_call(tool_name: str, tool_args: dict, config: Config):
    if not config:
        return
    
    tool_message = tool_show_message.get(tool_name, "Calling {tool_name}...")
    tool_message = tool_message.format(tool_name=tool_name, **tool_args)
    
    # 保存工具调用数据
    message_data = {
        "timestamp": datetime.now().isoformat(),
        "type": "tool_call",
        "tool_name": tool_name,
        "content": tool_message
    }
    _save_message(config, message_data)
