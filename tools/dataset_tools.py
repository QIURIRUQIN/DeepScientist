from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, PrivateAttr
from dataclasses import dataclass
from pathlib import Path
import os
import time
from loguru import logger

try:
    from langchain.tools import BaseTool
except ImportError:
    class BaseTool:
        name: str = ""
        description: str = ""
        args_schema: Any = None
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
        def _run(self, **kwargs):
            raise NotImplementedError
        async def _arun(self, **kwargs):
            raise NotImplementedError

# 确保导入的模块返回值匹配
from utils.dataset_download import KaggleAuthenticator, KaggleSearcher, KaggleDownloader, DatasetInfo
from utils.state import State

# 极简配置（仅保留必要项）
@dataclass
class KaggleToolConfig:
    config_path: Optional[str] = None
    default_download_path: str = "./datasets"
    auto_extract: bool = True

class KaggleDatasetInput(BaseModel):
    keyword: str = Field(description="搜索关键词（必填）")
    download_path: Optional[str] = Field(default=None, description="下载路径")

class KaggleDatasetTool(BaseTool):
    name: str = "kaggle_dataset_downloader"
    description: str = """仅下载1个含.csv的数据集，找到后立即终止所有操作"""
    args_schema: type[BaseModel] = KaggleDatasetInput
    _config: KaggleToolConfig = PrivateAttr()
    _authenticator: KaggleAuthenticator = PrivateAttr()
    _searcher: KaggleSearcher = PrivateAttr()
    _downloader: KaggleDownloader = PrivateAttr()

    def __init__(self, config: Optional[KaggleToolConfig] = None, **kwargs):
        super().__init__(** kwargs)
        self._config = config or KaggleToolConfig()
        try:
            self._authenticator = KaggleAuthenticator(self._config.config_path)
            self._searcher = KaggleSearcher(self._authenticator)
            self._downloader = KaggleDownloader(self._authenticator)
            # 修复kaggle.json权限
            kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
            if kaggle_json.exists():
                os.chmod(kaggle_json, 0o600)
        except Exception as e:
            raise RuntimeError(f"Kaggle初始化失败：{e}")

    @staticmethod
    def _check_csv_exists(path: str) -> bool:
        """检测是否有有效.csv文件"""
        if not path:
            return False
        p = Path(path)
        for csv_file in p.rglob("*.csv"):
            if csv_file.is_file() and csv_file.stat().st_size > 100:
                logger.info(f"✅ 找到有效CSV：{csv_file}")
                return True
        return False

    @staticmethod
    def _optimize_keywords(keyword: str) -> List[str]:
        """
        优化关键词，生成多个搜索策略（从精确到通用）
        策略1: 原始关键词（清理后）
        策略2: 提取核心名词（去除修饰词）
        策略3: 拆分复合关键词，分别尝试
        策略4: 使用单个核心词
        """
        import re
        
        # 清理关键词：去除特殊字符，保留字母、数字、空格、连字符
        clean_keyword = re.sub(r'[^\w\s-]', ' ', keyword)
        clean_keyword = " ".join([w.strip() for w in clean_keyword.split() if w.strip()])
        
        keywords = [clean_keyword]  # 策略1: 原始关键词
        
        # 策略2: 提取核心名词（去除常见修饰词）
        words = clean_keyword.split()
        # 常见修饰词列表（可以扩展）
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                     'of', 'with', 'by', 'from', 'as', 'is', 'are', 'was', 'were', 'be', 
                     'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 
                     'would', 'should', 'could', 'may', 'might', 'must', 'can', 'multi',
                     'classification', 'management', 'system', 'framework', 'model', 'method'}
        core_words = [w for w in words if w.lower() not in stop_words and len(w) > 2]
        if len(core_words) > 0:
            # 保留前3-5个核心词
            core_keyword = " ".join(core_words[:5])
            if core_keyword != clean_keyword:
                keywords.append(core_keyword)
        
        # 策略3: 如果关键词包含多个部分，尝试拆分
        if len(words) > 2:
            # 尝试前半部分
            first_half = " ".join(words[:len(words)//2 + 1])
            if first_half not in keywords:
                keywords.append(first_half)
            # 尝试后半部分
            second_half = " ".join(words[len(words)//2:])
            if second_half not in keywords:
                keywords.append(second_half)
        
        # 策略4: 使用单个最重要的核心词（通常是第一个或最长的）
        if core_words:
            # 选择最长的核心词，或者第一个核心词
            single_keyword = max(core_words, key=len) if core_words else words[0] if words else ""
            if single_keyword and single_keyword not in keywords:
                keywords.append(single_keyword)
        
        # 去重并保持顺序
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen and kw.strip():
                seen.add(kw_lower)
                unique_keywords.append(kw)
        
        return unique_keywords

    def _run(self, **kwargs) -> tuple[str, str, str]:
        """
        优化后的核心逻辑：多级降级策略，确保能找到数据集
        1. 尝试多个关键词变体（从精确到通用）
        2. 每个关键词尝试多个结果（max_results=5）
        3. 选择最佳匹配的数据集
        4. 验证CSV文件存在
        """
        # 1. 解析参数
        keyword = kwargs.get('keyword', '').strip()
        download_path = kwargs.get('download_path') or self._config.default_download_path
        os.makedirs(download_path, exist_ok=True)

        if not keyword:
            raise RuntimeError("关键词不能为空！")

        # 2. 生成多个关键词策略
        keyword_strategies = self._optimize_keywords(keyword)
        logger.info(f"🔍 原始关键词：{keyword}")
        logger.info(f"📋 生成搜索策略：{keyword_strategies}")

        # 3. 多级降级策略：依次尝试每个关键词
        all_datasets = []
        tried_keywords = []
        
        for search_keyword in keyword_strategies:
            tried_keywords.append(search_keyword)
            logger.info(f"🔎 尝试关键词：{search_keyword}")

            try:
                # 每个关键词尝试获取5个结果
                datasets = self._searcher.search_by_keyword(search_keyword, max_results=5)
                if datasets:
                    logger.info(f"✅ 关键词'{search_keyword}'找到{len(datasets)}个结果")
                    all_datasets.extend(datasets)
                    # 如果找到结果，继续尝试其他关键词以收集更多候选
                else:
                    logger.warning(f"⚠️ 关键词'{search_keyword}'无结果")
            except Exception as e:
                logger.warning(f"⚠️ 关键词'{search_keyword}'搜索出错：{e}")
                continue
        
        # 4. 如果没有找到任何数据集，使用通用关键词
        if not all_datasets:
            logger.warning("⚠️ 所有策略均失败，尝试通用关键词")
            generic_keywords = ["data", "dataset", "csv", "finance", "stock", "market", "crypto"]
            for gen_kw in generic_keywords:
                try:
                    datasets = self._searcher.search_by_keyword(gen_kw, max_results=3)
                    if datasets:
                        all_datasets.extend(datasets)
                        logger.info(f"✅ 通用关键词'{gen_kw}'找到{len(datasets)}个结果")
                        break
                except Exception as e:
                    continue
        
        if not all_datasets:
            raise RuntimeError(f"❌ 所有关键词策略均无检索结果。尝试的关键词：{tried_keywords}")
        
        # 5. 去重数据集（基于ref）
        seen_refs = set()
        unique_datasets = []
        for ds in all_datasets:
            if ds.ref not in seen_refs:
                seen_refs.add(ds.ref)
                unique_datasets.append(ds)
        
        logger.info(f"📊 共找到{len(unique_datasets)}个唯一数据集")
        
        # 6. 选择最佳匹配（优先选择与关键词最相关的）
        best_dataset = self._searcher.select_best_match(unique_datasets, keyword)
        if not best_dataset:
            # 如果选择失败，使用第一个
            best_dataset = unique_datasets[0]
        
        logger.info(f"📥 选择数据集：{best_dataset.title} ({best_dataset.ref})")
        
        # 7. 下载该数据集
        success, msg, output_path = self._downloader.download_dataset(
            best_dataset.ref, download_path, self._config.auto_extract
        )
        
        if not success:
            # 如果第一个失败，尝试其他数据集
            logger.warning(f"⚠️ 数据集{best_dataset.ref}下载失败，尝试其他数据集")
            for dataset in unique_datasets[:5]:  # 最多尝试5个
                if dataset.ref == best_dataset.ref:
                    continue
                logger.info(f"🔄 尝试下载：{dataset.ref}")
                success, msg, output_path = self._downloader.download_dataset(
                    dataset.ref, download_path, self._config.auto_extract
                )
                if success and self._check_csv_exists(output_path):
                    best_dataset = dataset
                    break
        
        # 8. 检测CSV，成功则返回
        if success and self._check_csv_exists(output_path):
            csv_files = list(Path(output_path).rglob("*.csv"))
            csv_file = csv_files[0] if csv_files else "未找到"
            final_msg = f"""✅ 下载完成！
- 原始关键词：{keyword}
- 使用关键词：{tried_keywords}
- 数据集：{best_dataset.title}
- 数据集引用：{best_dataset.ref}
- 路径：{output_path}
- CSV文件：{csv_file}"""
            return final_msg.strip(), output_path, best_dataset.url
        
        # 9. 失败则报错
        raise RuntimeError(f"""❌ 下载失败！
- 尝试的关键词：{tried_keywords}
- 数据集：{best_dataset.ref}
- 原因：{msg}（未找到有效CSV）""")

    async def _arun(self, **kwargs):
        import asyncio
        return await asyncio.get_event_loop().run_in_executor(None, lambda: self._run(** kwargs))

def create_kaggle_tool():
    def create_tool(state: State) -> State:
        # 获取关键词，支持多种来源
        raw_keyword = state.get("dataset", "").strip()
        
        # 如果dataset字段为空，尝试从其他字段获取
        if not raw_keyword:
            # 尝试从topic、new_idea等字段获取
            raw_keyword = state.get("topic", "").strip()
            if not raw_keyword:
                raw_keyword = state.get("new_idea", "").strip()
            if not raw_keyword:
                # 默认使用通用关键词
                raw_keyword = "finance data"
        
        final_keyword = raw_keyword.strip()
        logger.info(f'📌 最终检索关键词：{final_keyword}')

        # 初始化工具
        config = KaggleToolConfig()
        dataset_tool = KaggleDatasetTool(config=config)
        
        # 执行下载（使用优化后的多级降级策略）
        try:
            result, output_path, dataset_url = dataset_tool._run(
                keyword=final_keyword,
                download_path=state.get("download_path", "./datasets")
            )
        except Exception as e:
            logger.error(f"❌ 数据集检索失败：{e}")
            # 如果失败，尝试使用更通用的关键词
            logger.info("🔄 尝试使用通用关键词重新搜索...")
            try:
                result, output_path, dataset_url = dataset_tool._run(
                    keyword="data csv",
                    download_path=state.get("download_path", "./datasets")
                )
                logger.info("✅ 使用通用关键词成功找到数据集")
            except Exception as e2:
                raise RuntimeError(f"❌ 数据集检索完全失败：{e2}")

        # 处理结果
        state["input_data_path"] = output_path
        state["dataset_url"] = dataset_url
        state["download_status"] = result

        # 校验
        if not dataset_tool._check_csv_exists(output_path):
            raise RuntimeError("❌ 未找到有效CSV文件！")
        
        logger.info(f"✅ 数据集下载成功：{output_path}")
        return state

    return create_tool

# ==================== 测试代码 ====================
if __name__ == "__main__":
    # 模拟State类
    class State(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    # 修复权限
    try:
        kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
        if kaggle_json.exists():
            os.chmod(kaggle_json, 0o600)
            print("✅ 已修复kaggle.json权限")
        else:
            raise FileNotFoundError("kaggle.json不存在！")
    except Exception as e:
        print(f"权限错误：{e}")
        exit(1)

    # 测试执行（仅下载1个）
    tool = create_kaggle_tool()
    state = State({
        "dataset": "air pollution in beijing",
        "download_path": "/Users/chongyanghe/Desktop/DeepScientist/outputs/dataset"
    })

    try:
        result_state = tool(state)
        print("\n🎉 仅下载1个数据集成功！")
        print(f"路径：{result_state['input_data_path']}")
        print(f"状态：{result_state['download_status']}")
    except Exception as e:
        print(f"\n❌ 失败：{e}")
        import traceback
        traceback.print_exc()
