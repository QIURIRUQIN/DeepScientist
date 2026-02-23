import os
import base64
from pathlib import Path
from typing import Dict, Any
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from common.llm_config import get_llm, call_multimodal_llm
from common.utils import init_logger, get_pdf_files
from utils.state import State
from langchain_core.load import dumps, loads
from langchain.chat_models import init_chat_model
from loguru import logger

import json

# logger = init_logger("chatbot")

def create_simple_chatbot(llm, prompt_template: str):
    """
    Create a simple chatbot function without context management.
    
    Args:
        llm: Language model instance
        prompt_template: Prompt template string with placeholders like {literature_content}
    
    Returns:
        A chatbot function that can be used as a node in LangGraph
    """
    def chatbot(state_dict: State) -> State:
        """Simple chatbot node that formats prompt and calls LLM."""
        # Get existing messages
        all_messages = state_dict.get("messages", [])
        # 优化：只在必要时读取state.json，优先使用内存中的状态
        if "parsed_multimodal_content" not in state_dict or not state_dict.get("parsed_multimodal_content"):
            try:
                state_file = os.path.join(os.path.dirname(__file__), "..", "outputs/state.json")
                if os.path.exists(state_file):
                    with open(state_file, "r", encoding="utf-8") as f:
                        new_state = json.loads(f.read())
                        state_dict["parsed_multimodal_content"] = new_state.get("parsed_multimodal_content", [])
            except Exception as e:
                logger.warning(f"读取state.json失败，使用内存状态: {e}")
        
        # Check if summary phase has been initialized
        # Summary messages are identified by checking if there's a HumanMessage with summary prompt content
        # or if there's already a summary-related tool call
        has_summary_init = False
        summary_start_idx = 0
        
        for i, msg in enumerate(all_messages):
            if isinstance(msg, HumanMessage):
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                # Check if this is a summary prompt (contains "Introduction" or "Related Works" requirement)
                if "Introduction" in content and "Related Works" in content:
                    has_summary_init = True
                    summary_start_idx = i
                    break
            elif isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
                # Check if there's a summary_writer_tool call
                for tool_call in msg.tool_calls:
                    if tool_call.get("name") == "summary_writer_tool":
                        has_summary_init = True
                        summary_start_idx = i
                        break
                if has_summary_init:
                    break
        
        # If summary phase hasn't started, clear previous messages (from PDF parsing) and start fresh
        if not has_summary_init:
            messages = []
            logger.info("📝 开始生成Summary")
        else:
            # Keep only summary-related messages
            messages = all_messages[summary_start_idx:]
        
        # Only add initial prompt if messages is empty (fresh start)
        if not messages:
            # Extract literature content from state
            parsed_content = state_dict.get("parsed_multimodal_content", [])
            literature_texts = [
                item["content"] 
                for item in parsed_content 
                if item.get("status") == "success" and item.get("content")
            ]
            
            if not literature_texts:
                error_msg = "没有可用的有效内容用于生成报告"
                logger.error(f"❌ {error_msg}")
                state_dict["errors"] = state_dict.get("errors", []) + [error_msg]
                return state_dict
            
            literature_content = "\n\n---\n\n".join(literature_texts)
            
            # Format prompt
            prompt = prompt_template.format(literature_content=literature_content)
            
            # Add prompt as human message
            messages.append(HumanMessage(content=prompt))
        
        # Check if last message is an AIMessage without tool calls
        # If so, prompt LLM to call the tool
        if messages and isinstance(messages[-1], AIMessage):
            last_msg = messages[-1]
            # If LLM returned text but no tool calls, prompt it to call the tool
            if not (hasattr(last_msg, "tool_calls") and last_msg.tool_calls):
                tool_prompt = "\n\nPlease call the summary_writer_tool to save the generated report to a file. You must call this tool to complete the task."
                messages.append(HumanMessage(content=tool_prompt))
        
        # Call LLM with current messages
        try:
            response = llm.invoke(messages)
            messages.append(response)
            
            # Log if tool calls are present
            if hasattr(response, "tool_calls") and response.tool_calls:
                logger.info(f"✅ 摘要生成完成，调用工具保存")
        except Exception as e:
            error_msg = f"调用LLM失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            state_dict["errors"] = state_dict.get("errors", []) + [error_msg]
        
        # Update state with all messages
        # If summary phase just started, replace all messages with new summary messages
        # Otherwise, keep previous messages and append new summary messages
        if not has_summary_init:
            # Fresh start: replace all messages with summary messages
            state_dict["messages"] = messages
        else:
            # Summary phase already started: keep previous messages and update summary messages
            state_dict["messages"] = all_messages[:summary_start_idx] + messages
        return state_dict
    
    return chatbot

