# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/main.py
# 目的：训练、预测、验证和评估阶段编排脚本
# 输入：实验数据、模型参数和阶段配置
# 输出：训练集、预测 ECP、误差汇总和图表
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

# 文件摘要：主流程编排脚本（无类/函数定义）。__main__ 按注释编号顺序执行十一个阶段，
#          第 1~4 段为训练数据流水线（运行第 5 段起需先自行注释掉），第 5~11 段为
#          测试与评估流水线：
#          1) 训练数据采集：30 次迭代调用 A_train_data_1.run_single_iteration，
#             前后用 hfss.delete 清理遗留对象；
#          2) 270 组方向图复数平均，输出 Average_ECP_270.txt/csv；
#          3) 270 组单组 45° 极化 ECP，输出 ECP_single_1~270.csv；
#          4) 用 求3D_cn_4.build_Zn 构造虚拟阵列 Z 矩阵，对 270 组 ECP 最小二乘
#             求 cn，合并 30 份 8 维特征并展开为 6750 行单单元数据集，
#             保存 dataset_single_element_6750.csv；
#          5) 产生测试集：run_test(test_iteration=TEST_ITER)（TEST_ITER=999，
#             导出 train999_3D_* 前缀，避免覆盖 train1~30 训练原始数据）；
#          6) 测试特征每行扩展 25 份附 element_id → test_features_expanded_25x.csv
#             （读 test_features_iter_{TEST_ITER}.csv，与第 5 段写出同一来源）；
#          7) XGBoost 训练（270 样本按种子 42 划分 216/54 防泄漏）：训练误差
#             （cn_real/cn_imag × RMSE/MAE/R² × train/valid）存 xgb_train_error.csv
#             并打印；预测 cn 存 test_cn/test_cn_pred.csv；Z@cn 合成预测 ECP 存
#             ecp_output_2/3_ecp_1~25.txt；
#          8) 测试集真实值：读 train999_3D_*_{1..25} 按第 3 段同式计算 45° 极化
#             真实 ECP 存 test_ecp_real/ECP_test_real_1~25.csv；段内自建 Z_ls 对
#             全球复数 ECP 最小二乘反推真实 cn 存 test_cn/test_cn_real.csv；
#          9) 两层误差评估（纯文件驱动可独立重跑）：第一层 cn 相对误差/最大误差
#             及全局 RMSE/MAE（模型准确性第一层判断）；第二层 ECP 三切面
#             （CUT_PHI_LIST=[0,44,90]，45° 不在 2° 网格取 44°；θ=0~90°）的
#             幅度/相位/对齐相位/相对误差/幅度相关指标，明细与汇总存
#             test_ecp_comparison/，控制台先 cn 层后按切面打印；
#         10) ECP 预测 vs 真实对比绘图（调用 plot_ecp_compare_10，纯文件驱动）：25
#             样本每样本双输出 2×3 图（上行幅值两口径——线性 dB 还原 plots/ + 直接
#             dB plot_db/（计划009，同计划008 合阵图口径）/ 下行相位 degree 已对齐
#             × φ=0/44/90 三切面），真实红/预测蓝，相位按真实幅值峰值处对齐，输出
#             test_ecp_comparison/plots/ 与 plot_db/ 及 phase_align_offset.csv。
#         11) 合阵总方向图合成对比与误差评估（计划006，调用
#             total_array_ecp_compare_11，纯文件驱动）：25 份实测/预测单元 ECP
#             按阵列叠加合成物理 5×5 总方向图（导向方向由参数区全局变量
#             STEER_THETA_DEG/STEER_PHI_DEG 注入，计划009），1 张 2×3 对比图与
#             三切面幅度/相位误差汇总（输出 total_array_* 系列文件）。
#          注意：模块级参数区同时堆叠了 2/3/4/7 号脚本的参数（另含 6 号脚本的
#          输入输出路径）；time、hfss 实例、random 等名字依赖 A_train_data_1 /
#          A_test_5 的星号导入间接获得。
# 类/函数清单：（无类/函数定义，为顺序执行的编排脚本）
from xgboost import XGBRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

from A_train_data_1 import *
import numpy as np
import pandas as pd
# from 训练集产生ecp文件_2 import *
# from 求平均_ecp_3 import *
# from 求3D_cn_4 import *
from A_test_5 import *
from 求3D_cn_4 import build_Zn as build_Zn_4
from xgboost预测cn并计算真实ecp_7 import build_Zn as build_Zn_7
# from 测试集添加虚拟阵列序号_6 import *
# from xgboost预测cn并计算真实ecp_7 import *


# ====================== 路径 ======================训练集产生ecp文件_2
#base_path = r"E:\c50066007\pythonML_mianzhen_random\\"

# n_phi = 181  # Phi: 0~360 step 2
# n_theta = 91  # Theta: 0~180 step 2

file_index = 1  # 全局编号 1~270
# =====================================================


# ====================== 路径 ======================求平均_ecp_3
base_path = r"E:\c50066007\pythonML_mianzhen_random\\"

n_train = 30
n_group = 9
n_phi = 181  # Phi: 0~360 step 2
n_theta = 91  # Theta: 0~180 step 2

# 初始化复数累加数组（幅度+相位一起平均）
sum_ecp_complex = np.zeros((n_theta, n_phi), dtype=complex)
count = 0
# ===================================================================

