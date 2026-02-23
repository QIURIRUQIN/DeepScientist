"""PDF parser tools for literature parsing workflow"""
import os
import logging
from typing import Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from tools.pdf_parser import PDFParser
from common.utils import get_pdf_files
from utils.state import State
import json
from langchain_core.load import dumps, loads
from loguru import logger

# Suppress docling INFO logs - only show WARNING and above
logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("docling_core").setLevel(logging.WARNING)
logging.getLogger("docling.datamodel").setLevel(logging.WARNING)
logging.getLogger("docling.document_converter").setLevel(logging.WARNING)

# logger = logging.getLogger(__name__)


class PDFParserToolInput(BaseModel):
    pdf_path: str = Field(
        ...,
        description="Path to PDF file or directory containing PDF files to parse."
    )
    enable_formula_enrichment: bool = Field(
        default=False,
        description="Whether to enable formula enrichment (default False, as it's very slow)."
    )


class PDFParserTool(BaseTool):
    """Tool for parsing PDF files and converting them to markdown format."""
    name: str = "pdf_parser_tool"
    description: str = (
        "A tool that parses PDF files and converts them to markdown format with extracted images. "
        "You MUST use this tool to parse PDF files before generating summaries. "
        "Required parameter: pdf_path (path to PDF file or directory containing PDF files). "
        "Optional parameter: enable_formula_enrichment (default False, as it's very slow)."
    )
    args_schema: Type[BaseModel] = PDFParserToolInput
    state: dict = dict()
    pdf_dir: str = "../outputs/pdf"
    md_output_dir: str = "../outputs/markdown"

    def __init__(self, state: State = dict(), pdf_dir: str = "../outputs/pdf", md_output_dir: str = "../outputs/markdown"):
        super(PDFParserTool, self).__init__()
        self.pdf_dir = pdf_dir
        self.md_output_dir = md_output_dir
        self.state = state  # Store parsed state for tool node to access
        os.makedirs(self.pdf_dir, exist_ok=True)
        os.makedirs(self.md_output_dir, exist_ok=True)

    def _run(self, pdf_path: str, enable_formula_enrichment: bool = False) -> str:
        """Parse PDF file(s) and convert to markdown format."""
        try:
            # If pdf_path is a file, use it directly; if it's a directory, use it as pdf_dir
            if os.path.isfile(pdf_path):
                # Single file
                pdf_files = [pdf_path]
                actual_pdf_dir = os.path.dirname(pdf_path)
            elif os.path.isdir(pdf_path):
                # Directory - get all PDF files
                actual_pdf_dir = pdf_path
                pdf_files = get_pdf_files(pdf_path)
            else:
                # Use default pdf_dir
                actual_pdf_dir = self.pdf_dir
                pdf_files = get_pdf_files(self.pdf_dir)
            
            if not pdf_files:
                error_msg = f"No PDF files found in {actual_pdf_dir}"
                logger.warning(f"⚠️ {error_msg}")
                return f"Error: {error_msg}"
            
            logger.info(f"📚 发现 {len(pdf_files)} 个PDF文件")

            pdf_parser = PDFParser(actual_pdf_dir, self.md_output_dir, enable_formula_enrichment)
            self.state["downloaded_papers"] = pdf_files

            # Run parser with parallel processing and caching
            # 使用并行处理和缓存来加速
            max_workers = min(4, len(pdf_files))  # 最多4个并行线程
            self.state = pdf_parser.run(self.state, max_workers=max_workers, use_cache=True)
            success_count = sum(1 for r in self.state["parsed_multimodal_content"] if r.get("status") == "success")
            result_msg = f"Successfully parsed {success_count}/{len(self.state['parsed_multimodal_content'])} PDF file(s). "
            result_msg += f"Markdown files saved to {self.md_output_dir}"
            
            # Prepare state for serialization: convert set to list
            state_to_save = dict(self.state)
            if "processed_papers" in state_to_save and isinstance(state_to_save["processed_papers"], set):
                state_to_save["processed_papers"] = list(state_to_save["processed_papers"])
            
            # Save state to file
            state_file_path = os.path.join(os.path.dirname(__file__), "..", "outputs", "state.json")
            state_file_path = os.path.abspath(state_file_path)  # Get absolute path
            os.makedirs(os.path.dirname(state_file_path), exist_ok=True)
            
            try:
                with open(state_file_path, "w", encoding="utf-8") as f:
                    f.write(dumps(state_to_save, indent=2))
                logger.info(f"✅ State stored successfully to {state_file_path}")
            except Exception as save_error:
                logger.error(f"❌ Failed to save state with dumps: {str(save_error)}")
                logger.exception(save_error)  # Log full traceback
                # Try with json.dump as fallback (may fail if state contains non-serializable objects)
                try:
                    with open(state_file_path, "w", encoding="utf-8") as f:
                        json.dump(state_to_save, f, indent=2, default=str, ensure_ascii=False)
                    logger.info(f"✅ State stored using json.dump fallback")
                except Exception as fallback_error:
                    logger.error(f"❌ Failed to save state even with fallback: {str(fallback_error)}")
                    logger.exception(fallback_error)  # Log full traceback
            return result_msg
        except Exception as e:
            try:
                error_msg = f"Error parsing PDF: {str(e)}"
                logger.error(f"❌ {error_msg}")
                return f"Error: {error_msg}"
            except Exception as inner_e:
                # 如果格式化错误消息时出错，使用通用错误消息
                logger.error(f"❌ Error parsing PDF: {type(e).__name__}")
                logger.error(f"❌ Additional error while formatting: {str(inner_e)}")
                return f"Error: Failed to parse PDF (exception type: {type(e).__name__})"
