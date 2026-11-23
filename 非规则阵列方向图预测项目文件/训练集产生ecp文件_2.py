# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/训练集产生ecp文件_2.py
# 目的：训练方向图到 45 度极化 ECP 的转换脚本
# 输入：HFSS 幅度和相位导出文件
# 输出：单元 ECP CSV 文件
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：训练集产生ecp文件_2.py

功能：
遍历 train1～train30 下的 1～9 号子文件，共处理 270 组方向图 CSV。
每组读取 DirPhi、DirTheta 的幅度数据，以及 rEPhi、rETheta 的相位数据，
重建两个方向的复电场，并合成 45° 极化的 ECP。

输出：
生成 ECP_single_1.csv～ECP_single_270.csv。
每个 CSV 包含以下四列：
    Phi[deg]、Theta[deg]、ECP_dB、ECP_Phase_deg

说明：
本脚本按原始流程顺序执行，不定义类或函数。
"""

import numpy as np
import pandas as pd


# ========================== 路径与参数 ==========================

# 训练集方向图 CSV 所在目录
BASE_PATH = r"E:\c50066007\pythonML_mianzhen_random\\"

# 角度采样点数量
N_PHI = 181       # Phi：0～360°，步长 2°
N_THETA = 91      # Theta：0～180°，步长 2°

# 45° 极化角
POLARIZATION_DEG = 45

# 输出文件全局编号：1～270
file_index = 1


# ========================== 角度坐标 ==========================

phi_list = np.arange(0, 361, 2)
theta_list = np.arange(0, 181, 2)

# ========================== 遍历 train1～train30 ==========================

for train_idx in range(1, 31):
    print("\n======================================")
    print(f"正在处理 train{train_idx} ...")

    # 每个 train 目录对应 1～9 号子文件
    for x in range(1, 10):
        print(f" → 子文件 {x}（总序号：{file_index}）")

        # -------------------------- 输入文件路径 --------------------------

        file_dB_phi = (
            BASE_PATH + f"train{train_idx}_3D_dir_phi_{x}.csv"
        )
        file_dB_theta = (
            BASE_PATH + f"train{train_idx}_3D_dir_theta_{x}.csv"
        )
        file_deg_phi = (
            BASE_PATH + f"train{train_idx}_3D_phase_phi_{x}.csv"
        )
        file_deg_theta = (
            BASE_PATH + f"train{train_idx}_3D_phase_theta_{x}.csv"
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
        pol_rad = np.deg2rad(POLARIZATION_DEG)

        Ecp = (
            rEtheta * np.cos(phi_rad - pol_rad)
            - rEphi * np.sin(phi_rad - pol_rad)
        )

        # -------------------------- 提取 ECP 幅度与相位 --------------------------

        # 复电场幅度转换为 dB
        ecp_dB = 20 * np.log10(np.abs(Ecp))

        # 提取复电场相位，单位为度
        ecp_phase_deg = np.angle(Ecp, deg=True)

        # -------------------------- 重塑二维方向图 --------------------------

        ecp_dB_2d = ecp_dB.reshape(N_THETA, N_PHI)
        ecp_phase_2d = ecp_phase_deg.reshape(N_THETA, N_PHI)

        # -------------------------- 组织输出数据 --------------------------

        out_rows = []

        for t_idx, theta in enumerate(theta_list):
            for p_idx, phi in enumerate(phi_list):
                out_rows.append([
                    phi,
                    theta,
                    ecp_dB_2d[t_idx, p_idx],
                    ecp_phase_2d[t_idx, p_idx],
                ])

        out_data = np.array(out_rows)

        # -------------------------- 保存 CSV --------------------------

        csv_name = f"ECP_single_{file_index}.csv"

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
            csv_name,
            index=False,
            float_format="%.6f",
        )

        file_index += 1


# ========================== 全部处理完成 ==========================

print("\n🎉🎉🎉 全部 270 组数据处理完成！")
print("✅ 生成文件：ECP_single_1.csv ～ ECP_single_270.csv")
print("✅ 每个文件包含：幅度 ECP_dB + 相位 ECP_Phase_deg")

