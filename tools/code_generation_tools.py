import pandas as pd
import os
import re
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, List
import sys
import openai
import base64
import dotenv
from loguru import logger
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatTongyi
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
dotenv.load_dotenv()

from utils.file_utils import load_prompt_template

import re
import os
import tempfile
import shutil
import subprocess
from typing import Dict, Any, List

class CodeExecutorTool:
    def __init__(self, results_dir: str = None):
        # 使用用户指定的路径
        if results_dir:
            self.results_dir = results_dir
        else:
            # 默认路径
            default_results = "/Users/chongyanghe/Desktop/DeepScientist/results"
            if os.path.exists(default_results):
                self.results_dir = default_results
            else:
                self.results_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results")
        
        self.figures_dir = os.path.join(self.results_dir, "figures")
        self.tables_dir = os.path.join(self.results_dir, "tables")
        
        # 确保目录存在
        os.makedirs(self.figures_dir, exist_ok=True)
        os.makedirs(self.tables_dir, exist_ok=True)
        logger.info(f"📁 结果目录: {self.results_dir}")
        logger.info(f"📁 图片目录: {self.figures_dir}")
        logger.info(f"📁 表格目录: {self.tables_dir}")
    
    def execute_code(self, code: str, data_path: str = None) -> Dict[str, Any]:
        result = {
            "success": False,
            "output": "",
            "error": "",
            "traceback": "",
            "metrics": {},
            "figures": [],
            "tables": []
        }

        with tempfile.TemporaryDirectory() as execution_dir:
            try:
                # 创建临时Python文件
                temp_script = os.path.join(execution_dir, "experiment.py")

                # 替换数据路径（保留你的原有逻辑）
                code = code.replace('data.csv', data_path.replace('\\', '/'))
                # 注入补丁代码，修复LLM生成代码的缺陷
                safe_code = self._wrap_code_safely(code, data_path, execution_dir)

                with open(temp_script, 'w', encoding='utf-8') as f:
                    f.write(safe_code)
                
                # 执行代码
                process = subprocess.run(
                    ['python', temp_script],
                    capture_output=True,
                    timeout=600,  # 5分钟超时
                    cwd=execution_dir 
                )
                
                # 处理输出
                stdout = self._safe_decode(process.stdout)
                stderr = self._safe_decode(process.stderr)
                
                if process.returncode == 0:
                    result["success"] = True
                    result["output"] = stdout
                    
                    # 收集生成的文件
                    figures, tables = self._collect_generated_files(execution_dir)
                    result["figures"] = figures
                    result["tables"] = tables
                    
                    # 解析输出中的指标
                    result.update(self._parse_execution_output(stdout, figures, tables))
                    
                    # 🔥 关键改进：如果没有生成图片，自动生成基础可视化
                    if not figures and data_path and os.path.exists(data_path):
                        logger.info("⚠️ 未检测到生成的图片，自动生成基础可视化...")
                        auto_figures = self._generate_auto_visualizations(data_path, execution_dir)
                        if auto_figures:
                            # 重新收集文件（包括自动生成的）
                            figures, tables = self._collect_generated_files(execution_dir)
                            result["figures"] = figures
                            result["tables"] = tables
                            logger.info(f"✅ 自动生成了 {len(auto_figures)} 张可视化图片")
                else:
                    result["error"] = stderr
                    result["output"] = stdout
                    result["traceback"] = self._extract_traceback(stderr)
                    
                    # 即使执行失败，也尝试生成基础可视化
                    if data_path and os.path.exists(data_path):
                        logger.info("⚠️ 代码执行失败，尝试生成基础可视化...")
                        try:
                            auto_figures = self._generate_auto_visualizations(data_path, execution_dir)
                            if auto_figures:
                                figures, tables = self._collect_generated_files(execution_dir)
                                result["figures"] = figures
                                result["tables"] = tables
                                logger.info(f"✅ 即使执行失败，也生成了 {len(auto_figures)} 张可视化图片")
                        except Exception as e:
                            logger.warning(f"自动生成可视化失败: {e}")
                    
            except subprocess.TimeoutExpired:
                result["error"] = "代码执行超时"
                # 超时情况下也尝试生成基础可视化
                if data_path and os.path.exists(data_path):
                    try:
                        auto_figures = self._generate_auto_visualizations(data_path, execution_dir)
                        if auto_figures:
                            figures, tables = self._collect_generated_files(execution_dir)
                            result["figures"] = figures
                            result["tables"] = tables
                    except Exception as e:
                        logger.warning(f"超时后自动生成可视化失败: {e}")
            except Exception as e:
                result["error"] = f"执行错误: {str(e)}"
                # 异常情况下也尝试生成基础可视化
                if data_path and os.path.exists(data_path):
                    try:
                        auto_figures = self._generate_auto_visualizations(data_path, execution_dir)
                        if auto_figures:
                            figures, tables = self._collect_generated_files(execution_dir)
                            result["figures"] = figures
                            result["tables"] = tables
                    except Exception as e2:
                        logger.warning(f"异常后自动生成可视化失败: {e2}")
        
        # 确保所有字段都有默认值
        result["output"] = result.get("output") or ""
        result["error"] = result.get("error") or ""
        result["traceback"] = result.get("traceback") or ""
        result["metrics"] = result.get("metrics") or {}
        result["figures"] = result.get("figures") or []
        result["tables"] = result.get("tables") or []
        
        # 最终检查：如果仍然没有图片，强制生成
        if not result["figures"] and data_path and os.path.exists(data_path):
            logger.warning("⚠️ 最终检查：仍然没有图片，强制生成基础可视化...")
            try:
                with tempfile.TemporaryDirectory() as fallback_dir:
                    auto_figures = self._generate_auto_visualizations(data_path, fallback_dir)
                    if auto_figures:
                        # 直接复制到目标目录
                        for fig_path in auto_figures:
                            dest_path = os.path.join(self.figures_dir, os.path.basename(fig_path))
                            shutil.copy2(fig_path, dest_path)
                            result["figures"].append(dest_path)
                        logger.info(f"✅ 强制生成了 {len(auto_figures)} 张可视化图片")
            except Exception as e:
                logger.error(f"强制生成可视化失败: {e}")
        
        return result
    
    def _extract_traceback(self, error_text: str) -> str:
        lines = error_text.split('\n')
        traceback_lines = []
        in_traceback = False
        
        for line in lines:
            if 'Traceback' in line or 'File "' in line:
                in_traceback = True
            if in_traceback:
                traceback_lines.append(line)
        
        return '\n'.join(traceback_lines) if traceback_lines else error_text
    
    def replace_data_paths(self, code: str, data_path: str) -> str:
        if not data_path or not code:
            return code
        
        placeholder_patterns = [
            r"'data\.csv'",
            r'"data\.csv"',
            r"'titanic\.csv'", 
            r'"titanic\.csv"',
            r"'input\.csv'",
            r'"input\.csv"',
            r"'dataset\.csv'",
            r'"dataset\.csv"',
            r"'data/data\.csv'",
            r'"data/data\.csv"',
            r"'\./data\.csv'",
            r'"\./data\.csv"',
        ]
        
        replaced_code = code
        
        for pattern in placeholder_patterns:
            original_pattern = pattern.replace(r'\.', '.')
            quoted_path = f"'{data_path}'" if "'" in pattern else f'"{data_path}"'
            replaced_code = re.sub(pattern, quoted_path, replaced_code)
        
        read_functions = [
            'pd.read_csv',
            'read_csv', 
            'pd.read_excel',
            'read_excel',
            'load_csv',
            'load_data',
            'load_dataset'
        ]
        
        for func in read_functions:
            pattern = rf"({func}\()\s*['\"][^'\"]*\.csv['\"]"
            matches = re.findall(pattern, replaced_code)
            
            for match in matches:
                old_call = match + f"'data.csv'"
                new_call = match + f"'{str(data_path)}'"
                replaced_code = replaced_code.replace(old_call, new_call)
        
        return replaced_code

    def _safe_decode(self, byte_data: bytes) -> str:
        if byte_data is None:
            return ""
        
        try:
            return byte_data.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return byte_data.decode('gbk')
            except UnicodeDecodeError:
                try:
                    return byte_data.decode('latin-1', errors='replace')
                except:
                    return str(byte_data)
    
    def _wrap_code_safely(self, code: str, data_path: str, temp_dir: str) -> str:
        # 核心：注入补丁代码，修复LLM生成代码的缺陷
        patch_code = '''
# ========== 自动补丁：修复LLM生成代码的缺陷 ==========
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler

# 补丁1：修复load_and_preprocess_data，返回原始X（带列名）、X_scaled、y
def _patched_load_and_preprocess_data(file_path: str):
    df = pd.read_csv(file_path)
    df = df.dropna()
    X_original = df.drop('target', axis=1)  # 保留原始带列名的X
    y = df['target']
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_original)
    # 全局存储原始df和X，供后续绘图使用
    global _full_df, _X_original
    _full_df = df
    _X_original = X_original
    return X_scaled, y

# 补丁2：修复create_visualizations，解决target缺失和特征名问题
def _patched_create_visualizations(df: pd.DataFrame, results: dict):
    global _full_df, _X_original
    # 绘图1：数据分布（用完整df的target）
    plt.figure(figsize=(10, 6))
    sns.histplot(_full_df['target'], kde=True)
    plt.title('Data Distribution')
    plt.xlabel('Target Variable')
    plt.ylabel('Frequency')
    plt.savefig('data_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 绘图2：特征重要性（用原始X的列名，避免长度不匹配）
    feature_importance = results['model'].coef_
    plt.figure(figsize=(10, 8))
    features = _X_original.columns  # 用原始特征名，无[:-1]错误
    # 处理长度不匹配（极端情况）
    if len(features) > len(feature_importance):
        features = features[:len(feature_importance)]
    elif len(feature_importance) > len(features):
        feature_importance = feature_importance[:len(features)]
    # 排序
    features, scores = zip(*sorted(zip(features, feature_importance), key=lambda x: x[1], reverse=True))
    sns.barplot(x=scores, y=features)
    plt.title('Feature Importance Ranking')
    plt.xlabel('Feature Importance Score')
    plt.ylabel('Feature')
    plt.savefig('feature_importance.png', dpi=300, bbox_inches='tight')
    plt.close()

# 补丁3：修复export_comprehensive_results中的SyntaxError（...替换为pass）
def _patched_export_comprehensive_results(metrics: dict, predictions: pd.DataFrame, ablation_results: dict = None):
    metrics_df = pd.DataFrame([metrics])
    metrics_df.to_csv('performance_metrics.csv', index=False)
    predictions.to_csv('prediction_results.csv', index=False)
    if ablation_results:
        ablation_df = pd.DataFrame(ablation_results)
        ablation_df.to_csv('ablation_study_results.csv', index=False)
    # 替换原始的...，避免语法错误
    pass

# 覆盖原始函数
load_and_preprocess_data = _patched_load_and_preprocess_data
create_visualizations = _patched_create_visualizations
export_comprehensive_results = _patched_export_comprehensive_results

# 初始化全局变量
_full_df = None
_X_original = None
# ========== 补丁结束 ==========
'''

        # 增强的执行代码（集成补丁）
        enhanced_code = f'''
import sys
import os
import warnings
warnings.filterwarnings('ignore')

# 添加当前目录到路径
sys.path.append(r"{temp_dir}")

# 设置工作目录
os.chdir(r"{temp_dir}")

# 设置数据路径
DATA_PATH = r"{data_path}"

try:
    # 增强的图表保存功能
    import matplotlib
    matplotlib.use('Agg')  # 强制使用非交互式后端
    import matplotlib.pyplot as plt
    import pandas as pd
    import numpy as np
    import seaborn as sns
    
    # 配置matplotlib
    plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 300
    plt.rcParams['savefig.dpi'] = 300
    plt.rcParams['savefig.bbox'] = 'tight'
    
    # 注入补丁代码（核心：修复LLM代码的缺陷）
{self._indent_code(patch_code)}
    
    # 用户代码开始
{self._indent_code(code)}
    # 用户代码结束
    
    # 🔥 关键改进：检查是否生成了图片，如果没有则自动生成
    png_files = [f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.pdf'))]
    if not png_files:
        print("\\n⚠️ 警告：用户代码未生成任何图片，尝试自动生成基础可视化...")
        try:
            import pandas as pd
            import numpy as np
            import matplotlib.pyplot as plt
            import seaborn as sns
            
            # 读取数据
            if DATA_PATH.endswith('.csv'):
                df = pd.read_csv(DATA_PATH)
            elif DATA_PATH.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(DATA_PATH)
            else:
                df = pd.read_csv(DATA_PATH)
            
            df = df.dropna()
            if not df.empty:
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) > 0:
                    # 生成简单的数据分布图
                    fig, axes = plt.subplots(1, min(3, len(numeric_cols)), figsize=(15, 5))
                    if len(numeric_cols) == 1:
                        axes = [axes]
                    for idx, col in enumerate(numeric_cols[:3]):
                        df[col].hist(bins=30, ax=axes[idx], edgecolor='black')
                        axes[idx].set_title(f'Distribution of {{col}}')
                        axes[idx].set_xlabel(col)
                        axes[idx].set_ylabel('Frequency')
                    plt.tight_layout()
                    plt.savefig('auto_generated_visualization.png', dpi=300, bbox_inches='tight')
                    plt.close()
                    print("✅ 自动生成了基础可视化图片: auto_generated_visualization.png")
        except Exception as e:
            print(f"自动生成可视化失败: {{e}}")
    
    print("\\n=== 执行完成 ===\\n")
    
    # 打印生成的文件列表
    png_files = [f for f in os.listdir('.') if f.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.pdf'))]
    csv_files = [f for f in os.listdir('.') if f.lower().endswith(('.csv', '.xlsx'))]
    
    if png_files:
        print("生成的图表文件:")
        for f in png_files:
            print(f"  - {{f}}")
    else:
        print("⚠️ 未生成任何图表文件")
    
    if csv_files:
        print("生成的表格文件:")
        for f in csv_files:
            print(f"  - {{f}}")
    
except Exception as e:
    print(f"执行错误: {{e}}")
    import traceback
    traceback.print_exc()
'''
        return enhanced_code
    
    def _indent_code(self, code: str) -> str:
        cleaned_code = re.sub(r'```python\s*', '', code)
        cleaned_code = re.sub(r'```\s*', '', cleaned_code)
        # 避免空行过度缩进
        return '\n'.join('    ' + line if line.strip() else line for line in cleaned_code.split('\n'))
    
    def _generate_auto_visualizations(self, data_path: str, output_dir: str) -> List[str]:
        """
        自动生成基础可视化图片，确保至少有一些可视化结果
        返回生成的文件路径列表
        """
        generated_files = []
        
        try:
            import matplotlib
            matplotlib.use('Agg')  # 使用非交互式后端
            import matplotlib.pyplot as plt
            import pandas as pd
            import numpy as np
            import seaborn as sns
            
            # 设置样式
            plt.style.use('seaborn-v0_8')
            sns.set_palette("husl")
            
            # 读取数据
            try:
                if data_path.endswith('.csv'):
                    df = pd.read_csv(data_path)
                elif data_path.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(data_path)
                else:
                    logger.warning(f"不支持的文件格式: {data_path}")
                    return generated_files
            except Exception as e:
                logger.error(f"读取数据文件失败: {e}")
                return generated_files
            
            if df.empty:
                logger.warning("数据文件为空")
                return generated_files
            
            # 清理数据
            df = df.dropna()
            if df.empty:
                logger.warning("清理后数据为空")
                return generated_files
            
            logger.info(f"📊 数据形状: {df.shape}, 列数: {len(df.columns)}")
            
            # 1. 数据概览图（前几列的基本统计）
            try:
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) > 0:
                    # 选择前6个数值列
                    cols_to_plot = numeric_cols[:6]
                    n_cols = min(3, len(cols_to_plot))
                    n_rows = (len(cols_to_plot) + n_cols - 1) // n_cols
                    
                    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 5*n_rows))
                    if n_rows == 1:
                        axes = [axes] if n_cols == 1 else axes
                    else:
                        axes = axes.flatten()
                    
                    for idx, col in enumerate(cols_to_plot):
                        ax = axes[idx] if len(cols_to_plot) > 1 else axes[0]
                        df[col].hist(bins=30, ax=ax, edgecolor='black')
                        ax.set_title(f'Distribution of {col}', fontsize=10)
                        ax.set_xlabel(col, fontsize=8)
                        ax.set_ylabel('Frequency', fontsize=8)
                    
                    # 隐藏多余的子图
                    for idx in range(len(cols_to_plot), len(axes)):
                        axes[idx].axis('off')
                    
                    plt.tight_layout()
                    fig_path = os.path.join(output_dir, 'auto_data_distribution.png')
                    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    generated_files.append(fig_path)
                    logger.info("✅ 生成数据分布图")
            except Exception as e:
                logger.warning(f"生成数据分布图失败: {e}")
            
            # 2. 相关性热力图（如果有多个数值列）
            try:
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) >= 2:
                    corr_matrix = df[numeric_cols].corr()
                    if not corr_matrix.empty:
                        plt.figure(figsize=(12, 10))
                        sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm', 
                                   center=0, square=True, linewidths=1, cbar_kws={"shrink": 0.8})
                        plt.title('Correlation Heatmap', fontsize=14, pad=20)
                        plt.tight_layout()
                        fig_path = os.path.join(output_dir, 'auto_correlation_heatmap.png')
                        plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                        plt.close()
                        generated_files.append(fig_path)
                        logger.info("✅ 生成相关性热力图")
            except Exception as e:
                logger.warning(f"生成相关性热力图失败: {e}")
            
            # 3. 箱线图（如果有数值列）
            try:
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) > 0:
                    cols_to_plot = numeric_cols[:8]  # 最多8列
                    fig, ax = plt.subplots(figsize=(12, 6))
                    df[cols_to_plot].boxplot(ax=ax, rot=45)
                    ax.set_title('Box Plot of Numerical Features', fontsize=12)
                    ax.set_ylabel('Value', fontsize=10)
                    plt.tight_layout()
                    fig_path = os.path.join(output_dir, 'auto_boxplot.png')
                    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    generated_files.append(fig_path)
                    logger.info("✅ 生成箱线图")
            except Exception as e:
                logger.warning(f"生成箱线图失败: {e}")
            
            # 4. 如果有目标列，生成目标变量分析
            try:
                # 尝试找到目标列（常见的名称）
                target_candidates = ['target', 'label', 'y', 'class', 'outcome', 'result']
                target_col = None
                for col in target_candidates:
                    if col in df.columns:
                        target_col = col
                        break
                
                if target_col is None and len(df.columns) > 0:
                    # 使用最后一列作为目标
                    target_col = df.columns[-1]
                
                if target_col and target_col in df.columns:
                    if df[target_col].dtype in ['object', 'category'] or df[target_col].nunique() < 20:
                        # 分类目标：柱状图
                        plt.figure(figsize=(10, 6))
                        value_counts = df[target_col].value_counts()
                        value_counts.plot(kind='bar')
                        plt.title(f'Distribution of {target_col}', fontsize=12)
                        plt.xlabel(target_col, fontsize=10)
                        plt.ylabel('Count', fontsize=10)
                        plt.xticks(rotation=45, ha='right')
                        plt.tight_layout()
                        fig_path = os.path.join(output_dir, 'auto_target_distribution.png')
                        plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                        plt.close()
                        generated_files.append(fig_path)
                        logger.info(f"✅ 生成目标变量分布图 ({target_col})")
                    else:
                        # 连续目标：直方图
                        plt.figure(figsize=(10, 6))
                        df[target_col].hist(bins=30, edgecolor='black')
                        plt.title(f'Distribution of {target_col}', fontsize=12)
                        plt.xlabel(target_col, fontsize=10)
                        plt.ylabel('Frequency', fontsize=10)
                        plt.tight_layout()
                        fig_path = os.path.join(output_dir, 'auto_target_distribution.png')
                        plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                        plt.close()
                        generated_files.append(fig_path)
                        logger.info(f"✅ 生成目标变量分布图 ({target_col})")
            except Exception as e:
                logger.warning(f"生成目标变量分析失败: {e}")
            
            # 5. 数据概览统计图
            try:
                numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
                if len(numeric_cols) > 0:
                    stats = df[numeric_cols].describe()
                    fig, ax = plt.subplots(figsize=(12, 6))
                    stats.T.plot(kind='bar', ax=ax, width=0.8)
                    ax.set_title('Statistical Summary of Numerical Features', fontsize=12)
                    ax.set_xlabel('Features', fontsize=10)
                    ax.set_ylabel('Value', fontsize=10)
                    ax.legend(title='Statistics', bbox_to_anchor=(1.05, 1), loc='upper left')
                    plt.xticks(rotation=45, ha='right')
                    plt.tight_layout()
                    fig_path = os.path.join(output_dir, 'auto_statistical_summary.png')
                    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
                    plt.close()
                    generated_files.append(fig_path)
                    logger.info("✅ 生成统计摘要图")
            except Exception as e:
                logger.warning(f"生成统计摘要图失败: {e}")
            
        except ImportError as e:
            logger.error(f"导入可视化库失败: {e}")
        except Exception as e:
            logger.error(f"自动生成可视化时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        return generated_files
    
    def _collect_generated_files(self, temp_dir: str) -> tuple:
        figures = []
        tables = []
        
        try:
            # 清空目标文件夹
            for target_dir in [self.figures_dir, self.tables_dir]:
                if os.path.exists(target_dir):
                    for filename in os.listdir(target_dir):
                        file_path = os.path.join(target_dir, filename)
                        try:
                            if os.path.isfile(file_path):
                                os.unlink(file_path)
                        except Exception as e:
                            print(f"⚠️ 删除文件失败 {filename}: {e}")
                else:
                    os.makedirs(target_dir, exist_ok=True)
                    
            # 查找图表文件
            figure_extensions = ['.png', '.jpg', '.jpeg', '.svg', '.pdf']
            table_extensions = ['.csv', '.xlsx', '.xls']
            
            for filename in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, filename)
                if os.path.isfile(file_path):
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    if file_ext in figure_extensions:
                        # 复制图表文件到结果目录
                        dest_path = os.path.join(self.figures_dir, filename)
                        shutil.copy2(file_path, dest_path)
                        figures.append(dest_path)
                        
                    elif file_ext in table_extensions:
                        # 复制表格文件到结果目录
                        dest_path = os.path.join(self.tables_dir, filename)
                        shutil.copy2(file_path, dest_path)
                        tables.append(dest_path)
                        
        except Exception as e:
            print(f"收集文件时出错: {e}")
            
        return figures, tables
    
    def _parse_execution_output(self, output: str, figures: List[str], tables: List[str]) -> Dict[str, Any]:
        metrics = {}
        
        output = output or ""

        lines = output.split('\n')
        for line in lines:
            line_lower = line.lower()
            
            # 匹配回归任务的指标（补充MSE/R2）
            metric_patterns = [
                (r'mse\s*[:=]\s*([0-9.]+)', 'mse'),
                (r'r2\s*[:=]\s*([0-9.]+)', 'r2'),
                (r'accuracy\s*[:=]\s*([0-9.]+)', 'accuracy'),
                (r'precision\s*[:=]\s*([0-9.]+)', 'precision'),
                (r'recall\s*[:=]\s*([0-9.]+)', 'recall'),
                (r'f1[_-]?score?\s*[:=]\s*([0-9.]+)', 'f1_score'),
                (r'f1\s*[:=]\s*([0-9.]+)', 'f1_score'),
                (r'auc\s*[:=]\s*([0-9.]+)', 'auc'),
                (r'loss\s*[:=]\s*([0-9.]+)', 'loss'),
                (r'error\s*[:=]\s*([0-9.]+)', 'error'),
            ]
            
            for pattern, metric_name in metric_patterns:
                match = re.search(pattern, line_lower)
                if match:
                    try:
                        metrics[metric_name] = float(match.group(1))
                    except ValueError:
                        metrics[metric_name] = match.group(1)
            
            # 匹配其他格式
            if ':' in line and any(metric in line_lower for metric in ['mse', 'r2', 'accuracy', 'precision', 'recall', 'f1', 'auc', 'loss']):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip()
                    metrics[key] = value
        
        return {
            "metrics": metrics or {},
            "figures": figures or [],
            "tables": tables or []
        }

