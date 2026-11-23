# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/A_test_5.py
# 目的：测试阵列采集、合并和相位对齐脚本
# 输入：测试阵列参数、HFSS 工程和导出文件
# 输出：测试特征、位置表、合并幅相数据
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

# 文件摘要：测试数据生成与处理脚本。生成 5×5 阵列（25 单元，首点固定(0,0)，其余
#          随机撒点），计算与训练集同格式的 8 方位特征，驱动 HFSS 完整仿真并导出
#          方向图；另提供幅度/相位数据合并与相位对齐等后处理工具。
#          注意：模块级即实例化 HFSS()，导入本文件就会尝试连接 HFSS。
# 类/函数清单：
#   generate_test_antenna_array —— 生成 5×5 测试阵列坐标（逻辑对齐训练集）
#   calc_distance               —— 计算两点欧几里得距离
#   get_grid_direction          —— 格子索引差映射 8 方位编号(1~8)，非相邻返回 None
#   calculate_test_features     —— 单元 8 方位最近邻距离倒数特征（对齐训练集）
#   save_test_features_to_csv   —— 特征存 test_data/test_features_iter_N.csv
#                                   （25 行 × 8 列，表头与训练集一致）
#   save_antenna_position_to_csv —— 单元绝对位置存 CSV（unit_id/abs_x/abs_y）
#   run_test                    —— 单次测试主流程（默认 test_iteration=999，
#                                   导出 train999_ 前缀避免覆盖训练原始数据；
#                                   HFSS 报告用 test_amp/test_rE 前缀与训练隔离）：
#                                   生成阵列 → 存位置 → 算特征 →
#                                   按 5×5 方案②重设 ground/sub 底板位置+尺寸
#                                   （位置-2.5*xcell，尺寸外延2单元）→
#                                   驱动 HFSS 布尔/端口/仿真/四类方向图导出
#   merge_test_amp_data         —— 合并测试特征与幅度方向图（特征按单元复制 91 行），
#                                   输出 merged_test_amp_data.csv
#   merge_test_phase_data       —— 合并测试特征与相位数据 → merged_test_phase_data.csv
#   align_phase_data            —— 相位对齐：每个 theta 周期内相位减去该周期
#                                   theta=0° 处的相位值
#   __main__                    —— run_test → 合并幅度/相位 → 相位对齐
import random
import csv
import os
import pandas as pd
import glob
import re
import math
from hfss import HFSS  # 实际使用的HFSS类导入，不再模拟

# 模块级初始化：导入本文件时会立即尝试连接 HFSS。
hfss = HFSS()

# ========== 核心参数设定（对齐训练集：5×5阵列） ==========
FEATURE_SCALAR = 12  # 特征缩放系数（与训练集一致）
GRID_ROWS = 5  # 固定5行格子（对齐训练集）
GRID_COLS = 5  # 固定5列格子（对齐训练集）
CELL_SIDE = 80 # 格子边长（对齐训练集）
CELL_STEP = 400  # 格子步长（对齐训练集）
TOTAL_UNITS = GRID_ROWS * GRID_COLS  # 固定25个单元（对齐训练集）
BOARD_POS_X = "-2.5*xcell"      # 底板 ground/sub 的 XPosition（左外延2单元对称，计划005方案②）
BOARD_POS_Y = "-2.5*ycell"      # 底板 ground/sub 的 YPosition（同上）
BOARD_XSIZE = "xcell1+1580mil"  # 底板 ground/sub 的 XSize（5×5 阵列体外延2单元，计划005方案②）
BOARD_YSIZE = "ycell1+1580mil"  # 底板 ground/sub 的 YSize（5×5 阵列体外延2单元，计划005方案②）


