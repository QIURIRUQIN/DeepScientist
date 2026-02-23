"""Simple tool node for executing tool calls in LangGraph."""
import logging
from typing import Dict, Any, Optional, Callable
from langchain_core.messages import ToolMessage

logger = logging.getLogger(__name__)


class SimpleToolNode:
    """
    A tool node that executes tool calls from AI messages.
    Supports optional context injection for tools that need additional state information.
    """
    
    def __init__(
        self, 
        tools: list,
        context_provider: Optional[Callable[[Dict[str, Any], str, Dict[str, Any]], Dict[str, Any]]] = None
    ):
        """
        Initialize the tool node.
        
        Args:
            tools: List of tool instances
            context_provider: Optional function that enriches tool arguments with context from state.
                             Signature: (state_dict, tool_name, tool_args) -> enriched_tool_args
        """
        self.tools_by_name = {tool.name: tool for tool in tools}
        self.context_provider = context_provider
    
    def __call__(self, state_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute tool calls from the last AI message.
        
        Args:
            state_dict: Current state dictionary containing messages
        
        Returns:
            Updated state dictionary with tool execution results
        """
        messages = state_dict.get("messages", [])
        if not messages:
            logger.warning("No messages found in state")
            return state_dict
        
        last_message = messages[-1]
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            logger.warning("No tool calls found in last message")
            return state_dict
        
        outputs = []
        for tool_call in last_message.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            
            if tool_name not in self.tools_by_name:
                error_msg = f"Tool {tool_name} not found"
                logger.error(error_msg)
                outputs.append(
                    ToolMessage(
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=tool_call.get("id", ""),
                        status="error"
                    )
                )
                continue
            
            try:
                tool = self.tools_by_name[tool_name]
                
                # Enrich tool args with context if context_provider is provided
                if self.context_provider:
                    tool_args = self.context_provider(state_dict, tool_name, tool_args)
                
                tool_result = tool.invoke(tool_args)
                
                # Handle special tool results (e.g., update state)
                self._handle_tool_result(state_dict, tool_name, tool_result)
                
                outputs.append(
                    ToolMessage(
                        content=str(tool_result),
                        name=tool_name,
                        tool_call_id=tool_call.get("id", ""),
                        status="success"
                    )
                )
            except Exception as e:
                error_msg = f"Tool {tool_name} error: {str(e)}"
                logger.error(f"❌ {error_msg}")
                outputs.append(
                    ToolMessage(
                        content=error_msg,
                        name=tool_name,
                        tool_call_id=tool_call.get("id", ""),
                        status="error"
                    )
                )
        
        messages.extend(outputs)
        state_dict["messages"] = messages
        return state_dict
    
    def _handle_tool_result(self, state_dict: Dict[str, Any], tool_name: str, tool_result: Any):
        """
        Handle special tool results that need to update state.
        
        Args:
            state_dict: Current state dictionary
            tool_name: Name of the tool that was executed
            tool_result: Result from the tool execution
        """
        # If methodology_writer_tool succeeded, mark the paper as processed
        if tool_name == "methodology_writer_tool":
            # Extract paper_id from tool_result or from previous messages
            messages = state_dict.get("messages", [])
            processed_papers = state_dict.get("processed_papers", set())
            
            # Try to find paper_id from the last AI message's tool calls
            if messages:
                last_ai_msg = None
                for msg in reversed(messages):
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        last_ai_msg = msg
                        break
                
                if last_ai_msg:
                    for tool_call in last_ai_msg.tool_calls:
                        if tool_call.get("name") == "methodology_writer_tool":
                            paper_id = tool_call.get("args", {}).get("paper_id")
                            if paper_id:
                                # paper_id from tool is the PDF filename (e.g., "paper.pdf" or just "paper")
                                # We need to match it with the format used in chatbot (os.path.basename of pdf_path)
                                import os
                                # Get the basename and keep the .pdf extension if present
                                # This matches the format used in chatbot: os.path.basename(item.get("pdf_path", ""))
                                paper_id_clean = os.path.basename(paper_id)
                                # If it doesn't have .pdf extension, add it to match chatbot format
                                if not paper_id_clean.endswith('.pdf'):
                                    # Check if it's already in processed_papers without extension
                                    # We'll add both formats to be safe
                                    processed_papers.add(paper_id_clean)
                                    processed_papers.add(paper_id_clean + '.pdf')
                                else:
                                    processed_papers.add(paper_id_clean)
                                state_dict["processed_papers"] = processed_papers
                                break
        
        # If multimodal methodology tool succeeded, store the methodology result
        if tool_name == "multimodal_methodology_tool" and isinstance(tool_result, str):
            if "current_paper" in state_dict:
                state_dict["current_paper"]["methodology"] = tool_result
        
        # If pdf_parser_tool succeeded, update state with parsed content
        if tool_name == "pdf_parser_tool":
            tool = self.tools_by_name.get(tool_name)
            if tool and hasattr(tool, "_last_parsed_state"):
                parsed_state = tool._last_parsed_state
                # Update state_dict with parsed content
                state_dict["parsed_multimodal_content"] = parsed_state.parsed_multimodal_content
                state_dict["pdf_files"] = parsed_state.pdf_files
                if parsed_state.errors:
                    state_dict["errors"] = state_dict.get("errors", []) + parsed_state.errors
                # Clear the temporary state
                tool._last_parsed_state = None
