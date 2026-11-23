# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/total_array_ecp_compare_11.py
# 目的：总阵方向图合成、对比和误差评估
# 输入：单元 ECP、位置表和导向角
# 输出：总阵方向图、对比图和误差汇总
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

# 文件摘要：合阵总方向图合成对比与误差评估模块（计划 006，纯文件驱动；计划 008
#          增补波束扫描导向与 dB 轴；计划 009 导向角经 main()/plot_total() 参数
#          透传暴露，供 main.py 全局变量 STEER_* 注入；计划 011 幅相视图分离——
#          幅值视图不经过单元相位逐点直加、相位视图由单元复数直加取辐角）。
#          读 25 份实测单元 ECP
#          （test_ecp_real/ECP_test_real_{1..25}.csv）与 25 份预测单元 ECP
#          （ecp_output_2/3_ecp_{1..25}.txt）及单元物理位置表
#          （antenna_position_data.csv，mil），按阵列叠加原理合成物理 5×5 总方向图：
#          幅值视图 A(θ) = Σ 10^(ECP_dB_g/20)（不含单元相位/位置因子）；
#          相位视图 Φ(θ) = arg Σ [Ecp_g·e^{jφ_g}·e^{jβ(x_g(u−u₀)+y_g(v−v₀))}]；
#          u=sinθcosφ、v=sinθsinφ、(u₀,v₀) 为导向方向 (θ₀,φ₀)（参数区 STEER_*，
#          默认 20°/0°；计划009：main()/plot_total() 可显式传入覆盖，设 0/0 退化法向合成）。
#          理论依据：Maxwell 线性叠加（嵌入单元方向图相干
#          求和，Pozar active element pattern）+ 远场相位参考平移（各报告球心在
#          单元锚点，统一到全局原点）。合成的两支总方向图按 2×3 图对比（上行幅值
#          dB（计划008 改，不再还原线性）、下行相位卷绕+真实幅值峰值处对齐、真实
#          红/预测蓝），误差层口径不变（corr_amp 仍线性幅值，对齐 main.py 第 9 段）。
#          模块分层（设计模式要求）：参数区 / 数据层 / 合成层 / 绘图层 / 误差层；
#          绘图函数与样式复用 plot_ecp_compare_10（import 复用，不复制第三份）；
#          合成函数不写死单元数，可拓展到其他阵列规模；后续分解（Z 矩阵最小二乘）
#          归拢也落在本模块扩展。可独立运行（python total_array_ecp_compare_11.py）。
# 类/函数清单：
#   load_position_table —— 读天线位置 CSV（unit_id/abs_x/abs_y，mil），断言行数，
#                           返回 (n_units, 2) 米制数组
#   load_element_ecps   —— 读 n 份单元 ECP 文件（load_ecp），逐份网格断言后返回列表
#   _restore_complex    —— ECP_dB/ECP_Phase_deg → 复数电场
#   synthesis_total_field —— 视图分离阵列叠加：并行返回幅值视图 Σ 10^(ECP_dB/20)
#                             与复数视图 Σ Ecp_g·e^{j(φ+β·)}（计划011；单元数由输入
#                             决定；导向方向 θ₀/φ₀ 参数化，计划008 默认 20°/0°；
#                             θ/φ 网格取自首份文件并断言一致）→ (θ, φ, amp, E)
#   total_to_df           —— 视图分离转 4 列 ECP DataFrame：ECP_dB=20·log10(amp)、
#                             ECP_Phase_deg=deg(E)（幅值/相位两视图各自消费）
#   compute_total_error   —— 三切面误差指标：幅度 dB RMSE/MAE、幅度相关系数
#                             （线性幅值口径）、相位（对齐后卷绕）RMSE/MAE、
#                             复数相对误差
#   plot_total            —— 合成总图 2×3 对比图（样式与计划004 一致，1 张；
#                             计划008：上行幅值轴为 dB；计划009：导向角参数传入，
#                             suptitle 读实际导向角）
#   main                —— 加载 → 合成两侧（导向角默认参数区 STEER_*，可显式传入，
#                          计划009）→ 落盘总场 CSV → 绘图 → 误差汇总
import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# 复用计划004 绘图模块：切面提取/相位对齐/文件读取与样式常量（不复制第三份）
import plot_ecp_compare_10 as ecp_plot

