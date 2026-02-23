import os
import logging
from typing import Dict, Any, Optional, Callable
from langchain_core.messages import ToolMessage, AIMessage

logger = logging.getLogger(__name__)


def route_by_tool_call(
    state_dict: Dict[str, Any],
    tool_name: str = "summary_writer_tool",
    check_papers: bool = False,
    on_tool_success: Optional[Callable[[Dict[str, Any]], str]] = None
) -> str:
    """
    Universal routing function based on tool calls and workflow state.
    
    Args:
        state_dict: Current state dictionary
        tool_name: Name of the tool to check for success (default: "summary_writer_tool")
        check_papers: Whether to check if all papers are processed (for methodology workflow)
        on_tool_success: Optional callback function to determine routing when tool succeeds.
                        If None, returns "END" for summary workflow or checks papers for methodology.
    
    Returns:
        Routing decision: "TOOLS", "CONTINUE", or "END"
    """
    # For methodology workflow, check if all papers are processed first
    if check_papers:
        parsed_content = state_dict.get("parsed_multimodal_content", [])
        processed_papers = state_dict.get("processed_papers", set())
        
        # Count unprocessed papers
        unprocessed = [
            item for item in parsed_content
            if item.get("status") == "success" and 
            os.path.basename(item.get("pdf_path", "")) not in processed_papers
        ]
        
        if not unprocessed:
            return "END"
    
    messages = state_dict.get("messages", [])
    if not messages:
        return "CONTINUE"
    
    last_message = messages[-1]
    last_msg_type = type(last_message).__name__
    
    # If last message is a ToolMessage, check if target tool succeeded
    if isinstance(last_message, ToolMessage):
        if last_message.name == tool_name and getattr(last_message, "status", None) == "success":
            # Use custom callback if provided, otherwise use default logic
            if on_tool_success:
                result = on_tool_success(state_dict)
                return result
            
            # Default behavior: for methodology, check if more papers to process
            if check_papers:
                parsed_content = state_dict.get("parsed_multimodal_content", [])
                processed_papers = state_dict.get("processed_papers", set())
                unprocessed = [
                    item for item in parsed_content
                    if item.get("status") == "success" and 
                    os.path.basename(item.get("pdf_path", "")) not in processed_papers
                ]
                if unprocessed:
                    return "CONTINUE"
                else:
                    return "END"
            else:
                # For summary workflow, tool success means end
                return "END"
        
        # Tool failed or other tool, continue to chatbot
        logger.debug(f"Tool message is not target tool or failed, continuing to chatbot")
        return "CONTINUE"
    
    # If last message is AIMessage with tool calls, route to tool node
    if isinstance(last_message, AIMessage):
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            tool_names = [tc.get("name") for tc in last_message.tool_calls]
            return "TOOLS"
    
    # Otherwise, continue to chatbot
    return "CONTINUE"


# Convenience functions for backward compatibility
def route_by_tool_call_summary(state_dict: Dict[str, Any]) -> str:
    """Route for summary workflow - tool success means end."""
    return route_by_tool_call(
        state_dict,
        tool_name="summary_writer_tool",
        check_papers=False
    )


def route_methodology_workflow(state_dict: Dict[str, Any]) -> str:
    """Route for methodology workflow - checks papers and processes multiple papers."""
    return route_by_tool_call(
        state_dict,
        tool_name="methodology_writer_tool",
        check_papers=True
    )


def route_pdf_parser_workflow(state_dict: Dict[str, Any]) -> str:
    """Route for PDF parser workflow - tool success means move to summary phase."""
    return route_by_tool_call(
        state_dict,
        tool_name="pdf_parser_tool",
        check_papers=False,
        on_tool_success=lambda _: "END"  # After PDF parsing, move to summary
    )