def create_methodology_chatbot(llm_with_tools, prompt_template: str, md_output_dir: str, methods_save_path: str = "../outputs/methods"):
    """
    Create a chatbot function for methodology extraction with image support.
    
    Args:
        llm_with_tools: Multimodal LLM instance with bound tools
        prompt_template: Prompt template string with placeholders for paper info and images
        md_output_dir: Directory containing markdown files extracted from PDFs
        methods_save_path: Directory path for saving methodology files
    
    Returns:
        A chatbot function that can be used as a node in LangGraph
    """
    def chatbot(state_dict: State) -> State:
        """Methodology chatbot node that handles multimodal content (text + images)."""
        # IMPORTANT: Methodology phase is independent of summary phase
        # Clear all messages when entering methodology phase and reinitialize
        all_messages = state_dict.get("messages", [])
        # 优化：只在必要时读取state.json，优先使用内存中的状态
        if "parsed_multimodal_content" not in state_dict or not state_dict.get("parsed_multimodal_content"):
            try:
                state_file = os.path.join(os.path.dirname(__file__), "..", "outputs/state.json")
                if os.path.exists(state_file):
                    with open(state_file, "r", encoding="utf-8") as f:
                        new_state = json.loads(f.read())
                        state_dict["parsed_multimodal_content"] = new_state.get("parsed_multimodal_content", [])
            except Exception as e:
                logger.warning(f"读取state.json失败，使用内存状态: {e}")
        
        # Simple check: if we have any methodology-related message
        # Methodology messages are identified by:
        # 1. HumanMessage with multimodal content (list format, even if no images)
        # 2. The list format distinguishes it from summary phase (which uses string)
        has_methodology_init = any(
            isinstance(msg, HumanMessage) and 
            isinstance(msg.content, list) and 
            len(msg.content) > 0 and
            isinstance(msg.content[0], dict) and msg.content[0].get("type") == "text"
            for msg in all_messages
        )
        
        # If methodology is already initialized, keep all messages
        # Otherwise, clear all (from summary phase) and start fresh
        if has_methodology_init:
            messages = all_messages
        else:
            # Clear all messages and start fresh for methodology phase
            messages = []
            logger.info("🔬 开始提取Methodology")
        
        processed_papers = state_dict.get("processed_papers", set())
        parsed_content = state_dict.get("parsed_multimodal_content", [])
        
        # Find next unprocessed paper with successful parsing
        unprocessed_papers = [
            item for item in parsed_content
            if item.get("status") == "success" and 
            os.path.basename(item.get("pdf_path", "")) not in processed_papers
        ]
        
        # Initialize current_paper for first call if messages is empty
        # Only initialize if messages is empty (fresh start or no methodology messages yet)
        if not messages and unprocessed_papers:
            current_paper = unprocessed_papers[0]
            pdf_path = current_paper.get("pdf_path", "")
            paper_id = os.path.splitext(os.path.basename(pdf_path))[0]
            markdown_content = current_paper.get("content", "")
            
            # Save current_paper info to state_dict for later use
            state_dict["current_paper"] = {
                "paper_id": paper_id,
                "pdf_path": pdf_path,
                "content": markdown_content,
                "figures": current_paper.get("figures", [])
            }
            logger.info(f"📄 准备处理论文: {paper_id}")
        
        # Handle case with no unprocessed papers
        elif not unprocessed_papers and not messages:
            error_msg = "没有可处理的论文内容用于Methodology提取"
            logger.error(f"❌ {error_msg}")
            state_dict["errors"] = state_dict.get("errors", []) + [error_msg]
            return state_dict
        
        # Call multimodal LLM using call_multimodal_llm (similar to openlens-ai's approach)
        # This approach generates content first, then manually calls the tool to save it
        try:
            # Check if we have a current paper to process
            current_paper_info = state_dict.get('current_paper', {})
            
            # If no current paper or current paper is None, fetch next unprocessed paper
            if not current_paper_info:
                # Recalculate unprocessed papers to get the latest state
                parsed_content = state_dict.get("parsed_multimodal_content", [])
                processed_papers = state_dict.get("processed_papers", set())
                unprocessed_papers = [
                    item for item in parsed_content
                    if item.get("status") == "success" and 
                    os.path.basename(item.get("pdf_path", "")) not in processed_papers
                ]
                
                if unprocessed_papers:
                    current_paper = unprocessed_papers[0]
                    pdf_path = current_paper.get("pdf_path", "")
                    paper_id = os.path.splitext(os.path.basename(pdf_path))[0]
                    current_paper_info = {
                        "paper_id": paper_id,
                        "pdf_path": pdf_path,
                        "content": current_paper.get("content", ""),
                        "figures": current_paper.get("figures", [])
                    }
                    state_dict["current_paper"] = current_paper_info
            
            if not current_paper_info:
                error_msg = "没有可处理的论文内容"
                logger.error(f"❌ {error_msg}")
                state_dict["errors"] = state_dict.get("errors", []) + [error_msg]
                state_dict["messages"] = messages
                return state_dict
            
            paper_id = current_paper_info.get("paper_id", "unknown")
            markdown_content = current_paper_info.get("content", "")
            figures = current_paper_info.get("figures", [])
            
            # Format prompt
            figures_info = []
            for idx, fig_path_rel in enumerate(figures[:6]): 
                figures_info.append(f"Image {idx + 1}: {fig_path_rel}")
            
            formatted_prompt = prompt_template.format(
                paper_id=paper_id,
                markdown_content=markdown_content,
                figures_info="\n".join(figures_info) if figures_info else "No image information"
            )
            
            # Collect image paths for call_multimodal_llm
            md_dir = md_output_dir.rstrip("/") if md_output_dir else "res/markdown"
            base_path = Path(md_dir)
            image_paths = []
            for fig_path_rel in figures[:6]: 
                fig_path = base_path / fig_path_rel
                if fig_path.exists():
                    image_paths.append(str(fig_path))
            
            # Call multimodal LLM using the common method (similar to openlens-ai)
            logger.info("🤖 调用多模态模型生成Methodology...")
            methodology_content = call_multimodal_llm(
                llm=llm_with_tools,
                prompt=formatted_prompt,
                image_paths=image_paths,
                logger_instance=logger
            )
            
            # Filter out thinking content if present
            if methodology_content:
                import re
                if "<think>" in methodology_content.lower() or "思考过程" in methodology_content or "thinking:" in methodology_content.lower():
                    methodology_content = re.sub(r'<think>.*?</think>', '', methodology_content, flags=re.DOTALL | re.IGNORECASE)
                    methodology_content = re.sub(r'思考过程[:：].*?\n', '', methodology_content, flags=re.DOTALL)
                    methodology_content = re.sub(r'Thinking[:：].*?\n', '', methodology_content, flags=re.DOTALL | re.IGNORECASE)
            
            # Automatically call the tool to save the methodology content
            from tools.methodology_tools import MethodologyWriterTool
            tool = MethodologyWriterTool(save_path=methods_save_path)
            try:
                result = tool._run(methodology_content=methodology_content, paper_id=paper_id)
                logger.info(f"✅ Methodology已保存: {paper_id}")
                
                # Add messages to state for tracking
                messages.append(HumanMessage(content=formatted_prompt))
                messages.append(AIMessage(content=methodology_content))
                # Add ToolMessage to indicate tool was called
                tool_message = ToolMessage(
                    content=result,
                    tool_call_id="auto_save_methodology",
                    name="methodology_writer_tool"
                )
                messages.append(tool_message)
                
            except Exception as tool_error:
                logger.error(f"❌ 保存Methodology失败: {tool_error}")
                state_dict["errors"] = state_dict.get("errors", []) + [f"保存Methodology失败: {str(tool_error)}"]
                
            # Mark this paper as processed
            processed_papers = state_dict.get("processed_papers", set())
            processed_papers.add(os.path.basename(current_paper_info.get("pdf_path", "")))
            state_dict["processed_papers"] = processed_papers
            
            # Clear current_paper to force fetching next unprocessed paper on next call
            state_dict["current_paper"] = None
            
        except Exception as e:
            logger.error(f"❌ 调用Multimodal LLM生成Methodology失败: {str(e)}")
            state_dict["errors"] = state_dict.get("errors", []) + [f"调用Multimodal LLM生成Methodology失败: {str(e)}"]
        
        state_dict["messages"] = messages
        return state_dict
    
    return chatbot

