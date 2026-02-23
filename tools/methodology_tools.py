"""Methodology tools for literature parsing workflow"""
import os
import logging
from typing import Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from loguru import logger

# logger = logging.getLogger(__name__)

class MethodologyWriterToolInput(BaseModel):
    methodology_content: str = Field(
        ...,
        description="Methodology content in markdown format."
    )
    paper_id: str = Field(
        ...,
        description="Paper identifier (usually PDF filename without extension)."
    )

class MethodologyWriterTool(BaseTool):
    """Tool for writing methodology content to files."""
    name: str = "methodology_writer_tool"
    description: str = (
        "Save methodology content to a file. "
        "Call this tool after generating methodology content. "
        "Parameters: paper_id (string, paper identifier) and methodology_content (string, methodology in markdown format)."
    )
    args_schema: Type[BaseModel] = MethodologyWriterToolInput
    save_path: str = "../outputs/methods"

    def __init__(self, save_path: str = "../outputs/methods"):
        super().__init__()
        # Convert relative path to absolute path
        if not os.path.isabs(save_path):
            # Get the project root directory (parent of tools directory)
            tools_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(tools_dir)
            self.save_path = os.path.abspath(os.path.join(project_root, save_path))
        else:
            self.save_path = save_path
        os.makedirs(self.save_path, exist_ok=True)
        logger.debug(f"MethodologyWriterTool initialized with save_path: {self.save_path}")

    def _run(self, methodology_content: str, paper_id: str) -> str:
        """Write methodology content to file."""
        try:
            # Remove file extension from paper_id if present
            paper_id_clean = os.path.splitext(paper_id)[0] + os.path.splitext(paper_id)[-1]
            file_name = f"{paper_id_clean}_methodology.md"
            file_path = os.path.join(self.save_path, file_name)
            
            # Ensure directory exists (double check)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Validate inputs
            if not methodology_content:
                logger.warning(f"Methodology content is empty for paper_id: {paper_id}")
            
            if not paper_id:
                raise ValueError("paper_id cannot be empty")
            
            # Write file with explicit flush
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {paper_id} - Methodology\n\n")
                f.write(methodology_content)
                f.flush()  # Explicitly flush to ensure data is written
                os.fsync(f.fileno())  # Force write to disk
            
            # Verify file was created and has content
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File was not created: {file_path}")
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise ValueError(f"File was created but is empty: {file_path}")
            
            logger.info(f"✅ Methodology written successfully to {file_path} (size: {file_size} bytes)")
            return f"Methodology written to {file_path}"
            
        except Exception as e:
            error_msg = f"Failed to write methodology for paper_id {paper_id}: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.exception(e)  # Log full traceback
            raise  # Re-raise to let caller handle it
