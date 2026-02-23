import os
import logging
from typing import List

def init_logger(name: str) -> logging.Logger:
    """初始化日志器"""
    logger = logging.getLogger(name)
    if logger.handlers:  # 避免重复添加handler
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def get_pdf_files(pdf_dir: str = "data/pdf/") -> List[str]:
    """获取指定目录下的所有PDF文件路径"""
    pdf_files = []
    if not os.path.exists(pdf_dir):
        logging.warning(f"PDF目录不存在: {pdf_dir}")
        return pdf_files
    
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.abspath(os.path.join(pdf_dir, filename))
            pdf_files.append(pdf_path)
    return pdf_files

def ensure_dirs():
    """确保输出目录存在"""
    dirs = [
        "outputs/parsed",
        "outputs/reports",
        "outputs/methods",
        "data/pdf",
        "res/markdown"  # PDF解析输出目录
    ]
    for dir_path in dirs:
        os.makedirs(dir_path, exist_ok=True)