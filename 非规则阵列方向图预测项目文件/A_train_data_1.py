# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/A_train_data_1.py
# 目的：训练数据采集与 HFSS 仿真脚本
# 输入：随机阵列参数
# 输出：训练特征 CSV、HFSS 幅相方向图和运行日志
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

"""
文件：A_train_data_1.py

功能：
1. 随机生成 3×3 天线阵列布局。首个单元固定在原点，其余单元在各自格子内均匀随机分布。
2. 为每个单元计算 8 个方位的最近邻距离倒数特征，并保存为 CSV。
3. 驱动 HFSS 完成阵列单元移动、相对坐标系建立、底板尺寸调整、布尔开缝、
   端口激励、仿真以及四类方向图数据导出。
4. 连续执行多次迭代，记录每次迭代耗时。

函数清单：
- generate_5x5_antenna_array：生成阵列坐标及格子索引。
- calc_distance：计算两点之间的欧几里得距离。
- get_grid_direction：根据格子索引差判断 8 个方位。
- calculate_unit_features：计算单个单元的 8 维特征。
- save_25x8_features：保存所有单元的特征数据。
- run_single_iteration：执行一次数据生成与 HFSS 仿真流程。

说明：
当前 GRID_ROWS 和 GRID_COLS 均为 3，因此实际生成的是 3×3 阵列，共 9 个单元。
为兼容原脚本，保留了原函数名 generate_5x5_antenna_array 和 save_25x8_features。
"""

import csv
import math
import os
import random
import time

from hfss import HFSS


# ========================== HFSS 初始化 ==========================

# 实际运行时初始化 HFSS。
hfss = HFSS()


# ========================== 固定参数 ==========================

GRID_ROWS = 3
GRID_COLS = 3

CELL_SIDE = 80
CELL_STEP = 400
FEATURE_SCALAR = 12

TOTAL_UNITS = GRID_ROWS * GRID_COLS

# 底板 ground/sub 的位置和尺寸（3×3 阵列方案②）
BOARD_POS_X = "-2.5*xcell"
BOARD_POS_Y = "-2.5*ycell"
BOARD_XSIZE = "xcell1+780mil"
BOARD_YSIZE = "ycell1+780mil"

# 特征 CSV 保存目录
FEATURE_SAVE_DIR = "E:/c50066007/pythonML_mianzhen_random/train_data/"


# ========================== 阵列生成 ==========================

def generate_5x5_antenna_array():
    """
    生成阵列坐标及格子索引。

    当前参数为 3×3，因此生成 9 个单元。
    第一个单元固定在 (0, 0)，其余单元在各自格子范围内均匀随机分布。

    Returns:
        tuple:
            point_list: 每个元素为 (x, y, i, j)，分别表示坐标和格子索引。
            point_list: 为兼容原脚本，第二个返回值仍保留为 point_list。
    """
    point_list = []
    first_point = True

    for i in range(GRID_ROWS):
        for j in range(GRID_COLS):
            if first_point:
                x, y = 0.0, 0.0
                first_point = False
            else:
                x_start = i * CELL_STEP
                y_start = j * CELL_STEP

                x = random.uniform(x_start, x_start + CELL_SIDE)
                y = random.uniform(y_start, y_start + CELL_SIDE)

            # (x 坐标, y 坐标, 格子行索引 i, 格子列索引 j)
            point_list.append((x, y, i, j))

    # 保留原脚本的双返回值接口，避免影响现有调用方式。
    return point_list, point_list


# ========================== 特征计算 ==========================

def calc_distance(p1, p2):
    """计算两点之间的欧几里得距离。"""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])


def get_grid_direction(center_grid, neighbor_grid):
    """
    根据两个单元的格子索引差判断邻居方位。

    方位编号：
        1：右
        2：右上
        3：上
        4：左上
        5：左
        6：左下
        7：下
        8：右下

    Args:
        center_grid: 中心单元的格子索引 (i0, j0)。
        neighbor_grid: 邻居单元的格子索引 (i1, j1)。

    Returns:
        int | None: 方位编号 1～8；如果不是相邻格子，则返回 None。
    """
    i0, j0 = center_grid
    i1, j1 = neighbor_grid

    delta_i = i1 - i0
    delta_j = j1 - j0

    direction_map = {
        (0, 1): 1,    # 右
        (-1, 1): 2,   # 右上
        (-1, 0): 3,   # 上
        (-1, -1): 4,  # 左上
        (0, -1): 5,   # 左
        (1, -1): 6,   # 左下
        (1, 0): 7,    # 下
        (1, 1): 8,    # 右下
    }

    return direction_map.get((delta_i, delta_j))