# ========== 核心修改：生成5×5天线阵列（对齐训练集逻辑） ==========
def generate_test_antenna_array():
    """
    生成测试用5×5天线阵列：第一个点固定为(0,0)，其余点在格子内随机撒点
    （完全对齐训练集的generate_5x5_antenna_array逻辑）
    返回:
        array: 天线阵列坐标列表（展平的一维列表，每个元素为(x, y, i, j)）
        grid_info: 格子信息（与antenna_array一致，保持参数兼容）
    """
    point_list = []  # 存储所有点的坐标 (x, y, i, j)
    first_point = True  # 标记是否是第一个点

    for i in range(GRID_ROWS):  # i：行索引，控制x轴（向下）
        for j in range(GRID_COLS):  # j：列索引，控制y轴（向右）
            if first_point:
                # 第一个点固定为(0, 0)
                x_random = 0.0
                y_random = 0.0
                first_point = False
            else:
                # 计算当前格子的左上角坐标（与训练集逻辑一致）
                x_start = i * CELL_STEP
                y_start = j * CELL_STEP
                # 在格子内随机生成点
                x_random = random.uniform(x_start, x_start + CELL_SIDE)
                y_random = random.uniform(y_start, y_start + CELL_SIDE)
            point_list.append((x_random, y_random, i, j))

    # 返回坐标列表（包含行列信息）
    return point_list, point_list  # 第二个返回值保持与原代码兼容


# ========== 核心修改：基于格子方位计算8个特征（对齐训练集逻辑） ==========
def calc_distance(p1, p2):
    """计算两点欧几里得距离（与训练集完全一致）"""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def get_grid_direction(center_grid, neighbor_grid):
    """
    基于格子索引判断方位（8个方位，完全对齐训练集逻辑）
    center_grid: (i0,j0) 中心单元的格子索引
    neighbor_grid: (i1,j1) 邻居单元的格子索引
    返回：1-8（对应右、右上、上、左上、左、左下、下、右下），无则返回None
    """
    i0, j0 = center_grid
    i1, j1 = neighbor_grid
    delta_i = i1 - i0
    delta_j = j1 - j0

    # 8个格子方位的索引差映射（与训练集完全一致）
    direction_map = {
        (0, 1): 1,    # 右：同列，右一列
        (-1, 1): 2,   # 右上：上一行，右一列
        (-1, 0): 3,   # 上：上一行，同列
        (-1, -1): 4,  # 左上：上一行，左一列
        (0, -1): 5,   # 左：同列，左一列
        (1, -1): 6,   # 左下：下一行，左一列
        (1, 0): 7,    # 下：下一行，同列
        (1, 1): 8     # 右下：下一行，右一列
    }
    return direction_map.get((delta_i, delta_j), None)


def calculate_test_features(antenna_array, grid_info, unit_idx):
    """
    计算测试用的天线单元特征（完全对齐训练集：8个格子方位的距离倒数特征）
    参数:
        antenna_array: 天线阵列坐标列表（一维，(x, y, i, j)）
        grid_info: 格子信息列表（与antenna_array一致，保持参数兼容）
        unit_idx: 单元索引（从0开始）
    返回:
        features: 包含8个特征的列表（对应8个方位，无邻居则为0）
    """
    center_unit = antenna_array[unit_idx]
    center_grid = (center_unit[2], center_unit[3])  # (i0,j0)

    # 初始化8个方位的最近距离（与训练集一致）
    min_dist_dict = {1: float('inf'), 2: float('inf'), 3: float('inf'), 4: float('inf'),
                     5: float('inf'), 6: float('inf'), 7: float('inf'), 8: float('inf')}

    # 遍历所有邻居单元
    for idx, neighbor_unit in enumerate(antenna_array):
        if idx == unit_idx:  # 跳过自身
            continue
        neighbor_grid = (neighbor_unit[2], neighbor_unit[3])  # (i1,j1)
        direction = get_grid_direction(center_grid, neighbor_grid)
        if direction is None:  # 非8个目标方位的格子，跳过
            continue
        # 计算距离并更新该方位的最近距离
        dist = calc_distance(center_unit, neighbor_unit)
        if dist < min_dist_dict[direction]:
            min_dist_dict[direction] = dist

    # 生成8个特征（严格按训练集顺序：右、右上、上、左上、左、左下、下、右下）
    features = []
    for dir_num in [1, 2, 3, 4, 5, 6, 7, 8]:
        min_dist = min_dist_dict[dir_num]
        if min_dist != float('inf'):
            feature = (1 / min_dist) * FEATURE_SCALAR
            features.append(round(feature, 6))
        else:
            features.append(0.0)

    return features


