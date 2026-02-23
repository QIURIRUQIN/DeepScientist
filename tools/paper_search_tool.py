from typing import Type, List, Dict
from pydantic import BaseModel, Field

from langchain_core.tools import BaseTool

from utils.search_utils import ArxivSearch

arxiv_searcher = ArxivSearch()

def sync_to_async(func):
    """装饰器：将同步函数包装为异步函数"""
    import asyncio
    import functools

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
    
    return async_wrapper

class searchArxivInput(BaseModel):
    "Input arguments for searching papers on ArXiv"
    query: str = Field(..., description="Search query string (e.g., 'machine learning')")
    max_results: int = Field(10, description="Maximum number of papers to return")

class searhArxivTool(BaseTool):
    "Tool for searching academic papers from AriXv database"
    name: str = "search_academicPapers_from_AriXv"
    description: str = "Search for academic papers on ArXiv.org based on a query string.\
        Returns papers' metadata including title, authors, abstract, and other details"
    args_schema: Type[BaseModel] = searchArxivInput
    def _run(self, query: str = "", max_results: int = 10) -> List[Dict]:
        papers = arxiv_searcher.search(query, max_results)
        return [paper.to_dict() for paper in papers] if papers else []

    async def _arun(self, query: str = "", max_results: int = 10) -> List[Dict]:
        """Asynchronously execute arXiv search"""
        return await sync_to_async(self._run)(query, max_results)
