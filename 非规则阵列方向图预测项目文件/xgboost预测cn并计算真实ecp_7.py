# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/xgboost预测cn并计算真实ecp_7.py
# 目的：XGBoost cn 预测与 ECP 合成脚本
# 输入：平均 ECP、训练数据和测试特征
# 输出：预测 cn、预测 ECP 和训练误差
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：xgboost预测cn并计算真实ecp_7.py

功能：
1. 读取 Average_ECP_270.csv，将平均 ECP 的幅度和相位还原为复数方向图 g_ave。
2. 根据 5×5 虚拟阵列参数构建 Z 矩阵。
3. 读取 dataset_single_element_6750.csv，使用 XGBoost 训练 cn 实部和虚部预测模型。
4. 读取扩展后的测试特征，预测每个测试样本对应的 25 个虚拟阵元复激励系数 cn。
5. 使用 Z @ cn 合成测试样本的复数 ECP，提取幅度和相位并逐样本导出。

输入：
- Average_ECP_270.csv
- dataset_single_element_6750.csv
- test_data/test_features_expanded_25x.csv

输出：
- ecp_output_2/3_ecp_1.txt、3_ecp_2.txt、...

说明：
保留原脚本的模型参数、矩阵构造方式、文件路径、测试集读取方式和计算流程。
本脚本中的 XGBRegressor 采用双输出标签（cn_real、cn_imag）进行训练；
是否支持该用法取决于当前安装的 XGBoost 版本。
"""


import os

import numpy as np
import pandas as pd
from xgboost import XGBRegressor


# ========================== 1. 基础参数定义 ==========================

# 电磁参数
FREQ = 27.5e9
C = 3e8
LAMBDA = C / FREQ
BETA = 2 * np.pi / LAMBDA

# 5×5 虚拟阵列参数
VIRTUAL_ROWS = np.arange(1, 6)
VIRTUAL_COLS = np.arange(1, 6)

m_grid, n_grid = np.meshgrid(VIRTUAL_ROWS, VIRTUAL_COLS)
m_flat = m_grid.flatten()
n_flat = n_grid.flatten()

NUM_VIRTUAL = 25
D_VIRTUAL_X = 0.005
D_VIRTUAL_Y = 0.005
CENTER_COMP = -2

# 数据路径
BASE_PATH = r"E:/c50066007/pythonML_mianzhen_random/"

G_AVE_PATH = os.path.join(BASE_PATH, "Average_ECP_270.csv")
TRAIN_PATH = os.path.join(BASE_PATH, "dataset_single_element_6750.csv")
TEST_PATH = os.path.join(
    BASE_PATH,
    "test_data/test_features_expanded_25x.csv",
)

# ECP 输出目录
SAVE_DIR = os.path.join(BASE_PATH, "ecp_output_2")


# ========================== 2. 加载平均方向图 g_ave ==========================

print("正在读取平均方向图 Average_ECP_270.csv ...")

df_gave = pd.read_csv(G_AVE_PATH)

theta_deg = df_gave["Theta[deg]"].values
phi_deg = df_gave["Phi[deg]"].values
g_ave_dB = df_gave["ECP_dB"].values
g_ave_phase_deg = df_gave["ECP_Phase_deg"].values

# 根据 Theta、Phi 计算方向余弦 u、v。
theta_rad = np.deg2rad(theta_deg)
phi_rad = np.deg2rad(phi_deg)

u_list = np.sin(theta_rad) * np.cos(phi_rad)
v_list = np.sin(theta_rad) * np.sin(phi_rad)

# 将平均 ECP 的 dB 幅度和相位还原为复数方向图。
g_ave_linear = 10 ** (g_ave_dB / 20)
g_ave_linear = g_ave_linear * np.exp(
    1j * np.deg2rad(g_ave_phase_deg)
)

g_ave = np.array(g_ave_linear, dtype=complex)

print(f"平均方向图加载完成，采样点数量：{len(g_ave)}")


# ========================== 3. 构建 Z 矩阵 ==========================

def build_Zn(
    g_ave,
    u_list,
    v_list,
    m_flat,
    n_flat,
    beta,
    dx,
    dy,
    center_comp,
):
    """
    构造虚拟阵列 Z 矩阵。

    矩阵关系：
        Z = G @ E

    其中：
        G：由平均方向图 g_ave 构成的对角矩阵。
        E：各虚拟阵元在每个 (u, v) 方向上的相位因子矩阵。

    Args:
        g_ave: 平均方向图复数数组。
        u_list: 各方向采样点的 u 方向余弦。
        v_list: 各方向采样点的 v 方向余弦。
        m_flat: 虚拟阵列单元行索引展开数组。
        n_flat: 虚拟阵列单元列索引展开数组。
        beta: 波数。
        dx: x 方向虚拟阵元间距。
        dy: y 方向虚拟阵元间距。
        center_comp: 阵列中心补偿系数。

    Returns:
        np.ndarray: Z 矩阵，形状为 (方向采样点数量, 虚拟阵元数量)。
    """
    num_directions = len(u_list)
    num_elements = len(m_flat)

    # 平均方向图对角矩阵。
    G = np.diag(g_ave)

    # 虚拟阵列空间相位因子矩阵。
    E = np.zeros(
        (num_directions, num_elements),
        dtype=complex,
    )

    for k in range(num_directions):
        u = u_list[k]
        v = v_list[k]

        # 阵列中心补偿相位项。
        cx = center_comp * dx * u
        cy = center_comp * dy * v

        for j in range(num_elements):
            m = m_flat[j]
            n = n_flat[j]

            # 当前虚拟阵元的位置相位项。
            sx = (n - 1) * dx * u
            sy = (m - 1) * dy * v

            phase = 1j * beta * (cx + cy + sx + sy)
            E[k, j] = np.exp(phase)

    Z = G @ E

    return Z


# ========================== 4. 主流程 ==========================

def main():
    """训练 cn 预测模型，并根据预测结果合成测试 ECP。"""

    # -------------------------- 4.1 构建 Z 矩阵 --------------------------

    print("\n正在构建 Z 矩阵...")

    Z = build_Zn(
        g_ave,
        u_list,
        v_list,
        m_flat,
        n_flat,
        BETA,
        D_VIRTUAL_X,
        D_VIRTUAL_Y,
        CENTER_COMP,
    )

    print(f"Z 矩阵构建完成，形状：{Z.shape}")


    # ========================== 5. XGBoost 模型训练 ==========================

    print("\n正在读取训练数据...")

    df_train = pd.read_csv(TRAIN_PATH)

    # 输入：8 维阵列布局特征 + 1 维虚拟阵元编号。
    X_train = df_train.iloc[:, :9].values

    # 输出：cn 实部和虚部两个标签。
    y_train = df_train.iloc[:, 9:].values

    print(f"训练输入形状：{X_train.shape}")
    print(f"训练标签形状：{y_train.shape}")

    # 按原始参数创建 XGBoost 回归模型。
    model = XGBRegressor(
        n_estimators=500,
        learning_rate=0.1,
        max_depth=8,
        random_state=42,
    )

    print("正在训练 XGBoost 模型...")
    model.fit(X_train, y_train)
    print("模型训练完成！")


    # ========================== 6. 读取扩展后的测试集 ==========================

    print("\n正在读取测试集...")

    # 保留原脚本的 skiprows=26 读取方式。
    df_test = pd.read_csv(TEST_PATH, skiprows=26)

    # 测试集输入同样为 9 列。
    X_test = df_test.values
    num_test = len(X_test)

    print(f"测试集总数：{num_test}")


    # ========================== 7. 预测 cn 并合成 ECP ==========================

    os.makedirs(SAVE_DIR, exist_ok=True)

    print("\n开始生成 ECP 文件...")

    # 对扩展测试集中的每一行预测 cn 实部和虚部。
    y_pred = model.predict(X_test)

    # 每 25 行对应一个原始测试样本的 25 个虚拟阵元。
    num_original_samples = num_test // NUM_VIRTUAL

    for sample_idx in range(num_original_samples):

        # -------------------------- 7.1 提取当前样本的 25 个预测结果 --------------------------

        start = sample_idx * NUM_VIRTUAL
        end = start + NUM_VIRTUAL

        pred_25 = y_pred[start:end]

        # -------------------------- 7.2 重建 25 个复激励系数 cn --------------------------

        cn_real = pred_25[:, 0]
        cn_imag = pred_25[:, 1]

        cn = cn_real + 1j * cn_imag

        # -------------------------- 7.3 使用 Z 矩阵合成 ECP --------------------------

        ecp_complex = Z @ cn

        # 提取 ECP 幅度和相位。
        ecp_dB = 20 * np.log10(np.abs(ecp_complex) + 1e-10)
        ecp_phase_deg = np.angle(ecp_complex, deg=True)

        # -------------------------- 7.4 组织并保存当前样本的 ECP --------------------------

        df_out = pd.DataFrame({
            "Phi[deg]": phi_deg,
            "Theta[deg]": theta_deg,
            "ECP_dB": ecp_dB,
            "ECP_Phase_deg": ecp_phase_deg,
        })

        file_num = sample_idx + 1
        file_name = f"3_ecp_{file_num}.txt"
        save_path = os.path.join(SAVE_DIR, file_name)

        df_out.to_csv(
            save_path,
            index=False,
            float_format="%.6f",
        )

        print(f"已保存：{file_name}")


    # ========================== 8. 完成 ==========================

    print(
        f"\n✅ 全部完成！已生成 {num_original_samples} 个 ECP 文件"
    )
    print(f"📁 输出目录：{SAVE_DIR}")


# ========================== 9. 程序入口 ==========================

if __name__ == "__main__":
    main()