# ========== 核心修改：保存8个特征（对齐训练集格式：25行8列） ==========
def save_test_features_to_csv(features_data, test_id=1):
    """
    保存测试用的特征数据到CSV文件（完全对齐训练集格式）
    参数:
        features_data: 包含所有单元特征的列表（25行×8列）
        test_id: 测试编号，默认为1
    """
    # 保存路径（与训练集同目录，区分文件名）
    save_dir = "E:/c50066007/pythonML_mianzhen_random/test_data/"
    os.makedirs(save_dir, exist_ok=True)
    filename = os.path.join(save_dir, f"test_features_iter_{test_id}.csv")

    # 列标题（与训练集完全一致）
    headers = [
        "right", "right_up", "up", "left_up",
        "left", "left_down", "down", "right_down"
    ]

    # 写入CSV（严格25行8列，与训练集格式一致）
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)  # 写入标题行
        writer.writerows(features_data)  # 写入25行特征数据

    print(f"✅ 测试{test_id}：特征数据已保存（25行×8列）→ {filename}")


# ========== 保留原有功能函数（完全不修改） ==========
def save_antenna_position_to_csv(antenna_array, save_path):
    """
    保存天线单元的绝对位置和累加值到CSV文件
    参数:
        antenna_array: 天线阵列坐标列表（一维，(x, y, i, j)）
        save_path: 保存文件的路径
    """
    # 初始化累加值
    x_accum = 0.0
    y_accum = 0.0
    position_data = []
    # 定义列标题
    headers = ["unit_id", "abs_x", "abs_y"]

    for unit_id, (x, y, i, j) in enumerate(antenna_array, 1):
        # 累加当前位置的x、y值
        x_accum += x
        y_accum += y
        # 存储数据：单元编号、绝对x、绝对y、累加x、累加y
        position_data.append([
            unit_id,
            round(x, 6),
            round(y, 6),
        ])

    # 确保保存目录存在
    os.makedirs(os.path.dirname(save_path), exist_ok=True)

    # 写入CSV文件
    with open(save_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        writer.writerows(position_data)

    print(f"天线位置数据（绝对位置+累加值）已保存到: {save_path}")


def run_test(test_iteration=999):
    """
    运行单次测试的主函数（适配5×5阵列和8特征逻辑）
    test_iteration 默认 999：hfss 导出文件名含 train{iteration} 前缀，
    用 999 与训练数据 train1~30 隔离，避免覆盖训练原始数据
    """
    n = TOTAL_UNITS  # 25个单元

    print("=== 开始单次测试（5×5阵列）===\n")

    # 生成5×5天线阵列（对齐训练集）
    print("生成5×5天线阵列（第一个点固定为(0,0)，其余随机撒点）：")
    antenna_array, grid_info = generate_test_antenna_array()
    # 打印阵列坐标
    for idx, (x, y, i, j) in enumerate(antenna_array, 1):
        print(f"单元{idx} → 行{i} 列{j} → 坐标(x：{x:.2f}，y：{y:.2f})")

    # 保存天线位置数据
    position_save_path = f"E:/c50066007/pythonML_mianzhen_random/antenna_position_data.csv"
    save_antenna_position_to_csv(antenna_array, position_save_path)

    # 计算每个单元的8个特征（对齐训练集）
    print("\n计算特征数据（8个格子方位特征）：")
    features_data = []
    unit_id = 1

    for unit_idx in range(len(antenna_array)):
        x, y, i, j = antenna_array[unit_idx]
        features = calculate_test_features(antenna_array, grid_info, unit_idx)

        # 构建数据行：8个方位特征
        data_row = features
        features_data.append(data_row)

        print(f"  单元{unit_id} ({x:.2f},{y:.2f}) → 方位特征：{features}")
        unit_id += 1

    # 保存特征到CSV（对齐训练集格式）
    save_test_features_to_csv(features_data, test_id=test_iteration)

    # 执行HFSS仿真操作（适配25个单元）
    print("\n执行HFSS仿真操作：")
    command_count = 0
    relative_cs_count = 71

    for x, y, i, j in antenna_array:
        command_count += 1

        # 移动天线单元：第一个点是(0,0)，跳过移动
        if x != 0 or y != 0:
            hfss.move(col_distance=x, row_distance=y)
            pass

            # 建立坐标系
        hfss.move_xyz(col_pos=x, row_pos=y, relative_cs_count=relative_cs_count)
        relative_cs_count += 1

    # 执行 HFSS 建模与仿真（适配 25 个单元）。
    hfss.set_board_size(BOARD_POS_X, BOARD_POS_Y, BOARD_XSIZE, BOARD_YSIZE)  # 按5×5方案②重设 ground/sub 位置+尺寸（计划005）
    hfss.Box60(BOARD_POS_X, BOARD_POS_Y, BOARD_XSIZE, BOARD_YSIZE)  # Box60 与 ground/sub 统一 X/Y（存在先删，Z 不变；计划005）
    hfss.Box60_Box61(GRID_ROWS)
    hfss.kuidian(n=n)
    hfss.run()
    hfss.source_context(n=n)
    # 测试侧 HFSS 报告使用独立前缀（test_amp Plot / test_rE Plot），与训练残留报告隔离；
    # CSV 文件名仍为 train999_ 前缀不变（计划003）
    hfss.phase_theta_cycle(iteration=test_iteration, n=TOTAL_UNITS, report_prefix="test_rE Plot")
    hfss.phase_phi_cycle(iteration=test_iteration, n=TOTAL_UNITS, report_prefix="test_rE Plot")
    #
    # hfss.amp_cycle(iteration=iteration, n=TOTAL_UNITS)
    hfss.amp_theta_cycle(iteration=test_iteration, n=TOTAL_UNITS, report_prefix="test_amp Plot")
    hfss.amp_phi_cycle(iteration=test_iteration, n=TOTAL_UNITS, report_prefix="test_amp Plot")
    #hfss.all_directivity(n=0)
    #hfss.delete()

    # 合并测试数据（注释保留）
    print("\n合并测试数据：")
    #merge_iteration_data(iteration=test_iteration)

    print("\n=== 单次测试完成 ===")


def merge_test_amp_data(base_path="E:/c50066007/pythonML_mianzhen_random/"):
    """
    合并测试数据：test_features.csv 和 Directivity Plot test1_real.csv ~ test9_real.csv
    参数:
        base_path: 文件基础路径
    """
    # 定义文件路径（适配新的测试特征文件名）
    features_file = os.path.join(base_path, "test_data/test_features_iter_1.csv")
    directivity_pattern = os.path.join(base_path, "Directivity Plot test*_real.csv")

    # 读取特征数据
    try:
        features_df = pd.read_csv(features_file)
        print(f"成功读取测试特征文件: {features_file}")
        print(f"特征数据包含{len(features_df)}个单元的特征")
    except FileNotFoundError:
        print(f"测试特征文件不存在: {features_file}")
        return None

    # 查找所有对应的方向图文件
    directivity_files = glob.glob(directivity_pattern)
    if len(directivity_files) != TOTAL_UNITS:  # 适配25个单元
        print(f"警告：找到{len(directivity_files)}个测试方向图文件（预期25个）")

    # 按单元编号排序文件（使用正则表达式提取test后的数字）
    def extract_test_number(file_path):
        """从文件名中提取test后面的数字"""
        match = re.search(r'test(\d+)_real', file_path)
        if match:
            return int(match.group(1))
        return 0

    # 按test编号排序
    directivity_files.sort(key=extract_test_number)

    # 显示找到的文件及其编号
    print("\n找到的方向图文件：")
    for file_path in directivity_files:
        test_num = extract_test_number(file_path)
        print(f"  test{test_num}: {os.path.basename(file_path)}")

    # 存储合并结果
    merged_data = []

    # 逐个单元处理（按test编号匹配）
    for i, file_path in enumerate(directivity_files):
        unit_index = i  # 特征数据按行索引对应单元1-25（索引0-24）

        # 检查索引是否有效
        if unit_index >= len(features_df):
            print(f"    警告：特征数据中没有单元{i + 1}的数据")
            continue

        # 读取方向图数据
        try:
            dir_df = pd.read_csv(file_path)
            test_num = extract_test_number(file_path)
            print(f"  读取test{test_num} (单元{i + 1})方向图数据: {os.path.basename(file_path)}")

            # 验证数据行数
            if len(dir_df) != 91:
                print(f"    警告：test{test_num}方向图数据有{len(dir_df)}行（预期91行）")
        except Exception as e:
            print(f"    读取方向图文件失败: {e}")
            continue

        # 获取对应单元的特征数据（按行索引）
        unit_features = features_df.iloc[[unit_index]]

        # 将特征数据复制91次（与方向图数据行数匹配）
        features_repeated = pd.concat([unit_features] * len(dir_df), ignore_index=True)

        # 合并特征数据和方向图数据
        unit_merged = pd.concat([features_repeated, dir_df], axis=1)
        merged_data.append(unit_merged)

    # 合并所有单元的数据
    if merged_data:
        final_merged = pd.concat(merged_data, ignore_index=True)

        # 保存结果
        output_file = os.path.join(base_path, "merged_test_amp_data.csv")
        final_merged.to_csv(output_file, index=False, float_format='%.6f')
        print(f"\n测试数据合并完成！结果保存到: {output_file}")
        print(f"总数据行数: {len(final_merged)}")

        return output_file
    else:
        print("没有测试数据被合并")
        return None


def merge_test_phase_data(base_path="E:/c50066007/pythonML_mianzhen_random/"):
    """
    合并测试数据：test_features.csv 和 Phase Plot test1_real.csv ~ test9_real.csv
    参数:
        base_path: 文件基础路径
    """
    # 定义文件路径（适配新的测试特征文件名）
    features_file = os.path.join(base_path, "test_data/test_features_iter_1.csv")
    phase_pattern = os.path.join(base_path, "Phase Plot test*_real.csv")

    # 读取特征数据
    try:
        features_df = pd.read_csv(features_file)
        print(f"成功读取测试特征文件: {features_file}")
        print(f"特征数据包含{len(features_df)}个单元的特征")
    except FileNotFoundError:
        print(f"测试特征文件不存在: {features_file}")
        return None

    # 查找所有对应的相位文件
    phase_files = glob.glob(phase_pattern)
    if len(phase_files) != TOTAL_UNITS:  # 适配25个单元
        print(f"警告：找到{len(phase_files)}个测试相位文件（预期25个）")

    # 按单元编号排序文件（使用正则表达式提取test后的数字）
    def extract_test_number(file_path):
        """从文件名中提取test后面的数字"""
        match = re.search(r'test(\d+)_real', file_path)
        if match:
            return int(match.group(1))
        return 0

    # 按test编号排序
    phase_files.sort(key=extract_test_number)

    # 显示找到的文件及其编号
    print("\n找到的相位文件：")
    for file_path in phase_files:
        test_num = extract_test_number(file_path)
        print(f"  test{test_num}: {os.path.basename(file_path)}")

    # 存储合并结果
    merged_data = []

    # 逐个单元处理（按test编号匹配）
    for i, file_path in enumerate(phase_files):
        unit_index = i  # 特征数据按行索引对应单元1-25（索引0-24）

        # 检查索引是否有效
        if unit_index >= len(features_df):
            print(f"    警告：特征数据中没有单元{i + 1}的数据")
            continue

        # 读取相位数据
        try:
            phase_df = pd.read_csv(file_path)
            test_num = extract_test_number(file_path)
            print(f"  读取test{test_num} (单元{i + 1})相位数据: {os.path.basename(file_path)}")

            # 验证数据行数
            if len(phase_df) != 91:
                print(f"    警告：test{test_num}相位数据有{len(phase_df)}行（预期91行）")
        except Exception as e:
            print(f"    读取相位文件失败: {e}")
            continue

        # 获取对应单元的特征数据（按行索引）
        unit_features = features_df.iloc[[unit_index]]

        # 将特征数据复制91次（与相位数据行数匹配）
        features_repeated = pd.concat([unit_features] * len(phase_df), ignore_index=True)

        # 合并特征数据和相位数据
        unit_merged = pd.concat([features_repeated, phase_df], axis=1)
        merged_data.append(unit_merged)

    # 合并所有单元的数据
    if merged_data:
        final_merged = pd.concat(merged_data, ignore_index=True)

        # 保存结果
        output_file = os.path.join(base_path, "merged_test_phase_data.csv")
        final_merged.to_csv(output_file, index=False, float_format='%.6f')
        print(f"\n测试相位数据合并完成！结果保存到: {output_file}")
        print(f"总数据行数: {len(final_merged)}")

        return output_file
    else:
        print("没有测试数据被合并")
        return None


def align_phase_data(input_file, output_file):
    """
    对相位数据进行对齐处理：每个theta周期内的相位值减去该周期内theta=0度的相位值
    直接替换原始相位列，不保留原始数据
    【修改】移除了相位值周期性处理的逻辑
    参数:
        input_file: 输入文件路径
        output_file: 输出文件路径
    """
    # 读取数据
    df = pd.read_csv(input_file)
    print(f"成功读取数据: {input_file}")
    print(f"数据总行数: {len(df)}")

    # 计算周期数（每91行一个周期：-90到90度，步长2度）
    cycle_length = 91  # -90, -88, ..., 88, 90
    num_cycles = len(df) // cycle_length

    print(f"检测到周期数: {num_cycles}")
    print(f"每个周期行数: {cycle_length}")

    # 创建结果列表
    aligned_data = []

    # 逐个周期处理
    for cycle_idx in range(num_cycles):
        # 获取当前周期的数据
        start_idx = cycle_idx * cycle_length
        end_idx = start_idx + cycle_length
        cycle_data = df.iloc[start_idx:end_idx].copy()

        # 找到当前周期中theta=0度的行
        theta_zero_row = cycle_data[cycle_data['Theta [deg]'] == 0]

        if len(theta_zero_row) == 0:
            print(f"警告：周期{cycle_idx + 1}中未找到theta=0度的数据，跳过该周期")
            aligned_data.append(cycle_data)
            continue

        # 获取theta=0度对应的相位值
        phase_zero = theta_zero_row['cang_deg(rEL3X) [deg]'].values[0]
        print(f"周期{cycle_idx + 1}: theta=0度的相位值 = {phase_zero:.4f}度")

        # 对当前周期的相位值进行对齐（减去theta=0度的相位值）
        cycle_data['cang_deg(rEL3X) [deg]'] = cycle_data['cang_deg(rEL3X) [deg]'] - phase_zero

        # 【移除】处理相位值的周期性（确保在-180到180度之间）的代码段

        aligned_data.append(cycle_data)

    # 合并所有周期的数据
    final_df = pd.concat(aligned_data, ignore_index=True)

    # 保存结果
    final_df.to_csv(output_file, index=False, float_format='%.6f')
    print(f"\n相位对齐完成！结果保存到: {output_file}")
    print(f"输出数据行数: {len(final_df)}")

    # 显示一些统计信息
    aligned_range = (final_df['cang_deg(rEL3X) [deg]'].min(), final_df['cang_deg(rEL3X) [deg]'].max())
    print(f"\n对齐后相位值范围: {aligned_range[0]:.2f} ~ {aligned_range[1]:.2f}度")

    return final_df


# 执行测试数据生成与处理
if __name__ == "__main__":
    run_test()
    # # # # 取消注释可执行后续数据处理
    merge_test_amp_data()
    merge_test_phase_data()
    input_path = "E:/c50066007/pythonML_mianzhen_random/merged_test_phase_data.csv"
    output_path = "E:/c50066007/pythonML_mianzhen_random/merged_test_phase_data_xiangweiduiqi.csv"
    aligned_df = align_phase_data(input_path, output_path)

