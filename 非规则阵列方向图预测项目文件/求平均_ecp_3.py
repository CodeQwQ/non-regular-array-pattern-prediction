# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/求平均_ecp_3.py
# 目的：训练 ECP 复数平均脚本
# 输入：270 组单元方向图文件
# 输出：平均 ECP TXT/CSV 文件
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：求平均_ecp_3.py

功能：
遍历 train1～train30 下的 1～9 号子文件，共处理 270 组 HFSS 导出的方向图 CSV。
每组读取 DirPhi、DirTheta 的幅度数据，以及 rEPhi、rETheta 的相位数据，
重建复电场并合成 45° 极化 ECP。

所有组的 ECP 以复数形式累加，最后对复电场求平均，再提取平均结果的幅度和相位。

输出文件：
- Average_ECP_270.txt
- Average_ECP_270.csv

输出列：
Phi[deg]、Theta[deg]、ECP_dB、ECP_Phase_deg

数据排列顺序：
Theta 固定，Phi 从 0° 递增至 360°；每行对应一个 (Phi, Theta) 采样点。

说明：
本脚本按原始流程顺序执行，不定义类或函数。
"""

import numpy as np
import pandas as pd


# ========================== 路径与参数 ==========================

# HFSS 导出的方向图 CSV 所在目录
BASE_PATH = r"E:\c50066007\pythonML_mianzhen_random\\"

# 数据组数
N_TRAIN = 30
N_GROUP = 9
TOTAL_GROUPS = N_TRAIN * N_GROUP

# 角度采样点数量
N_PHI = 181       # Phi：0～360°，步长 2°
N_THETA = 91      # Theta：0～180°，步长 2°

# 极化角
POLARIZATION_DEG = 45


# ========================== 初始化复数累加数组 ==========================

# 对每个 (Theta, Phi) 采样点累加复数 ECP。
# 复数平均能够同时考虑电场幅度和相位，避免直接分别平均幅度与相位。
sum_ecp_complex = np.zeros((N_THETA, N_PHI), dtype=complex)
count = 0


# ========================== 遍历全部方向图数据 ==========================

for train_idx in range(1, N_TRAIN + 1):
    print(f"处理 train{train_idx} ...")

    for group_idx in range(1, N_GROUP + 1):

        # -------------------------- 输入文件路径 --------------------------

        file_dB_phi = (
            BASE_PATH + f"train{train_idx}_3D_dir_phi_{group_idx}.csv"
        )
        file_dB_theta = (
            BASE_PATH + f"train{train_idx}_3D_dir_theta_{group_idx}.csv"
        )
        file_deg_phi = (
            BASE_PATH + f"train{train_idx}_3D_phase_phi_{group_idx}.csv"
        )
        file_deg_theta = (
            BASE_PATH + f"train{train_idx}_3D_phase_theta_{group_idx}.csv"
        )

        # -------------------------- 读取方向图数据 --------------------------

        # Phi 分量幅度及角度坐标
        df_phi = pd.read_csv(file_dB_phi)
        phi_deg = df_phi["Phi[deg]"].values
        theta_deg = df_phi["Theta[deg]"].values
        rEphi_dB = df_phi["dB(DirPhi)"].values

        # Theta 分量幅度
        df_theta = pd.read_csv(file_dB_theta)
        rEtheta_dB = df_theta["dB(DirTheta)"].values

        # Phi 分量相位
        df_phase_phi = pd.read_csv(file_deg_phi)
        rEphi_deg = df_phase_phi["ang_deg(rEPhi)[deg]"].values

        # Theta 分量相位
        df_phase_theta = pd.read_csv(file_deg_theta)
        rEtheta_deg = df_phase_theta["ang_deg(rETheta)[deg]"].values

        # -------------------------- 重建复电场 --------------------------

        # 将 dB 幅度转换为线性幅度，并结合相位构造复数电场：
        # E = 10^(dB/20) * exp(j * phase)
        rEtheta = (
            10 ** (rEtheta_dB / 20)
        ) * np.exp(1j * np.deg2rad(rEtheta_deg))

        rEphi = (
            10 ** (rEphi_dB / 20)
        ) * np.exp(1j * np.deg2rad(rEphi_deg))

        # -------------------------- 合成 45° 极化 ECP --------------------------

        phi_rad = np.deg2rad(phi_deg)
        polarization_rad = np.deg2rad(POLARIZATION_DEG)

        Ecp = (
            rEtheta * np.cos(phi_rad - polarization_rad)
            - rEphi * np.sin(phi_rad - polarization_rad)
        )

        # -------------------------- 调整数据形状并累加 --------------------------

        # 将一维方向图数据恢复为 (Theta, Phi) 二维矩阵。
        ecp_2d = Ecp.reshape(N_THETA, N_PHI)

        # 对复数电场进行累加，保留幅度与相位信息。
        sum_ecp_complex += ecp_2d
        count += 1

        print(
            f"  已处理 train{train_idx} / group{group_idx}，"
            f"当前累计 {count}/{TOTAL_GROUPS} 组"
        )


# ========================== 计算复数平均值 ==========================

if count == 0:
    raise RuntimeError("没有读取到任何有效方向图数据，无法计算平均 ECP。")

if count != TOTAL_GROUPS:
    print(
        f"⚠️ 实际处理组数为 {count}，"
        f"与预期组数 {TOTAL_GROUPS} 不一致。"
    )

# 对全部复数 ECP 求平均。
avg_ecp_complex = sum_ecp_complex / count


# ========================== 提取平均 ECP 的幅度与相位 ==========================

# 平均复电场的幅度转换为 dB。
avg_ecp_dB = 20 * np.log10(np.abs(avg_ecp_complex))

# 提取平均复电场的相位，单位为度。
avg_ecp_phase = np.angle(avg_ecp_complex, deg=True)


# ========================== 生成角度坐标与输出数据 ==========================

phi_list = np.arange(0, 361, 2)
theta_list = np.arange(0, 181, 2)

# 按指定顺序排列：
# Theta 固定，Phi 从 0° 递增至 360°；随后 Theta 增加 2°。
out_rows = []

for t_idx, theta in enumerate(theta_list):
    for p_idx, phi in enumerate(phi_list):
        out_rows.append([
            phi,
            theta,
            avg_ecp_dB[t_idx, p_idx],
            avg_ecp_phase[t_idx, p_idx],
        ])

out_data = np.array(out_rows)


# ========================== 保存 TXT 文件 ==========================

header_txt = "Phi[deg]\tTheta[deg]\tECP_dB\tECP_Phase_deg"

np.savetxt(
    "Average_ECP_270.txt",
    out_data,
    fmt="%.6f",
    delimiter="\t",
    header=header_txt,
    comments="",
)


# ========================== 保存 CSV 文件 ==========================

df_out = pd.DataFrame(
    out_data,
    columns=[
        "Phi[deg]",
        "Theta[deg]",
        "ECP_dB",
        "ECP_Phase_deg",
    ],
)

df_out.to_csv(
    "Average_ECP_270.csv",
    index=False,
    float_format="%.6f",
)


# ========================== 完成 ==========================

print("\n🎉 全部处理完成！（幅度 + 相位已通过复数形式平均）")
print("✅ 已生成 TXT：Average_ECP_270.txt")
print("✅ 已生成 CSV：Average_ECP_270.csv")
print("✅ 包含：Phi、Theta、ECP 幅度、ECP 相位")
print("✅ 数据排列：Theta 固定，Phi 从 0° 递增至 360°，然后 Theta 增加 2°")
print(f"✅ 实际参与平均的组数：{count}")