def create_pdf_parser_chatbot(llm, prompt_template: str, pdf_dir: str = "data/pdf/"):
    """
    Create a chatbot function for PDF parsing.
    
    Args:
        llm: Language model instance with bound tools
        prompt_template: Prompt template string with placeholders for pdf_path
        pdf_dir: Default directory containing PDF files
    
    Returns:
        A chatbot function that can be used as a node in LangGraph
    """
    def chatbot(state_dict: State) -> State:
        """PDF parser chatbot node that prompts LLM to parse PDFs."""
        messages = state_dict.get("messages", [])
        
        # Only add initial prompt if messages is empty
        if not messages:
            # Check if there are PDF files to parse
            pdf_files = state_dict.get("downloaded_papers", [])
            if not pdf_files:
                # Try to get PDF files from pdf_dir
                pdf_files = get_pdf_files(pdf_dir)
                if pdf_files:
                    state_dict["downloaded_papers"] = pdf_files
            
            if not pdf_files:
                # Use pdf_dir as the path to parse
                pdf_path = pdf_dir
            else:
                # Use the first PDF file's directory, or the file itself
                if len(pdf_files) == 1:
                    pdf_path = pdf_files[0]
                else:
                    # Multiple files, use the directory
                    pdf_path = os.path.dirname(pdf_files[0]) if pdf_files else pdf_dir
            
            # Format prompt
            prompt = prompt_template.format(pdf_path=pdf_path)
            
            # Add prompt as human message
            messages.append(HumanMessage(content=prompt))
            logger.info(f"📚 开始解析PDF: {os.path.basename(pdf_path) if pdf_path else pdf_dir}")
        
        # Call LLM with current messages
        try:
            response = llm.invoke(messages)
            messages.append(response)
            # Log if tool calls are present
            if hasattr(response, "tool_calls") and response.tool_calls:
                logger.info(f"✅ PDF解析完成")
        except Exception as e:
            error_msg = f"调用PDF解析LLM失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            state_dict["errors"] = state_dict.get("errors", []) + [error_msg]
        
        state_dict["messages"] = messages
        return state_dict
    
    return chatbot