# ------------------------------ 参数区 ------------------------------
BASE_PATH = r"E:/c50066007/pythonML_mianzhen_random"
REAL_DIR = os.path.join(BASE_PATH, "test_ecp_real")        # 实测单元 ECP（ECP_test_real_{g}.csv）
PRED_DIR = os.path.join(BASE_PATH, "ecp_output_2")         # 预测单元 ECP（3_ecp_{g}.txt）
POSITION_CSV = os.path.join(BASE_PATH, "antenna_position_data.csv")  # A_test_5 落盘（mil）

EVAL_DIR = os.path.join(BASE_PATH, "test_ecp_comparison")  # 输出与计划004 同目录
PLOT_DIR = os.path.join(EVAL_DIR, "plots")
REAL_TOTAL_CSV = os.path.join(EVAL_DIR, "total_array_ecp_real.csv")
PRED_TOTAL_CSV = os.path.join(EVAL_DIR, "total_array_ecp_pred.csv")
ERROR_CSV = os.path.join(EVAL_DIR, "total_array_error_summary.csv")
ALIGN_CSV = os.path.join(EVAL_DIR, "total_array_phase_align_offset.csv")

FREQ_HZ = 27.5e9                  # 与 build_Zn 同源（27.5 GHz）
C_LIGHT = 3e8                     # 与 求3D_cn_4/xgboost_7 同源
N_UNITS = 25                      # 5×5；合成函数本身不写死，仅用于文件数断言
MIL_TO_M = 0.0254                 # 位置表 mil → m
EXPECTED_GRID_POINTS = 91 * 181   # 16471 点/文件（防截断）

REAL_COLOR = ecp_plot.REAL_COLOR  # 真实红
PRED_COLOR = ecp_plot.PRED_COLOR  # 预测蓝

# 波束扫描导向（计划008）：主瓣平移目标方向 (θ₀, φ₀)；设回 0/0 即退化为法向合成
STEER_THETA_DEG = 20             # θ₀=20°（φ=0 切面内右移 20°，恰在 2° 网格点上）
STEER_PHI_DEG = 0                # φ₀=0°


