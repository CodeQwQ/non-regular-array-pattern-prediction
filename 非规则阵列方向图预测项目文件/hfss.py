# 文件基本信息
# 文件：非规则阵列方向图预测项目文件/hfss.py
# 目的：HFSS COM 自动化适配层
# 输入：HFSS 工程、设计名称和阵列参数
# 输出：仿真报告、方向图 CSV 和清理结果
# 维护：修改后必须同步目录索引、函数/类说明、测试和变更记录。

# hfss api
#
# 文件摘要：HFSS COM API 封装类。通过 win32com 连接 Ansoft HFSS，激活项目
#          MiRC_Slot_fed_filtenna_throughvias / 设计 number1，提供阵列单元移动、
#          相对坐标系创建、布尔运算、端口激励、仿真运行、幅度/相位方向图报告
#          导出与遗留对象清理等自动化操作，是全部训练/测试数据采集的底层接口。
# 类/函数清单：
#   class HFSS —— HFSS 自动化操作封装类
#     __init__               连接 HFSS 并激活指定项目/设计/3D建模器，可接收任务隔离输出目录
#     move                   将天线单元沿 x/y 方向平移指定距离(mil)
#     move_xyz               在指定位置创建相对坐标系 RelativeCS（用于定位单元）
#     Box60                  创建金属地小板 Box60（X/Y 位置与尺寸由传入表达式
#                            决定，与 ground/sub 统一；已存在先删，Z 写死不变）
#     Box60_Box61(n)         Box60 与 Box61_1~Box61_(n*n) 执行布尔减
#     set_board_size         重设模板工程底板实体 ground/sub 的位置与尺寸
#                            （照 record/changeProperty.py 录制模板：经 CreateBox:1
#                            历史操作节点，NAME:Position 块三分量 + XSize/YSize，
#                            逐实体 ChangeProperty，缺失即报错；计划005 方案②）
#     kuidian(n)             配置 n 个端口激励（幅度1W、相位0deg）
#     run                    调用 AnalyzeAllNominal 运行仿真
#     source_context(n)      设置 n 个源的上下文
#     _delete_report_quiet   删除指定报告（不存在时静默忽略）
#     _export_and_validate   统一导出生命周期：删旧文件→导出→读回校验→删报告
#     amp_theta_cycle        theta 分量 dB(DirTheta) 报告导出（建前删+导出后删+读回校验，
#                            report_prefix 参数支持训练/测试报告名分离；含球存在性预检）
#     amp_phi_cycle          phi 分量 dB(DirPhi) 报告导出（同上生命周期与预检）
#     phase_theta_cycle      theta 分量 rETheta 相位报告导出（同上生命周期；缺球补建）
#     phase_phi_cycle        phi 分量 rEPhi 相位报告导出（同上生命周期；缺球补建）
#     export_total_field_cycle 全源总方向图导出（计划007）：球先删后建（Infinite
#                            Sphere500 绑 RelativeCS70），4 个 Rectangular Plot
#                            报告显式传全部端口 SourceContext，导出整阵总场
#                            train{iter}_3D_total_*.csv（同上生命周期）
#     all_directivity(n)     创建 Infinite Sphere 与 Directivity 报告并导出 CSV
#     delete(n)              清理 RelativeCS 等仿真遗留对象
#   _validate_exported_csv   模块级：导出 CSV 读回校验（表头量名+行数），
#                            防 AEDT 报告静默回退脏数据落盘（计划003）
# ============================================================

from win32com import client
import os
import time


def _output_root():
    """返回 HFSS 导出目录；未配置时保留实验脚本默认目录。"""

    root = os.getenv("ARRAYLAB_HFSS_OUTPUT_ROOT", r"E:\c50066007\pythonML_mianzhen_random")
    return root if root.endswith(("/", "\\")) else root + os.sep


def _validate_exported_csv(file_path, expected_column, min_data_rows=16000):
    """
    导出 CSV 读回校验（计划003 核心防线）

    ExportToFile 后立即读回文件，断言表头包含期望量名且数据行数达标，
    防止 AEDT 报告静默回退/截断导致的脏数据落盘
    （2026-09-24 train999 污染事故：报告定义失效后 AEDT 用默认量/默认上下文顶替）。

    参数:
        file_path       导出的 CSV 完整路径
        expected_column 期望出现在表头的量名（子串匹配，如 "dB(DirTheta)"）
        min_data_rows   数据行数下限（方向图 91x181=16471 点，默认 16000 容差防截断）

    异常:
        RuntimeError    重试后仍存在 文件缺失 / 表头量名不符 / 行数不足
    """
    max_attempts = 5
    actual_header = None
    actual_rows = 0
    for attempt in range(max_attempts):
        if os.path.isfile(file_path):
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.read().splitlines()
                if lines:
                    actual_header = lines[0]
                    actual_rows = max(len(lines) - 1, 0)
                    if expected_column in actual_header and actual_rows >= min_data_rows:
                        return
            except OSError:
                pass
        # 文件可能尚未写完（AEDT 异步导出），短暂等待后重试（最后一次失败无需再等）
        if attempt < max_attempts - 1:
            time.sleep(1)
    if actual_header is None:
        raise RuntimeError(
            f"导出校验失败: {file_path}\n"
            f"  文件未生成或始终无法读取（重试 {max_attempts} 次）。\n"
            f"  可能原因: AEDT 导出静默失败 / 路径或权限问题 / 文件被占用"
        )
    raise RuntimeError(
        f"导出校验失败: {file_path}\n"
        f"  期望表头包含: {expected_column}\n"
        f"  实际表头: {actual_header}\n"
        f"  实际数据行数: {actual_rows}（要求 >= {min_data_rows}）\n"
        f"  可能原因: AEDT 报告定义失效回退 / 导出被截断 / 球或源上下文无效"
    )