# ===================== 1. 基础参数 =====================求3D_cn_4
freq = 27.5e9
c = 3e8
lamda = c / freq
beta = 2 * np.pi / lamda

virtual_rows = np.arange(1, 6)
virtual_cols = np.arange(1, 6)
m_grid, n_grid = np.meshgrid(virtual_rows, virtual_cols)
m_flat = m_grid.flatten()
n_flat = n_grid.flatten()
num_virtual = 25
d_virtual_x = 0.005
d_virtual_y = 0.005
center_comp = -2

# ===================== 2. 加载平均方向图 g_ave =====================求3D_cn_4
g_ave_path = "E:/c50066007/pythonML_mianzhen_random/Average_ECP_270.csv"
df_gave = pd.read_csv(g_ave_path)
g_ave_dB = df_gave["ECP_dB"].values
g_ave_phase_deg = df_gave["ECP_Phase_deg"].values

g_ave_linear = 10 ** (g_ave_dB / 20)
g_ave_linear = g_ave_linear * np.exp(1j * np.deg2rad(g_ave_phase_deg))
g_ave = np.array(g_ave_linear, dtype=complex)
#===================================================================

# ===================== 1. 基础参数定义 =====================xgboost预测cn并计算真实ecp_7
freq = 27.5e9
c = 3e8
lamda = c / freq
#beta = 2 * np.pi / lamda

virtual_rows = np.arange(1, 6)
virtual_cols = np.arange(1, 6)
m_grid, n_grid = np.meshgrid(virtual_rows, virtual_cols)
# m_flat = m_grid.flatten()
# n_flat = n_grid.flatten()
# d_virtual_x = 0.005
# d_virtual_y = 0.005
# center_comp = -2

# ===================== 2. 直接读取 g_ave =====================xgboost预测cn并计算真实ecp_7
g_ave_path = r"E:/c50066007/pythonML_mianzhen_random/Average_ECP_270.csv"
df_gave = pd.read_csv(g_ave_path)

theta_deg = df_gave["Theta[deg]"].values
phi_deg = df_gave["Phi[deg]"].values
g_ave_dB = df_gave["ECP_dB"].values
g_ave_phase_deg = df_gave["ECP_Phase_deg"].values

theta_rad = np.deg2rad(theta_deg)
phi_rad = np.deg2rad(phi_deg)
u_list = np.sin(theta_rad) * np.cos(phi_rad)
v_list = np.sin(theta_rad) * np.sin(phi_rad)

g_ave_linear = 10 ** (g_ave_dB / 20)
g_ave_linear = g_ave_linear * np.exp(1j * np.deg2rad(g_ave_phase_deg))
g_ave = np.array(g_ave_linear, dtype=complex)

# ==================== 你只需要改这里 ====================
TEST_ITER = 999  # 测试集编号单一来源：run_test 导出前缀 train{TEST_ITER}_3D_* 与
                 # 特征文件 test_features_iter_{TEST_ITER}.csv、第 8 段读数共用此常量
input_path = f"E:/c50066007/pythonML_mianzhen_random/test_data/test_features_iter_{TEST_ITER}.csv"
output_path = r"E:/c50066007/pythonML_mianzhen_random/test_data/test_features_expanded_25x.csv"

# 合阵总方向图波束扫描导向（计划009 全局变量入口，第 11 段注入 total_array_ecp_compare_11）：
# 主瓣平移目标方向 (θ₀, φ₀)；设 0/0 即退化为法向合成（不导向）
STEER_THETA_DEG = 20   # θ₀（°）：φ=0 切面内主瓣右移角度（默认 20°，恰在 2° 网格点上）
STEER_PHI_DEG = 0      # φ₀（°）
# ========================================================