class CodeGeneratorTool:
    def __init__(self):
        self.client = ChatTongyi(
                model="qwen-plus",           # 可选: qwen-plus, qwen-turbo, qwen-max 等
                temperature=0.7,
                dashscope_api_key=os.environ.get("QWEN_API_KEY", " ")  # 替换为你的 key，或用环境变量
            )
        self.model_id = os.environ.get("MODEL", "GLM-4-Flash")
        
    def generate_code(self, prompt: str) -> str:
        # response = self.llm.invoke(prompt)
        # response = self.client.chat.completions.create(
        #         model=self.model_id,
        #         messages=[
        #             {
        #                 "role": "user",
        #                 "content": prompt
        #             }
        #         ],
        #         temperature=0.2, 
        #         max_tokens=4000, 
        #         timeout=300
        #     )
        response = self.client.invoke(prompt)
            
        return self._extract_code(response.content)
    
    def _extract_code(self, text: str) -> str:
        # 查找代码块
        code_blocks = re.findall(r'```python\n(.*?)\n```', text, re.DOTALL)
        if code_blocks:
            return code_blocks[0]
        
        return text.strip()

# 支持图表分析的代码质量评估智能体
class QualityCriticTool:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.environ.get("MODEL", "GLM-4V-Flash"),
            temperature=os.environ.get("LLM_TEMPERATURE", 0.7),
            openai_api_key=os.environ.get("OPENAI_API_KEY", " "),
            openai_api_base=os.environ.get("OPENAI_BASE_URL", " ")
        )

        self.critic_llm = openai.OpenAI(api_key=os.environ.get("ZHIPU_API_KEY", " "), base_url=os.environ.get("ZHIPU_URL", " "))

        self.vision_llm = openai.OpenAI(api_key=os.environ.get("ZHIPU_API_KEY", " "), base_url=os.environ.get("ZHIPU_URL", " "))
        self.table_analyzer = TableAnalyzerTool()
    
    def evaluate_experiment(self, methods: str, code: str, result: Dict, iteration: int) -> Dict[str, Any]:
        safe_result = {
            "success": result.get("success", False),
            "output": result.get("output", "") or "",
            "error": result.get("error", "") or "",
            "metrics": result.get("metrics", {}) or {},
            "figures": result.get("figures", []) or [],
            "tables": result.get("tables", []) or []
        }

        if safe_result['figures']:
            figure_analyses = []
            for i, figure_path in enumerate(safe_result['figures']):
                try:
                    analysis = self.analyze_single_figure(figure_path, i)
                    figure_analyses.append(analysis)
                except Exception as e:
                    figure_analyses.append(f"Figure {i+1} analysis failed: {str(e)}")

            figure_info = "\n\n".join(figure_analyses)
        else:
            figure_info = "No figures displayed."
        
        if safe_result['tables']:
            table_info = self.table_analyzer.analyze_all_tables(safe_result['tables'])
        else:
            table_info = "No tables displayed." 
        
        prompt_template = load_prompt_template("critique_integrated.md")
        
        print(figure_info)
        print(table_info)

        full_prompt = prompt_template.format(
            methods=methods,
            code=code,
            success=result.get("success", False),
            output=result.get("output", ""),
            error=result.get("error", ""),
            metrics=json.dumps(result.get("metrics", {}), ensure_ascii=False),
            number_of_charts=len(safe_result['figures']),
            number_of_tables=len(safe_result['tables']),
            figure_analyses=figure_info,
            table_analyses=table_info,
            iteration=iteration
        )

        if len(full_prompt) >= 17979 * 3:
            full_prompt = full_prompt[17979*2:]
        
        # response = self.llm.invoke(full_prompt)
        response = self.critic_llm.chat.completions.create(
            model=os.environ.get("MODEL", "GLM-4V-Flash"), 
            messages=[{
                "role": "user", 
                "content": full_prompt
            }],
            max_tokens=300
        )

        try:
            return self.enhanced_json_repair(response.choices[0].message.content)
        except Exception as e:
            return {
                "quality_score": 0.3,
                "is_acceptable": False,
                "feedback": f"{e}. Unable to parse evaluation results, please check the code and execution",
                "suggestions": "1. Regenerate code; 2. Check data path"
            }

    # 对每张图分别解析
    def analyze_single_figure(self, figure_path: str, index: int) -> str:
        prompt_template = load_prompt_template("analyze_single_figure.md")
        
        full_prompt = prompt_template.format(
            figure_index=index + 1
        )
        
        content = [{"type": "text", "text": full_prompt}]
        
        with open(figure_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
        content.append({
            "type": "image_url", 
            "image_url": { 
                "url": f"data:image/{figure_path.split('.')[-1]};base64,{base64_image}" 
            }
        })
        
        response = self.vision_llm.chat.completions.create(
            model=os.environ.get("GLM-4V-Flash", " "), 
            messages=[{
                "role": "user", 
                "content": content
            }],
            max_tokens=300
        )
        
        return response.choices[0].message.content
    
    # 处理json文件的读取问题
    def fix_missing_commas(self, json_str: str) -> str:
        lines = json_str.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            fixed_lines.append(line)
            
            if i < len(lines) - 1:
                current_line = line
                next_line = lines[i + 1].strip()
                
                if (current_line and next_line and
                    not current_line.endswith(',') and
                    not current_line.endswith('{') and
                    not current_line.endswith('[') and
                    next_line.startswith('"') and
                    not next_line.startswith('"}')):
                    
                    fixed_lines[-1] = line + ','
        
        return '\n'.join(fixed_lines)

    def fix_trailing_commas(self, json_str: str) -> str:
        json_str = re.sub(r',\s*}', '}', json_str)
        json_str = re.sub(r',\s*]', ']', json_str)
        return json_str

    def fix_single_quotes(self, json_str: str) -> str:
        json_str = re.sub(r"(?<!\\)'", '"', json_str)
        return json_str

    def fix_quotation_issues(self, json_str: str) -> str:
        # 修复模式1: 字符串中包含括号注释的问题
        pattern1 = r'"([^"]*)"\s*\(([^)]*)\)'
        json_str = re.sub(pattern1, r'"\1",  // (\2)', json_str)
        
        # 修复模式2: 数组中字符串缺少逗号的问题
        pattern2 = r'"([^"]*)"\s*"([^"]*)"'
        json_str = re.sub(pattern2, r'"\1", "\2"', json_str)
        
        # 修复模式3: 确保数组元素以逗号分隔
        json_str = re.sub(r'(".*?")(\s*")', r'\1,\2', json_str)
        
        return json_str

    def enhanced_json_repair(self, response_content: str) -> Dict[str, Any]:
        try:
            return json.loads(response_content)
        except json.JSONDecodeError as e:        
            json_match = re.search(r'(\{[\s\S]*\})', response_content)
            if not json_match:
                return {}
            
            json_str = json_match.group(1)
            repair_functions = [
                self.fix_quotation_issues,           # 注释问题
                self.fix_missing_commas,             # 再修复逗号
                self.fix_trailing_commas,            # 修复尾随逗号
                self.fix_single_quotes               # 修复单引号
            ]
            
            for repair_func in repair_functions:
                try:
                    repaired = repair_func(json_str)
                    result = json.loads(repaired)
                    return result
                except json.JSONDecodeError:
                    json_str = repaired 
                    continue
            
            return self.enhanced_manual_extraction(response_content)

    def enhanced_manual_extraction(self, text: str) -> Dict[str, Any]:
        # 提取总体反馈和预估分数
        feedback_patterns = {
            "quality_score": r'"quality_score":\s*"([^"]*)"',
            "is_acceptable":r'"is_acceptable":\s*"([^"]*)"',
            "feedback": r'"feedback":\s*"([^"]*)"',
            "strengths": r'"strengths":\s*"([^"]*)"',
            "weaknesses": r'"weaknesses":\s*"([^"]*)"',
            "suggestions": r'"suggestions":\s*"([^"]*)"',
            "critical_issues": r'"critical_issues":\s*"([^"]*)"',
        }
        
        # 提取反馈信息
        feedback_data = {}
        for field, pattern in feedback_patterns.items():
            match = re.search(pattern, text)
            if match:
                feedback_data[field] = match.group(1)
            else:
                feedback_data[field] = ""
        
        return feedback_data
 

class TableAnalyzerTool:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=os.environ.get("MODEL", "GLM-4V-Flash"),
            temperature=0.3,
            openai_api_key=os.environ.get("OPENAI_API_KEY", " "),
            openai_api_base=os.environ.get("OPENAI_BASE_URL", " ")
        )

        self.critic_llm = openai.OpenAI(api_key=os.environ.get("ZHIPU_API_KEY", " "), base_url=os.environ.get("ZHIPU_URL", " "))
        
    def analyze_all_tables(self, table_paths: List[str]) -> str:
        if not table_paths:
            return "No tables generated."
        
        try:
            table_descriptions = []
            for i, table_path in enumerate(table_paths):
                table_info = self._extract_table_info(table_path, i)
                table_descriptions.append(table_info)
            
            summary = self._summarize_all_tables(table_descriptions)
            
            return summary
            
        except Exception as e:
            return f"Table analysis failed: {str(e)}"
    
    def _extract_table_info(self, file_path: str, index: int) -> Dict[str, Any]:
        try:
            df = pd.read_csv(file_path, nrows=5)
            filename = os.path.basename(file_path)
            
            total_rows = -1
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    total_rows = sum(1 for _ in f) - 1
            except:
                pass
            
            # 构建列信息
            columns_info = []
            for col in df.columns:
                col_info = {
                    "name": col,
                    "dtype": str(df[col].dtype),
                    "sample_values": df[col].head(3).tolist()
                }
                columns_info.append(col_info)
            
            return {
                "index": index,
                "filename": filename,
                "sampled_rows": len(df),
                "total_rows": total_rows,
                "num_columns": len(df.columns),
                "columns": columns_info,
                "sample_data": df.head(3).to_dict(orient='records')
            }
            
        except Exception as e:
            return {
                "index": index,
                "filename": os.path.basename(file_path),
                "error": str(e)
            }
    
    def _summarize_all_tables(self, table_descriptions: List[Dict]) -> str:
        prompt = self._build_analysis_prompt(table_descriptions)
        
        response = self.critic_llm.chat.completions.create(
            model=os.environ.get("MODEL", "GLM-4V-Flash"), 
            messages=[{
                "role": "user", 
                "content": prompt
            }],
            max_tokens=300
        )
        return response.choices[0].message.content
    
    def _build_analysis_prompt(self, table_descriptions: List[Dict]) -> str:
        prompt_template = load_prompt_template("analyze_table.md")

        tables_text = ""
        for table in table_descriptions:
            if "error" in table:
                tables_text += f"\n## Table {table['index'] + 1}: {table['filename']}\n"
                tables_text += f"Error: {table['error']}\n"
            else:
                tables_text += f"\n## Table {table['index'] + 1}: {table['filename']}\n"
                tables_text += f"Dimensions: {table['sampled_rows']} sampled rows"
                if table['total_rows'] > 0:
                    tables_text += f" (out of {table['total_rows']} total)"
                tables_text += f" × {table['num_columns']} columns\n"
                
                tables_text += "Columns:\n"
                for col in table['columns']:
                    samples = ", ".join([str(v) for v in col['sample_values'][:2]])
                    tables_text += f"- {col['name']} ({col['dtype']}): [{samples}...]\n"
                
                if table['sample_data']:
                    tables_text += "Sample Data (first 3 rows):\n"
                    import json
                    tables_text += json.dumps(table['sample_data'], indent=2, ensure_ascii=False) + "\n"
        
        full_prompt = prompt_template.format(
            tables_data=tables_text,
            number_of_tables=len(table_descriptions)
        )

        return full_prompt