def load_position_table(path, n_units=N_UNITS):
    """读天线位置表（unit_id/abs_x/abs_y，mil），返回 (n_units, 2) 米制数组。

    fail-loud：文件缺失 / 行数≠n_units / unit_id 不连续 一律 raise。
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"天线位置表不存在：{path}")
    df = pd.read_csv(path)
    required = {"unit_id", "abs_x", "abs_y"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} 缺少列 {sorted(missing)}，实际列：{list(df.columns)}")
    if len(df) != n_units:
        raise ValueError(f"位置表 {len(df)} 行，预期 {n_units} 行")
    ids = df["unit_id"].values
    if not np.array_equal(ids, np.arange(1, n_units + 1)):
        raise ValueError(f"unit_id 不为 1..{n_units} 连续序列：{ids}")
    pos_mil = df.sort_values("unit_id")[["abs_x", "abs_y"]].values.astype(float)
    return pos_mil * MIL_TO_M


def load_element_ecps(directory, filename_pattern, n_units=N_UNITS):
    """读 n 份单元 ECP 文件并逐份网格断言，返回 DataFrame 列表（下标 g-1）。

    filename_pattern 用 {g} 占位（如 "ECP_test_real_{g}.csv"）。
    fail-loud：任一文件缺失即 raise（计划003 防线：不静默跳过）。
    """
    dfs = []
    for g in range(1, n_units + 1):
        path = os.path.join(directory, filename_pattern.format(g=g))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"单元 ECP 文件缺失（单元 {g}）：{path}")
        df = ecp_plot.load_ecp(path)
        if len(df) != EXPECTED_GRID_POINTS:
            raise ValueError(f"{path} 数据行数 {len(df)}，预期 {EXPECTED_GRID_POINTS}")
        dfs.append(df)
    return dfs


def _restore_complex(df):
    """ECP_dB/ECP_Phase_deg → 复数电场（管线同式：10^(dB/20)·e^{jφ}）。"""
    amp = 10 ** (df["ECP_dB"].values / 20)
    phase = np.deg2rad(df["ECP_Phase_deg"].values)
    return amp * np.exp(1j * phase)


def synthesis_total_field(ecp_dfs, positions_m, freq=FREQ_HZ,
                          steer_theta_deg=STEER_THETA_DEG,
                          steer_phi_deg=STEER_PHI_DEG):
    """阵列叠加合成总方向图（计划008 含导向；计划011 幅相视图分离）：

        幅度视图  A(θ,φ)   = Σ_g 10^(ECP_dB_g(θ,φ)/20)
        相位视图  Φ(θ,φ)   = arg Σ_g Ecp_g(θ,φ)·e^{jφ_g}·e^{jβ[x_g(u−u₀)+y_g(v−v₀)]}

        u=sinθcosφ，v=sinθsinφ；u₀=sinθ₀cosφ₀，v₀=sinθ₀sinφ₀（波束扫描导向）

    计划011：幅值与相位两视图分离——幅值视图只取单元 dB（不消费单元相位），
    平滑无干涉尖刺；相位视图用单元复数直加取辐角，完整保留干涉结构。
    两视图均不含 ECP_Phase_deg 的标量加减（° 列仅 deg2rad 进入复数）。
    导向项使 (θ₀,φ₀) 处 25 单元同相叠加 → 主瓣平移至 (θ₀,φ₀)；
    steer_theta_deg=0 且 steer_phi_deg=0 时退化为原法向合成（计划006 原式）。

    ecp_dfs     单元 ECP DataFrame 列表（单元数任意，由输入决定，可拓展规模）
    positions_m (n, 2) 米制单元位置（x_g, y_g），下标与 ecp_dfs 一一对应
    steer_theta_deg / steer_phi_deg  导向目标方向（默认参数区 20°/0°）
    返回 (theta_deg, phi_deg, amp_total 线性幅值, E_total 复数)。

    网格以首份文件为准，其余单元必须键一致（fail-loud，不按行号对齐）。
    """
    n = len(ecp_dfs)
    if len(positions_m) != n:
        raise ValueError(f"单元 ECP 数 {n} 与位置数 {len(positions_m)} 不一致")

    # 网格基准：首份文件；用 (Theta, Phi) 键校验其余文件，防行序不一致静默错位
    base = ecp_dfs[0]
    grid_keys = list(zip(base["Theta[deg]"].values, base["Phi[deg]"].values))
    for idx, df in enumerate(ecp_dfs[1:], start=2):
        keys = list(zip(df["Theta[deg]"].values, df["Phi[deg]"].values))
        if keys != grid_keys:
            raise ValueError(f"单元 {idx} 的 (Theta,Phi) 网格与单元 1 不一致，禁止按行号叠加")

    theta_deg = base["Theta[deg]"].values
    phi_deg = base["Phi[deg]"].values
    theta_rad = np.deg2rad(theta_deg)
    phi_rad = np.deg2rad(phi_deg)
    u = np.sin(theta_rad) * np.cos(phi_rad)
    v = np.sin(theta_rad) * np.sin(phi_rad)
    # 导向目标方向 (θ₀,φ₀)（计划008）
    theta0_rad = np.deg2rad(steer_theta_deg)
    phi0_rad = np.deg2rad(steer_phi_deg)
    u0 = np.sin(theta0_rad) * np.cos(phi0_rad)
    v0 = np.sin(theta0_rad) * np.sin(phi0_rad)
    beta = 2 * np.pi * freq / C_LIGHT

    amp_total = np.zeros(len(theta_deg))          # 幅值视图：线性幅值逐点直加
    E_total = np.zeros(len(theta_deg), dtype=complex)  # 相位视图：复数直加
    for g in range(n):
        amp_g = 10 ** (ecp_dfs[g]["ECP_dB"].values / 20)   # 只用 dB，不消费相位
        amp_total += amp_g
        E_total += _restore_complex(ecp_dfs[g]) * np.exp(
            1j * beta * (positions_m[g, 0] * (u - u0) + positions_m[g, 1] * (v - v0))
        )
    return theta_deg, phi_deg, amp_total, E_total


def total_to_df(theta_deg, phi_deg, amp_total, e_total):
    """视图分离转 4 列 ECP DataFrame（计划011）：ECP_dB 取幅值视图，
    ECP_Phase_deg 取复数视图的辐角；列名与单元文件一致，可复用全部切面/绘图函数。"""
    return pd.DataFrame({
        "Phi[deg]": phi_deg,
        "Theta[deg]": theta_deg,
        "ECP_dB": 20 * np.log10(amp_total + 1e-10),
        "ECP_Phase_deg": np.angle(e_total, deg=True),
    })


def compute_total_error(real_total, pred_total, cut_phi_list=ecp_plot.CUT_PHI_LIST,
                        theta_max=ecp_plot.THETA_CUT_MAX):
    """三切面误差指标（口径对齐 main.py 第 9 段第二层），返回逐切面记录列表。

    指标：幅度 dB RMSE/MAE、幅度相关系数、相位（对齐后卷绕）RMSE/MAE、
    复数相对误差；相位对齐用计划004 同式（真实幅值峰值处）。
    计划011 视图分离提示：DataFrame 中 ECP_dB 来自幅值视图（Σ 直加）、
    ECP_Phase_deg 来自相位视图（复数直加 arg），二者已非同一复数的
    一致极坐标表示；因此 rel_l2 为"混义"综合参考指标（幅差+相位差的
    拼合），非严格复数场误差，解读时与 amp/phase 两行指标对照使用。
    """
    records = []
    for cut_phi in cut_phi_list:
        sub_r = ecp_plot.extract_cut(real_total, cut_phi, theta_max)
        sub_p = ecp_plot.extract_cut(pred_total, cut_phi, theta_max)
        theta = sub_r["Theta[deg]"].values
        if not np.allclose(theta, sub_p["Theta[deg]"].values):
            raise ValueError(f"切面 φ={cut_phi}°：预测/真实 θ 序列不一致")

        real_dB = sub_r["ECP_dB"].values
        pred_dB = sub_p["ECP_dB"].values
        real_phase = sub_r["ECP_Phase_deg"].values
        pred_phase = sub_p["ECP_Phase_deg"].values
        # 相位对齐参考：真实幅值峰值处。argmax(real_amp) 与 argmax(real_dB) 同点
        # （10^(x/20) 严格单调），与 plot_ecp_compare_10.plot_sample 计划009 写法等价
        real_amp = 10 ** (real_dB / 20)

        theta_ref = float(theta[np.argmax(real_amp)])
        pred_aligned, offset, theta_ref_used = ecp_plot.align_phase(
            real_phase, pred_phase, theta, theta_ref)

        real_w = (real_phase + 180.0) % 360.0 - 180.0
        pred_w = (pred_aligned + 180.0) % 360.0 - 180.0

        real_c = _restore_complex(sub_r)
        pred_c = _restore_complex(sub_p)
        rel_l2 = float(np.linalg.norm(pred_c - real_c) / np.linalg.norm(real_c))
        # 幅度相关系数：线性幅值口径（与 main.py 第 9 段 corr_amp 一致）
        corr = float(np.corrcoef(np.abs(pred_c), np.abs(real_c))[0, 1])

        records.append({
            "cut_phi_deg": int(cut_phi),
            "amp_rmse_dB": float(np.sqrt(np.mean((pred_dB - real_dB) ** 2))),
            "amp_mae_dB": float(np.mean(np.abs(pred_dB - real_dB))),
            "corr_amp": corr,
            "phase_rmse_deg": float(np.sqrt(np.mean((pred_w - real_w) ** 2))),
            "phase_mae_deg": float(np.mean(np.abs(pred_w - real_w))),
            "rel_l2": rel_l2,
            "align_theta_deg": theta_ref_used,
            "phase_offset_deg": offset,
        })
    return records


def plot_total(real_total, pred_total, out_png_path,
               steer_theta_deg=STEER_THETA_DEG, steer_phi_deg=STEER_PHI_DEG):
    """合成总图对比：2×3（上行幅值 dB/下行相位卷绕+对齐 × φ=0/44/90），样式与计划004 一致。

    计划008：上行幅值轴改 dB（直接画 ECP_dB 列，不再还原线性）；
    相位对齐参考仍取真实幅值峰值处（dB 与线性单调同序，argmax 同点）。
    计划009：导向角经参数传入（默认参数区 STEER_*），suptitle 读传入值——
    非默认导向时标题与实际一致（008 审查遗留 P3 顺手解决）。
    复用 ecp_plot.extract_cut / align_phase / 颜色与坐标轴口径；返回对齐记录列表。
    """
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    align_records = []

    for col, cut_phi in enumerate(ecp_plot.CUT_PHI_LIST):
        sub_p = ecp_plot.extract_cut(pred_total, cut_phi)
        sub_r = ecp_plot.extract_cut(real_total, cut_phi)
        theta = sub_p["Theta[deg]"].values
        if not np.allclose(theta, sub_r["Theta[deg]"].values):
            raise ValueError(f"总图切面 φ={cut_phi}°：预测/真实 θ 序列不一致")

        real_dB = sub_r["ECP_dB"].values
        pred_dB = sub_p["ECP_dB"].values
        real_phase = sub_r["ECP_Phase_deg"].values
        pred_phase = sub_p["ECP_Phase_deg"].values

        # 上行：幅值（dB 直接为纵轴，计划008；不再 10^(dB/20) 还原线性）
        ax_amp = axes[0, col]
        ax_amp.plot(theta, real_dB, color=REAL_COLOR, linewidth=1.6, label="真实")
        ax_amp.plot(theta, pred_dB, color=PRED_COLOR, linewidth=1.6, label="预测")
        ax_amp.set_title(f"φ = {cut_phi}°")
        ax_amp.set_xlabel("θ (°)")
        ax_amp.set_ylabel("幅值 (dB)")
        ax_amp.xaxis.set_major_locator(
            ecp_plot.MultipleLocator(15))
        ax_amp.yaxis.set_major_locator(ecp_plot.MaxNLocator(nbins=6))
        ax_amp.grid(True, alpha=0.3)
        ax_amp.legend(loc="best", fontsize=9)

        # 下行：相位（卷绕 + 真实幅值峰值处对齐），与计划004 同式
        theta_ref_deg = float(theta[np.argmax(real_dB)])
        pred_aligned, offset, theta_ref = ecp_plot.align_phase(
            real_phase, pred_phase, theta, theta_ref_deg)
        real_w = (real_phase + 180.0) % 360.0 - 180.0
        pred_w = (pred_aligned + 180.0) % 360.0 - 180.0

        ax_ph = axes[1, col]
        ax_ph.plot(theta, real_w, color=REAL_COLOR, linewidth=1.6, label="真实")
        ax_ph.plot(theta, pred_w, color=PRED_COLOR, linewidth=1.6, label="预测（已对齐）")
        ax_ph.axvline(theta_ref, color="gray", linestyle="--", linewidth=1.0)
        ax_ph.annotate(f"对齐参考 θ={theta_ref:.0f}°\noffset={offset:+.1f}°",
                       xy=(theta_ref, ax_ph.get_ylim()[1]), xytext=(0.05, 0.95),
                       textcoords="axes fraction", va="top", fontsize=8, color="gray")
        ax_ph.set_title(f"φ = {cut_phi}°")
        ax_ph.set_xlabel("θ (°)")
        ax_ph.set_ylabel("相位 (°)")
        ax_ph.xaxis.set_major_locator(ecp_plot.MultipleLocator(15))
        ax_ph.yaxis.set_major_locator(ecp_plot.MultipleLocator(45))
        ax_ph.grid(True, alpha=0.3)
        ax_ph.legend(loc="best", fontsize=9)

        align_records.append(["total", int(cut_phi), theta_ref, offset])

    fig.suptitle("合阵总方向图：预测 vs 真实（红=真实 蓝=预测，25 单元叠加，"
                 f"波束导向 θ={steer_theta_deg}°/φ={steer_phi_deg}°）", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return align_records


def main(steer_theta_deg=STEER_THETA_DEG, steer_phi_deg=STEER_PHI_DEG):
    """加载 25+25 份单元 ECP 与位置表 → 合成两侧总场（导向默认 θ₀=20°/φ₀=0°，
    计划008；计划009 可经参数显式传入——main.py 全局变量 STEER_* 注入入口，
    0/0 退化法向合成）→ 落盘/绘图/误差汇总。"""
    os.makedirs(PLOT_DIR, exist_ok=True)

    positions_m = load_position_table(POSITION_CSV, n_units=N_UNITS)

    print("加载实测单元 ECP ...")
    real_ecps = load_element_ecps(REAL_DIR, "ECP_test_real_{g}.csv", n_units=N_UNITS)
    print("加载预测单元 ECP ...")
    pred_ecps = load_element_ecps(PRED_DIR, "3_ecp_{g}.txt", n_units=N_UNITS)

    print("合成实测总方向图 ...")
    theta_r, phi_r, amp_r, E_real = synthesis_total_field(
        real_ecps, positions_m,
        steer_theta_deg=steer_theta_deg, steer_phi_deg=steer_phi_deg)
    print("合成预测总方向图 ...")
    theta_p, phi_p, amp_p, E_pred = synthesis_total_field(
        pred_ecps, positions_m,
        steer_theta_deg=steer_theta_deg, steer_phi_deg=steer_phi_deg)
    if not (np.allclose(theta_r, theta_p) and np.allclose(phi_r, phi_p)):
        raise ValueError("实测/预测合成总场网格不一致")

    real_total = total_to_df(theta_r, phi_r, amp_r, E_real)
    pred_total = total_to_df(theta_p, phi_p, amp_p, E_pred)
    real_total.to_csv(REAL_TOTAL_CSV, index=False, float_format="%.6f")
    pred_total.to_csv(PRED_TOTAL_CSV, index=False, float_format="%.6f")
    print(f"✅ 实测总场已存：{REAL_TOTAL_CSV}")
    print(f"✅ 预测总场已存：{PRED_TOTAL_CSV}")

    out_png = os.path.join(PLOT_DIR, "total_array_ecp_compare.png")
    align_records = plot_total(real_total, pred_total, out_png,
                               steer_theta_deg=steer_theta_deg,
                               steer_phi_deg=steer_phi_deg)
    print(f"✅ 对比图已保存：{out_png}")

    df_align = pd.DataFrame(align_records, columns=["sample_id", "cut_phi_deg",
                                                    "align_theta_deg", "phase_offset_deg"])
    df_align.to_csv(ALIGN_CSV, index=False, float_format="%.6f")
    print(f"✅ 相位对齐差值已保存：{ALIGN_CSV}")

    records = compute_total_error(real_total, pred_total)
    df_err = pd.DataFrame(records)
    df_err.to_csv(ERROR_CSV, index=False, float_format="%.6f")
    print("\n合阵总方向图三切面误差：")
    print(df_err.to_string(index=False))
    print(f"✅ 误差汇总已保存：{ERROR_CSV}")


if __name__ == "__main__":
    main()

