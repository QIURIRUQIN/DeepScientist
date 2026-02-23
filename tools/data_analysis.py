import os
import pandas as pd
import numpy as np
from typing import Dict, List, Any, TypedDict, Optional, Type
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# ====================== 第一步：基于BaseTool定义标准化工具 ======================
# 工具入参Schema（Pydantic校验）
class DataPathInput(BaseModel):
    data_path: str = Field(description="数据文件的完整路径（支持CSV/Excel）")

class LoadDataTool(BaseTool):
    """加载数据文件的标准化工具（继承BaseTool）"""
    name: str = "load_data"
    description: str = "读取指定路径的CSV/Excel数据文件，返回文件基本信息和加载后的DataFrame"
    args_schema: type[BaseModel] = DataPathInput  # 入参校验Schema

    def _run(self, data_path: str) -> Dict[str, Any]:
        """同步执行方法（BaseTool核心）"""
        filePath = ""
        for file in os.listdir(data_path):
            filePath = os.path.join(data_path, file)
            if os.path.isfile(filePath):
                break

        try:
            # 识别文件格式并读取
            file_ext = os.path.splitext(filePath)[1].lower()
            if file_ext == '.csv':
                df = pd.read_csv(filePath)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(filePath, engine='openpyxl')
            else:
                return {
                    "success": False,
                    "error": f"不支持的文件格式：{file_ext}，仅支持CSV/Excel"
                }

            # 基础信息提取
            basic_info = {
                "file_path": filePath,
                "file_name": os.path.basename(filePath),
                "row_count": len(df),
                "column_count": len(df.columns),
                "columns": list(df.columns),
                "data_types": df.dtypes.astype(str).to_dict(),
                "missing_values": df.isnull().sum().to_dict(),
                "duplicate_rows": df.duplicated().sum()
            }
            return {
                "success": True,
                "data": basic_info,
                "df": df  # 返回加载后的DataFrame供后续工具使用
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"加载数据失败：{str(e)}"
            }
        
class ColumnMeaningInput(BaseModel):
    column_name: str
    dtype: str
    nunique: int
    sample_values: List[str]

class ColumnMeaningTool(BaseTool):
    """Tool for inferring the business meaning of a single column"""
    name: str = "analyze_column_meaning"
    description: str = (
        "Infer the business semantics of a column based on its name, "
        "data type, and value characteristics"
    )
    args_schema: Type[BaseModel] = ColumnMeaningInput

    def _run(
        self,
        column_name: str,
        dtype: str,
        nunique: int,
        sample_values: List[str],
    ) -> str:
        col_name = column_name.lower()

        if any(k in col_name for k in ["id", "uid", "userid", "编号"]):
            return "Unique identifier column (e.g., user ID or record ID)"

        if any(k in col_name for k in ["time", "date", "datetime", "时间", "日期"]):
            return "Temporal column representing time or date information"

        if any(k in col_name for k in ["name", "姓名", "标题"]):
            return "Name or short textual description column"

        if "int" in dtype or "float" in dtype:
            if nunique <= 10:
                return (
                    "Categorical numeric column "
                    "(e.g., rating, level, or status code)"
                )
            return (
                "Continuous numerical column "
                "(e.g., amount, quantity, or measured value)"
            )

        if "object" in dtype or "string" in dtype:
            if nunique / max(len(sample_values), 1) < 0.3:
                return (
                    "Categorical text column "
                    "(e.g., gender, region, or category label)"
                )
            return (
                "Free-form text column "
                "(e.g., comments, descriptions, or notes)"
            )

        return (
            "Unable to infer the column semantics with high confidence; "
            "additional domain knowledge may be required"
        )

def compute_column_statistics(df: pd.DataFrame) -> Dict[str, Any]:
    column_stats = {}
    for col in df.columns:
        col_data = df[col]
        stats = {
            "column_name": col,
            "data_type": str(col_data.dtype),
            "non_null_count": int(col_data.notnull().sum()),
            "null_count": int(col_data.isnull().sum()),
            "null_ratio": round(float(col_data.isnull().sum() / len(col_data)), 4) if len(col_data) else 0.0,
        }

        if pd.api.types.is_numeric_dtype(col_data):
            stats.update({
                "min": None if col_data.dropna().empty else float(col_data.min()),
                "max": None if col_data.dropna().empty else float(col_data.max()),
                "mean": None if col_data.dropna().empty else round(float(col_data.mean()), 4),
                "median": None if col_data.dropna().empty else float(col_data.median()),
                "std": None if col_data.dropna().empty else round(float(col_data.std()), 4),
                "unique_values": int(col_data.nunique()),
                "top_value": None,
            })
        else:
            vc = col_data.value_counts(dropna=True)
            stats.update({
                "unique_values": int(col_data.nunique()),
                "top_value": None if vc.empty else str(vc.index[0]),
                "top_value_count": 0 if vc.empty else int(vc.iloc[0]),
                "value_counts": {str(k): int(v) for k, v in vc.head(5).items()},
            })

        column_stats[col] = stats

    return column_stats

# ====================== 示例调用 ======================
if __name__ == "__main__":
    pass
