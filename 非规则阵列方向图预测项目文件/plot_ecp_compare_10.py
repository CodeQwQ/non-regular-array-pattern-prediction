# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/plot_ecp_compare_10.py
# 目的：单元 ECP 预测与真实结果对比绘图
# 输入：预测/真实 ECP 文件
# 输出：PNG 图表、相位对齐和误差文件
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

# 文件摘要：ECP 预测值与真实值对比绘图模块（计划 004；计划 009 增补幅值轴 dB 双输出）。
#          纯文件驱动：读第 7 段预测 ECP（ecp_output_2/3_ecp_{s}.txt）与第 8 段真实
#          ECP（test_ecp_real/ECP_test_real_{s}.csv），对全部 25 个测试样本每样本
#          输出 2 张 PNG（2 行 × 3 列，16:9，同数据同版式）：上行幅值轴两种口径——
#          "linear" = dB 还原线性（落 plots/，计划004 原行为）、"dB" = 直接画 ECP_dB
#          列（落 plot_db/，计划009，与计划008 合阵图同口径）；下行均 = 相位
#          （degree，已做相位对齐）；3 列对应 3 个半球切面 φ=0°/44°/90°，每切面
#          θ ∈ [0°, 90°] 步长 2°（46 点）。真实曲线红色、预测曲线蓝色。
#          相位对齐：取该切面真实幅值峰值处（argmax real_dB；dB 与线性单调同序、
#          argmax 同点，计划009 统一口径）的 θ 作参考，offset = 真实相位 − 预测
#          相位（卷绕到 [-180,180)），给预测曲线所有点加上该 offset；两口径对齐
#          构造性恒等，对齐差值汇总写一份 phase_align_offset.csv。
#          依赖 matplotlib（Agg 后端只存图不弹窗）；可独立运行（python 本文件）。
# 类/函数清单：
#   - load_ecp(path)：读单个 ECP 文件（.txt/.csv 自适应），返回含 Phi/Theta/ECP_dB/ECP_Phase_deg 的 DataFrame
#   - extract_cut(df, cut_phi, theta_max)：按 φ 精确匹配 + θ ≤ theta_max 取行并按 θ 升序，
#     断言点数由 theta_max 推导（90→46 点原行为；180→91 点，计划007）且步长 2°
#   - align_phase(real_phase_deg, pred_phase_deg, theta_deg, theta_ref_deg)：算 offset（卷绕）并对预测相位整体加偏移，返回 (pred_aligned, offset, theta_ref)
#   - plot_sample(sample_id, pred_df, real_df, out_png_path, amp_axis="linear")：
#     生成某样本的 2×3 子图并保存，返回该样本 3 个切面的对齐记录；amp_axis 双口径
#     ——"linear" 幅值轴线性还原（原行为）/"dB" 幅值轴直接画 ECP_dB（计划009），
#     suptitle 相应标注
#   - main()：遍历 1..25 逐样本双输出（线性 → plots/ + dB → plot_db/）并汇总
#     对齐差值 CSV，打印进度与输出路径
import os

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")  # 服务器无显示环境：只存 PNG，不弹窗
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, MaxNLocator

# 中文字体回退链（缺字体时退化为方框但不报错）
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DengXian", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ------------------------------ 参数区 ------------------------------
BASE_PATH = r"E:/c50066007/pythonML_mianzhen_random"
PRED_DIR = os.path.join(BASE_PATH, "ecp_output_2")          # 预测 ECP（3_ecp_{s}.txt）
REAL_DIR = os.path.join(BASE_PATH, "test_ecp_real")         # 真实 ECP（ECP_test_real_{s}.csv）
EVAL_DIR = os.path.join(BASE_PATH, "test_ecp_comparison")   # 误差评估目录
PLOT_DIR = os.path.join(EVAL_DIR, "plots")                  # 图片输出目录（幅值轴线性）
PLOT_DB_DIR = os.path.join(EVAL_DIR, "plot_db")             # 幅值轴 dB 版图片目录（计划009，与 plots 同级）
ALIGN_CSV = os.path.join(EVAL_DIR, "phase_align_offset.csv")

CUT_PHI_LIST = [0, 44, 90]   # 3 个半球切面；45° 不在 2° 网格，取最近格点 44°
THETA_CUT_MAX = 90           # 切面 θ 上限（含）
THETA_STEP = 2               # 网格步长（度），用于断言
EXPECTED_CUT_POINTS = THETA_CUT_MAX // THETA_STEP + 1  # 46 点