def calculate_unit_features(antenna_array, unit_idx):
    """
    计算指定单元的 8 维特征。

    每个方位的特征为：
        FEATURE_SCALAR / 该方位最近邻单元的欧几里得距离

    如果某个方位没有邻居，则该方位特征为 0。

    Returns:
        list[float]: 按右、右上、上、左上、左、左下、下、右下排列的 8 维特征。
    """
    center_unit = antenna_array[unit_idx]
    center_grid = (center_unit[2], center_unit[3])

    # 初始化 8 个方位的最近距离，无穷大表示该方位暂时没有邻居。
    min_dist_dict = {
        direction: float("inf")
        for direction in range(1, 9)
    }

    # 遍历其他单元，寻找每个方位上的最近邻。
    for idx, neighbor_unit in enumerate(antenna_array):
        if idx == unit_idx:
            continue

        neighbor_grid = (neighbor_unit[2], neighbor_unit[3])
        direction = get_grid_direction(center_grid, neighbor_grid)

        # 非 8 个相邻方位的格子不参与特征计算。
        if direction is None:
            continue

        dist = calc_distance(center_unit, neighbor_unit)

        if dist < min_dist_dict[direction]:
            min_dist_dict[direction] = dist

    # 严格按照指定方位顺序生成 8 个特征。
    features = []

    for direction in range(1, 9):
        min_dist = min_dist_dict[direction]

        if min_dist != float("inf"):
            feature = (1 / min_dist) * FEATURE_SCALAR
            features.append(round(feature, 6))
        else:
            features.append(0.0)

    return features


# ========================== 特征数据保存 ==========================

def save_25x8_features(features_data, iteration):
    """
    保存阵列单元的 8 维特征数据。

    当前 3×3 阵列对应 9 行 × 8 列。
    函数名保留原脚本命名，以兼容现有调用方式。
    """
    os.makedirs(FEATURE_SAVE_DIR, exist_ok=True)

    filename = os.path.join(
        FEATURE_SAVE_DIR,
        f"train_features_iter_{iteration}.csv",
    )

    headers = [
        "right",
        "right_up",
        "up",
        "left_up",
        "left",
        "left_down",
        "down",
        "right_down",
    ]

    with open(filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(headers)
        writer.writerows(features_data)

    print(
        f"✅ 迭代 {iteration}：特征数据已保存 "
        f"（{len(features_data)} 行 × 8 列）→ {filename}"
    )


# ========================== 单次迭代主流程 ==========================

def run_single_iteration(iteration):
    """
    执行一次完整的数据生成与 HFSS 仿真流程。
    """
    print(f"\n===== 开始迭代 {iteration} =====")

    # 1. 生成阵列坐标。
    antenna_array, _ = generate_5x5_antenna_array()
    print(f"✅ 生成 {GRID_ROWS}×{GRID_COLS} 阵列，共 {len(antenna_array)} 个单元")

    # 2. 计算每个单元的 8 维特征。
    all_features = []

    for unit_idx in range(TOTAL_UNITS):
        features = calculate_unit_features(antenna_array, unit_idx)
        all_features.append(features)

    # 3. 保存特征数据。
    save_25x8_features(all_features, iteration)

    # 4. 驱动 HFSS 执行阵列单元移动及相对坐标系建立。
    print("🔧 执行 HFSS 仿真操作...")

    relative_cs_count = 70

    for x, y, i, j in antenna_array:
        if x == 0 and y == 0:
            hfss.move_xyz(
                col_pos=x,
                row_pos=y,
                relative_cs_count=relative_cs_count + 1,
            )
            relative_cs_count += 2
        else:
            hfss.move(col_distance=x, row_distance=y)
            hfss.move_xyz(
                col_pos=x,
                row_pos=y,
                relative_cs_count=relative_cs_count,
            )
            relative_cs_count += 1

    # 5. 设置底板尺寸并执行 HFSS 建模、端口激励和仿真。
    hfss.set_board_size(
        BOARD_POS_X,
        BOARD_POS_Y,
        BOARD_XSIZE,
        BOARD_YSIZE,
    )

    hfss.Box60(
        BOARD_POS_X,
        BOARD_POS_Y,
        BOARD_XSIZE,
        BOARD_YSIZE,
    )

    hfss.Box60_Box61(GRID_ROWS)
    hfss.kuidian(n=TOTAL_UNITS)
    hfss.run()
    hfss.source_context(n=TOTAL_UNITS)

    # 6. 导出相位和幅度方向图数据。
    hfss.phase_theta_cycle(iteration=iteration, n=TOTAL_UNITS)
    hfss.phase_phi_cycle(iteration=iteration, n=TOTAL_UNITS)

    # hfss.amp_cycle(iteration=iteration, n=TOTAL_UNITS)
    hfss.amp_theta_cycle(iteration=iteration, n=TOTAL_UNITS)
    hfss.amp_phi_cycle(iteration=iteration, n=TOTAL_UNITS)

    # 7. 清理 HFSS 遗留对象。
    hfss.delete(5)

    print(f"===== 迭代 {iteration} 完成 =====\n")


# ========================== 主程序入口 ==========================

if __name__ == "__main__":
    TOTAL_ITERATIONS = 30

    for iter_num in range(1, TOTAL_ITERATIONS + 1):
        start_time = time.time()

        run_single_iteration(iter_num)

        end_time = time.time()
        elapsed_time = end_time - start_time

        print(
            f"第 {iter_num} 次迭代完成，"
            f"耗时：{elapsed_time:.6f} 秒\n"
        )

    print(
        f"🎉 所有 {TOTAL_ITERATIONS} 次迭代完成！"
        f"特征 CSV 为 {TOTAL_UNITS} 行 × 8 列格式。"
    )

    # hfss.delete()

