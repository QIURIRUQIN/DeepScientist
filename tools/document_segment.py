import logging
from pathlib import Path
from tqdm import tqdm
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF未安装，无法使用PDF页面转图片功能。请运行: pip install PyMuPDF")

# Suppress docling INFO logs - only show WARNING and above
logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("docling_core").setLevel(logging.WARNING)
logging.getLogger("docling.datamodel").setLevel(logging.WARNING)
logging.getLogger("docling.document_converter").setLevel(logging.WARNING)

IMAGE_RESOLUTION_SCALE = 2

class SegmentTool:
    def __init__(self, enable_formula_enrichment: bool = False):
        """
    
        使用 DocumentConverter 进行 PDF 转换，配置了图片和公式识别功能

        参考: https://docling-project.github.io/docling/examples/export_figures/

        Args:
            enable_formula_enrichment: 是否启用公式识别（默认 False，因为非常慢）
        """
        pipeline_options = PdfPipelineOptions()
        pipeline_options.images_scale = IMAGE_RESOLUTION_SCALE
        pipeline_options.generate_page_images = True                        # 生成页面图片
        pipeline_options.generate_picture_images = True                     # 生成图片元素的图片
        pipeline_options.do_formula_enrichment = enable_formula_enrichment  # 公式识别（启用会很慢）
        
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        
    def convert_pdf_to_md(self, pdf_path: str, md_path:str):
        """
        将 PDF 文件转换为 Markdown 格式
        
        对于每个 PDF 文件（例如 aaabbb.pdf）:
        1. 创建 my_work/data/markdown/aaabbb/ 目录
        2. 在该目录下保存转换后的 markdown 文件
        3. 创建 aaabbb/figs/ 子目录保存图片
        4. 公式会直接在 markdown 中以 LaTeX 格式显示
        
        Args:
            pdf_path: PDF 文件所在目录路径
        """
        pdf_dir = Path(pdf_path)
        
        # 遍历目录中的所有 PDF 文件
        pdf_files = list(pdf_dir.glob("*.pdf"))
        
        if not pdf_files:
            logging.warning(f"在目录 {pdf_path} 中未找到 PDF 文件")
            return
        
        for pdf_file in tqdm(pdf_files, desc="转换 PDF 文件"):
            try:
                file_stem = pdf_file.stem
                output_dir = Path(md_path) / file_stem
                output_dir.mkdir(parents=True, exist_ok=True)
                figs_dir = output_dir / "figs"
                figs_dir.mkdir(parents=True, exist_ok=True)
                
                logging.info(f"正在处理: {pdf_file.name} -> {output_dir}")
                
                # convert pdf to docling resultp
                conv_res = self.converter.convert(str(pdf_file))
                
                # export figures
                self._export_figures(conv_res, figs_dir, file_stem)
                
                # 步骤4: 将文档导出为 Markdown
                # 使用 REFERENCED 模式，图片会引用到相对路径 figs/ 目录
                md_file = output_dir / f"{file_stem}.md"
                conv_res.document.save_as_markdown(
                    str(md_file), 
                    image_mode=ImageRefMode.REFERENCED,
                    artifacts_dir=figs_dir
                )
                
                logging.info(f"✓ 完成: {md_file}")
                
            except Exception as e:
                logging.error(f"处理文件 {pdf_file.name} 时出错: {e}")
                import traceback
                logging.error(traceback.format_exc())
                continue
    
    def _export_figures(self, conv_res, figs_dir: Path, file_stem: str):
        
       # Save images of figures and tables
        picture_counter = 0
        table_counter = 0
        
        for element, _level in conv_res.document.iterate_items():
            # 处理PictureItem
            if isinstance(element, PictureItem):
                picture_counter += 1
                element_image_filename = figs_dir / f"{file_stem}_picture_{picture_counter}.png"
                
                try:
                    img = element.get_image(conv_res.document)
                    with element_image_filename.open("wb") as fp:
                        img.save(fp, "PNG")
                    logging.debug(f"  保存图片: {element_image_filename.name}")
                except Exception as e:
                    logging.warning(f"  提取图片失败 (picture {picture_counter}): {e}")
            
            # 处理TableItem
            # elif isinstance(element, TableItem):
            #     table_counter += 1
            #     element_image_filename = figs_dir / f"{file_stem}_table_{table_counter}.png"
                
            #     try:
            #         img = element.get_image(conv_res.document)
            #         with element_image_filename.open("wb") as fp:
            #             img.save(fp, "PNG")
            #         logging.debug(f"  保存表格图片: {element_image_filename.name}")
            #     except Exception as e:
            #         logging.warning(f"  提取表格图片失败 (table {table_counter}): {e}")
        
        if picture_counter > 0:
            logging.info(f"  共提取 {picture_counter} 张图片到 {figs_dir}")
    
    def convert_pdf_pages_to_images(self, pdf_path: str, output_dir: str, dpi: int = 200):
        """
        将PDF的每一页转换为图片并保存
        
        Args:
            pdf_path: PDF文件路径
            output_dir: 输出目录路径，图片将保存在该目录下的pages子目录中
            dpi: 图片分辨率，默认200（越高越清晰但文件越大）
        
        Returns:
            List[str]: 保存的图片文件路径列表
        """
        if not PYMUPDF_AVAILABLE:
            raise ImportError("PyMuPDF未安装，无法使用PDF页面转图片功能。请运行: pip install PyMuPDF")
        
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")
        
        # 创建输出目录
        output_path = Path(output_dir)
        pages_dir = output_path / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)
        
        file_stem = pdf_file.stem
        saved_images = []
        
        try:
            # 打开PDF文件
            doc = fitz.open(str(pdf_file))
            total_pages = len(doc)
            
            logging.info(f"开始转换PDF页面为图片: {pdf_file.name} (共{total_pages}页)")
            
            # 计算缩放因子（dpi转换为缩放因子，72是PDF的标准DPI）
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            
            # 遍历每一页
            for page_num in tqdm(range(total_pages), desc="转换页面"):
                page = doc[page_num]
                
                # 渲染页面为图片
                pix = page.get_pixmap(matrix=mat)
                
                # 保存图片
                image_filename = pages_dir / f"{file_stem}_page_{page_num + 1:03d}.png"
                pix.save(str(image_filename))
                saved_images.append(str(image_filename))
                
                logging.debug(f"  保存页面 {page_num + 1}: {image_filename.name}")
            
            doc.close()
            logging.info(f"✓ 完成: 共转换{total_pages}页，图片保存在 {pages_dir}")
            
        except Exception as e:
            logging.error(f"转换PDF页面为图片时出错: {e}")
            import traceback
            logging.error(traceback.format_exc())
            raise
        
        return saved_images
