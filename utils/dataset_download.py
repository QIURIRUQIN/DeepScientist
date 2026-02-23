import os
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
from pathlib import Path
import kaggle
from kaggle.api.kaggle_api_extended import KaggleApi

# Kaggle 认证模块（无改动）
class KaggleAuthenticator:
    """适配官方Kaggle包的认证模块"""
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self._find_kaggle_config()
        self.api = KaggleApi()
        self._authenticate()

    def _find_kaggle_config(self) -> str:
        possible_paths = [
            Path.home() / ".kaggle" / "kaggle.json",
            Path("/etc/kaggle/kaggle.json"),
            Path.cwd() / "kaggle.json"
        ]
        for path in possible_paths:
            if path.exists():
                os.environ['KAGGLE_CONFIG_DIR'] = str(path.parent)
                return str(path)
        raise FileNotFoundError(
            "未找到kaggle.json配置文件。请前往Kaggle网站创建API Token，"
            "并将kaggle.json放置在 ~/.kaggle/ 目录下"
        )

    def _authenticate(self):
        try:
            self.api.authenticate()
        except Exception as e:
            raise PermissionError(f"Kaggle认证失败: {e}\n请检查kaggle.json是否正确")

    def get_official_api(self) -> KaggleApi:
        return self.api

@dataclass
class DatasetInfo:
    """数据集信息类（仅保留基础属性）"""
    ref: str  # username/dataset-name
    title: str
    description: str
    size: str
    downloads: int
    votes: int
    url: str
    tags: List[str]
    is_public: bool

class KaggleSearcher:
    """使用官方API的Kaggle搜索模块（彻底移除dataset_metadata）"""
    def __init__(self, authenticator):
        self.auth = authenticator
        self.api = authenticator.get_official_api()

    def search_by_keyword(self, keyword: str, max_results: int = 10) -> List[DatasetInfo]:
        """
        仅用官方支持的参数搜索，且只依赖dataset_list返回的基础属性
        """
        try:
            raw_datasets = self.api.dataset_list(
                search=keyword,
                sort_by='hottest',
                page=1
            )
            # 切片限制结果数
            raw_datasets = raw_datasets[:max_results]
            
            if not raw_datasets:
                raw_datasets = self.api.dataset_list(search=keyword)[:max_results]
            
            datasets = self._parse_official_results(raw_datasets)
            return datasets

        except Exception as e:
            raise RuntimeError(f"搜索失败: {e}")

    def _parse_official_results(self, raw_datasets) -> List[DatasetInfo]:
        datasets = []
        for ds in raw_datasets:
            try:
                # 仅提取dataset_list返回的基础属性（官方保证这些属性存在）
                dataset = DatasetInfo(
                    ref=ds.ref,
                    title=ds.title,
                    # 描述：直接用标题替代（避免调用错误的元数据接口）
                    description=f"Dataset: {ds.title} (Search keyword: {ds.ref.split('/')[1]})",
                    size="未知大小",  # 无可靠方式获取，直接标注
                    downloads=getattr(ds, 'downloads', 0) or 0,
                    votes=getattr(ds, 'votes', 0) or 0,
                    url=f"https://www.kaggle.com/datasets/{ds.ref}",
                    tags=[],  # 无可靠方式获取，留空
                    is_public=True  # 搜索结果默认是公开数据集
                )
                datasets.append(dataset)
            except Exception as e:
                print(f"解析数据集 {getattr(ds, 'ref', '未知')} 失败: {e}")
                continue
        return datasets

    def select_best_match(self, datasets: List[DatasetInfo], keyword: str) -> Optional[DatasetInfo]:
        """选择最佳匹配"""
        if not datasets:
            return None
        keyword_lower = keyword.lower()
        scored_datasets = []
        for dataset in datasets:
            score = 0
            # 标题匹配
            if keyword_lower in dataset.title.lower():
                score += 50
            if keyword_lower == dataset.title.lower():
                score += 50
            # 描述匹配（基于标题的描述）
            if keyword_lower in dataset.description.lower():
                score += 20
            # 受欢迎程度
            score += min(dataset.downloads / 1000, 15)
            score += min(dataset.votes / 100, 10)
            scored_datasets.append((score, dataset))
        scored_datasets.sort(reverse=True, key=lambda x: x[0])
        return scored_datasets[0][1]

class KaggleDownloader:
    """下载模块"""
    def __init__(self, authenticator):
        self.auth = authenticator
        self.api = authenticator.get_official_api()

    def download_dataset(self, dataset_ref: str, 
                        output_dir: str = "./datasets",
                        extract: bool = True) -> Tuple[bool, str]:
        """仅用官方download_files方法，不调用任何元数据接口"""
        try:
            output_path = Path(output_dir) / dataset_ref.split('/')[-1]
            output_path.mkdir(parents=True, exist_ok=True)
            
            print(f"正在下载数据集 {dataset_ref} 到 {output_path}")
            # 下载
            self.api.dataset_download_files(
                dataset_ref,
                path=str(output_path),
                unzip=extract,
                quiet=False
            )
            # 统计本地文件
            file_list = []
            for root, dirs, files in os.walk(output_path):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), output_path)
                    file_list.append(rel_path)
            # 格式化输出
            file_list_str = "\n".join(file_list[:10])
            if len(file_list) > 10:
                file_list_str += f"\n... 共 {len(file_list)} 个文件"
            message = f"""
数据集下载完成！
📂 存储位置：{output_path}
📊 文件总数：{len(file_list)}
📋 文件列表：
{file_list_str}
            """.strip()
            return True, message, output_path
        except Exception as e:
            return False, f"下载失败: {str(e)}", " "

    def get_dataset_info(self, dataset_ref: str) -> Optional[Dict]:
        """废弃：不再尝试获取元数据，直接返回空"""
        return None