class HFSS:
    def __init__(self, project_path=r"E:\c50066007\MiRC_Slot_fed_filtenna_throughvias.aedt", design_name="number1", output_root=None):

        self.output_root = output_root or _output_root()
        if not self.output_root.endswith(("/", "\\")):
            self.output_root += os.sep

        # ==================== 1. 检查工程路径 ====================
        project_path = os.path.abspath(project_path)

        if not os.path.isfile(project_path):
            raise FileNotFoundError(
                f"HFSS工程不存在: {project_path}"
            )

        project_name = os.path.splitext(
            os.path.basename(project_path)
        )[0]

        # ==================== 2. 尝试连接已有COM实例 ====================
        attached_existing = False

        try:
            self.oAnsoftApp = client.GetActiveObject(
                "AnsoftHfss.HfssScriptInterface"
            )
            self._bootstrap_desktop = (
                self.oAnsoftApp.GetAppDesktop()
            )
            attached_existing = True

            print("成功获取已注册的HFSS实例")

        except Exception:
            # 如果无法直接获取，创建一个临时连接入口
            print("未能直接获取COM实例，尝试通过实例管理器连接")

            self.oAnsoftApp = client.Dispatch(
                "AnsoftHfss.HfssScriptInterface"
            )

            self._bootstrap_desktop = (
                self.oAnsoftApp.GetAppDesktop()
            )

        bootstrap_pid = int(
            self._bootstrap_desktop.GetProcessID()
        )

        # ==================== 3. 获取运行实例管理器 ====================
        oRunningInstances = (
            self._bootstrap_desktop.GetRunningInstancesMgr()
        )

        self.oDesktop = None

        # 优先根据工程完整路径寻找Desktop
        for key in (project_path, project_name):
            try:
                candidate = (
                    oRunningInstances.GetRunningInstanceByProject(key)
                )

                # 验证返回对象确实是可用的Desktop
                candidate.GetProcessID()

                self.oDesktop = candidate
                print(f"找到目标工程对应的Desktop: {key}")
                break

            except Exception:
                continue

        # ==================== 4. 如果没找到，遍历所有实例 ====================
        if self.oDesktop is None:

            all_desktops = (
                oRunningInstances.GetAllRunningInstances()
            )

            matched = []
            other_desktops = []

            for desktop in all_desktops:
                try:
                    pid = int(desktop.GetProcessID())

                    projects = [
                        os.path.splitext(
                            os.path.basename(str(p))
                        )[0].lower()
                        for p in desktop.GetProjectList()
                    ]

                    if project_name.lower() in projects:
                        matched.append(desktop)

                    elif pid != bootstrap_pid:
                        other_desktops.append(desktop)

                except Exception:
                    continue

            if len(matched) == 1:
                self.oDesktop = matched[0]

            elif len(matched) > 1:
                raise RuntimeError(
                    "发现多个打开同名工程的Desktop，"
                    "请检查工程路径是否重复。"
                )

            elif attached_existing:
                # 已经通过GetActiveObject获取了现有实例
                self.oDesktop = self._bootstrap_desktop

            elif len(other_desktops) == 1:
                # 只有一个其他Desktop，直接连接
                self.oDesktop = other_desktops[0]

            elif len(other_desktops) == 0:
                # 没有其他Desktop，使用当前实例
                self.oDesktop = self._bootstrap_desktop

            else:
                raise RuntimeError(
                    "发现多个HFSS Desktop，且没有找到目标工程。"
                    "请先在目标Desktop中打开对应工程。"
                )

        # ==================== 5. 激活或打开工程 ====================
        target_pid = int(self.oDesktop.GetProcessID())

        self.oDesktop.RestoreWindow()

        opened_projects = [
            os.path.splitext(os.path.basename(str(p)))[0].lower()
            for p in self.oDesktop.GetProjectList()
        ]

        if project_name.lower() not in opened_projects:
            print("目标工程尚未打开，正在打开...")
            self.oDesktop.OpenProject(project_path)

        # 通过完整路径激活工程
        try:
            self.oProject = (
                self.oDesktop.SetActiveProjectByPath(project_path)
            )
        except Exception:
            self.oProject = (
                self.oDesktop.SetActiveProject(project_name)
            )

        # ==================== 6. 激活Design和Editor ====================
        self.oDesign = self.oProject.SetActiveDesign(design_name)

        self.oEditor = self.oDesign.SetActiveEditor("3D Modeler")

        print("HFSS连接成功！")
        print("Desktop PID:", target_pid)
        print("Project:", project_name)
        print("Design:", design_name)

        # ==================== 7. 关闭临时Desktop ====================
        # 只关闭由Dispatch创建的临时连接入口，
        # 绝不关闭真正连接的目标Desktop。
        if not attached_existing and target_pid != bootstrap_pid:
            try:
                self._bootstrap_desktop.QuitApplication()
                print("临时Desktop已关闭")
            except Exception as e:
                print("临时Desktop关闭失败:", e)

    def move(self, col_distance=0, row_distance=0):
        """
        移动天线单元到指定位置
        :param col_distance: 列方向(x轴)移动距离（数值）
        :param row_distance: 行方向(y轴)移动距离（数值）
        :param z_value: z轴移动距离（数值）
        """
        x_component = f"{col_distance}mil" if col_distance != 0 else "0mil"
        y_component = f"{row_distance}mil" if row_distance != 0 else "0mil"


        if self.oEditor:
            self.oEditor.DuplicateAlongLine(
                [
                    "NAME:Selections",
                    "Selections:=", "art01",  #需要调整
                    "NewPartsModelFlag:=", "Model"
                ],
                [
                    "NAME:DuplicateToAlongLineParameters",
                    "CreateNewObjects:=", True,
                    "XComponent:=", x_component,
                    "YComponent:=", y_component,
                    "ZComponent:=", "0mil",
                    "NumClones:=", "2"
                ],
                [
                    "NAME:Options",
                    "DuplicateAssignments:=", True
                ],
                [
                    "CreateGroupsForNewObjects:=", False
                ])

            self.oEditor.DuplicateAlongLine(
                [
                    "NAME:Selections",
                    "Selections:=", "Box61",  # 需要调整
                    "NewPartsModelFlag:=", "Non Model"
                ],
                [
                    "NAME:DuplicateToAlongLineParameters",
                    "CreateNewObjects:=", True,
                    "XComponent:=", x_component,
                    "YComponent:=", y_component,
                    "ZComponent:=", "0mil",
                    "NumClones:=", "2"
                ],
                [
                    "NAME:Options",
                    "DuplicateAssignments:=", True
                ],
                [
                    "CreateGroupsForNewObjects:=", False
                ])

    def move_xyz(self, col_pos=0, row_pos=0, relative_cs_count=0):
        """
        创建相对坐标系（用于定位单元）
        :param col_pos: 列方向(x轴)位置
        :param row_pos: 行方向(y轴)位置
        :param z_pos: z轴位置
        :param relative_cs_count: 坐标系编号
        """
        self.oEditor.SetWCS(
            [
                "NAME:SetWCS Parameter",
                "Working Coordinate System:=", "RelativeCS70",
                "RegionDepCSOk:=", False
            ])

        origin_x = f"{col_pos}mil" if col_pos != 0 else "0mil"
        origin_y = f"{row_pos}mil" if row_pos != 0 else "0mil"


        cs_name = f"RelativeCS{relative_cs_count}"

        if self.oEditor:
            self.oEditor.CreateRelativeCS(
                [
                    "NAME:RelativeCSParameters",
                    "Mode:=", "Euler Angle ZYZ",
                    "OriginX:=", origin_x,
                    "OriginY:=", origin_y,
                    "OriginZ:=", "0mil",
                    "Psi:=", "0deg",
                    "Theta:=", "0deg",
                    "Phi:=", "0deg"
                ],
                [
                    "NAME:Attributes",
                    "Name:=", cs_name
                ])
            self.oEditor.SetWCS(
                [
                    "NAME:SetWCS Parameter",
                    "Working Coordinate System:=", "RelativeCS70",
                    "RegionDepCSOk:=", False
                ])

        print(f"已创建坐标系：{cs_name}，位置({origin_x}, {origin_y})")

    def Box60(self, pos_x, pos_y, size_x, size_y):
        """
        创建金属地小板 Box60（与 ground/sub 同 X/Y 位置与尺寸，计划005 方案②）
        :param pos_x: XPosition 表达式（与 sub 一致："-2.5*xcell"）
        :param pos_y: YPosition 表达式（"-2.5*ycell"）
        :param size_x: XSize 表达式（3×3 时 "xcell1+780mil"、5×5 时 "xcell1+1580mil"）
        :param size_y: YSize 表达式（同 size_x 口径）
        ZPosition/ZSize 不随规模变化（保持模板原值 47.44mil/2mil，写死）；
        若已存在（上一轮迭代残留、尺寸可能是旧值）则先删除再按新参数重建；
        其后 Box60_Box61 会以 Box60 为 Blank 执行布尔开缝，依赖本方法先执行。
        """
        existing_objects = set()
        for group in ["Solids", "Sheets", "Lines", "Unclassified"]:
            try:
                existing_objects.update(
                    self.oEditor.GetObjectsInGroup(group)
                )
            except Exception:
                pass

        if "Box60" in existing_objects:
            self.oEditor.Delete(
                [
                    "NAME:Selections",
                    "Selections:=", "Box60"
                ]
            )

        self.oEditor.CreateBox(
            [
                "NAME:BoxParameters",
                "XPosition:=", f"{pos_x}",
                "YPosition:=", f"{pos_y}",
                "ZPosition:="      , "47.44mil",
                "XSize:="      , f"{size_x}",
                "YSize:="      , f"{size_y}",
                "ZSize:="      , "2mil"
            ],
            [
                "NAME:Attributes",
                "Name:="       , "Box60",
                "Flags:="      , "",
                "Color:="      , "(143 175 143)",
                "Transparency:="    , 0,
                "PartCoordinateSystem:=", "Global",
                "UDMId:="      , "",
                "MaterialValue:="   , "\"pec\"",
                "SurfaceMaterialValue:=", "\"\"",
                "SolveInside:="    , False,
                "ShellElement:="    , False,
                "ShellElementThickness:=", "0mil",
                "IsMaterialEditable:="  , True,
                "UseMaterialAppearance:=", False,
                "IsLightweight:="   , False
            ])


    def Box60_Box61(self, n):
        """
        执行Subtract操作：以Box60为被减部件，Box61_1~Box61_8为减工具部件
        KeepOriginals=True 表示保留所有原始部件（仅生成减法后的新模型）
        """
        # 1. 构造Tool Parts列表：生成Box61_1到Box61_8的部件名称
        # range(1,9) 生成1-8的整数，拼接成"Box61_1"、"Box61_2"..."Box61_8"
        tool_parts = ["Box61"]
        tool_parts += [f"Box61_{i}" for i in range(1, n*n)]
        #tool_parts += [f"Box61_{i}" for i in range(1, 100)]

        # 2. 转换为HFSS要求的格式：多个部件用【英文逗号+空格】分隔的字符串
        tool_parts_str = ", ".join(tool_parts)

        # 3. 执行布尔减操作（核心逻辑不变，仅替换Tool Parts参数）
        self.oEditor.Subtract(
            [
                "NAME:Selections",
                "Blank Parts:=", "Box60",  # 被减部件（空白部件）
                "Tool Parts:=", tool_parts_str  # 减工具部件（Box61_1~Box61_8）
            ],
            [
                "NAME:SubtractParameters",
                "KeepOriginals:=", True  # 保留原始部件（False则删除Tool Parts）
            ]
        )

    def set_board_size(self, pos_x, pos_y, size_x, size_y, entity_names=("ground", "sub"), pos_z="2mil"):
        """
        按传入表达式重设底板实体（ground/sub）的位置与尺寸（计划005 方案②）
        :param pos_x: Position 的 X 分量表达式（两侧外延2单元对称："-2.5*xcell"）
        :param pos_y: Position 的 Y 分量表达式（"-2.5*ycell"）
        :param size_x: XSize 表达式（3×3 时 "xcell1+780mil"、5×5 时 "xcell1+1580mil"）
        :param size_y: YSize 表达式（3×3 时 "ycell1+780mil"、5×5 时 "ycell1+1580mil"）
        :param entity_names: 待改底板实体名元组（模板工程既有实体，默认 ground 与 sub）
        :param pos_z: Position 的 Z 分量（默认 "2mil"，取自录制模板中 sub 的值；
                      若 ground 的创建 Z 与之不同，调用时传参覆盖）
        参数结构照抄 record/changeProperty.py 的 AEDT 录制模板：经各实体的
        CreateBox:1 历史操作节点（PropServers 传 实体名:CreateBox:1），
        ChangedProps 用 NAME:Position 块（X:=/Y:=/Z:= 三分量）与 XSize/YSize 块
        （Value:=）；逐实体发 ChangeProperty；任一实体不存在即 raise（fail loud，
        延续计划003 防线思路）；ground/sub 为永久实体，delete() 不清理，
        训练/测试交替运行会跨脚本残留，故每次生成前都重设。
        """
        existing_objects = set()
        for group in ["Solids", "Sheets", "Lines", "Unclassified"]:
            try:
                existing_objects.update(
                    self.oEditor.GetObjectsInGroup(group)
                )
            except Exception:
                pass

        missing = [name for name in entity_names if name not in existing_objects]
        if missing:
            raise RuntimeError(
                f"set_board_size 失败: 底板实体不存在: {', '.join(missing)}\n"
                f"  期望实体: {', '.join(entity_names)}\n"
                f"  可能原因: 模板工程实体名与默认不符，需改调用参数 entity_names"
            )
        for name in entity_names:
            self.oEditor.ChangeProperty(
                [
                    "NAME:AllTabs",
                    [
                        "NAME:Geometry3DCmdTab",
                        [
                            "NAME:PropServers",
                            f"{name}:CreateBox:1"
                        ],
                        [
                            "NAME:ChangedProps",
                            [
                                "NAME:Position",
                                "X:="         , f"{pos_x}",
                                "Y:="         , f"{pos_y}",
                                "Z:="         , f"{pos_z}"
                            ],
                            [
                                "NAME:XSize",
                                "Value:="      , f"{size_x}"
                            ],
                            [
                                "NAME:YSize",
                                "Value:="      , f"{size_y}"
                            ]
                        ]
                    ]
                ])
        print(f"已重设底板: {', '.join(entity_names)} → 位置({pos_x}, {pos_y}, {pos_z}) 尺寸 XSize={size_x}, YSize={size_y}")

    def kuidian(self, n=16):  # n为端口数量，默认16，可根据需要传入其他值
        self.oModule = self.oDesign.GetModule("Solutions")

        # 构建端口配置列表：先添加固定的全局设置，再循环生成n个端口的配置
        sources_config = [
            [
                "IncludePortPostProcessing:=", False,
                "SpecifySystemPower:=", False
            ]
        ]

        # 循环生成从1:1到n:1的端口配置（幅度1W，相位0deg）
        for i in range(1, n * 2, 2):
            port_config = [
                "Name:=", f"{i}:1",  # 端口名称：1:1, 3:1, ...,
                "Magnitude:=", "1W",
                "Phase:=", "0deg"
            ]
            sources_config.append(port_config)

        # 调用EditSources方法，传入动态生成的配置
        self.oModule.EditSources(sources_config)

    def run(self):
        self.oDesign.AnalyzeAllNominal()

    def source_context(self, n=16):  # n为源的数量，默认16，可灵活调整
        self.oModule = self.oDesign.GetModule("Solutions")
        all_source_names = []  # 存储所有源名称（1:1到n:1）

        # 循环生成n个源（1:1到n:1）并编辑参数
        for i in range(1, n * 2, 2):
            source_name = f"{i}:1"  # 动态生成源名称（如"1:1", "3:1", ..., "49:1"）
            all_source_names.append(source_name)  # 添加到源名称列表

            # 编辑当前源的参数（幅度、相位可根据需要修改）
            self.oModule.EditSources(
                [
                    [
                        "IncludePortPostProcessing:=", False,
                        "SpecifySystemPower:=", False
                    ],
                    [
                        "Name:=", source_name,
                        "Magnitude:=", "1W",  # 固定幅度，若需动态可改为参数（如magnitudes[i-1]）
                        "Phase:=", "0deg"  # 固定相位，若需动态可改为参数（如phases[i-1]）
                    ]
                ])

        # 批量设置所有源的上下文
        self.oModule.SetSourceContexts([all_source_names])

    # def amp_cycle(self, iteration, n=16):
    #     """
    #     循环创建 n 个 3D Polar 方向图（Directivity 总方向性）
    #     结构与 phase_phi_cycle 完全一致
    #     输出：dB(DirTotal)
    #     """
    #     rad_field_module = self.oDesign.GetModule("RadField")
    #     self.oModule = self.oDesign.GetModule("ReportSetup")
    #
    #     base_path = _output_root()
    #
    #     for idx in range(n):
    #         # ===== 动态构造核心命名参数（和你给的代码完全一样） =====
    #         coord_system = f"RelativeCS{idx + 71}"
    #         sphere_name = f"Infinite Sphere{idx + 1}"
    #         source_context = f"{idx * 2 + 1}:1"
    #         report_name = f"Directivity Plot {1 + idx}"
    #         file_path = f"{base_path}train{iteration}_3D_polar_directivity_{idx + 1}.csv"
    #
    #         # 创建 3D Polar Plot (Directivity)
    #         self.oModule.CreateReport(
    #             report_name,
    #             "Far Fields",
    #             "3D Polar Plot",
    #             "Setup1 : LastAdaptive",
    #             [
    #                 "Context:=", sphere_name,
    #                 "SourceContext:=", source_context
    #             ],
    #             [
    #                 "Phi:=", ["All"],
    #                 "Theta:=", ["All"],
    #                 "Freq:=", ["25GHz"],
    #                 "xcell:=", ["Nominal"],
    #                 "ycell:=", ["Nominal"],
    #                 "h_art9:=", ["Nominal"],
    #                 "h_solder:=", ["Nominal"],
    #                 "h_art8:=", ["Nominal"],
    #                 "h_sub78:=", ["Nominal"],
    #                 "h_art7:=", ["Nominal"],
    #                 "h_sub67:=", ["Nominal"],
    #                 "h_art6:=", ["Nominal"],
    #                 "h_sub56:=", ["Nominal"],
    #                 "h_art5:=", ["Nominal"],
    #                 "h_sub45:=", ["Nominal"],
    #                 "h_art4:=", ["Nominal"],
    #                 "h_sub34:=", ["Nominal"],
    #                 "h_art3:=", ["Nominal"],
    #                 "h_sub23:=", ["Nominal"],
    #                 "h_art2:=", ["Nominal"],
    #                 "h_sub12:=", ["Nominal"],
    #                 "h_art1:=", ["Nominal"],
    #                 "art_c:=", ["Nominal"],
    #                 "h_copper_L4:=", ["Nominal"],
    #                 "h_copper_L2:=", ["Nominal"],
    #                 "h_sub3:=", ["Nominal"],
    #                 "h_copper_L1:=", ["Nominal"],
    #                 "pos_add_layer:=", ["Nominal"],
    #                 "fillet:=", ["Nominal"],
    #                 "W1:=", ["Nominal"],
    #                 "Ws1:=", ["Nominal"],
    #                 "sweep_face:=", ["Nominal"],
    #                 "riempimentoL2:=", ["Nominal"],
    #                 "riempimentoL2top:=", ["Nominal"],
    #                 "Wp2:=", ["Nominal"],
    #                 "L_partch:=", ["Nominal"],
    #                 "chamfer:=", ["Nominal"],
    #                 "W_patch:=", ["Nominal"],
    #                 "Pos_patch:=", ["Nominal"],
    #                 "Wp1:=", ["Nominal"],
    #                 "Lp2:=", ["Nominal"],
    #                 "Lp1:=", ["Nominal"],
    #                 "Ws2:=", ["Nominal"],
    #                 "R1:=", ["Nominal"],
    #                 "W2:=", ["Nominal"],
    #                 "h_air:=", ["Nominal"],
    #                 "Wgx:=", ["Nominal"],
    #                 "Wgy:=", ["Nominal"],
    #                 "R1_pad_patch:=", ["Nominal"],
    #                 "W3:=", ["Nominal"],
    #                 "Wf1:=", ["Nominal"],
    #                 "lenght1:=", ["Nominal"],
    #                 "Wport:=", ["Nominal"],
    #                 "L_tappo:=", ["Nominal"],
    #                 "l_slot:=", ["Nominal"],
    #                 "w4:=", ["Nominal"],
    #                 "x_slot:=", ["Nominal"],
    #                 "w_slot:=", ["Nominal"],
    #                 "length_slot:=", ["Nominal"],
    #                 "chamfer1:=", ["Nominal"],
    #                 "lenghtslot2:=", ["Nominal"],
    #                 "wslot:=", ["Nominal"],
    #                 "R3:=", ["Nominal"],
    #                 "w5:=", ["Nominal"],
    #                 "pcb_l:=", ["Nominal"],
    #                 "pcb_w:=", ["Nominal"],
    #                 "pcb_c:=", ["Nominal"],
    #                 "hPML:=", ["Nominal"],
    #                 "phi_scan:=", ["Nominal"],
    #                 "theta_scan:=", ["Nominal"],
    #                 "origal_x:=", ["Nominal"],
    #                 "origal_y:=", ["Nominal"]
    #             ],
    #             [
    #                 "Phi Component:=", "Phi",
    #                 "Theta Component:=", "Theta",
    #                 "Mag Component:=", ["dB(DirTotal)"]  # 这里是总方向性
    #             ]
    #         )
    #
    #         # 导出 CSV
    #         self.oModule.ExportToFile(report_name, file_path)



    def _delete_report_quiet(self, report_name):
        """删除指定报告；报告不存在时 COM 会抛错，静默忽略。
        用于 CreateReport 前清残留、ExportToFile 后防累积（计划003）。"""
        try:
            self.oModule.DeleteReports([report_name])
        except Exception:
            pass

    def _export_and_validate(self, report_name, file_path, expected_column):
        """统一导出生命周期（计划003）：
        删除旧文件 → ExportToFile → 读回校验（表头量名+行数）→ 删除报告。
        先删旧文件是为了确保读回校验读到的是本次导出结果而非历史残留；
        导出后删除报告则杜绝报告跨次运行累积（污染事故根因）。"""
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except OSError as e:
                # 删除失败（如文件被 Excel 占用）时若继续导出，读回校验可能
                # 误读历史残留数据——正是本次污染事故的同类静默路径，必须中止
                raise RuntimeError(
                    f"旧导出文件删除失败（可能被其他程序占用）: {file_path}（{e}），"
                    f"为避免校验误读历史数据已中止导出"
                )
        self.oModule.ExportToFile(report_name, file_path)
        try:
            _validate_exported_csv(file_path, expected_column)
        finally:
            # 无论校验是否通过都清理报告，失败路径不留残留
            self._delete_report_quiet(report_name)

    def amp_theta_cycle(self, iteration, n=16, report_prefix="ampDirectivity Plot"):
        """
        循环创建 n 个 3D Polar 方向图（Directivity Theta）
        结构与 pattern_phase、phase_phi_cycle 完全一致
        输出：dB(DirTheta)

        report_prefix：报告名前缀，默认训练侧原名 "ampDirectivity Plot"；
        测试侧传 "test_amp Plot" 与训练残留报告隔离（计划003）。
        """
        rad_field_module = self.oDesign.GetModule("RadField")
        self.oModule = self.oDesign.GetModule("ReportSetup")

        # 球存在性预检：Infinite Sphere 由 phase cycle 负责创建且先于 amp 调用，
        # 缺失说明前置链路已坏；AEDT 对无效上下文会静默回退默认报告（污染事故根因），
        # 此处必须显式报错而非静默导出
        existing_spheres = set(
            rad_field_module.GetSetupNames("Infinite Sphere") or []
        )

        base_path = self.output_root

        for idx in range(n):
            # ===== 动态构造核心命名参数 =====
            # 坐标系名称：RelativeCS0 → RelativeCS(n-1)
            coord_system = f"RelativeCS{idx + 71}"
            # Infinite Sphere名称：Infinite Sphere1 → Infinite Sphere{n}
            sphere_name = f"Infinite Sphere{idx + 1}"
            if sphere_name not in existing_spheres:
                raise RuntimeError(
                    f"{sphere_name} 不存在（amp 阶段不做补建），"
                    f"请确认 phase_theta_cycle/phase_phi_cycle 已先运行并创建 Infinite Sphere1~{n}"
                )
            # SourceContext：1:1 → n:1
            source_context = f"{idx * 2 + 1}:1"
            report_name = f"{report_prefix} {1 + idx * 2}"
            file_path = f"{base_path}train{iteration}_3D_dir_theta_{idx + 1}.csv"

            # 建前删除同名残留报告，防止 CreateReport 撞上历史定义而静默失效
            self._delete_report_quiet(report_name)

            # 创建 3D Polar Plot (dB(DirTheta))
            self.oModule.CreateReport(
                report_name,
                "Far Fields",
                "3D Polar Plot",
                "Setup1 : LastAdaptive",
                [
                    "Context:=", sphere_name,
                    "SourceContext:=", source_context
                ],
                [
                    "Phi:=", ["All"],
                    "Theta:=", ["All"],
                    "Freq:=", ["27.5GHz"],
                    "xcell:=", ["Nominal"],
                    "ycell:=", ["Nominal"],
                    "h_art9:=", ["Nominal"],
                    "h_solder:=", ["Nominal"],
                    "h_art8:=", ["Nominal"],
                    "h_sub78:=", ["Nominal"],
                    "h_art7:=", ["Nominal"],
                    "h_sub67:=", ["Nominal"],
                    "h_art6:=", ["Nominal"],
                    "h_sub56:=", ["Nominal"],
                    "h_art5:=", ["Nominal"],
                    "h_sub45:=", ["Nominal"],
                    "h_art4:=", ["Nominal"],
                    "h_sub34:=", ["Nominal"],
                    "h_art3:=", ["Nominal"],
                    "h_sub23:=", ["Nominal"],
                    "h_art2:=", ["Nominal"],
                    "h_sub12:=", ["Nominal"],
                    "h_art1:=", ["Nominal"],
                    "art_c:=", ["Nominal"],
                    "h_copper_L4:=", ["Nominal"],
                    "h_copper_L2:=", ["Nominal"],
                    "h_sub3:=", ["Nominal"],
                    "h_copper_L1:=", ["Nominal"],
                    "pos_add_layer:=", ["Nominal"],
                    "fillet:=", ["Nominal"],
                    "W1:=", ["Nominal"],
                    "Ws1:=", ["Nominal"],
                    "sweep_face:=", ["Nominal"],
                    "riempimentoL2:=", ["Nominal"],
                    "riempimentoL2top:=", ["Nominal"],
                    "Wp2:=", ["Nominal"],
                    "L_partch:=", ["Nominal"],
                    "chamfer:=", ["Nominal"],
                    "W_patch:=", ["Nominal"],
                    "Pos_patch:=", ["Nominal"],
                    "Wp1:=", ["Nominal"],
                    "Lp2:=", ["Nominal"],
                    "Lp1:=", ["Nominal"],
                    "Ws2:=", ["Nominal"],
                    "R1:=", ["Nominal"],
                    "W2:=", ["Nominal"],
                    "h_air:=", ["Nominal"],
                    "Wgx:=", ["Nominal"],
                    "Wgy:=", ["Nominal"],
                    "R1_pad_patch:=", ["Nominal"],
                    "W3:=", ["Nominal"],
                    "Wf1:=", ["Nominal"],
                    "lenght1:=", ["Nominal"],
                    "Wport:=", ["Nominal"],
                    "L_tappo:=", ["Nominal"],
                    "l_slot:=", ["Nominal"],
                    "w4:=", ["Nominal"],
                    "x_slot:=", ["Nominal"],
                    "w_slot:=", ["Nominal"],
                    "length_slot:=", ["Nominal"],
                    "chamfer1:=", ["Nominal"],
                    "lenghtslot2:=", ["Nominal"],
                    "wslot:=", ["Nominal"],
                    "R3:=", ["Nominal"],
                    "w5:=", ["Nominal"],
                    "pcb_l:=", ["Nominal"],
                    "pcb_w:=", ["Nominal"],
                    "pcb_c:=", ["Nominal"],
                    "hPML:=", ["Nominal"],
                    "phi_scan:=", ["Nominal"],
                    "theta_scan:=", ["Nominal"],
                    "origal_x:=", ["Nominal"],
                    "origal_y:=", ["Nominal"]
                ],
                [
                    "Phi Component:=", "Phi",
                    "Theta Component:=", "Theta",
                    "Mag Component:=", ["dB(DirTheta)"]  # 这里是 Directivity Theta
                ]
            )

            # 统一导出生命周期：删旧文件→导出→读回校验（表头量名+行数）→删报告
            self._export_and_validate(report_name, file_path, "dB(DirTheta)")

    def amp_phi_cycle(self, iteration, n=16, report_prefix="ampDirectivity Plot"):
        """
        循环创建 n 个 3D Polar 方向图（Directivity Phi）
        结构与 pattern_phase、phase_phi_cycle 完全一致
        输出：dB(DirPhi)

        report_prefix：报告名前缀，默认训练侧原名 "ampDirectivity Plot"；
        测试侧传 "test_amp Plot" 与训练残留报告隔离（计划003）。
        """
        rad_field_module = self.oDesign.GetModule("RadField")
        self.oModule = self.oDesign.GetModule("ReportSetup")

        # 球存在性预检（与 amp_theta_cycle 相同，缺失即报错，防 AEDT 静默回退）
        existing_spheres = set(
            rad_field_module.GetSetupNames("Infinite Sphere") or []
        )

        base_path = self.output_root

        for idx in range(n):
            # ===== 动态构造核心命名参数 =====
            # 坐标系名称：RelativeCS0 → RelativeCS(n-1)
            coord_system = f"RelativeCS{idx + 71}"
            # Infinite Sphere名称：Infinite Sphere1 → Infinite Sphere{n}
            sphere_name = f"Infinite Sphere{idx + 1}"
            if sphere_name not in existing_spheres:
                raise RuntimeError(
                    f"{sphere_name} 不存在（amp 阶段不做补建），"
                    f"请确认 phase_theta_cycle/phase_phi_cycle 已先运行并创建 Infinite Sphere1~{n}"
                )
            # SourceContext：1:1 → n:1
            source_context = f"{idx * 2 + 1}:1"
            report_name = f"{report_prefix} {2 + idx * 2}"
            file_path = f"{base_path}train{iteration}_3D_dir_phi_{idx + 1}.csv"

            # 建前删除同名残留报告，防止 CreateReport 撞上历史定义而静默失效
            self._delete_report_quiet(report_name)

            # 创建 3D Polar Plot (dB(DirPhi))
            self.oModule.CreateReport(
                report_name,
                "Far Fields",
                "3D Polar Plot",
                "Setup1 : LastAdaptive",
                [
                    "Context:=", sphere_name,
                    "SourceContext:=", source_context
                ],
                [
                    "Phi:=", ["All"],
                    "Theta:=", ["All"],
                    "Freq:=", ["27.5GHz"],
                    "xcell:=", ["Nominal"],
                    "ycell:=", ["Nominal"],
                    "h_art9:=", ["Nominal"],
                    "h_solder:=", ["Nominal"],
                    "h_art8:=", ["Nominal"],
                    "h_sub78:=", ["Nominal"],
                    "h_art7:=", ["Nominal"],
                    "h_sub67:=", ["Nominal"],
                    "h_art6:=", ["Nominal"],
                    "h_sub56:=", ["Nominal"],
                    "h_art5:=", ["Nominal"],
                    "h_sub45:=", ["Nominal"],
                    "h_art4:=", ["Nominal"],
                    "h_sub34:=", ["Nominal"],
                    "h_art3:=", ["Nominal"],
                    "h_sub23:=", ["Nominal"],
                    "h_art2:=", ["Nominal"],
                    "h_sub12:=", ["Nominal"],
                    "h_art1:=", ["Nominal"],
                    "art_c:=", ["Nominal"],
                    "h_copper_L4:=", ["Nominal"],
                    "h_copper_L2:=", ["Nominal"],
                    "h_sub3:=", ["Nominal"],
                    "h_copper_L1:=", ["Nominal"],
                    "pos_add_layer:=", ["Nominal"],
                    "fillet:=", ["Nominal"],
                    "W1:=", ["Nominal"],
                    "Ws1:=", ["Nominal"],
                    "sweep_face:=", ["Nominal"],
                    "riempimentoL2:=", ["Nominal"],
                    "riempimentoL2top:=", ["Nominal"],
                    "Wp2:=", ["Nominal"],
                    "L_partch:=", ["Nominal"],
                    "chamfer:=", ["Nominal"],
                    "W_patch:=", ["Nominal"],
                    "Pos_patch:=", ["Nominal"],
                    "Wp1:=", ["Nominal"],
                    "Lp2:=", ["Nominal"],
                    "Lp1:=", ["Nominal"],
                    "Ws2:=", ["Nominal"],
                    "R1:=", ["Nominal"],
                    "W2:=", ["Nominal"],
                    "h_air:=", ["Nominal"],
                    "Wgx:=", ["Nominal"],
                    "Wgy:=", ["Nominal"],
                    "R1_pad_patch:=", ["Nominal"],
                    "W3:=", ["Nominal"],
                    "Wf1:=", ["Nominal"],
                    "lenght1:=", ["Nominal"],
                    "Wport:=", ["Nominal"],
                    "L_tappo:=", ["Nominal"],
                    "l_slot:=", ["Nominal"],
                    "w4:=", ["Nominal"],
                    "x_slot:=", ["Nominal"],
                    "w_slot:=", ["Nominal"],
                    "length_slot:=", ["Nominal"],
                    "chamfer1:=", ["Nominal"],
                    "lenghtslot2:=", ["Nominal"],
                    "wslot:=", ["Nominal"],
                    "R3:=", ["Nominal"],
                    "w5:=", ["Nominal"],
                    "pcb_l:=", ["Nominal"],
                    "pcb_w:=", ["Nominal"],
                    "pcb_c:=", ["Nominal"],
                    "hPML:=", ["Nominal"],
                    "phi_scan:=", ["Nominal"],
                    "theta_scan:=", ["Nominal"],
                    "origal_x:=", ["Nominal"],
                    "origal_y:=", ["Nominal"]
                ],
                [
                    "Phi Component:=", "Phi",
                    "Theta Component:=", "Theta",
                    "Mag Component:=", ["dB(DirPhi)"]  # 这里是 DirPhi
                ]
            )

            # 统一导出生命周期：删旧文件→导出→读回校验（表头量名+行数）→删报告
            self._export_and_validate(report_name, file_path, "dB(DirPhi)")

    def export_total_field_cycle(self, iteration, n=25,
                                 report_prefix="test_total Plot",
                                 sphere_name="Infinite Sphere500",
                                 coord_system="RelativeCS70"):
        """
        全源总方向图导出（计划007，仿真真实线专用）：
        建一个不绑定单端口的 Infinite Sphere + 4 个 Rectangular Plot 报告，
        报告上下文只传 Context（球），**不传 SourceContext**——AEDT 缺省即展示
        当前激励（kuidian/source_context 设好的全端口 1W/0deg）的总场
        （先例：all_directivity 录制模板只有 Context 无 SourceContext）。
        注：曾按用户拍板改用显式 25 端口列表传 SourceContext，2026-11-11 服务器
        实跑 CreateReport 抛 COM 异常（-2147024382），按计划007 预案回退缺省写法；
        n 参数保留仅为调用接口兼容。

        必须在 run()（解算完成）之后调用；仅对已解算数据建视图导出，零新增仿真。
        球先删后建（1° 网格事故教训：绝不沿用工程里可能的旧球定义）。
        导出文件名 train{iteration}_3D_total_dir_theta/dir_phi/phase_theta/phase_phi.csv
        （目录与其余 cycle 一致为 base_path 根）。
        """
        rad_field_module = self.oDesign.GetModule("RadField")
        self.oModule = self.oDesign.GetModule("ReportSetup")

        base_path = self.output_root

        # 1. 球先删后建：不查存在性直接删（不存在时 COM 报错静默忽略），
        #    杜绝旧定义（如 1° 步长）静默沿用
        try:
            rad_field_module.DeleteInfiniteSphereSetup(sphere_name)
            print(f"{sphere_name} 已存在，先删除重建")
        except Exception:
            print(f"{sphere_name} 不存在，直接创建")

        rad_field_module.InsertInfiniteSphereSetup(
            [
                f"NAME:{sphere_name}",
                "UseCustomRadiationSurface:=", False,
                "CSDefinition:=", "Theta-Phi",
                "Polarization:=", "Linear",
                "ThetaStart:=", "0deg",
                "ThetaStop:=", "180deg",
                "ThetaStep:=", "2deg",
                "PhiStart:=", "0deg",
                "PhiStop:=", "360deg",
                "PhiStep:=", "2deg",
                "UseLocalCS:=", True,
                "CoordSystem:=", coord_system
            ])

        # 2. 四个报告循环导出（量名→文件名后缀映射），结构照 amp/phase cycle；
        #    上下文只传 Context（球）不传 SourceContext——缺省即当前全端口激励总场
        quantity_files = [
            ("dB(DirTheta)", "dir_theta"),
            ("dB(DirPhi)", "dir_phi"),
            ("ang_deg(rETheta)", "phase_theta"),
            ("ang_deg(rEPhi)", "phase_phi"),
        ]
        for mag_component, file_tag in quantity_files:
            report_name = f"{report_prefix} {file_tag}"
            file_path = f"{base_path}train{iteration}_3D_total_{file_tag}.csv"

            # 建前删除同名残留报告，防止 CreateReport 撞历史定义而静默失效
            self._delete_report_quiet(report_name)

            self.oModule.CreateReport(
                report_name,
                "Far Fields",
                "Rectangular Plot",
                "Setup1 : LastAdaptive",
                [
                    "Context:=", sphere_name
                ],
                [
                    "Theta:=", ["All"],
                    "Phi:=", ["All"],
                    "Freq:=", ["27.5GHz"],
                    "xcell:=", ["Nominal"],
                    "ycell:=", ["Nominal"],
                    "h_art9:=", ["Nominal"],
                    "h_solder:=", ["Nominal"],
                    "h_art8:=", ["Nominal"],
                    "h_sub78:=", ["Nominal"],
                    "h_art7:=", ["Nominal"],
                    "h_sub67:=", ["Nominal"],
                    "h_art6:=", ["Nominal"],
                    "h_sub56:=", ["Nominal"],
                    "h_art5:=", ["Nominal"],
                    "h_sub45:=", ["Nominal"],
                    "h_art4:=", ["Nominal"],
                    "h_sub34:=", ["Nominal"],
                    "h_art3:=", ["Nominal"],
                    "h_sub23:=", ["Nominal"],
                    "h_art2:=", ["Nominal"],
                    "h_sub12:=", ["Nominal"],
                    "h_art1:=", ["Nominal"],
                    "art_c:=", ["Nominal"],
                    "h_copper_L4:=", ["Nominal"],
                    "h_copper_L2:=", ["Nominal"],
                    "h_sub3:=", ["Nominal"],
                    "h_copper_L1:=", ["Nominal"],
                    "pos_add_layer:=", ["Nominal"],
                    "fillet:=", ["Nominal"],
                    "W1:=", ["Nominal"],
                    "Ws1:=", ["Nominal"],
                    "sweep_face:=", ["Nominal"],
                    "riempimentoL2:=", ["Nominal"],
                    "riempimentoL2top:=", ["Nominal"],
                    "Wp2:=", ["Nominal"],
                    "L_partch:=", ["Nominal"],
                    "chamfer:=", ["Nominal"],
                    "W_patch:=", ["Nominal"],
                    "Pos_patch:=", ["Nominal"],
                    "Wp1:=", ["Nominal"],
                    "Lp2:=", ["Nominal"],
                    "Lp1:=", ["Nominal"],
                    "Ws2:=", ["Nominal"],
                    "R1:=", ["Nominal"],
                    "W2:=", ["Nominal"],
                    "h_air:=", ["Nominal"],
                    "Wgx:=", ["Nominal"],
                    "Wgy:=", ["Nominal"],
                    "R1_pad_patch:=", ["Nominal"],
                    "W3:=", ["Nominal"],
                    "Wf1:=", ["Nominal"],
                    "lenght1:=", ["Nominal"],
                    "Wport:=", ["Nominal"],
                    "L_tappo:=", ["Nominal"],
                    "l_slot:=", ["Nominal"],
                    "w4:=", ["Nominal"],
                    "x_slot:=", ["Nominal"],
                    "w_slot:=", ["Nominal"],
                    "length_slot:=", ["Nominal"],
                    "chamfer1:=", ["Nominal"],
                    "lenghtslot2:=", ["Nominal"],
                    "wslot:=", ["Nominal"],
                    "R3:=", ["Nominal"],
                    "w5:=", ["Nominal"],
                    "pcb_l:=", ["Nominal"],
                    "pcb_w:=", ["Nominal"],
                    "pcb_c:=", ["Nominal"],
                    "hPML:=", ["Nominal"],
                    "phi_scan:=", ["Nominal"],
                    "theta_scan:=", ["Nominal"],
                    "xcell1:=", ["Nominal"],
                    "ycell1:=", ["Nominal"],
                    "origal_x:=", ["Nominal"],
                    "origal_y:=", ["Nominal"]
                ],
                [
                    "Phi Component:=", "Phi",
                    "Theta Component:=", "Theta",
                    "Mag Component:=", [mag_component]
                ]
            )

            # 统一导出生命周期：删旧文件→导出→读回校验（表头量名+行数）→删报告
            self._export_and_validate(report_name, file_path, mag_component)
            print(f"已导出全源总场：{file_path}")

    # def pattern_amplitude(self, iteration, n=16):  # n为模式数量，默认16，可调整为8、16等
    #     """
    #     动态生成多个方向图报告并导出CSV文件
    #     :param iteration: 迭代次数（用于文件命名，模板保留该参数）
    #     :param n: 模式数量，默认16，支持8/16等自定义
    #     """
    #     # 获取ReportSetup模块
    #     self.oModule = self.oDesign.GetModule("ReportSetup")
    #
    #     # 定义基础路径（和模板保持一致）
    #     base_path = _output_root()
    #
    #     # 循环处理1到n的模式（动态范围）
    #     for i in range(0, n):  # 范围1到n，支持灵活数量
    #
    #         # 构造当前模式的参数（动态生成名称和路径）
    #         source_context = f"{i * 2 + 1}:1"  # 生成"1:1"到"n:1"
    #         report_name = f"Directivity Plot {i+1}"
    #         #file_path = f"{base_path}Directivity Plot {iteration}_{i+1}.csv"
    #         file_path = f"{base_path}Directivity Plot test{i+1}_real.csv"
    #
    #         # 创建报告（保留原始所有参数，仅动态替换source_context）
    #         self.oModule.CreateReport(
    #             report_name,
    #             "Far Fields",
    #             "Rectangular Plot",
    #             "Setup1 : LastAdaptive",
    #             [
    #                 "Context:=", "Infinite Sphere198",
    #                 "SourceContext:=", source_context
    #             ],
    #             [
    #                 # 保留原始代码中所有参数（完整复刻，未删减）
    #                 "Theta:=", ["All"],
    #                 "Phi:=", ["90deg"],
    #                 "Freq:=", ["25GHz"],  # 原始是25GHz，模板中改的2.25GHz已还原
    #                 "xcell:=", ["Nominal"],
    #                 "ycell:=", ["Nominal"],
    #                 "h_art9:=", ["Nominal"],
    #                 "h_solder:=", ["Nominal"],
    #                 "h_art8:=", ["Nominal"],
    #                 "h_sub78:=", ["Nominal"],
    #                 "h_art7:=", ["Nominal"],
    #                 "h_sub67:=", ["Nominal"],
    #                 "h_art6:=", ["Nominal"],
    #                 "h_sub56:=", ["Nominal"],
    #                 "h_art5:=", ["Nominal"],
    #                 "h_sub45:=", ["Nominal"],
    #                 "h_art4:=", ["Nominal"],
    #                 "h_sub34:=", ["Nominal"],
    #                 "h_art3:=", ["Nominal"],
    #                 "h_sub23:=", ["Nominal"],
    #                 "h_art2:=", ["Nominal"],
    #                 "h_sub12:=", ["Nominal"],
    #                 "h_art1:=", ["Nominal"],
    #                 "art_c:=", ["Nominal"],
    #                 "h_copper_L4:=", ["Nominal"],
    #                 "h_copper_L2:=", ["Nominal"],
    #                 "h_sub3:=", ["Nominal"],
    #                 "h_copper_L1:=", ["Nominal"],
    #                 "pos_add_layer:=", ["Nominal"],
    #                 "fillet:=", ["Nominal"],
    #                 "W1:=", ["Nominal"],
    #                 "Ws1:=", ["Nominal"],
    #                 "sweep_face:=", ["Nominal"],
    #                 "riempimentoL2:=", ["Nominal"],
    #                 "riempimentoL2top:=", ["Nominal"],
    #                 "Wp2:=", ["Nominal"],
    #                 "L_partch:=", ["Nominal"],
    #                 "chamfer:=", ["Nominal"],
    #                 "W_patch:=", ["Nominal"],
    #                 "Pos_patch:=", ["Nominal"],
    #                 "Wp1:=", ["Nominal"],
    #                 "Lp2:=", ["Nominal"],
    #                 "Lp1:=", ["Nominal"],
    #                 "Ws2:=", ["Nominal"],
    #                 "R1:=", ["Nominal"],
    #                 "W2:=", ["Nominal"],
    #                 "h_air:=", ["Nominal"],
    #                 "Wgx:=", ["Nominal"],
    #                 "Wgy:=", ["Nominal"],
    #                 "R1_pad_patch:=", ["Nominal"],
    #                 "W3:=", ["Nominal"],
    #                 "Wf1:=", ["Nominal"],
    #                 "lenght1:=", ["Nominal"],
    #                 "Wport:=", ["Nominal"],
    #                 "L_tappo:=", ["Nominal"],
    #                 "l_slot:=", ["Nominal"],
    #                 "w4:=", ["Nominal"],
    #                 "x_slot:=", ["Nominal"],
    #                 "w_slot:=", ["Nominal"],
    #                 "length_slot:=", ["Nominal"],
    #                 "chamfer1:=", ["Nominal"],
    #                 "lenghtslot2:=", ["Nominal"],
    #                 "wslot:=", ["Nominal"],
    #                 "R3:=", ["Nominal"],
    #                 "w5:=", ["Nominal"],
    #                 "pcb_l:=", ["Nominal"],
    #                 "pcb_w:=", ["Nominal"],
    #                 "pcb_c:=", ["Nominal"],
    #                 "hPML:=", ["Nominal"],
    #                 "phi_scan:=", ["Nominal"],
    #                 "theta_scan:=", ["Nominal"],
    #                 "xcell1:=", ["Nominal"],
    #                 "ycell1:=", ["Nominal"],
    #                 "origal_x:=", ["Nominal"],
    #                 "origal_y:=", ["Nominal"]
    #             ],
    #             [
    #                 "X Component:=", "Theta",
    #                 "Y Component:=", ["dB(DirTotal)"]
    #             ]
    #         )
    #
    #         # 导出到动态路径的CSV文件
    #         self.oModule.ExportToFile(report_name, file_path, False)

    def phase_theta_cycle(self, iteration, n=16, report_prefix="rE Plot"):
        """
        循环创建 n 个 3D Polar 方向图（rETheta 相位）

        Infinite Sphere 处理逻辑：
        1. 查询当前已经存在的 Infinite Sphere
        2. 检查 Infinite Sphere1 ~ Infinite SphereN
        3. 已存在 -> 跳过
        4. 缺失 -> 只创建缺失的

        report_prefix：报告名前缀，默认训练侧原名 "rE Plot"；
        测试侧传 "test_rE Plot" 与训练残留报告隔离（计划003）。
        """

        rad_field_module = self.oDesign.GetModule("RadField")
        self.oModule = self.oDesign.GetModule("ReportSetup")

        base_path = self.output_root

        # ==========================================================
        # 1. 查询 HFSS 当前已经存在的 Infinite Sphere
        # ==========================================================
        existing_spheres = set(
            rad_field_module.GetSetupNames("Infinite Sphere") or []
        )

        # print("当前已有 Infinite Sphere:")
        # print(existing_spheres)

        # ==========================================================
        # 2. 计算理论上应该存在的 Infinite Sphere
        # ==========================================================
        required_spheres = {
            f"Infinite Sphere{i}"
            for i in range(1, n + 1)
        }

        # ==========================================================
        # 3. 找出缺失的 Sphere
        # ==========================================================
        #missing_spheres = required_spheres - existing_spheres

        # if not missing_spheres:
        #     print(
        #         f"Infinite Sphere1 ~ Infinite Sphere{n} 全部存在，"
        #         f"无需重新创建"
        #     )
        # else:
        #     print("缺少以下 Infinite Sphere:")
        #     print(sorted(missing_spheres))

        # ==========================================================
        # 4. 后续正常循环
        # ==========================================================
        for idx in range(n):

            # RelativeCS71、RelativeCS72 ...
            coord_system = f"RelativeCS{idx + 71}"

            # Infinite Sphere1、Infinite Sphere2 ...
            sphere_name = f"Infinite Sphere{idx + 1}"

            # SourceContext
            source_context = f"{idx * 2 + 1}:1"

            # Report 名称（report_prefix 支持训练/测试前缀分离）
            report_name = f"{report_prefix} {idx * 2 + 1}"

            # 建前删除同名残留报告，防止 CreateReport 撞上历史定义而静默失效
            self._delete_report_quiet(report_name)

            # CSV 导出路径
            file_path = (
                f"{base_path}"
                f"train{iteration}_3D_phase_theta_{idx + 1}.csv"
            )

            # ======================================================
            # 5. Infinite Sphere：
            #    已存在 -> 不做任何操作
            #    不存在 -> 创建
            # ======================================================
            if sphere_name not in existing_spheres:

                print(
                    f"{sphere_name} 不存在，"
                    f"创建并绑定到 {coord_system}"
                )

                rad_field_module.InsertInfiniteSphereSetup(
                    [
                        f"NAME:{sphere_name}",
                        "UseCustomRadiationSurface:=", False,
                        "CSDefinition:=", "Theta-Phi",
                        "Polarization:=", "Linear",

                        "ThetaStart:=", "0deg",
                        "ThetaStop:=", "180deg",
                        "ThetaStep:=", "2deg",

                        "PhiStart:=", "0deg",
                        "PhiStop:=", "360deg",
                        "PhiStep:=", "2deg",

                        "UseLocalCS:=", True,
                        "CoordSystem:=", coord_system
                    ]
                )

                # 更新集合
                # 防止后续代码再次认为这个 Sphere 不存在
                existing_spheres.add(sphere_name)

            else:
                print(
                    f"{sphere_name} 已存在，跳过创建"
                )

            # ======================================================
            # 6. 创建报告
            # ======================================================
            self.oModule.CreateReport(
                report_name,
                "Far Fields",
                "3D Polar Plot",
                "Setup1 : LastAdaptive",
                [
                    "Context:=", sphere_name,
                    "SourceContext:=", source_context
                ],
                [
                    "Phi:=", ["All"],
                    "Theta:=", ["All"],
                    "Freq:=", ["27.5GHz"],

                    "xcell:=", ["Nominal"],
                    "ycell:=", ["Nominal"],
                    "h_art9:=", ["Nominal"],
                    "h_solder:=", ["Nominal"],
                    "h_art8:=", ["Nominal"],
                    "h_sub78:=", ["Nominal"],
                    "h_art7:=", ["Nominal"],
                    "h_sub67:=", ["Nominal"],
                    "h_art6:=", ["Nominal"],
                    "h_sub56:=", ["Nominal"],
                    "h_art5:=", ["Nominal"],
                    "h_sub45:=", ["Nominal"],
                    "h_art4:=", ["Nominal"],
                    "h_sub34:=", ["Nominal"],
                    "h_art3:=", ["Nominal"],
                    "h_sub23:=", ["Nominal"],
                    "h_art2:=", ["Nominal"],
                    "h_sub12:=", ["Nominal"],
                    "h_art1:=", ["Nominal"],
                    "art_c:=", ["Nominal"],
                    "h_copper_L4:=", ["Nominal"],
                    "h_copper_L2:=", ["Nominal"],
                    "h_sub3:=", ["Nominal"],
                    "h_copper_L1:=", ["Nominal"],
                    "pos_add_layer:=", ["Nominal"],
                    "fillet:=", ["Nominal"],
                    "W1:=", ["Nominal"],
                    "Ws1:=", ["Nominal"],
                    "sweep_face:=", ["Nominal"],
                    "riempimentoL2:=", ["Nominal"],
                    "riempimentoL2top:=", ["Nominal"],
                    "Wp2:=", ["Nominal"],
                    "L_partch:=", ["Nominal"],
                    "chamfer:=", ["Nominal"],
                    "W_patch:=", ["Nominal"],
                    "Pos_patch:=", ["Nominal"],
                    "Wp1:=", ["Nominal"],
                    "Lp2:=", ["Nominal"],
                    "Lp1:=", ["Nominal"],
                    "Ws2:=", ["Nominal"],
                    "R1:=", ["Nominal"],
                    "W2:=", ["Nominal"],
                    "h_air:=", ["Nominal"],
                    "Wgx:=", ["Nominal"],
                    "Wgy:=", ["Nominal"],
                    "R1_pad_patch:=", ["Nominal"],
                    "W3:=", ["Nominal"],
                    "Wf1:=", ["Nominal"],
                    "lenght1:=", ["Nominal"],
                    "Wport:=", ["Nominal"],
                    "L_tappo:=", ["Nominal"],
                    "l_slot:=", ["Nominal"],
                    "w4:=", ["Nominal"],
                    "x_slot:=", ["Nominal"],
                    "w_slot:=", ["Nominal"],
                    "length_slot:=", ["Nominal"],
                    "chamfer1:=", ["Nominal"],
                    "lenghtslot2:=", ["Nominal"],
                    "wslot:=", ["Nominal"],
                    "R3:=", ["Nominal"],
                    "w5:=", ["Nominal"],
                    "pcb_l:=", ["Nominal"],
                    "pcb_w:=", ["Nominal"],
                    "pcb_c:=", ["Nominal"],
                    "hPML:=", ["Nominal"],
                    "phi_scan:=", ["Nominal"],
                    "theta_scan:=", ["Nominal"],
                    "origal_x:=", ["Nominal"],
                    "origal_y:=", ["Nominal"]
                ],
                [
                    "Phi Component:=", "Phi",
                    "Theta Component:=", "Theta",
                    "Mag Component:=", ["ang_deg(rETheta)"]
                ]
            )

            # ======================================================
            # 7. 导出 CSV
            # ======================================================
            # 统一导出生命周期：删旧文件→导出→读回校验（表头量名+行数）→删报告
            self._export_and_validate(report_name, file_path, "ang_deg(rETheta)")

    def phase_phi_cycle(self, iteration, n=16, report_prefix="rE Plot"):
        """
        循环创建 n 个 3D Polar 方向图（rEPhi 相位）

        Infinite Sphere 处理逻辑：
        1. 查询当前已经存在的 Infinite Sphere
        2. 检查 Infinite Sphere1 ~ Infinite SphereN
        3. 已存在 -> 跳过
        4. 缺失 -> 只创建缺失的

        report_prefix：报告名前缀，默认训练侧原名 "rE Plot"；
        测试侧传 "test_rE Plot" 与训练残留报告隔离（计划003）。

        输出：ang_deg(rEPhi)
        """

        rad_field_module = self.oDesign.GetModule("RadField")
        self.oModule = self.oDesign.GetModule("ReportSetup")

        base_path = self.output_root

        # ==========================================================
        # 1. 查询 HFSS 当前已经存在的 Infinite Sphere
        # ==========================================================
        existing_spheres = set(
            rad_field_module.GetSetupNames("Infinite Sphere") or []
        )

        # ==========================================================
        # 2. 后续正常循环
        # ==========================================================
        for idx in range(n):

            # RelativeCS71、RelativeCS72 ...
            coord_system = f"RelativeCS{idx + 71}"

            # Infinite Sphere1、Infinite Sphere2 ...
            sphere_name = f"Infinite Sphere{idx + 1}"

            # SourceContext
            source_context = f"{idx * 2 + 1}:1"

            # Report名称（report_prefix 支持训练/测试前缀分离）
            report_name = f"{report_prefix} {2 + idx * 2}"

            # 建前删除同名残留报告，防止 CreateReport 撞上历史定义而静默失效
            self._delete_report_quiet(report_name)

            # CSV路径
            file_path = (
                f"{base_path}"
                f"train{iteration}_3D_phase_phi_{idx + 1}.csv"
            )

            # ======================================================
            # 3. Infinite Sphere：
            #    已存在 -> 不做任何操作
            #    不存在 -> 创建
            # ======================================================
            if sphere_name not in existing_spheres:

                print(
                    f"{sphere_name} 不存在，"
                    f"创建并绑定到 {coord_system}"
                )

                rad_field_module.InsertInfiniteSphereSetup(
                    [
                        f"NAME:{sphere_name}",
                        "UseCustomRadiationSurface:=", False,
                        "CSDefinition:=", "Theta-Phi",
                        "Polarization:=", "Linear",

                        "ThetaStart:=", "0deg",
                        "ThetaStop:=", "180deg",
                        "ThetaStep:=", "2deg",

                        "PhiStart:=", "0deg",
                        "PhiStop:=", "360deg",
                        "PhiStep:=", "2deg",

                        "UseLocalCS:=", True,
                        "CoordSystem:=", coord_system
                    ]
                )

                existing_spheres.add(sphere_name)

            else:
                print(
                    f"{sphere_name} 已存在，跳过创建"
                )

            # ======================================================
            # 4. 创建 3D Polar Plot (rEPhi)
            # ======================================================
            self.oModule.CreateReport(
                report_name,
                "Far Fields",
                "3D Polar Plot",
                "Setup1 : LastAdaptive",
                [
                    "Context:=", sphere_name,
                    "SourceContext:=", source_context
                ],
                [
                    "Phi:=", ["All"],
                    "Theta:=", ["All"],
                    "Freq:=", ["27.5GHz"],

                    "xcell:=", ["Nominal"],
                    "ycell:=", ["Nominal"],
                    "h_art9:=", ["Nominal"],
                    "h_solder:=", ["Nominal"],
                    "h_art8:=", ["Nominal"],
                    "h_sub78:=", ["Nominal"],
                    "h_art7:=", ["Nominal"],
                    "h_sub67:=", ["Nominal"],
                    "h_art6:=", ["Nominal"],
                    "h_sub56:=", ["Nominal"],
                    "h_art5:=", ["Nominal"],
                    "h_sub45:=", ["Nominal"],
                    "h_art4:=", ["Nominal"],
                    "h_sub34:=", ["Nominal"],
                    "h_art3:=", ["Nominal"],
                    "h_sub23:=", ["Nominal"],
                    "h_art2:=", ["Nominal"],
                    "h_sub12:=", ["Nominal"],
                    "h_art1:=", ["Nominal"],
                    "art_c:=", ["Nominal"],
                    "h_copper_L4:=", ["Nominal"],
                    "h_copper_L2:=", ["Nominal"],
                    "h_sub3:=", ["Nominal"],
                    "h_copper_L1:=", ["Nominal"],
                    "pos_add_layer:=", ["Nominal"],
                    "fillet:=", ["Nominal"],
                    "W1:=", ["Nominal"],
                    "Ws1:=", ["Nominal"],
                    "sweep_face:=", ["Nominal"],
                    "riempimentoL2:=", ["Nominal"],
                    "riempimentoL2top:=", ["Nominal"],
                    "Wp2:=", ["Nominal"],
                    "L_partch:=", ["Nominal"],
                    "chamfer:=", ["Nominal"],
                    "W_patch:=", ["Nominal"],
                    "Pos_patch:=", ["Nominal"],
                    "Wp1:=", ["Nominal"],
                    "Lp2:=", ["Nominal"],
                    "Lp1:=", ["Nominal"],
                    "Ws2:=", ["Nominal"],
                    "R1:=", ["Nominal"],
                    "W2:=", ["Nominal"],
                    "h_air:=", ["Nominal"],
                    "Wgx:=", ["Nominal"],
                    "Wgy:=", ["Nominal"],
                    "R1_pad_patch:=", ["Nominal"],
                    "W3:=", ["Nominal"],
                    "Wf1:=", ["Nominal"],
                    "lenght1:=", ["Nominal"],
                    "Wport:=", ["Nominal"],
                    "L_tappo:=", ["Nominal"],
                    "l_slot:=", ["Nominal"],
                    "w4:=", ["Nominal"],
                    "x_slot:=", ["Nominal"],
                    "w_slot:=", ["Nominal"],
                    "length_slot:=", ["Nominal"],
                    "chamfer1:=", ["Nominal"],
                    "lenghtslot2:=", ["Nominal"],
                    "wslot:=", ["Nominal"],
                    "R3:=", ["Nominal"],
                    "w5:=", ["Nominal"],
                    "pcb_l:=", ["Nominal"],
                    "pcb_w:=", ["Nominal"],
                    "pcb_c:=", ["Nominal"],
                    "hPML:=", ["Nominal"],
                    "phi_scan:=", ["Nominal"],
                    "theta_scan:=", ["Nominal"],
                    "origal_x:=", ["Nominal"],
                    "origal_y:=", ["Nominal"]
                ],
                [
                    "Phi Component:=", "Phi",
                    "Theta Component:=", "Theta",
                    "Mag Component:=", ["ang_deg(rEPhi)"]
                ]
            )

            # ======================================================
            # 5. 导出 CSV
            # ======================================================
            # 统一导出生命周期：删旧文件→导出→读回校验（表头量名+行数）→删报告
            self._export_and_validate(report_name, file_path, "ang_deg(rEPhi)")

    # def pattern_phase(self, iteration, n=16):  # n为总数量，默认16，可调整为8、16等
    #     """
    #     动态生成n个Infinite Sphere设置 + n个Phase方向图报告，导出CSV文件
    #     :param iteration: 迭代次数（用于文件命名）
    #     :param n: 模式数量，默认16，支持8/16等自定义
    #     """
    #     # 1. 获取RadField模块（创建Infinite Sphere）和ReportSetup模块（创建报告）
    #     rad_field_module = self.oDesign.GetModule("RadField")
    #     self.oModule = self.oDesign.GetModule("ReportSetup")
    #
    #     # 2. 定义基础路径（和模板保持一致）
    #     base_path = _output_root()
    #
    #     # 3. 循环处理n个模式（索引0到n-1，对应1到n的命名）
    #     for idx in range(n):  # 0到n-1，共n个元素
    #         # ===== 动态构造核心命名参数 =====
    #         # 坐标系名称：RelativeCS0 → RelativeCS(n-1)
    #         coord_system = f"RelativeCS{idx + 71}"
    #         # Infinite Sphere名称：Infinite Sphere1 → Infinite Sphere{n}
    #         sphere_name = f"Infinite Sphere{idx + 1}"
    #         # SourceContext：1:1 → n:1
    #         source_context = f"{idx * 2 + 1}:1"
    #         # 报告名称：Phase Plot 1 → Phase Plot{n}
    #         report_name = f"Phase Plot {idx + 1}"
    #         # 文件路径（保留模板两种命名方式，注释切换）
    #         # file_path = f"{base_path}Phase Plot {iteration}_{idx + 1}.csv"  # 含迭代次数
    #         file_path = f"{base_path}Phase Plot test{idx + 1}_real.csv"  # 测试命名
    #
    #         # ===== 步骤1：创建当前模式的Infinite Sphere设置 =====
    #         rad_field_module.InsertInfiniteSphereSetup(
    #             [
    #                 f"NAME:{sphere_name}",  # 动态球体名称
    #                 "UseCustomRadiationSurface:=", False,
    #                 "CSDefinition:=", "Theta-Phi",
    #                 "Polarization:=", "Linear",
    #                 "ThetaStart:=", "-90deg",
    #                 "ThetaStop:=", "90deg",
    #                 "ThetaStep:=", "2deg",
    #                 "PhiStart:=", "45deg",
    #                 "PhiStop:=", "45deg",
    #                 "PhiStep:=", "0deg",
    #                 "UseLocalCS:=", True,
    #                 "CoordSystem:=", coord_system  # 关联动态坐标系
    #             ])
    #
    #         # ===== 步骤2：创建当前模式的Phase报告 =====
    #         self.oModule.CreateReport(
    #             report_name,
    #             "Far Fields",
    #             "Rectangular Plot",
    #             "Setup1 : LastAdaptive",
    #             [
    #                 "Context:=", sphere_name,  # 关联当前Infinite Sphere
    #                 "SourceContext:=", source_context  # 动态SourceContext
    #             ],
    #             [
    #                 # 保留原始代码中所有参数（完整复刻，未删减）
    #                 "Theta:=", ["All"],
    #                 "Phi:=", ["45deg"],
    #                 "Freq:=", ["25GHz"],
    #                 "xcell:=", ["Nominal"],
    #                 "ycell:=", ["Nominal"],
    #                 "h_art9:=", ["Nominal"],
    #                 "h_solder:=", ["Nominal"],
    #                 "h_art8:=", ["Nominal"],
    #                 "h_sub78:=", ["Nominal"],
    #                 "h_art7:=", ["Nominal"],
    #                 "h_sub67:=", ["Nominal"],
    #                 "h_art6:=", ["Nominal"],
    #                 "h_sub56:=", ["Nominal"],
    #                 "h_art5:=", ["Nominal"],
    #                 "h_sub45:=", ["Nominal"],
    #                 "h_art4:=", ["Nominal"],
    #                 "h_sub34:=", ["Nominal"],
    #                 "h_art3:=", ["Nominal"],
    #                 "h_sub23:=", ["Nominal"],
    #                 "h_art2:=", ["Nominal"],
    #                 "h_sub12:=", ["Nominal"],
    #                 "h_art1:=", ["Nominal"],
    #                 "art_c:=", ["Nominal"],
    #                 "h_copper_L4:=", ["Nominal"],
    #                 "h_copper_L2:=", ["Nominal"],
    #                 "h_sub3:=", ["Nominal"],
    #                 "h_copper_L1:=", ["Nominal"],
    #                 "pos_add_layer:=", ["Nominal"],
    #                 "fillet:=", ["Nominal"],
    #                 "W1:=", ["Nominal"],
    #                 "Ws1:=", ["Nominal"],
    #                 "sweep_face:=", ["Nominal"],
    #                 "riempimentoL2:=", ["Nominal"],
    #                 "riempimentoL2top:=", ["Nominal"],
    #                 "Wp2:=", ["Nominal"],
    #                 "L_partch:=", ["Nominal"],
    #                 "chamfer:=", ["Nominal"],
    #                 "W_patch:=", ["Nominal"],
    #                 "Pos_patch:=", ["Nominal"],
    #                 "Wp1:=", ["Nominal"],
    #                 "Lp2:=", ["Nominal"],
    #                 "Lp1:=", ["Nominal"],
    #                 "Ws2:=", ["Nominal"],
    #                 "R1:=", ["Nominal"],
    #                 "W2:=", ["Nominal"],
    #                 "h_air:=", ["Nominal"],
    #                 "Wgx:=", ["Nominal"],
    #                 "Wgy:=", ["Nominal"],
    #                 "R1_pad_patch:=", ["Nominal"],
    #                 "W3:=", ["Nominal"],
    #                 "Wf1:=", ["Nominal"],
    #                 "lenght1:=", ["Nominal"],
    #                 "Wport:=", ["Nominal"],
    #                 "L_tappo:=", ["Nominal"],
    #                 "l_slot:=", ["Nominal"],
    #                 "w4:=", ["Nominal"],
    #                 "x_slot:=", ["Nominal"],
    #                 "w_slot:=", ["Nominal"],
    #                 "length_slot:=", ["Nominal"],
    #                 "chamfer1:=", ["Nominal"],
    #                 "lenghtslot2:=", ["Nominal"],
    #                 "wslot:=", ["Nominal"],
    #                 "R3:=", ["Nominal"],
    #                 "w5:=", ["Nominal"],
    #                 "pcb_l:=", ["Nominal"],
    #                 "pcb_w:=", ["Nominal"],
    #                 "pcb_c:=", ["Nominal"],
    #                 "hPML:=", ["Nominal"],
    #                 "phi_scan:=", ["Nominal"],
    #                 "theta_scan:=", ["Nominal"],
    #                 "xcell1:=", ["Nominal"],
    #                 "ycell1:=", ["Nominal"],
    #                 "origal_x:=", ["Nominal"],
    #                 "origal_y:=", ["Nominal"]
    #             ],
    #             [
    #                 "X Component:=", "Theta",
    #                 "Y Component:=", ["cang_deg(rEL3X)"]  # rE替换为Phase
    #             ]
    #         )
    #
    #         # ===== 步骤3：导出当前模式的报告到CSV =====
    #         self.oModule.ExportToFile(report_name, file_path, False)

    def all_directivity(self, n):
        # 计算Sphere编号：初始200 + (n-1)，n=1→200, n=2→201, ...
        sphere_number = 300 + (n - 1)
        sphere_name = f"Infinite Sphere{sphere_number}"
        coord_system = f"RelativeCS70"

        self.oModule = self.oDesign.GetModule("RadField")
        self.oModule.InsertInfiniteSphereSetup(
            [
                f"NAME:{sphere_name}",  # 使用动态生成的Sphere名称
                "UseCustomRadiationSurface:=", False,
                "CSDefinition:=", "Theta-Phi",
                "Polarization:=", "Linear",
                "ThetaStart:=", "0deg",
                "ThetaStop:="   , "180deg",
                "ThetaStep:="      , "2deg",
                "PhiStart:="       , "0deg",
                "PhiStop:="    , ".60deg",
                "PhiStep:="    , "2deg",
                "UseLocalCS:="     , False,
                "CoordSystem:=", coord_system  # 关联动态坐标系
            ])

        self.oModule = self.oDesign.GetModule("ReportSetup")
        # 动态生成报告名称：Directivity Plot {sphere_number}_{n}
        report_name = f"Directivity Plot {sphere_number}_{n}"
        # 动态生成导出文件路径：all_directivity_{n}.csv
        export_path = f"{self.output_root}test_2_directivity_{n}.csv"
        self.oModule.CreateReport(report_name, "Far Fields", "Rectangular Plot", "Setup1 : LastAdaptive",
                             [
                                 "Context:="    , sphere_name
                             ],
                             [
                                 "Theta:="     , ["All"],
                                 "Phi:=", ["All"],
                                 "Freq:="      , ["27.5GHz"],
                                 "xcell:="     , ["Nominal"],
                                 "ycell:="     , ["Nominal"],
                                 "h_art9:="    , ["Nominal"],
                                 "h_solder:="      , ["Nominal"],
                                 "h_art8:="    , ["Nominal"],
                                 "h_sub78:="       , ["Nominal"],
                                 "h_art7:="    , ["Nominal"],
                                 "h_sub67:="       , ["Nominal"],
                                 "h_art6:="    , ["Nominal"],
                                 "h_sub56:="       , ["Nominal"],
                                 "h_art5:="    , ["Nominal"],
                                 "h_sub45:="       , ["Nominal"],
                                 "h_art4:="    , ["Nominal"],
                                 "h_sub34:="       , ["Nominal"],
                                 "h_art3:="    , ["Nominal"],
                                 "h_sub23:="       , ["Nominal"],
                                 "h_art2:="    , ["Nominal"],
                                 "h_sub12:="       , ["Nominal"],
                                 "h_art1:="    , ["Nominal"],
                                 "art_c:="     , ["Nominal"],
                                 "h_copper_L4:="       , ["Nominal"],
                                 "h_copper_L2:="       , ["Nominal"],
                                 "h_sub3:="    , ["Nominal"],
                                 "h_copper_L1:="       , ["Nominal"],
                                 "pos_add_layer:="  , ["Nominal"],
                                 "fillet:="    , ["Nominal"],
                                 "W1:="       , ["Nominal"],
                                 "Ws1:="          , ["Nominal"],
                                 "sweep_face:="    , ["Nominal"],
                                 "riempimentoL2:="  , ["Nominal"],
                                 "riempimentoL2top:="   , ["Nominal"],
                                 "Wp2:="          , ["Nominal"],
                                 "L_partch:="      , ["Nominal"],
                                 "chamfer:="       , ["Nominal"],
                                 "W_patch:="       , ["Nominal"],
                                 "Pos_patch:="     , ["Nominal"],
                                 "Wp1:="          , ["Nominal"],
                                 "Lp2:="          , ["Nominal"],
                                 "Lp1:="          , ["Nominal"],
                                 "Ws2:="          , ["Nominal"],
                                 "R1:="       , ["Nominal"],
                                 "W2:="       , ["Nominal"],
                                 "h_air:="     , ["Nominal"],
                                 "Wgx:="          , ["Nominal"],
                                 "Wgy:="          , ["Nominal"],
                                 "R1_pad_patch:="   , ["Nominal"],
                                 "W3:="       , ["Nominal"],
                                 "Wf1:="          , ["Nominal"],
                                 "lenght1:="       , ["Nominal"],
                                 "Wport:="     , ["Nominal"],
                                 "L_tappo:="       , ["Nominal"],
                                 "l_slot:="    , ["Nominal"],
                                 "w4:="       , ["Nominal"],
                                 "x_slot:="    , ["Nominal"],
                                 "w_slot:="    , ["Nominal"],
                                 "length_slot:="       , ["Nominal"],
                                 "chamfer1:="      , ["Nominal"],
                                 "lenghtslot2:="       , ["Nominal"],
                                 "wslot:="     , ["Nominal"],
                                 "R3:="       , ["Nominal"],
                                 "w5:="       , ["Nominal"],
                                 "pcb_l:="     , ["Nominal"],
                                 "pcb_w:="     , ["Nominal"],
                                 "pcb_c:="     , ["Nominal"],
                                 "hPML:="      , ["Nominal"],
                                 "phi_scan:="      , ["Nominal"],
                                 "theta_scan:="    , ["Nominal"],
                                 "origal_x:="      , ["Nominal"],
                                 "origal_y:="      , ["Nominal"]
                             ],
                             [
                                "Phi Component:=", "Phi",
                                "Theta Component:=", "Theta",
                                "Mag Component:="      , ["dB(DirTotal)"]
                             ])
        # 导出文件时使用动态名称和路径
        self.oModule.ExportToFile(report_name, export_path, False)


    def delete(self, n):
            # self.oModule.DeleteReports(["Directivity Plot 1", "Directivity Plot 2", "Directivity Plot 3", "Directivity Plot 4", "Directivity Plot 5", "Directivity Plot 6", "Directivity Plot 7", "Directivity Plot 8", "Directivity Plot 9"])
            # self.oModule.DeleteReports([
            #     "rE Plot 1", "rE Plot 2", "rE Plot 3", "rE Plot 4", "rE Plot 5",
            #     "rE Plot 6", "rE Plot 7", "rE Plot 8", "rE Plot 9", "rE Plot 10",
            #     "rE Plot 11", "rE Plot 12", "rE Plot 13", "rE Plot 14", "rE Plot 15",
            #     "rE Plot 16", "rE Plot 17", "rE Plot 18"
            # ])

        # self.oEditor.SetWCS(
        #     [
        #         "NAME:SetWCS Parameter",
        #         "Working Coordinate System:=", "RelativeCS71",
        #         "RegionDepCSOk:=", False
        #     ])
        # ============================================================
        # 2. 删除 RelativeCS71 ~ RelativeCS(70 + n^2)
        # ============================================================

        # 获取 HFSS 当前存在的所有坐标系
        existing_cs = set(self.oEditor.GetCoordinateSystems())

        # 根据 n 生成理论上需要删除的坐标系
        relative_names = [
            f"RelativeCS{i}"
            for i in range(72, 72 + n ** 2)
        ]

        # 只保留 HFSS 中实际存在的坐标系
        relative_to_delete = [
            name for name in relative_names
            if name in existing_cs
        ]

        # 有东西才调用 Delete，避免传空字符串
        if relative_to_delete:
            self.oEditor.Delete(
                [
                    "NAME:Selections",
                    "Selections:=", ",".join(relative_to_delete)
                ]
            )

        # ============================================================
        # 3. 获取 HFSS 当前存在的几何对象
        # ============================================================

        existing_objects = set()

        # Box / art 可能属于 Solid、Sheet、Line 等不同类型，
        # 所以这里统一获取
        for group in ["Solids", "Sheets", "Lines", "Unclassified"]:
            try:
                objects = self.oEditor.GetObjectsInGroup(group)
                existing_objects.update(objects)
            except Exception:
                pass

        # ============================================================
        # 4. 删除 Box61_1 ~ Box61_n^2
        # ============================================================

        box_names = [
            f"Box61_{i}"
            for i in range(1, 1 + n ** 2)
        ]

        box_to_delete = [
            name for name in box_names
            if name in existing_objects
        ]

        if box_to_delete:
            self.oEditor.Delete(
                [
                    "NAME:Selections",
                    "Selections:=", ",".join(box_to_delete)
                ]
            )

        # ============================================================
        # 5. 删除 art01_1 ~ art01_n^2
        # ============================================================

        art_names = [
            f"art01_{i}"
            for i in range(1, 1 + n ** 2)
        ]

        art_to_delete = [
            name for name in art_names
            if name in existing_objects
        ]

        if art_to_delete:
            self.oEditor.Delete(
                [
                    "NAME:Selections",
                    "Selections:=", ",".join(art_to_delete)
                ]
            )

        # ============================================================
        # 6. 删除 Box60
        # ============================================================

        if "Box60" in existing_objects:
            self.oEditor.Delete(
                [
                    "NAME:Selections",
                    "Selections:=", "Box60"
                ]
            )

        # ============================================================
        # 7. 获取 ReportSetup Module
        # ============================================================

        self.oModule = self.oDesign.GetModule("ReportSetup")

