# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/测试集添加虚拟阵列序号_6.py
# 目的：测试特征展开和虚拟阵元编号脚本
# 输入：测试特征 CSV
# 输出：带 element_id 的展开测试特征
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：测试集添加虚拟阵列序号_6.py

功能：
读取测试集的 8 维方向特征，将每一行特征复制 25 份，
并分别添加虚拟阵元编号 element_id（1～25）。

输入：
test_data/test_features_iter_1.csv

输出：
test_data/test_features_expanded_25x.csv

输出数据格式：
8 个方向特征 + 1 个虚拟阵元编号，共 9 列。

说明：
本脚本按原始流程顺序执行，不定义类或函数。
"""


import pandas as pd


# ========================== 1. 输入与输出路径 ==========================

INPUT_PATH = (
    r"E:/c50066007/pythonML_mianzhen_random/"
    r"test_data/test_features_iter_1.csv"
)

OUTPUT_PATH = (
    r"E:/c50066007/pythonML_mianzhen_random/"
    r"test_data/test_features_expanded_25x.csv"
)


# ========================== 2. 读取原始 8 维测试特征 ==========================

# 按原始脚本设置 header=None，即将 CSV 的所有行都作为数据读取。
df = pd.read_csv(INPUT_PATH, header=None)

print(f"原始测试集形状：{df.shape}")


# ========================== 3. 每条特征扩展为 25 条数据 ==========================

expanded_rows = []

for idx, row in df.iterrows():
    # 当前测试样本的 8 维特征。
    features = row.values

    # 为当前样本分别添加 1～25 号虚拟阵元编号。
    for element_id in range(1, 26):
        new_row = list(features) + [element_id]
        expanded_rows.append(new_row)


# ========================== 4. 转换为 DataFrame 并设置列名 ==========================

df_out = pd.DataFrame(expanded_rows)

# 列名与训练集展开格式保持一致。
column_names = [
    "right",
    "right_up",
    "up",
    "left_up",
    "left",
    "left_down",
    "down",
    "right_down",
    "element_id",
]

df_out.columns = column_names


# ========================== 5. 保存扩展后的测试集 ==========================

df_out.to_csv(
    OUTPUT_PATH,
    index=False,
    float_format="%.8f",
)


# ========================== 6. 输出处理结果 ==========================

print(
    f"✅ 扩展完成！新数据形状：{df_out.shape} "
    "（原始样本数 × 25 行，9 列）"
)
print(f"✅ 已保存到：{OUTPUT_PATH}")

