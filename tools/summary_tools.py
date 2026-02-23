"""Summary tools for literature parsing workflow"""
import os
import logging
from typing import Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class SummaryWriterToolInput(BaseModel):
    summary_report: str = Field(
        ...,
        description="Summary report with Introduction and Related Works sections in markdown format."
    )
    file_name: str = Field(
        default="report_draft.md",
        description="The name of the file to write to. Default is 'report_draft.md'."
    )


class SummaryWriterTool(BaseTool):
    """Tool for writing summary reports to files."""
    name: str = "summary_writer_tool"
    description: str = "A tool that writes summary reports (Introduction and Related Works) to a fixed location."
    args_schema: Type[BaseModel] = SummaryWriterToolInput
    save_path: str = "../outputs/reports"
    file_name: str = ""

    def __init__(self, save_path: str = "../outputs/reports", file_name: str = ""):
        super().__init__()
        self.save_path = save_path
        self.file_name = file_name
        os.makedirs(self.save_path, exist_ok=True)
        
    def _run(self, summary_report: str, file_name: str = "report_draft.md") -> str:
        """Write summary report to file after parsing and validating format."""
        if self.file_name:
            file_name = self.file_name
        
        # Parse and extract Introduction and Related Works sections
        intro_start = summary_report.find("# Introduction")
        related_start = summary_report.find("# Related Works")
        
        if intro_start == -1 or related_start == -1:
            # If format is incorrect, try to save as-is but log a warning
            logger.warning(
                "Report format may be incorrect. Expected '## Introduction' and '## Related Works' sections. "
                "Saving content as-is."
            )
            # Save the entire content
            parsed_content = summary_report
        else:
            # Extract only the Introduction and Related Works sections
            introduction = summary_report[intro_start:related_start].strip()
            related_works = summary_report[related_start:].strip()
            parsed_content = introduction + "\n\n" + related_works
        
        file_path = os.path.join(self.save_path, file_name)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(parsed_content)
        
        return f"Summary report written to {file_path}"

