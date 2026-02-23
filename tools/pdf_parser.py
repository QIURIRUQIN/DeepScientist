from typing import List, Dict, Any
from pathlib import Path
from tools.document_segment import SegmentTool
from docling_core.types.doc import ImageRefMode
from utils.state import State
from common.utils import init_logger, get_pdf_files, ensure_dirs
import os
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from langchain_core.load import dumps, loads

# logger = init_logger("pdf_parser_agent")

class PDFParser:
    def __init__(self, pdf_path, md_out_path, enable_formula_enrichment: bool = False):
        """
        初始化PDF解析代理
        
        Args:
            enable_formula_enrichment: 是否启用公式识别（默认False，因为很慢）
        """
        ensure_dirs()
        self.pdf_dir = pdf_path
        self.md_output_dir = md_out_path
        self.segment_tool = SegmentTool(enable_formula_enrichment=enable_formula_enrichment)
    
    def _is_pdf_cached(self, pdf_path: str, md_output_dir: str) -> bool:
        """
        检查PDF是否已经解析过（缓存检查）
        
        Args:
            pdf_path: PDF文件路径
            md_output_dir: Markdown输出目录
        
        Returns:
            True如果已缓存且PDF未修改，False否则
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            return False
        
        file_stem = pdf_file.stem
        output_dir = Path(md_output_dir) / file_stem
        md_file = output_dir / f"{file_stem}.md"
        
        # 如果markdown文件不存在，需要解析
        if not md_file.exists():
            return False
        
        # 检查PDF文件的修改时间
        pdf_mtime = pdf_file.stat().st_mtime
        md_mtime = md_file.stat().st_mtime
        
        # 如果PDF比markdown新，需要重新解析
        if pdf_mtime > md_mtime:
            logger.info(f"📄 PDF已更新，需要重新解析: {pdf_file.name}")
            return False
        
        return True
    
    def _convert_single_pdf(self, pdf_path: str, md_output_dir: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        转换单个PDF文件为Markdown
        
        Args:
            pdf_path: PDF文件路径
            md_output_dir: Markdown输出目录
            use_cache: 是否使用缓存（如果已解析过则跳过）
        
        Returns:
            Dict包含转换结果信息
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        file_stem = pdf_file.stem
        output_dir = Path(md_output_dir) / file_stem
        output_dir.mkdir(parents=True, exist_ok=True)
        figs_dir = output_dir / "figs"
        figs_dir.mkdir(parents=True, exist_ok=True)
        
        # 检查缓存
        if use_cache and self._is_pdf_cached(pdf_path, md_output_dir):
            logger.info(f"⚡ 使用缓存: {pdf_file.name} (跳过解析)")
            md_file = output_dir / f"{file_stem}.md"
            content = ""
            if md_file.exists():
                with open(md_file, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            figures = []
            if figs_dir.exists():
                for f in sorted(figs_dir.glob("*.png")):
                    figures.append(str(f.relative_to(Path(md_output_dir))))
            
            page_images_relative = []
            pages_dir = output_dir / "pages"
            if pages_dir.exists():
                for f in sorted(pages_dir.glob("*.png")):
                    page_images_relative.append(str(f.relative_to(Path(md_output_dir))))
            
            md_path_relative = None
            if md_file.exists():
                md_path_relative = str(md_file.relative_to(Path(md_output_dir)))
            
            return {
                "pdf_path": pdf_path,
                "markdown_path": md_path_relative,
                "content": content,
                "figures": figures,
                "page_images": page_images_relative,
                "status": "success",
                "cached": True
            }
        
        logger.info(f"🔄 正在处理: {pdf_file.name} -> {output_dir}")
        
        # 转换PDF
        conv_res = self.segment_tool.converter.convert(str(pdf_file))
        self.segment_tool._export_figures(conv_res, figs_dir, file_stem)
        
        # 将PDF每一页转换为图片（已注释，因为很慢）
        page_images = []
        
        # 导出Markdown
        md_file = output_dir / f"{file_stem}.md"
        conv_res.document.save_as_markdown(
            str(md_file),
            image_mode=ImageRefMode.REFERENCED,
            artifacts_dir=figs_dir
        )
        
        content = ""
        if md_file.exists():
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()
        
        figures = []
        if figs_dir.exists():
            for f in sorted(figs_dir.glob("*.png")):
                figures.append(str(f.relative_to(Path(md_output_dir))))
        
        page_images_relative = []
        pages_dir = output_dir / "pages"
        if pages_dir.exists():
            for f in sorted(pages_dir.glob("*.png")):
                page_images_relative.append(str(f.relative_to(Path(md_output_dir))))
        
        md_path_relative = None
        if md_file.exists():
            md_path_relative = str(md_file.relative_to(Path(md_output_dir)))
        
        return {
            "pdf_path": pdf_path,
            "markdown_path": md_path_relative,
            "content": content,
            "figures": figures,
            "page_images": page_images_relative,
            "status": "success",
            "cached": False
        }
    
    def run(self, state: State, max_workers: int = 4, use_cache: bool = True) -> State:
        """
        执行PDF解析流程（支持并行处理和缓存）
        
        Args:
            state: 状态字典
            max_workers: 最大并行工作线程数（默认4）
            use_cache: 是否使用缓存（默认True）
        
        Returns:
            更新后的状态字典
        """
        logger.info("🚀 开始PDF解析流程（并行模式）")
        
        pdf_files = state.get("downloaded_papers", [])
        if not pdf_files:
            logger.warning("⚠️ 未找到需要解析的PDF文件")
            return state
        
        logger.info(f"📚 发现 {len(pdf_files)} 个PDF文件")
        
        # 先检查缓存，分离需要解析和已缓存的文件
        files_to_parse = []
        cached_results = []
        
        for pdf_path in pdf_files:
            if use_cache and self._is_pdf_cached(pdf_path, self.md_output_dir):
                # 直接从缓存加载
                try:
                    result = self._convert_single_pdf(pdf_path, self.md_output_dir, use_cache=True)
                    cached_results.append(result)
                    logger.info(f"⚡ 从缓存加载: {Path(pdf_path).name}")
                except Exception as e:
                    logger.warning(f"⚠️ 缓存加载失败，将重新解析: {Path(pdf_path).name}, 错误: {e}")
                    files_to_parse.append(pdf_path)
            else:
                files_to_parse.append(pdf_path)
        
        parsed_results = cached_results.copy()
        
        # 并行处理需要解析的文件
        if files_to_parse:
            logger.info(f"🔄 需要解析 {len(files_to_parse)} 个文件（并行处理，最大线程数: {max_workers}）")
            
            def parse_single(pdf_path):
                """单个PDF解析任务"""
                try:
                    result = self._convert_single_pdf(pdf_path, self.md_output_dir, use_cache=False)
                    logger.info(f"✓ 成功解析: {Path(pdf_path).name}")
                    return result
                except Exception as e:
                    error_msg = f"解析{pdf_path}失败: {str(e)}"
                    logger.error(f"❌ {error_msg}", exc_info=True)
                    return {
                        "pdf_path": pdf_path,
                        "markdown_path": None,
                        "content": "",
                        "figures": [],
                        "page_images": [],
                        "status": "failed",
                        "error": str(e)
                    }
            
            # 使用线程池并行处理
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_pdf = {
                    executor.submit(parse_single, pdf_path): pdf_path 
                    for pdf_path in files_to_parse
                }
                
                # 收集结果
                for future in as_completed(future_to_pdf):
                    pdf_path = future_to_pdf[future]
                    try:
                        result = future.result()
                        parsed_results.append(result)
                    except Exception as e:
                        logger.error(f"❌ 处理 {Path(pdf_path).name} 时出错: {e}")
                parsed_results.append({
                    "pdf_path": pdf_path,
                    "markdown_path": None,
                    "content": "",
                    "figures": [],
                    "page_images": [],
                    "status": "failed",
                    "error": str(e)
                })
        
        # 更新状态
        if "parsed_multimodal_content" in state and state["parsed_multimodal_content"]:
            state["parsed_multimodal_content"].extend(parsed_results)
        else:
            state["parsed_multimodal_content"] = parsed_results
        
        # 更新错误列表
        failed_results = [r for r in parsed_results if r.get("status") == "failed"]
        if failed_results:
            if "errors" not in state:
                state["errors"] = []
            for result in failed_results:
                if "error" in result:
                    state["errors"].append(result["error"])
        
        success_count = sum(1 for r in parsed_results if r.get("status") == "success")
        cached_count = sum(1 for r in parsed_results if r.get("cached", False))
        logger.info(f"✅ PDF解析完成: 成功 {success_count}/{len(parsed_results)} 个文件 (其中 {cached_count} 个使用缓存)")
        
        return state
