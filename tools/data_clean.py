import pandas as pd
from datetime import datetime
from utils.logger import logger
from utils.path_tool import get_abs_path


class DataCleaner:
    def __init__(self, df: pd.DataFrame = None, file_path: str = None):
        """
        初始化清洗器
        - 传入 DataFrame 或文件路径二选一
        """
        if file_path:
            ext = file_path.split('.')[-1].lower()
            self.df = pd.read_csv(file_path) if ext == 'csv' else pd.read_excel(file_path)
            self.original_df = self.df.copy()
            logger.info(f"已从文件加载数据: {file_path}")
        elif df is not None:
            self.df = df.copy()
            self.original_df = df.copy()
        else:
            raise ValueError("必须提供 df 或 file_path")

        self.report = {}

    # ---------- 1. 探查 ----------
    def profile(self):
        """生成基础数据画像"""
        profile_dict = {
            'shape': self.df.shape,
            'columns': self.df.columns.tolist(),
            'dtypes': self.df.dtypes.astype(str).to_dict(),
            'missing_count': self.df.isnull().sum().to_dict(),
            'missing_percent': (self.df.isnull().sum() / len(self.df) * 100).round(2).to_dict(),
            'duplicated_rows': self.df.duplicated().sum()
        }
        self.report['before'] = profile_dict
        logger.info("=== 清洗前数据概况 ===")
        for k, v in profile_dict.items():
            logger.info(f"{k}: {v}")
        return self

    # ---------- 2. 清洗动作 ----------
    def drop_high_missing(self, threshold=0.8):
        """删除缺失率过高的列"""
        before_cols = set(self.df.columns)
        self.df = self.df.loc[:, self.df.isnull().mean() < threshold]
        dropped = before_cols - set(self.df.columns)
        if dropped:
            logger.info(f"已删除缺失率高于 {threshold * 100}% 的列: {dropped}")
        return self

    def fill_missing(self, strategy='auto'):
        """
        智能填充缺失值
        - strategy='auto': 数值列用0填充，文本列用'Unknown'
        - strategy='median': 数值列用中位数填充
        - strategy='mean': 数值列用均值填充
        """
        for col in self.df.columns:
            if self.df[col].dtype == 'object':
                self.df[col] = self.df[col].fillna('Unknown')
            elif pd.api.types.is_numeric_dtype(self.df[col]):
                if strategy == 'median':
                    self.df[col] = self.df[col].fillna(self.df[col].median())
                elif strategy == 'mean':
                    self.df[col] = self.df[col].fillna(self.df[col].mean())
                else:
                    self.df[col] = self.df[col].fillna(0)
            elif pd.api.types.is_datetime64_any_dtype(self.df[col]):
                pass
        logger.info(f"已使用 strategy={strategy} 填充缺失值")
        return self

    def remove_duplicates(self, subset=None):
        """去除重复行"""
        before = len(self.df)
        self.df = self.df.drop_duplicates(subset=subset)
        after = len(self.df)
        logger.info(f"已删除重复行: {before - after}")
        return self

    def standardize_text_columns(self, columns=None):
        """文本标准化：去空格、大小写统一"""
        if columns is None:
            columns = self.df.select_dtypes(include=['object']).columns
        for col in columns:
            if col in self.df.columns:
                self.df[col] = self.df[col].astype(str).str.strip().str.title()
        logger.info(f"已标准化文本列: {list(columns)}")
        return self

    def convert_dtypes(self):
        """自动识别并转换日期列"""
        for col in self.df.select_dtypes(include=['object']).columns:
            try:
                self.df[col] = pd.to_datetime(self.df[col], errors='ignore')
                if pd.api.types.is_datetime64_any_dtype(self.df[col]):
                    logger.info(f"列 {col} 已转换为 datetime")
            except Exception:
                pass
        return self

    def drop_duplicated_columns(self):
        """删除重复列（列名相同或内容完全相同的列）"""
        before_cols = len(self.df.columns)
        self.df = self.df.loc[:, ~self.df.columns.duplicated()]
        dropped = before_cols - len(self.df.columns)
        if dropped:
            logger.info(f"已删除 {dropped} 个重复列")
        return self

    def auto_clean(self, missing_threshold=0.8):
        """
        根据探查结果自动决策清洗策略
        - missing_threshold: 缺失率阈值，超过则删除该列
        """
        if not self.report.get('before'):
            self.profile()

        actions = []

        # 1. 删除高缺失率列
        for col, pct in self.report['before']['missing_percent'].items():
            if col in self.df.columns and pct > missing_threshold * 100:
                self.df = self.df.drop(columns=[col])
                actions.append(f"删除高缺失率列 [{col}] ({pct:.1f}%)")

        # 2. 填充缺失值
        for col, null_count in self.report['before']['missing_count'].items():
            if col not in self.df.columns or null_count == 0:
                continue

            if self.df[col].dtype == 'object':
                mode_vals = self.df[col].dropna().mode()
                fill_val = mode_vals[0] if len(mode_vals) > 0 else 'Unknown'
                self.df[col] = self.df[col].fillna(fill_val)
                actions.append(f"文本列 [{col}] 用众数 '{fill_val}' 填充")
            elif pd.api.types.is_numeric_dtype(self.df[col]):
                median_val = self.df[col].median()
                self.df[col] = self.df[col].fillna(median_val)
                actions.append(f"数值列 [{col}] 用中位数 {median_val} 填充")

        # 3. 删除重复行
        dup_count = self.report['before']['duplicated_rows']
        if dup_count > 0:
            self.df = self.df.drop_duplicates()
            actions.append(f"删除 {dup_count} 行重复数据")

        # 4. 删除重复列
        before_cols = len(self.df.columns)
        self.df = self.df.loc[:, ~self.df.columns.duplicated()]
        dropped_cols = before_cols - len(self.df.columns)
        if dropped_cols > 0:
            actions.append(f"删除 {dropped_cols} 个重复列")

        # 5. 文本列标准化
        text_cols = self.df.select_dtypes(include=['object']).columns
        for col in text_cols:
            self.df[col] = self.df[col].astype(str).str.strip().str.title()
        if len(text_cols) > 0:
            actions.append(f"标准化 {len(text_cols)} 个文本列")

        # 记录清洗动作
        self.report['auto_clean_actions'] = actions
        logger.info("=== 自动清洗完成 ===")
        for action in actions:
            logger.info(f"  - {action}")
        return self

    # ---------- 3. 输出 ----------
    def export_report(self, filepath=None):
        import os
        if filepath is None:
            filepath = os.path.join(get_abs_path("logs"), "cleaning_report.txt")
        """生成清洗报告"""
        self.report['after'] = {
            'shape': self.df.shape,
            'missing_count': self.df.isnull().sum().to_dict(),
            'duplicated_rows': self.df.duplicated().sum()
        }
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"清洗报告 - {datetime.now()}\n")
            f.write(str(self.report))
        logger.info(f"清洗报告已保存至: {filepath}")
        return self

    def save_clean_data(self, filepath, format='csv'):
        """保存清洗后数据"""
        import os
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else get_abs_path("output"), exist_ok=True)
        if format == 'csv':
            self.df.to_csv(filepath, index=False, encoding='utf-8-sig')
        elif format in ('excel', 'xlsx'):
            self.df.to_excel(filepath, index=False)
        logger.info(f"清洗后数据已保存至: {filepath}")
        return self

    def get_cleaned_df(self) -> pd.DataFrame:
        """返回清洗后的 DataFrame"""
        return self.df


# ---------- 便捷函数 ----------
def clean_data(file_path: str, output_path: str = None, **kwargs) -> pd.DataFrame:
    """
    一行代码完成数据清洗
    用法示例:
        cleaned_df = clean_data("data.csv", "output/cleaned.csv",
                               drop_high_missing=0.8,
                               fill_missing='median',
                               remove_duplicates=True)
    """
    cleaner = DataCleaner(file_path=file_path)

    # 链式调用所有指定的清洗方法
    if kwargs.get('drop_high_missing') is not None:
        cleaner.drop_high_missing(kwargs['drop_high_missing'])
    if kwargs.get('fill_missing'):
        cleaner.fill_missing(kwargs['fill_missing'])
    if kwargs.get('remove_duplicates'):
        cleaner.remove_duplicates()
    if kwargs.get('standardize_text'):
        cleaner.standardize_text_columns()
    if kwargs.get('convert_dtypes'):
        cleaner.convert_dtypes()

    if output_path:
        cleaner.save_clean_data(output_path)

    return cleaner.get_cleaned_df()