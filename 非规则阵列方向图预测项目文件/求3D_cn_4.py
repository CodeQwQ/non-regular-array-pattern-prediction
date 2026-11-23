# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/求3D_cn_4.py
# 目的：虚拟阵列 Z 矩阵和 cn 标签生成脚本
# 输入：ECP 文件、平均 ECP 和布局特征
# 输出：6750 行单元训练数据集
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：求3D_cn_4.py

功能：
1. 读取 Average_ECP_270.csv，将平均 ECP 的幅度和相位重建为复数方向图 g_ave。
2. 构建 5×5 虚拟阵列，阵元间距为 0.005 m。
3. 遍历 ECP_single_1.csv～ECP_single_270.csv，构造每组方向图对应的 Z 矩阵，
   并求解 25 个虚拟阵元的复激励系数 cn。
4. 将每组 cn 拆分为实部和虚部，得到 270×50 的标签矩阵。
5. 读取 30 份 train_features_iter 文件，合并为 270 组 8 维输入特征。
6. 将每组样本按 25 个虚拟阵元展开，生成 6750 行训练数据：
   8 维方向特征 + 1 维虚拟阵元编号 -> 1 维 cn 实部 + 1 维 cn 虚部。

输出：
dataset_single_element_6750.csv

每行包含 11 列：
8 个方向特征、element_id、cn_real、cn_imag。