N_SAMPLES = 25               # 测试样本数（第 7/8 段各落盘 1..25）
ALIGN_THETA_DEG = None       # 相位对齐参考 θ；None = 自动取该切面真实幅值峰值处

REAL_COLOR = "red"           # 真实曲线颜色
PRED_COLOR = "blue"          # 预测曲线颜色


def load_ecp(path):
    """读单个 ECP 文件，返回含 Phi[deg]/Theta[deg]/ECP_dB/ECP_Phase_deg 的 DataFrame。"""
    df = pd.read_csv(path)
    required = {"Phi[deg]", "Theta[deg]", "ECP_dB", "ECP_Phase_deg"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path} 缺少列 {sorted(missing)}，实际列：{list(df.columns)}")
    return df


def extract_cut(df, cut_phi, theta_max=THETA_CUT_MAX):
    """按 φ 精确匹配 + θ ≤ theta_max 取行并按 θ 升序排序。

    断言点数由 theta_max 推导（int(theta_max)//2 + 1，步长 2°），
    theta_max=90 时仍为 46 点（计划004 原行为，向后兼容）；
    theta_max=180 时为 91 点（计划007 全局切面用）。
    """
    expected_points = int(theta_max) // THETA_STEP + 1
    mask = np.isclose(df["Phi[deg]"].values, cut_phi) & \
           (df["Theta[deg]"].values <= theta_max + 1e-9)
    sub = df[mask].sort_values("Theta[deg]").reset_index(drop=True)
    theta = sub["Theta[deg]"].values
    if len(sub) != expected_points:
        raise ValueError(f"φ={cut_phi}° 切面取到 {len(sub)} 点，预期 {expected_points} 点")
    if not np.allclose(np.diff(theta), THETA_STEP):
        raise ValueError(f"φ={cut_phi}° 切面 θ 序列步长异常：{theta}")
    return sub


def align_phase(real_phase_deg, pred_phase_deg, theta_deg, theta_ref_deg):
    """相位对齐：offset = wrap(real(θ_ref) − pred(θ_ref))；返回 (pred_aligned, offset, theta_ref)。

    pred_aligned = 预测相位所有点 + offset（用户约定）。
    """
    idx = int(np.argmin(np.abs(theta_deg - theta_ref_deg)))
    theta_ref = float(theta_deg[idx])
    offset = float((real_phase_deg[idx] - pred_phase_deg[idx] + 180.0) % 360.0 - 180.0)
    pred_aligned = pred_phase_deg + offset
    return pred_aligned, offset, theta_ref