if __name__ == "__main__":
    # 1. 产生训练数据
    TOTAL_ITERATIONS = 30
    for iter_num in range(1, TOTAL_ITERATIONS + 1):
        hfss.delete(5)
        # 1. 记录函数执行前的时间戳
        start_time = time.time()
        run_single_iteration(iter_num)
        # 3. 记录函数执行后的时间戳，计算耗时
        end_time = time.time()
        elapsed_time = end_time - start_time
        # 4. 输出本次循环耗时
        print(f"第 {iter_num} 次迭代完成，耗时：{elapsed_time:.6f} 秒\n")
    print(f"🎉 所有{TOTAL_ITERATIONS}次迭代完成！所有CSV文件均为25行×8列格式")
    hfss.delete(3)

    # 2. 计算平均ecp
    # ====================== 遍历 270 个文件 ======================
    for train_idx in range(1, n_train + 1):
        print(f"处理 train{train_idx} ...")

        for g_idx in range(1, n_group + 1):
            # 文件路径
            file_dB_phi = base_path + f"train{train_idx}_3D_dir_phi_{g_idx}.csv"
            file_dB_theta = base_path + f"train{train_idx}_3D_dir_theta_{g_idx}.csv"
            file_deg_phi = base_path + f"train{train_idx}_3D_phase_phi_{g_idx}.csv"
            file_deg_theta = base_path + f"train{train_idx}_3D_phase_theta_{g_idx}.csv"

            # 读取数据
            df = pd.read_csv(file_dB_phi)
            #print("实际列名:", df.columns.tolist())
            if "dB(DirPhi)" not in df.columns:
                print("\n========== CSV异常 ==========")
                print("train_idx:", train_idx)
                print("g_idx:", g_idx)
                print("文件:", file_dB_phi)
                print("实际列名:", df.columns.tolist())
                print("前5行:")
                print(df.head())
                print("=============================")

                raise ValueError(
                    f"{file_dB_phi} 中不存在 dB(DirPhi)"
                )


            phi_deg = df["Phi[deg]"].values
            theta_deg = df["Theta[deg]"].values
            rEphi_dB = df["dB(DirPhi)"].values

            df_theta = pd.read_csv(file_dB_theta)
            rEtheta_dB = df_theta["dB(DirTheta)"].values

            df_phase_phi = pd.read_csv(file_deg_phi)
            rEphi_deg = df_phase_phi["ang_deg(rEPhi)[deg]"].values

            df_phase_theta = pd.read_csv(file_deg_theta)
            rEtheta_deg = df_phase_theta["ang_deg(rETheta)[deg]"].values

            # 复电场计算
            rEtheta = (10 ** (rEtheta_dB / 20)) * np.exp(1j * np.deg2rad(rEtheta_deg))
            rEphi = (10 ** (rEphi_dB / 20)) * np.exp(1j * np.deg2rad(rEphi_deg))

            # 45°极化 ECP（复数形式，包含幅度+相位）
            phi_rad = np.deg2rad(phi_deg)
            pol_rad = np.deg2rad(45)
            Ecp = rEtheta * np.cos(phi_rad - pol_rad) - rEphi * np.sin(phi_rad - pol_rad)

            # 形状对齐
            ecp_2d = Ecp.reshape(n_theta, n_phi)

            # 复数累加（正确平均方式）
            sum_ecp_complex += ecp_2d
            count += 1

    # 270个复数平均（最科学）
    avg_ecp_complex = sum_ecp_complex / count

    # 从平均后的复数中提取 幅度 和 相位
    avg_ecp_dB = 20 * np.log10(np.abs(avg_ecp_complex))  # 幅度dB
    avg_ecp_phase = np.angle(avg_ecp_complex, deg=True)  # 相位（度）

    # ====================== 生成坐标 ======================
    phi_list = np.arange(0, 361, 2)
    theta_list = np.arange(0, 181, 2)

    # 按你要的顺序：Theta固定 → Phi 0→360
    out_rows = []
    for t_idx, t in enumerate(theta_list):
        for p_idx, p in enumerate(phi_list):
            out_rows.append([
                p,
                t,
                avg_ecp_dB[t_idx, p_idx],
                avg_ecp_phase[t_idx, p_idx]
            ])

    out_data = np.array(out_rows)

    # ====================== 保存 TXT ======================
    header_txt = "Phi[deg]\tTheta[deg]\tECP_dB\tECP_Phase_deg"
    np.savetxt("Average_ECP_270.txt", out_data, fmt="%.6f",
               delimiter="\t", header=header_txt, comments='')

    # ====================== 保存 CSV ======================
    df_out = pd.DataFrame(out_data, columns=["Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg"])
    df_out.to_csv("Average_ECP_270.csv", index=False, float_format="%.6f")

    # ====================== 完成 ======================
    print("\n🎉 全部处理完成！（幅度+相位 已正确平均）")
    print(f"✅ 已生成 TXT：Average_ECP_270.txt")
    print(f"✅ 已生成 CSV：Average_ECP_270.csv")
    print(f"✅ 包含：Phi | Theta | ECP幅度 | ECP相位")
    print(f"✅ 顺序：Theta固定 → Phi 0→360 → Theta+2")


    #3. 计算训练集ecp
    # ====================== 遍历 train1 ~ train30 ======================
    for train_idx in range(1, 31):
        print(f"\n======================================")
        print(f"正在处理 train{train_idx} ...")

        # 每组内 1~9
        for x in range(1, 10):
            print(f" → 子文件 {x} (总序号: {file_index})")

            # 文件路径
            file_dB_phi = base_path + f"train{train_idx}_3D_dir_phi_{x}.csv"
            file_dB_theta = base_path + f"train{train_idx}_3D_dir_theta_{x}.csv"
            file_deg_phi = base_path + f"train{train_idx}_3D_phase_phi_{x}.csv"
            file_deg_theta = base_path + f"train{train_idx}_3D_phase_theta_{x}.csv"

            # 读取数据
            df = pd.read_csv(file_dB_phi)
            phi_deg = df["Phi[deg]"].values
            theta_deg = df["Theta[deg]"].values
            rEphi_dB = df["dB(DirPhi)"].values

            df_theta = pd.read_csv(file_dB_theta)
            rEtheta_dB = df_theta["dB(DirTheta)"].values

            df_phase_phi = pd.read_csv(file_deg_phi)
            rEphi_deg = df_phase_phi["ang_deg(rEPhi)[deg]"].values

            df_phase_theta = pd.read_csv(file_deg_theta)
            rEtheta_deg = df_phase_theta["ang_deg(rETheta)[deg]"].values

            # 复电场计算
            rEtheta = (10 ** (rEtheta_dB / 20)) * np.exp(1j * np.deg2rad(rEtheta_deg))
            rEphi = (10 ** (rEphi_dB / 20)) * np.exp(1j * np.deg2rad(rEphi_deg))

            # 45°极化 ECP
            phi_rad = np.deg2rad(phi_deg)
            pol_rad = np.deg2rad(45)
            Ecp = rEtheta * np.cos(phi_rad - pol_rad) - rEphi * np.sin(phi_rad - pol_rad)

            # 幅度 + 相位
            ecp_dB = 20 * np.log10(np.abs(Ecp))
            ecp_phase_deg = np.angle(Ecp, deg=True)

            #  reshape
            ecp_dB_2d = ecp_dB.reshape(n_theta, n_phi)
            ecp_phase_2d = ecp_phase_deg.reshape(n_theta, n_phi)

            # 生成坐标
            phi_list = np.arange(0, 361, 2)
            theta_list = np.arange(0, 181, 2)

            out_rows = []
            for t_idx, t in enumerate(theta_list):
                for p_idx, p in enumerate(phi_list):
                    out_rows.append([p, t, ecp_dB_2d[t_idx, p_idx], ecp_phase_2d[t_idx, p_idx]])

            out_data = np.array(out_rows)

            # ====================== 只保存 CSV，不保存 TXT ======================
            csv_name = f"ECP_single_{file_index}.csv"

            df_out = pd.DataFrame(out_data, columns=["Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg"])
            df_out.to_csv(csv_name, index=False, float_format="%.6f")

            file_index += 1

    print("\n🎉🎉🎉 全部 270 组数据处理完成！")
    print(f"✅ 生成文件：ECP_single_1.csv ~ ECP_single_270.csv")
    print(f"✅ 每个文件包含：幅度ECP_dB + 相位ECP_Phase_deg")

    #4. 计算虚拟阵列的cn
    print("正在计算 270 组 cn 标签...")
    all_cn = []

    for idx in range(1, 271):
        csv_path = f"E:/c50066007/pythonML_mianzhen_random/ECP_single_{idx}.csv"
        df = pd.read_csv(csv_path)

        phi_deg = df["Phi[deg]"].values
        theta_deg = df["Theta[deg]"].values
        g_n_dB = df["ECP_dB"].values
        g_n_phase_deg = df["ECP_Phase_deg"].values

        g_n_linear = 10 ** (g_n_dB / 20)
        g_n_linear = g_n_linear * np.exp(1j * np.deg2rad(g_n_phase_deg))

        theta_rad = np.deg2rad(theta_deg)
        phi_rad = np.deg2rad(phi_deg)
        u_list = np.sin(theta_rad) * np.cos(phi_rad)
        v_list = np.sin(theta_rad) * np.sin(phi_rad)

        Z_n = build_Zn_4(g_ave, u_list, v_list, m_flat, n_flat, beta, d_virtual_x, d_virtual_y, center_comp)
        Z_H = Z_n.conj().T
        g_n = g_n_linear.astype(complex)
        cn = np.linalg.inv(Z_H @ Z_n) @ Z_H @ g_n

        row = np.hstack([np.real(cn), np.imag(cn)])
        all_cn.append(row)

        if idx % 50 == 0:
            print(f"已处理 {idx}/270")

    all_cn = np.array(all_cn)
    print(f"cn 标签形状: {all_cn.shape} (270 × 50)")

    # ===================== 5. 读取 270 条 8维特征 =====================
    print("正在读取 8 维特征...")
    feats = []
    base_feat = "E:/c50066007/pythonML_mianzhen_random/train_data/train_features_iter_"

    for i in range(1, 31):
        df_feat = pd.read_csv(f"{base_feat}{i}.csv")
        feats.append(df_feat.values)

    feats = np.vstack(feats)
    print(f"特征形状: {feats.shape} (270 × 8)")

    # ==============================================================================
    # 🔴🔴🔴 6. 【核心修改】展开成 270×25 = 6750 条数据
    # ==============================================================================
    print("\n正在展开数据集为 单输出格式（每条数据对应1个虚拟单元）...")

    expanded_data = []

    for sample_idx in range(270):
        # 取出当前样本的 8 维特征
        f = feats[sample_idx]  # shape (8,)

        # 取出 25 实部 + 25 虚部
        re = all_cn[sample_idx, :25]
        im = all_cn[sample_idx, 25:]

        # 每个虚拟单元单独拆成一条数据
        for elem_idx in range(25):
            # 新输入：8维 + 单元编号(1~25)
            new_feature = np.hstack([f, elem_idx + 1])

            # 新输出：对应单元的实部 + 虚部
            new_label = np.array([re[elem_idx], im[elem_idx]])

            # 拼起来
            expanded_row = np.hstack([new_feature, new_label])
            expanded_data.append(expanded_row)

    expanded_data = np.array(expanded_data)

    print(f"✅ 展开完成！新数据集形状: {expanded_data.shape} (6750 × 11)")
    print("   每条数据：9个输入特征(8+1) + 2个输出标签 = 11列")

    # ===================== 7. 保存 =====================
    col_names = [
        "right", "right_up", "up", "left_up",
        "left", "left_down", "down", "right_down",
        "element_id",  # 🔴 新增：虚拟单元编号 1~25
        "cn_real",  # 🔴 单个单元实部
        "cn_imag"  # 🔴 单个单元虚部
    ]

    df_out = pd.DataFrame(expanded_data, columns=col_names)
    df_out.to_csv("dataset_single_element_6750.csv", index=False, float_format="%.8f")

    print("\n🎉 全部完成！")
    print("📁 输出文件：dataset_single_element_6750.csv")
    print("📏 每条数据：9输入 + 2输出")

    # 5. 产生测试集（run_test 传 TEST_ITER=999，导出 train{TEST_ITER}_3D_* 前缀，
    #    与训练数据 train1~30 隔离，避免覆盖训练原始数据）
    hfss.delete(5)
    run_test(test_iteration=TEST_ITER)
    hfss.delete(5)

    # 6. 测试集添加虚拟阵列编号变为和训练集格式一致
    df = pd.read_csv(input_path, header=None, skiprows=1)
    print(f"原始测试集形状: {df.shape}")

    expanded_rows = []
    for idx, row in df.iterrows():
        feat = row.values  # 8个特征
        for elem_id in range(1, 26):  # 1~25
            new_row = list(feat) + [elem_id]
            expanded_rows.append(new_row)
    df_out = pd.DataFrame(expanded_rows)
    col_names = [
        "right","right_up","up","left_up",
        "left","left_down","down","right_down",
        "element_id"  # 9列：8+1
    ]
    df_out.columns = col_names
    df_out.to_csv(output_path, index=False, float_format="%.8f")
    print(f"✅ 扩展完成！新形状: {df_out.shape}  (应该是 N×25 行, 9列)")
    print(f"✅ 已保存到: {output_path}")

    # 7. XGBoost 训练（含训练误差）→ 预测 cn 落盘 → Z@cn 合成预测 ECP
    Z = build_Zn_7(g_ave, u_list, v_list, m_flat, n_flat, beta, d_virtual_x, d_virtual_y, center_comp)

    # ===================== 4. XGBoost 训练模型 =====================
    train_path = r"E:/c50066007/pythonML_mianzhen_random/dataset_single_element_6750.csv"
    df_train = pd.read_csv(train_path)

    # 输入是 9 个特征，输出是 2 个标签
    X_all = df_train.iloc[:, :9].values          # 8+1 = 9个输入
    y_all = df_train.iloc[:, 9:].values          # 输出：cn_real, cn_imag

    # 训练误差评估：样本级划分防泄漏（每样本 25 行从 element_id=1 开始，
    # 行级随机划分会因同样本 25 行特征几乎相同而虚高）
    elem_ids = df_train["element_id"].values
    sample_ids = np.cumsum(elem_ids == 1) - 1
    n_samples_total = int(sample_ids.max()) + 1
    valid_samples = np.random.RandomState(42).choice(n_samples_total, size=54, replace=False)
    valid_mask = np.isin(sample_ids, valid_samples)
    print(f"样本级划分：共 {n_samples_total} 样本，训练 {n_samples_total - 54}，验证 54（种子 42）")

    model = XGBRegressor(
        n_estimators=500,
        learning_rate=0.1,
        max_depth=8,
        random_state=42
    )
    print("正在训练 XGBoost 模型...")
    model.fit(X_all[~valid_mask], y_all[~valid_mask])
    print("模型训练完成！")

    # 训练误差：cn_real / cn_imag 各自 RMSE / MAE / R²（训练集与验证集各一套）
    metric_rows = []
    for ds_name, y_t, y_p in [
        ("train", y_all[~valid_mask], model.predict(X_all[~valid_mask])),
        ("valid", y_all[valid_mask], model.predict(X_all[valid_mask])),
    ]:
        for col_idx, out_name in [(0, "cn_real"), (1, "cn_imag")]:
            metric_rows.append([ds_name, out_name, "RMSE",
                                float(np.sqrt(mean_squared_error(y_t[:, col_idx], y_p[:, col_idx])))])
            metric_rows.append([ds_name, out_name, "MAE",
                                float(mean_absolute_error(y_t[:, col_idx], y_p[:, col_idx]))])
            metric_rows.append([ds_name, out_name, "R2",
                                float(r2_score(y_t[:, col_idx], y_p[:, col_idx]))])

    df_err = pd.DataFrame(metric_rows, columns=["dataset", "output", "metric", "value"])
    train_error_path = r"E:/c50066007/pythonML_mianzhen_random/xgb_train_error.csv"
    df_err.to_csv(train_error_path, index=False, float_format="%.8f")
    print("\n训练误差评估（已保存到 xgb_train_error.csv）：")
    print(df_err.to_string(index=False))

    # ===================== 5. 读取测试集 =====================
    test_path = r"E:/c50066007/pythonML_mianzhen_random/test_data/test_features_expanded_25x.csv"
    df_test = pd.read_csv(test_path)
    X_test = df_test.values        # 测试集也是 9 列
    num_test = len(X_test)
    print(f"测试集总数：{num_test}")

    # ===================== 6. 预测 cn → 计算 ECP =====================
    print("\n开始预测 cn 并生成 ECP 文件...")
    y_pred = model.predict(X_test)  # 输出 shape: (N, 2)

    # 预测 cn 落盘（sample_id / element_id / cn_real / cn_imag）
    cn_dir = r"E:/c50066007/pythonML_mianzhen_random/test_cn"
    os.makedirs(cn_dir, exist_ok=True)
    cn_pred_rows = []
    for row_idx in range(num_test):
        cn_pred_rows.append([row_idx // 25 + 1, row_idx % 25 + 1,
                             y_pred[row_idx, 0], y_pred[row_idx, 1]])
    df_cn_pred = pd.DataFrame(cn_pred_rows, columns=["sample_id", "element_id", "cn_real", "cn_imag"])
    df_cn_pred.to_csv(os.path.join(cn_dir, "test_cn_pred.csv"), index=False, float_format="%.8f")
    print(f"✅ 预测 cn 已保存：{os.path.join(cn_dir, 'test_cn_pred.csv')}")

    # 把测试集还原成 原始样本数（每25行一个样本）
    num_original_samples = num_test // 25

    save_dir = r"E:/c50066007/pythonML_mianzhen_random/ecp_output_2"
    os.makedirs(save_dir, exist_ok=True)

    for sample_idx in range(num_original_samples):
        # 取出当前样本对应的 25 个单元预测
        start = sample_idx * 25
        end = start + 25
        pred_25 = y_pred[start:end]  # shape (25,2)

        # 拼成 25 个复 cn
        cn = pred_25[:, 0] + 1j * pred_25[:, 1]

        # 计算 ECP
        ecp_complex = Z @ cn
        ecp_dB = 20 * np.log10(np.abs(ecp_complex) + 1e-10)
        ecp_phase_deg = np.angle(ecp_complex, deg=True)

        # 保存
        df_out = pd.DataFrame({
            "Phi[deg]": phi_deg,
            "Theta[deg]": theta_deg,
            "ECP_dB": ecp_dB,
            "ECP_Phase_deg": ecp_phase_deg
        })
        file_num = sample_idx + 1
        save_path = os.path.join(save_dir, f"3_ecp_{file_num}.txt")
        df_out.to_csv(save_path, index=False, float_format="%.6f")
        print(f"已保存：3_ecp_{file_num}.txt")

    print(f"\n✅ 全部完成！已生成 {num_original_samples} 个 ECP 文件")

    # 8. 测试集真实 ECP 与真实 cn（读 train{TEST_ITER}_3D_*_{1..25}，公式与第 3 段一致）
    real_ecp_dir = r"E:/c50066007/pythonML_mianzhen_random/test_ecp_real"
    os.makedirs(real_ecp_dir, exist_ok=True)
    cn_dir = r"E:/c50066007/pythonML_mianzhen_random/test_cn"
    os.makedirs(cn_dir, exist_ok=True)

    # 本段自建 Z_ls（与第 7 段同一构造），使第 8 段可脱离第 7 段独立重跑
    Z_ls = build_Zn_7(g_ave, u_list, v_list, m_flat, n_flat, beta, d_virtual_x, d_virtual_y, center_comp)

    cn_real_rows = []
    for g in range(1, 26):
        print(f"计算测试样本 {g}/25 真实 ECP ...")

        # 文件路径（命名机制与训练集相同，仅 iteration=999）
        file_dB_phi = base_path + f"train{TEST_ITER}_3D_dir_phi_{g}.csv"
        file_dB_theta = base_path + f"train{TEST_ITER}_3D_dir_theta_{g}.csv"
        file_deg_phi = base_path + f"train{TEST_ITER}_3D_phase_phi_{g}.csv"
        file_deg_theta = base_path + f"train{TEST_ITER}_3D_phase_theta_{g}.csv"

        # 读取数据（列名与训练集导出一致）
        df = pd.read_csv(file_dB_phi)
        phi_deg_r = df["Phi[deg]"].values
        theta_deg_r = df["Theta[deg]"].values
        rEphi_dB = df["dB(DirPhi)"].values

        rEtheta_dB = pd.read_csv(file_dB_theta)["dB(DirTheta)"].values
        rEphi_deg = pd.read_csv(file_deg_phi)["ang_deg(rEPhi)[deg]"].values
        rEtheta_deg = pd.read_csv(file_deg_theta)["ang_deg(rETheta)[deg]"].values

        # 复电场计算（与第 3 段一致）
        rEtheta = (10 ** (rEtheta_dB / 20)) * np.exp(1j * np.deg2rad(rEtheta_deg))
        rEphi = (10 ** (rEphi_dB / 20)) * np.exp(1j * np.deg2rad(rEphi_deg))

        # 45°极化 ECP（与第 3 段一致）
        phi_rad = np.deg2rad(phi_deg_r)
        pol_rad = np.deg2rad(45)
        Ecp = rEtheta * np.cos(phi_rad - pol_rad) - rEphi * np.sin(phi_rad - pol_rad)

        ecp_dB = 20 * np.log10(np.abs(Ecp))
        ecp_phase_deg = np.angle(Ecp, deg=True)

        df_out = pd.DataFrame({
            "Phi[deg]": phi_deg_r,
            "Theta[deg]": theta_deg_r,
            "ECP_dB": ecp_dB,
            "ECP_Phase_deg": ecp_phase_deg
        })
        df_out.to_csv(os.path.join(real_ecp_dir, f"ECP_test_real_{g}.csv"), index=False, float_format="%.6f")

        # 真实 cn：全球复数 ECP 最小二乘（与第 4 段求训练 cn 同法同基）
        g_n = Ecp.astype(complex)
        Z_H = Z_ls.conj().T
        cn_g = np.linalg.inv(Z_H @ Z_ls) @ Z_H @ g_n
        for elem_idx in range(25):
            cn_real_rows.append([g, elem_idx + 1,
                                 float(np.real(cn_g[elem_idx])), float(np.imag(cn_g[elem_idx]))])

    df_cn_real = pd.DataFrame(cn_real_rows, columns=["sample_id", "element_id", "cn_real", "cn_imag"])
    df_cn_real.to_csv(os.path.join(cn_dir, "test_cn_real.csv"), index=False, float_format="%.8f")
    print(f"✅ 真实 ECP（25 个）已存 {real_ecp_dir}")
    print(f"✅ 真实 cn 已存 {os.path.join(cn_dir, 'test_cn_real.csv')}")

    # 9. 两层误差评估（纯文件驱动，可独立重跑）
    #    第一层：cn（模型输出 vs 真实 cn）；第二层：ECP 三切面（φ=0/44/90，θ=0~90°）
    CUT_PHI_LIST = [0, 44, 90]   # 45° 不在 2° 网格，取最近格点 44°（想改 46° 只改这里）
    THETA_CUT_MAX = 90           # 切面 θ 上限
    eval_dir = r"E:/c50066007/pythonML_mianzhen_random/test_ecp_comparison"
    real_ecp_dir = r"E:/c50066007/pythonML_mianzhen_random/test_ecp_real"
    cn_dir = r"E:/c50066007/pythonML_mianzhen_random/test_cn"
    save_dir = r"E:/c50066007/pythonML_mianzhen_random/ecp_output_2"
    os.makedirs(eval_dir, exist_ok=True)

    # ---------- 第一层：cn 误差（模型准确性） ----------
    df_cp = pd.read_csv(os.path.join(cn_dir, "test_cn_pred.csv"))
    df_cr = pd.read_csv(os.path.join(cn_dir, "test_cn_real.csv"))
    merged = df_cp.merge(df_cr, on=["sample_id", "element_id"], suffixes=("_pred", "_real"))
    if len(merged) == 0:
        raise ValueError("cn_pred 与 cn_real 无可对齐样本，请检查两文件的 sample_id/element_id")

    pred_cn_all = merged["cn_real_pred"].values + 1j * merged["cn_imag_pred"].values
    real_cn_all = merged["cn_real_real"].values + 1j * merged["cn_imag_real"].values
    eval_sample_ids = np.unique(merged["sample_id"].values)

    cn_rel_l2_map = {}
    cn_max_err_map = {}
    for s in eval_sample_ids:
        m = merged["sample_id"].values == s
        diff_cn = pred_cn_all[m] - real_cn_all[m]
        cn_rel_l2_map[s] = float(np.linalg.norm(diff_cn) / np.linalg.norm(real_cn_all[m]))
        cn_max_err_map[s] = float(np.max(np.abs(diff_cn)))

    cn_global = {
        "cn_real_RMSE": float(np.sqrt(np.mean((merged["cn_real_pred"] - merged["cn_real_real"]) ** 2))),
        "cn_real_MAE": float(np.mean(np.abs(merged["cn_real_pred"] - merged["cn_real_real"]))),
        "cn_imag_RMSE": float(np.sqrt(np.mean((merged["cn_imag_pred"] - merged["cn_imag_real"]) ** 2))),
        "cn_imag_MAE": float(np.mean(np.abs(merged["cn_imag_pred"] - merged["cn_imag_real"]))),
        "cn_rel_l2_mean": float(np.mean(list(cn_rel_l2_map.values()))),
        "cn_rel_l2_max": float(np.max(list(cn_rel_l2_map.values()))),
    }

    # ---------- 第二层：ECP 误差（每样本 × 每切面 46 点） ----------
    detail_rows = []
    for s in eval_sample_ids:
        df_pred = pd.read_csv(os.path.join(save_dir, f"3_ecp_{s}.txt"))
        df_real = pd.read_csv(os.path.join(real_ecp_dir, f"ECP_test_real_{s}.csv"))

        for cut_phi in CUT_PHI_LIST:
            mask_p = np.isclose(df_pred["Phi[deg]"].values, cut_phi) & \
                     (df_pred["Theta[deg]"].values <= THETA_CUT_MAX + 1e-9)
            mask_r = np.isclose(df_real["Phi[deg]"].values, cut_phi) & \
                     (df_real["Theta[deg]"].values <= THETA_CUT_MAX + 1e-9)
            sub_p = df_pred[mask_p].sort_values("Theta[deg]").reset_index(drop=True)
            sub_r = df_real[mask_r].sort_values("Theta[deg]").reset_index(drop=True)

            # 切面点集一致性校验（每切面应为 46 点且 θ 序列一致）
            if len(sub_p) != len(sub_r):
                raise ValueError(f"样本 {s} 切面 φ={cut_phi}：预测 {len(sub_p)} 点 / 真实 {len(sub_r)} 点，数量不一致")
            if not np.allclose(sub_p["Theta[deg]"].values, sub_r["Theta[deg]"].values):
                raise ValueError(f"样本 {s} 切面 φ={cut_phi}：预测/真实 Theta 序列不一致")
            if len(sub_p) != 46:  # θ=0~90° 步长 2° 应恰为 46 点（防两文件同源同错）
                raise ValueError(f"样本 {s} 切面 φ={cut_phi}：取到 {len(sub_p)} 点，预期 46 点")

            pred_dB = sub_p["ECP_dB"].values
            real_dB = sub_r["ECP_dB"].values
            d_amp = np.abs(pred_dB - real_dB)

            d_phase = sub_p["ECP_Phase_deg"].values - sub_r["ECP_Phase_deg"].values
            d_wrap = (d_phase + 180.0) % 360.0 - 180.0
            mean_offset = np.degrees(np.angle(np.mean(np.exp(1j * np.deg2rad(d_wrap)))))
            d_aligned = (d_wrap - mean_offset + 180.0) % 360.0 - 180.0

            pred_c = (10 ** (pred_dB / 20)) * np.exp(1j * np.deg2rad(sub_p["ECP_Phase_deg"].values))
            real_c = (10 ** (real_dB / 20)) * np.exp(1j * np.deg2rad(sub_r["ECP_Phase_deg"].values))

            detail_rows.append([
                int(s), int(cut_phi),
                cn_rel_l2_map[s], cn_max_err_map[s],
                float(np.mean(d_amp)), float(np.max(d_amp)),
                float(np.mean(np.abs(d_wrap))),
                float(np.mean(np.abs(d_aligned))),
                float(np.linalg.norm(pred_c - real_c) / np.linalg.norm(real_c)),
                float(np.corrcoef(np.abs(pred_c), np.abs(real_c))[0, 1]),
            ])

    detail_cols = ["sample_id", "cut_phi_deg", "cn_rel_l2", "cn_max_abs_err",
                   "amp_mean_err_dB", "amp_max_err_dB", "phase_mean_err_deg",
                   "phase_mean_err_aligned_deg", "rel_l2", "corr_amp"]
    df_detail = pd.DataFrame(detail_rows, columns=detail_cols)
    df_detail.to_csv(os.path.join(eval_dir, "error_per_sample.csv"), index=False, float_format="%.6f")

    # 汇总：ECP 层按切面 + 总体；cn 层全局一并列入
    summary_rows = []
    ecp_metric_cols = detail_cols[4:]
    scopes = [(f"cut_{c}", df_detail[df_detail["cut_phi_deg"] == c]) for c in CUT_PHI_LIST]
    scopes.append(("overall", df_detail))
    for scope_name, sub in scopes:
        for m in ecp_metric_cols:
            summary_rows.append(["ECP", scope_name, m,
                                 float(sub[m].mean()), float(sub[m].max()), float(sub[m].min())])
    for k, v in cn_global.items():
        summary_rows.append(["cn", "global", k, v, "", ""])
    df_summary = pd.DataFrame(summary_rows, columns=["layer", "scope", "metric", "mean", "max", "min"])
    df_summary.to_csv(os.path.join(eval_dir, "error_summary.csv"), index=False, float_format="%.6f")

    # 控制台汇总（先 cn 层，后按切面 ECP 层）
    print("\n==== 误差评估汇总（三切面 φ=0/44/90，θ=0~90°） ====")
    print("第一层：cn 误差（模型准确性）")
    for k, v in cn_global.items():
        print(f"  {k}: {v:.6g}")
    print("第二层：ECP 误差（各切面跨样本均值）")
    for cut_phi in CUT_PHI_LIST:
        sub = df_detail[df_detail["cut_phi_deg"] == cut_phi]
        print(f"  φ={cut_phi}°: 幅度误差均值 {sub['amp_mean_err_dB'].mean():.3f} dB"
              f"（最大 {sub['amp_max_err_dB'].max():.3f}）, "
              f"相位误差均值 {sub['phase_mean_err_deg'].mean():.2f}°, "
              f"相对误差均值 {sub['rel_l2'].mean():.4f}, 幅度相关均值 {sub['corr_amp'].mean():.4f}")
    print(f"\n✅ 误差评估完成，输出目录: {eval_dir}")

    # 10. ECP 预测 vs 真实对比绘图（纯文件驱动，读第 7/8 段已落盘的 ECP 文件；
    #     计划009 每样本双输出）：25 样本每样本 2 张 2×3 图（上行幅值两口径——
    #     线性还原 + 直接 dB / 下行相位 degree × φ=0/44/90 三切面），真实红/预测蓝，
    #     相位按真实幅值峰值对齐；输出 test_ecp_comparison/plots/（线性）与
    #     plot_db/（dB）及 phase_align_offset.csv。模块可独立重跑（python plot_ecp_compare_10.py）。
    import plot_ecp_compare_10
    plot_ecp_compare_10.main()

    # 11. 合阵总方向图合成对比与误差评估（纯文件驱动，计划006；计划008 导向+dB 轴，
    #     计划009 导向全局变量注入）：读 25 份实测与 25 份预测单元 ECP 及位置表，
    #     按阵列叠加（E_total = Σ Ecp_g·e^{jβ[x_g(u−u₀)+y_g(v−v₀)]}）合成两侧
    #     物理 5×5 总方向图，导向方向 (θ₀,φ₀) 取参数区全局变量
    #     STEER_THETA_DEG/STEER_PHI_DEG（改全局变量即换扫描角；0/0 退化法向合成），
    #     输出 total_array_ecp_real/pred.csv、plots/total_array_ecp_compare.png
    #     （2×3 样式与第 10 段一致，上行 dB）、total_array_error_summary.csv、
    #     total_array_phase_align_offset.csv。模块可独立重跑
    #     （python total_array_ecp_compare_11.py，走模块默认导向 20°/0°）。
    import total_array_ecp_compare_11
    total_array_ecp_compare_11.main(steer_theta_deg=STEER_THETA_DEG,
                                    steer_phi_deg=STEER_PHI_DEG)