说明：
保留原脚本的计算流程、矩阵构造方式、路径及输出格式。
"""


import numpy as np
import pandas as pd


# ========================== 1. 基础参数 ==========================

# 电磁参数
FREQ = 27.5e9
C = 3e8
LAMBDA = C / FREQ
BETA = 2 * np.pi / LAMBDA

# 5×5 虚拟阵列
VIRTUAL_ROWS = np.arange(1, 6)
VIRTUAL_COLS = np.arange(1, 6)

m_grid, n_grid = np.meshgrid(VIRTUAL_ROWS, VIRTUAL_COLS)
m_flat = m_grid.flatten()
n_flat = n_grid.flatten()

NUM_VIRTUAL = 25
D_VIRTUAL_X = 0.005
D_VIRTUAL_Y = 0.005

# 虚拟阵列中心补偿
CENTER_COMP = -2

# 数据规模
N_TRAIN = 30
N_GROUP = 9
N_SAMPLES = N_TRAIN * N_GROUP

# 数据路径
BASE_PATH = "E:/c50066007/pythonML_mianzhen_random/"
AVERAGE_ECP_PATH = BASE_PATH + "Average_ECP_270.csv"
FEATURE_BASE_PATH = BASE_PATH + "train_data/train_features_iter_"

# 输出文件
OUTPUT_PATH = "dataset_single_element_6750.csv"


# ========================== 2. 加载平均方向图 g_ave ==========================

print("正在读取平均方向图 Average_ECP_270.csv ...")

df_gave = pd.read_csv(AVERAGE_ECP_PATH)

g_ave_dB = df_gave["ECP_dB"].values
g_ave_phase_deg = df_gave["ECP_Phase_deg"].values

# 将 dB 幅度和相位还原为复数电场。
g_ave_linear = 10 ** (g_ave_dB / 20)
g_ave_linear = g_ave_linear * np.exp(
    1j * np.deg2rad(g_ave_phase_deg)
)

g_ave = np.array(g_ave_linear, dtype=complex)

print(f"平均方向图加载完成，采样点数量：{len(g_ave)}")


# ========================== 3. Z 矩阵构造函数 ==========================

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
    构造虚拟阵列的 Z 矩阵。

    矩阵关系：
        Z = G @ E

    其中：
        G：由平均方向图 g_ave 构成的对角矩阵。
        E：各虚拟阵元在每个 (u, v) 方向上的相位因子矩阵。

    Args:
        g_ave: 平均方向图复数数组，长度为方向采样点数量 N。
        u_list: 每个方向采样点对应的 u 分量。
        v_list: 每个方向采样点对应的 v 分量。
        m_flat: 虚拟阵列单元的行索引展开数组。
        n_flat: 虚拟阵列单元的列索引展开数组。
        beta: 波数。
        dx: 虚拟阵列 x 方向阵元间距。
        dy: 虚拟阵列 y 方向阵元间距。
        center_comp: 虚拟阵列中心补偿系数。

    Returns:
        np.ndarray: Z 矩阵，形状为 (N, M)。
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

        # 阵列中心补偿对应的相位项。
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


# ========================== 4. 主流程：计算 270 组 cn 标签 ==========================

def main():
    """计算复激励系数 cn，并构建单虚拟阵元训练数据集。"""

    print("\n正在计算 270 组 cn 标签...")

    all_cn = []

    # -------------------------- 4.1 遍历 270 组 ECP --------------------------

    for idx in range(1, N_SAMPLES + 1):
        csv_path = BASE_PATH + f"ECP_single_{idx}.csv"
        df = pd.read_csv(csv_path)

        # 读取角度坐标、ECP 幅度和相位。
        phi_deg = df["Phi[deg]"].values
        theta_deg = df["Theta[deg]"].values
        g_n_dB = df["ECP_dB"].values
        g_n_phase_deg = df["ECP_Phase_deg"].values

        # 将当前单组 ECP 还原为复数方向图。
        g_n_linear = 10 ** (g_n_dB / 20)
        g_n_linear = g_n_linear * np.exp(
            1j * np.deg2rad(g_n_phase_deg)
        )

        # -------------------------- 4.2 计算 u、v 方向余弦 --------------------------

        theta_rad = np.deg2rad(theta_deg)
        phi_rad = np.deg2rad(phi_deg)

        u_list = np.sin(theta_rad) * np.cos(phi_rad)
        v_list = np.sin(theta_rad) * np.sin(phi_rad)

        # -------------------------- 4.3 构造 Z 矩阵 --------------------------

        Z_n = build_Zn(
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

        # -------------------------- 4.4 最小二乘求解复激励系数 cn --------------------------

        # 原脚本采用正规方程形式：
        # cn = (Zᴴ Z)^(-1) Zᴴ g_n
        Z_H = Z_n.conj().T
        g_n = g_n_linear.astype(complex)

        cn = np.linalg.inv(Z_H @ Z_n) @ Z_H @ g_n

        # 将复数 cn 拆分为实部和虚部，拼接为长度 50 的标签。
        row = np.hstack([
            np.real(cn),
            np.imag(cn),
        ])

        all_cn.append(row)

        if idx % 50 == 0 or idx == N_SAMPLES:
            print(f"已处理 {idx}/{N_SAMPLES}")

    all_cn = np.array(all_cn)

    print(
        f"cn 标签形状：{all_cn.shape} "
        f"（{N_SAMPLES} × {NUM_VIRTUAL * 2}）"
    )


    # ========================== 5. 读取并合并 8 维特征 ==========================

    print("\n正在读取 8 维特征...")

    feats = []

    for train_idx in range(1, N_TRAIN + 1):
        feature_path = f"{FEATURE_BASE_PATH}{train_idx}.csv"
        df_feat = pd.read_csv(feature_path)

        feats.append(df_feat.values)

    # 30 份特征文件纵向合并。
    feats = np.vstack(feats)

    print(
        f"特征形状：{feats.shape} "
        f"（{N_SAMPLES} × 8）"
    )


    # ========================== 6. 展开为单虚拟阵元训练数据 ==========================

    print("\n正在展开数据集为单虚拟阵元格式...")

    expanded_data = []

    for sample_idx in range(N_SAMPLES):
        # 当前样本的 8 维输入特征。
        feature = feats[sample_idx]

        # 当前样本 25 个虚拟阵元对应的 cn 实部和虚部。
        cn_real = all_cn[sample_idx, :NUM_VIRTUAL]
        cn_imag = all_cn[sample_idx, NUM_VIRTUAL:]

        # 每个虚拟阵元单独展开为一条训练数据。
        for elem_idx in range(NUM_VIRTUAL):
            # 输入：8 维方向特征 + 虚拟阵元编号（1～25）。
            new_feature = np.hstack([
                feature,
                elem_idx + 1,
            ])

            # 输出：当前虚拟阵元 cn 的实部和虚部。
            new_label = np.array([
                cn_real[elem_idx],
                cn_imag[elem_idx],
            ])

            expanded_row = np.hstack([
                new_feature,
                new_label,
            ])

            expanded_data.append(expanded_row)

    expanded_data = np.array(expanded_data)

    expected_rows = N_SAMPLES * NUM_VIRTUAL
    expected_columns = 8 + 1 + 2

    print(
        f"✅ 展开完成！新数据集形状：{expanded_data.shape} "
        f"（{expected_rows} × {expected_columns}）"
    )
    print("   每条数据：9 个输入特征（8 + 1）+ 2 个输出标签")


    # ========================== 7. 保存训练数据集 ==========================

    col_names = [
        "right",
        "right_up",
        "up",
        "left_up",
        "left",
        "left_down",
        "down",
        "right_down",
        "element_id",
        "cn_real",
        "cn_imag",
    ]

    df_out = pd.DataFrame(
        expanded_data,
        columns=col_names,
    )

    df_out.to_csv(
        OUTPUT_PATH,
        index=False,
        float_format="%.8f",
    )

    print("\n🎉 全部完成！")
    print(f"📁 输出文件：{OUTPUT_PATH}")
    print("📏 每条数据：9 输入 + 2 输出")


# ========================== 8. 程序入口 ==========================

if __name__ == "__main__":
    main()