def plot_sample(sample_id, pred_df, real_df, out_png_path, amp_axis="linear"):
    """生成某样本的 2×3 子图（上行幅值/下行相位 degree × 3 个 φ 切面）并保存。

    amp_axis="linear"：上行幅值由 dB 还原线性 10^(dB/20)（计划004 原行为）；
    amp_axis="dB"：上行直接画 ECP_dB 列（计划009，与计划008 合阵图同口径），
    ylabel「幅值 (dB)」，suptitle 追加「（幅值轴 dB）」标注。
    返回该样本 3 个切面的对齐记录列表 [sample_id, cut_phi_deg, align_theta_deg, phase_offset_deg]。
    """
    if amp_axis not in ("linear", "dB"):
        raise ValueError(f"amp_axis 仅支持 'linear'/'dB'，实际：{amp_axis}")
    fig, axes = plt.subplots(2, 3, figsize=(16, 9))
    align_records = []

    for col, cut_phi in enumerate(CUT_PHI_LIST):
        sub_p = extract_cut(pred_df, cut_phi)
        sub_r = extract_cut(real_df, cut_phi)
        theta = sub_p["Theta[deg]"].values
        if not np.allclose(theta, sub_r["Theta[deg]"].values):
            raise ValueError(f"样本 {sample_id} 切面 φ={cut_phi}：预测/真实 θ 序列不一致")

        pred_dB = sub_p["ECP_dB"].values
        real_dB = sub_r["ECP_dB"].values
        pred_phase = sub_p["ECP_Phase_deg"].values
        real_phase = sub_r["ECP_Phase_deg"].values

        # ---------- 上行：幅值（amp_axis="linear" 还原线性 / "dB" 直接画 dB，计划009） ----------
        ax_amp = axes[0, col]
        if amp_axis == "dB":
            ax_amp.plot(theta, real_dB, color=REAL_COLOR, linewidth=1.6, label="真实")
            ax_amp.plot(theta, pred_dB, color=PRED_COLOR, linewidth=1.6, label="预测")
            ax_amp.set_ylabel("幅值 (dB)")
        else:
            real_amp = 10 ** (real_dB / 20)
            pred_amp = 10 ** (pred_dB / 20)
            ax_amp.plot(theta, real_amp, color=REAL_COLOR, linewidth=1.6, label="真实")
            ax_amp.plot(theta, pred_amp, color=PRED_COLOR, linewidth=1.6, label="预测")
            ax_amp.set_ylabel("幅值（线性，由 dB 还原）")
        ax_amp.set_title(f"φ = {cut_phi}°")
        ax_amp.set_xlabel("θ (°)")
        ax_amp.xaxis.set_major_locator(MultipleLocator(15))
        ax_amp.yaxis.set_major_locator(MaxNLocator(nbins=6))
        ax_amp.grid(True, alpha=0.3)
        ax_amp.legend(loc="best", fontsize=9)

        # ---------- 下行：相位（degree，先对齐再画） ----------
        theta_ref_deg = ALIGN_THETA_DEG
        if theta_ref_deg is None:
            # 真实幅值峰值处：dB 与线性单调同序，argmax(real_dB) 与原 argmax(real_amp)
            # 同一点（计划009 统一口径，两种 amp_axis 共用同一对齐参考）
            theta_ref_deg = float(theta[np.argmax(real_dB)])
        pred_aligned, offset, theta_ref = align_phase(real_phase, pred_phase, theta, theta_ref_deg)

        # 卷绕相位（不 unwrap）：直接画到 [-180,180)，与第 9 段数值口径一致，
        # 避免深零点处 unwrap 累积跳变产生虚假大偏差（±180° 处竖直跳变连线属正常）
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
        ax_ph.xaxis.set_major_locator(MultipleLocator(15))
        ax_ph.yaxis.set_major_locator(MultipleLocator(45))
        ax_ph.grid(True, alpha=0.3)
        ax_ph.legend(loc="best", fontsize=9)

        align_records.append([sample_id, int(cut_phi), theta_ref, offset])

    axis_tag = "（幅值轴 dB）" if amp_axis == "dB" else ""
    fig.suptitle(f"样本 {sample_id}：ECP 预测 vs 真实（红=真实 蓝=预测）{axis_tag}", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out_png_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return align_records


def main():
    """遍历 1..N_SAMPLES 逐样本读预测/真实 ECP → 每样本双输出（线性 plots/ +
    dB plot_db/，同数据同版式）→ 汇总相位对齐差值 CSV（两口径对齐构造性恒等，
    只写一份）。"""
    os.makedirs(PLOT_DIR, exist_ok=True)
    os.makedirs(PLOT_DB_DIR, exist_ok=True)
    all_align = []

    for s in range(1, N_SAMPLES + 1):
        pred_path = os.path.join(PRED_DIR, f"3_ecp_{s}.txt")
        real_path = os.path.join(REAL_DIR, f"ECP_test_real_{s}.csv")
        if not os.path.exists(pred_path):
            raise FileNotFoundError(f"预测 ECP 不存在：{pred_path}")
        if not os.path.exists(real_path):
            raise FileNotFoundError(f"真实 ECP 不存在：{real_path}")

        pred_df = load_ecp(pred_path)
        real_df = load_ecp(real_path)
        out_png_lin = os.path.join(PLOT_DIR, f"sample_{s:02d}_ecp_compare.png")
        all_align.extend(plot_sample(s, pred_df, real_df, out_png_lin, amp_axis="linear"))
        out_png_db = os.path.join(PLOT_DB_DIR, f"sample_{s:02d}_ecp_compare.png")
        plot_sample(s, pred_df, real_df, out_png_db, amp_axis="dB")
        print(f"[{s}/{N_SAMPLES}] 已保存：{out_png_lin}")
        print(f"{' ' * len(f'[{s}/{N_SAMPLES}] ')}          + {out_png_db}")

    df_align = pd.DataFrame(all_align, columns=["sample_id", "cut_phi_deg",
                                                "align_theta_deg", "phase_offset_deg"])
    df_align.to_csv(ALIGN_CSV, index=False, float_format="%.6f")
    print(f"\n✅ 全部完成！共 {N_SAMPLES}×2 张图（线性 → {PLOT_DIR}，dB → {PLOT_DB_DIR}）")
    print(f"✅ 相位对齐差值已保存：{ALIGN_CSV}")


if __name__ == "__main__":
    main()

