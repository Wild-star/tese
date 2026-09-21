# 矿区自动驾驶 3D 占用网格 GT 生成系统 —— 完整技术文档

> 代码基准：`ec05777`（P19 收敛）　·　主脚本 `eq_generate_fusionoccupancy_nuscenes_V10_qhc.py`（3121 行）
> 本文档为**单一权威技术文档**，合并了原《实验报告》《算法深潜》《技术文档》三份内容，
> 并对每个关键算法节点给出完善的思路、数学推导、伪代码、参数与复杂度。
> 数据集：`qhc_gt_test`（259 场景 / 14008 关键帧 / 148005 标注框）　·　运行模式：6 worker 并行全量

---

## 目录

**Part A 总览**
1. [项目概述](#1-项目概述)
2. [数据集与配置](#2-数据集与配置)
3. [系统架构与总体流程](#3-系统架构与总体流程)

**Part B 算法详解（关键节点完整细节）**
4. [数据加载（eq_nuscenes）](#4-数据加载eq_nuscenes)
5. [帧收集（关键帧 + v1.3 sweep 静态点采集）](#5-帧收集关键帧--v13-sweep-静态点采集)
6. [动静分类（motion.py）](#6-动静分类motionpy)
7. [位姿配准（ICP 完整数学推导）](#7-位姿配准icp-完整数学推导)
8. [掩码生成（ray casting 完整推导）](#8-掩码生成ray-casting-完整推导)
9. [多层融合（T1/T2/T3 完整伪代码）](#9-多层融合t1t2t3-完整伪代码)
10. [框点采样与贴回（process_multi_sensor_point）](#10-框点采样与贴回process_multi_sensor_point)
11. [体素化（process_points_vectorized，优先级写入）](#11-体素化process_points_vectorized优先级写入)
12. [KNN 增密（densify_by_knn 复杂度）](#12-knn-增密densify_by_knn-复杂度)
13. [标签映射 + 保存（save_result payload）](#13-标签映射--保存save_result-payload)

**Part C 版本演进与审查**
14. [版本演进与任务记录（P14–P19）](#14-版本演进与任务记录p14p19)
15. [代码审查发现（H/M/L 分级）](#15-代码审查发现hml-分级)

**Part D 全量运行与验证**
16. [全量运行配置与执行](#16-全量运行配置与执行)
17. [运行时间记录与估算](#17-运行时间记录与估算)
18. [对比实验（Gate A：V10 vs V3）](#18-对比实验gate-av10-vs-v3)

**Part E 附录**
19. [关键缺陷与改进建议](#19-关键缺陷与改进建议)
20. [结论](#20-结论)
21. [附录：基于本项目的简历信息](#21-附录基于本项目的简历信息)

---

# Part A 总览

## 1. 项目概述

### 1.1 目标
为矿区（露天矿）自动驾驶构建**可训练的 3D 语义占用网格真值（GT）生成系统**：输入 nuScenes 格式多传感器 LiDAR 点云 + 人标 3D 框 + lidarseg 语义，输出每关键帧的稠密占用网格 `labels.npz`，供下游 3D 占用预测模型训练。

### 1.2 核心难点

| 难点 | 说明 |
|---|---|
| 点云稀疏 | 单帧只覆盖可见表面，体素大量空洞 → 多帧/多传感器融合 + 增密 |
| 动/静分离 | 移动车不可进静态背景与跨帧增密；非刚体机械（挖机/装载机）全路径排除 |
| 标签空间 | 原始 72 类（0–71）↔ 训练 7 类，需解耦「内部逻辑」与「写盘输出」 |
| 跨帧对齐 | 多帧点云配准到当前帧（位姿粗配准 + ICP），矿区 160m×154m、遮挡重 |
| 掩码语义 | 训练只用「当前关键帧射线可达」体素，否则 CrossEntropy 无法监督 |

### 1.3 交付物
`V10 主脚本`(3121 行) · `until.py`(1249 行，融合/增密/配准/掩码) · `motion.py`(181 行，动静分类) · `get_mask.py`(403 行，ray casting) · `run_parallel_generate.py` + `run_v10_full_timed.sh` · `icp_numpy.py`(死代码归档)

---

## 2. 数据集与配置

### 2.1 数据集
| 项 | 值 |
|---|---|
| 路径 | `/e-vepfs-01/perception/hongwei/data/qhc_data/qhc_gt_test` |
| 场景 | 259（每场景 28–58 帧，均值 54.1，中位 56） |
| 关键帧 | 14008 帧 |
| 标注框 | 148005 |
| 传感器 | 4 路 LiDAR（LIDAR_TOP 为主，另有 3 路副传感器） |
| 输出结构 | `save_path/<bag>/<scene_name>/<frame_token>/labels.npz` |

自定义 `NuScenes` 为**按场景分表**：`nusc.scene/sample/sample_annotation/instance/log[indice]` 均为「每场景一个 list」。

### 2.2 配置
| 文件 | voxel_size | pc_range | occ_size | self_range |
|---|---|---|---|---|
| `config_ysj_smallrange.yaml`（全量用） | [0.15,0.15,0.1] | [-31.8,-76.8,-4.4,121.79,76.79,8.39] | [1024,1024,128] | [-10,-3.3,-100,0.9,3.3,100] |
| `config_ysj.yaml`（标准） | [0.3,0.24,0.1] | [-50.4,-80.64,-4.4,151.19,80.63,8.39] | [672,672,128] | 同上 |

### 2.3 标签映射
| 文件 | 性质 | 说明 |
|---|---|---|
| `nuscenes.yaml`（全量用） | **恒等** 0–71 | 输出保留原始 lidarseg id；含 `71=dumppile` |
| `nuscenes_new.yaml`（仅服务器） | 72→7 | 压缩 7 类，多 key `72` |
| `nuscenes_ori*.yaml`（禁用备份） | 缺 71 | 历史备份 |

**核心设计（P17）**：内部逻辑**始终用原始 0–71**（动/静名单、非刚体、增密全基于原始 id），`learning_map` 只在写盘前应用 → 72 类/7 类切换只改 `--label_mapping`。

---

## 3. 系统架构与总体流程

```
run_parallel_generate.py（6 worker，各自 --start/--end + 独立 _w{i} 目录，跑完原子合并）
        │  每 worker: python3 V10 --start s --end e
        ▼  主循环 for scene_idx in [start,end): print "processing sequence" → main1() → print "程序运行时间"
main1() 内部八步：
  ① 帧收集   关键帧→dict_list[sensor]；sweep→sweep_list（v1.3 静态点）
  ② 动静分类 motion.classify_instances → 5 种 MotionState
  ③ 位姿配准 粗配准(位姿链) → Open3D point-to-plane ICP → 去 yaw/xy → 累积地图
  ④ 掩码生成 ray casting：当前帧∪邻帧∪sweep 射线终点 → lidar_mask
  ⑤ 多层融合 T1(门控改标签)/T2(掩码内增密)/T3(掩码外+遮挡测试)
  ⑥ 体素化   process_points_vectorized（优先级写入 box>current>neighbor>sweep）
  ⑦ KNN 增密 densify_by_knn（6 邻域标签传播，默认关）
  ⑧ 保存     save_result → labels.npz
```

**单一事实来源**：动/静类别名单只在 `motion.py` 定义，V10/until 统一引用，V10:99 `assert` 防漂移。

---

# Part B 算法详解

## 4. 数据加载（eq_nuscenes）

- 加载 v1.0 表：category(71) / sensor(13) / calibrated_sensor(11) / ego_pose / scene(259) / sample(14008) / sample_annotation(148005)。
- 按场景 reverse-index：`nusc.sample[indice]` 等为每场景 list。
- `get_sample_data_multi(indice, token)` → `(lidar_path, boxes_ego系, _)`；`lidar_path` 倒数第 5 级目录 = bag 名 = `folder_name`。

---

## 5. 帧收集（关键帧 + v1.3 sweep 静态点采集）

### 5.1 主循环（V10:1502–1960）
对每个传感器沿 `sample_data.next` 链 `while True` 推进：关键帧 → 读点云+box 进 `dict_list[sensor]`；非关键帧（sweep）→ `use_v13_sweeps` 时采静态点进 `sweep_list`。

### 5.2 `collect_one_sweep_static`（V10:407，完整细节）
```
读 sweep .bin (N,4) + v1.3 lidarseg (N,1 uint8)
# P1 修复：pc 与 label 行数不匹配时「联合去重」
if pc 行数 != label 行数:
    unique_idx = unique(pc[:,:3]) 排序
    若 unique_idx 数 == label 行数 → pc = pc[unique_idx]
    否则 return None（跳过该 sweep）
points_label = points_label.astype(int32)   # 防 concat(float32,uint8)->float32 精度翻转
pc_with_semantic = [pc.xyz, label]
pc_with_semantic = filter_static_semantic_points(...)   # 只留静态类
lidar_to_world_to_lidar(pc, sweep标定/位姿, 帧0标定/位姿)   # 变到该雷达首帧 SENSOR 系
返回 dict{is_key_frame=False, label_source="auto", timestamp_s, ...}
```

### 5.3 邻帧/sweep 距离窗选取（V10:494 / 578）
- `coarse_register_to_current_frame_dist`：邻关键帧取「ego 平移距离 ≤ dist_window(8m)」；不足 `min_neighbor(2)` 时按距离补最近帧（停车/蠕行兜底）；超过 `max_neighbor(8)` 时只留最近 N 帧（防停车爆帧）。
- sweep 同理，`max_sweep_frames(128)` 防爆帧。

---

## 6. 动静分类（motion.py）

### 6.1 状态空间
```
MotionState: STATIC_RIGID=0 | DYNAMIC_RIGID=1 | NONRIGID=2 | DUST=3 | UNKNOWN=4
```
把「静/动 × 刚体/非刚体」折叠为单枚举。**单一事实来源名单**：

| 名单 | 值 | 用途 |
|---|---|---|
| `NONRIGID_CATEGORY_NAMES` | loader(2), excavator(3), breakinghammer(4), electric_loader(47), excavator_base(70) | 有框非刚体 |
| `NONRIGID_CLASS_IDS` | {2,3,4,29,47,70} | 非刚体 lidarseg id（含无框 dust=29） |
| `STATIC_OCC_CLASS_IDS` | {18,21,22,24,25,26,27,28,30,36,40,71} | 静态地形白名单 |

### 6.2 分类算法（速度信号 = 跨帧 box 中心位移 / dt）
```
classify_instances(instances, annotations, samples, cat_name_by_token, thr=0.5):
    rows_by_inst = group annotations by instance_token
    for it, rows in rows_by_inst:
        if cat ∈ NONRIGID_CATEGORY_NAMES → NONRIGID
        if len(rows) < 2 → DYNAMIC_RIGID           # 单帧无运动证据，保守排除
        rows.sort(by sample timestamp)
        dt_i = ts[i]-ts[i-1] (>0)；speed_i = ‖trans[i]-trans[i-1]‖ / (dt_i/1e6)
        median_speed = median(speeds)
        → STATIC_RIGID 若 median_speed < 0.5 否则 DYNAMIC_RIGID
```
**阈值标定**（P19 实测 5 场景 69 instance，dt 中位 0.5s）：静态抖动 p50≈0.20 m/s，移动卡车 1–4 m/s（p90≈2.1，max≈11.7）；0.5 m/s 留 ~2.5× 余量。可 `--motion_speed_threshold` 覆盖。

### 6.3 点级掩码
`static_geometry_mask(labels)=isin(labels, STATIC_OCC_CLASS_IDS)`；`nonrigid_mask(labels)=isin(labels, NONRIGID_CLASS_IDS)`。

---

## 7. 位姿配准（ICP 完整数学推导）

### 7.1 刚体变换与坐标链
SE(3) `T=[R t;0 1]`，点变换 `p'=Rp+t`。旋转 R ↔ 四元数 / 欧拉角（`zyx` 序，yaw=第 0 角）。
`lidar_to_world_to_lidar`（until.py:630）五步链：`源lidar→(R_cal,t_cal)→源ego→(R_ego,t_ego)→world→(−t_ego_tgt,R_ego_tgtᵀ)→目标ego→(−t_cal_tgt,R_cal_tgtᵀ)→目标lidar`，即「lidar→world→目标lidar」粗配准。

### 7.2 Point-to-Point：Kabsch / SVD（参考实现 icp_numpy.py:40）
最小化 `Σ‖Rp_i+t−q_i‖²`：
```
c_p=mean(p), c_q=mean(q)；p̃=p−c_p, q̃=q−c_q
H = P̃ᵀQ̃ → SVD: H=UΣVᵀ → R=VUᵀ（det R<0 时 V 末列取反，R=V·diag(1,1,−1)·Uᵀ）
t = c_q − R c_p
```

### 7.3 Point-to-Plane：线性化 6DoF（主流程实际采用）
主流程用 Open3D `registration_icp(..., TransformationEstimationPointToPlane())`（V10:2292/2393），最小化 `Σ(n_iᵀ(Rp_i+t−q_i))²`。小角线性化（ω=旋转向量，`nᵀ(ω×p)=(p×n)ᵀω`）：
```
e_i ≈ (p_i×n_i)ᵀω + n_iᵀt + n_iᵀ(p_i−q_i)；x=[ω;t]
A_i=[(p_i×n_i)ᵀ, n_iᵀ],  b_i=n_iᵀ(q_i−p_i)  →  lstsq(A,b)
R = I + (sinθ/θ)K + ((1−cosθ)/θ²)K²  (Rodrigues),  t=x[3:6]
```

### 7.4 去 yaw + 约束 xy
默认 `--icp_keep_yaw 0`：`rotate=remove_yaw_from_rotation_matrix(R)`（zyx 欧拉 yaw=0 后重组，until.py:690），`trans[:2]=0` → ICP 只修 **z/roll/pitch**，x/y/yaw 信任 ego（矿区 yaw 抖动大）。

### 7.5 ICP 循环（V10:2181–2489，完整细节）
```
criteria: relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=50
threshold=0.3m；icp_voxel_size=0.1m（仅配准用 voxel_down_sample）
for 每关键帧 i:
    邻帧 = 距离窗选取（已粗配准到当前帧系）
    keyframe_map = 当前帧点云
    accu_matrix = I
    for frame in past(倒序) 然后 future(正序):
        source_pc = 邻帧原分辨率 → pc_range 裁剪 → icp_downsample(0.1m)
        estimate_normals(source/keyframe_map)
        reg = registration_icp(source, keyframe_map, 0.3, I, PointToPlane)
        matrix = reg.transformation（去 yaw/xy 后）
        accu_matrix = matrix @ accu_matrix
        registered_full = source_pc_ori.transform(accu_matrix)   # ← H1 缺陷
        keyframe_map.points = concat(keyframe_map, registered_full)  # 地图逐帧生长
```

诊断量：`fitness`（内点率 0.9–0.99 健康）、`inlier_rmse`、`icp_diag_6dof`（yaw/dx/dy/dz）、`icp_diag_hessian`（信息矩阵 `JᵀJ` 6 特征值 → 6DoF 可观测性，tx,ty,tz,rx,ry,rz=yaw）。

### 7.6 H1 缺陷
- 正确：第 k 邻帧全分辨率输出 = `source_pc_ori.transform(matrix_k)`（只施加本帧变换）。
- **H1**（V10:2345/2444）：实际 `transform(accu_matrix)`，而 `accu_matrix=matrix_k@…@matrix_1` 含所有前序帧 → 越靠后邻帧漂移越大。
- 死代码：`source_pc.transform(accu_matrix)`（:2282/2383）被 :2285/2386 覆盖。

---

## 8. 掩码生成（ray casting 完整推导）

### 8.1 目的与口径
`lidar_mask` = 当前关键帧**射线可达**体素集合，训练只监督 mask 内体素。
**V10 口径**（V10:704–706）：射线终点 = `当前帧 ∪ 邻关键帧 ∪ v1.3 sweep`；邻帧/sweep 先剔非刚体 {2,3,4,29,47,70}（别时刻位置不能定义当前自由空间），当前帧不过滤。

### 8.2 `get_mask`（get_mask.py:299）
```
voxel_grid = zeros(W,H,D) ；voxel_grid[floor((pts−pc_range[:3])/voxel_size)] = 1  # 占用=1
center = floor((origin_xyz − pc_range[:3])/voxel_size)                          # 射线原点
voxels_mask = get_visible_voxels_vector(voxel_grid, center, free_id=0)
self_range(ego 车身盒) 内体素 → 0（排除自车）
return voxels_mask
```

### 8.3 核心：`get_visible_voxels_vector_numpy`（get_mask.py:181）
对每个占用体素 v，**向原点反向发一条射线**，`t=linspace(0,1,100)` 采样 100 点：
```
path = v + t·(center − v)                        # (N,100,3)
non_free_count = Σ(path 上非 free 体素，排除起点 v)
if non_free_count <= 1:                          # v 直达原点、无遮挡
    path 上所有体素 → mask=True                  # 射线沿途(自由空间+表面)可监督
```
**语义**：体素「在 mask 内」⇔ 位于「原点→某无遮挡表面体素」的视线上。被挡住的表面（`non_free_count>1`）不标记。

**与 T3 深度图区别**：mask 是逐体素反向射线可达性（离散 t 采样、`≤1` 遮挡阈值）；T3 深度图是角向足迹+最近深度的球面遮挡测试。

### 8.4 逐雷达（`--per_sensor_mask`）
| 档位 | 行为 |
|---|---|
| 0（默认） | 单原点（LIDAR_TOP），全部点一次 get_mask |
| 1（P15） | 每路雷达点转 ego 系，各自原点 get_mask 后 OR |
| 2（P16） | 邻帧/sweep 也按 sensor_id 分组 + 各自 max_range（TOP160/L80/R70/B60）过滤后逐雷达 |

`self_range` 契约（P15）：定义在 LIDAR_TOP 系，调用方平移到 ego 后传入。

### 8.5 复杂度
numpy 版 path_points 形状 (N,100,3)，N≈10⁵–10⁶ → 峰值 ~1.2GB（N=10⁶ 时 3×10⁸ float32），时间 O(100N)；numba 版逐体素循环内存 O(1)。

---

## 9. 多层融合（T1/T2/T3 完整伪代码）

（`until.py:366 fuse_layers`，把邻关键帧/sweep 两层与当前帧融合）

### 9.1 权威层与 FusionPolicy
- 权威层 `occ_authority = current_obs ∪ box_pts`（人标，永不覆盖）。
- 融合层 = `[(neighbor, SOURCE_NEIGHBOR, fids), (sweep, SOURCE_SWEEP, fids)]`。
- `FusionPolicy`（默认）：`enable_t2=augment_empty_static(1)`、`enable_t3=1`、`min_witness_t2=2`、`min_witness_t3=1`、`max_range=densify_max_range(80.0)`、`protect_radius=1`。

### 9.2 准备
```
occupied[cx,cy,cz]=True；label_grid[cx,cy,cz]=current.label
protect_mask = binary_dilation(非刚体体素, protect_radius)   # 保护区禁增密
若 enable_t3: t3_depth = _build_occ_depth_map(occupied, origin)
```

### 9.3 逐层处理
```
for (pts, src, fids) in layers:
    (nx,ny,nz,nv) = voxel_indices_xyz(pts)
    # —— T1 门控（改标签，不增占用）——
    keep_t1 = nv & occupied[nx,ny,nz]；t1.label = label_grid[其体素]
    # —— T2 掩码内可见空体素增密 ——
    cand = pts[静态类 & 未T1 & 空体素 & mask内]
    cand = cand[水平距离≤max_range]        # ① _per_point_horizontal_range（逐雷达）
    cand = cand[~protect_mask]              # ② 非刚体保护区
    cand = cand[_voxel_witness_keep(≥min_k_t2)]  # ③ 多帧见证
    # —— T3 掩码外 + 遮挡测试增密 ——
    cand = pts[静态类 & 未T1 & 空体素 & ~mask内]
    cand = cand[距离≤max_range]；cand = cand[~protect_mask]
    cand = cand[_query_visible_in_principle(...)]  # ③ 球面遮挡测试
    cand = cand[_voxel_witness_keep(≥min_k_t3)]    # ④ 见证
    merged = concat(t1,t2,t3) → 按 NEIGHBOR/SWEEP 分桶
```

### 9.4 辅助函数（完整细节）
**`_voxel_witness_keep`（until.py:255）**：同一体素需 ≥ min_k 个不同 frame_id 见证。线性索引 `lin=(nx·H+ny)·D+nz` → `lexsort((fids,lin))` 求 (体素,帧) 去重对 → `np.unique` 计每个体素的独立帧数 → `count≥min_k`。

**`_build_occ_depth_map`（until.py:279）**：占用体素 8 角点 → 球面 (方位 0.2°×俯仰 0.2°) 深度图，每 bin 存最近角深度（保守）。
```
n_az=2π/0.2°+2, n_el=π/0.2°+2；depth_map=inf
corners = occ_idx·voxel_size + pc_range[:3] + 8角偏移 − origin
depth=‖corner‖, az=arctan2(y,x), el=arctan2(z,√(x²+y²))
az_min/max, el_min/max, min_depth = min(角深度)
ia0/ia1/ie0/ie1 = clip(floor((角+π或π/2)/bin))
for 每个体素: 若 ia1<ia0 或 ie1<ie0 → continue   # ← H2：跨±π被跳过
    bins = ia×n_el+ie 的全组合 → depth_map[bins]=min(min_depth)
```
**`_query_visible_in_principle`（until.py:323）**：点深 `depth ≤ depth_map[bin]+0.15m` → 可见。

**`_per_point_horizontal_range`（until.py:351）**：逐点水平距离（有 sensor_id 按各自雷达原点，无则单原点）。

### 9.5 判据总表
| 层 | 点类别 | 目标体素 | 掩码 | 距离 | protect | 遮挡 | witness | 动作 |
|---|---|---|---|---|---|---|---|---|
| T1 | 任意 | 已占用 | — | — | — | — | — | 改标签 |
| T2 | 静态 | 空 | 内 | ≤80m | 排除 | — | ≥2 | 补占用 |
| T3 | 静态 | 空 | 外 | ≤80m | 排除 | 可见 | ≥1 | 补占用 |

---

## 10. 框点采样与贴回（process_multi_sensor_point）

（V10:1052–1186，把跨帧拼好的实例点贴回当前帧位姿）

```
for sensor in sensors:
    lidar_sensor_trans = dict["lidar_pc_with_semantic"]
    sensor_pcs[sensor] = concat(lidar, dust, excavator, nonrigid_extra)  # P15 逐雷达 mask 用
    boxes = get_sample_data_multi(...)
    filtered = [(box,token,cat) for ... if cat ∉ NONRIGID_CATEGORIES]    # V10：非刚体框不进 zoo
    gt_bbox_3d = [center, wlh, yaw]；yaw+=π/2；center.z −= h/2（转底心）
    # 贴回（object_token_zoo 跨帧拼好的点 → 当前 box 位姿）
    for j, token in enumerate(dict["object_tokens"]):
        if radar_dedup 且 该 instance 归属雷达 != sensor → continue    # P10 去重
        for k, zoo_token in enumerate(object_token_zoo[sensor]):
            if token == zoo_token:
                points = Rot_z(yaw) · object_points_vertice[sensor][k] + center[j]
                if len(points)≥5: points = points[points_in_boxes_cpu(points, gt_bbox_3d[j])]
                semantics = ones·object_semantic[sensor][k]；append [xyz, semantic]
    try: temp = concat(object_semantic_list) → LidarPointCloud → 逆标定变换到 LIDAR_TOP 系
    except: print("[P13] 框点拼接异常", traceback)；continue            # 框内无点 → 跳过，良性
```

**要点**：
- 非刚体框（NONRIGID_CATEGORIES）不进 `object_token_zoo`，避免被当刚体跨帧拼壳（V10 补齐 V3 漏的 loader/excavator_base）。
- P10 `--radar_dedup`（默认关）：同一 instance 只由归属雷达贴回，避免四份带测距噪声的点集并集把车体外扩一层。
- P13 异常是**捕获后 continue**（空框 `ValueError: need at least one array to concatenate`），非崩溃。

---

## 11. 体素化（process_points_vectorized，优先级写入）

（until.py:725，把融合后的点 → 体素，含跨 source 优先级）

```
x_idx=floor((x−pc_range[0])/voxel_size[0]) ... valid_mask 边界裁剪
offsets = points − voxel_centers[ix,iy,iz]        # 亚体素偏移（存进输出）
if sources is not None:
    PRIORITY = [1,2,3,0]   # index=source id：box(3)=0 < current(0)=1 < neighbor(1)=2 < sweep(2)=3
    sort_key = PRIORITY[sources]                  # box > current > neighbor > sweep
    if vote_mode(默认关):
        每体素取最高优先级 source 组内「众数+离体素中心最近」
    else(默认):
        argsort(sort_key, mergesort 稳定) → np.unique((x,y,z)) 取首次=最高优先级
    输出 [ix,iy,iz, ox,oy,oz, label] + source
else:
    np.unique((x,y,z,label))  # 无 source 时按(体素,标签)去重
```

**核心思路**：体素内多点冲突时，按 **box(3) > current(0) > neighbor(1) > sweep(2)** 优先级认领（P11 修复：旧版 `argsort(sources)` 让 current 覆盖 box 实例点）。输出存 `offsets`（点−体素中心的亚体素偏移），KNN 补出的体素 offsets 置 0。

---

## 12. KNN 增密（densify_by_knn 复杂度）

（until.py:883，形态学膨胀式标签传播；`--knn_densify` 默认关）

```
GROUND_CLASSES=[25,26,27,28,30,33]
offsets = 6邻域(默认保守) 或 26邻域
occ_flat = 位图(W·H·D) 标记已占用
cur = 初始占用体素（波前）
for _ in range(n_iters=1):
    src_is_ground = isin(cur.label, GROUND_CLASSES)
    cand = cur[:,None,:] + offsets[None,:,:]           # (N,K,3)
    边界裁剪 inb
    allow = (~src_is_ground)[:,None] | (offsets[:,2]==0)[None,:]   # 地面源只水平(dz==0)
    过滤: 未占用 & 在 lidar_mask 内
    去重: lexsort((off_idx, src_order, clin)) → np.unique 取首次认领者  # 先到先得
    occ_flat[new]=True；累积；cur=new                  # 下一轮波前
返回 concat(原体素, 新体素)，新体素 source=SOURCE_DENSIFY(=4), xyz偏移=0
```

**要点**：地面类只水平传播（抑制地面语义沿高度/斜向蔓延到墙）；去重严格等价 dict「先到先得」插入序（多轮 tie-break 一致）；补洞体素仍受 lidar_mask 约束，free 区不补。
**复杂度**：每轮候选 N·K（K=6/26），去重 lexsort O(NK log(NK))，n_iters 轮；内存 occ_flat 位图 1024×1024×128 bool=128MB + 候选 (N·K,3)。

---

## 13. 标签映射 + 保存（save_result payload）

### 13.1 `apply_learning_map`（until.py:21，仅写盘前）
```
arr = asarray(labels, int32)          # 规避 np.result_type(float32,uint8)=float32 陷阱
lut 大小 = max(max(label)+1, 256)，未知填 unknown_to=34(other)
mapped = lut[arr]；越界/未知 id → WARN 但不崩帧
```

### 13.2 `save_result`（V10:1217，完整 payload）
```
payload = {
  "semantics": dense_voxels_with_semantic,     # (N,7) [ix,iy,iz,ox,oy,oz,label]
  "lidar_mask": lidar_mask,                     # (W,H,D) bool 射线可达
  "use_v13_sweeps": uint8, "fusion_tag": str,
  "dist_window": float32, "max_neighbor_frames": int32, "max_sweep_frames": int32,
  "source": voxel_source(int32, 可选),
}
gt_valid = lidar_mask.copy()；gt_valid[occupied 体素]=True   # free(负监督)∪合法占用(正监督)
payload["gt_valid"] = gt_valid
np.savez_compressed(dirs/"labels.npz", **payload)          # ⚠️ 非原子写
```
`gt_valid` 语义（Step C）：`lidar_mask`（当前帧射线原义，free 不被融合点污染）∪ 全部合法占用体素。
`apply_fusion_save_path` 追加 `with_autolabel`/`no_autolabel` tag，两种模式并存。

---

# Part C 版本演进与审查

## 14. 版本演进与任务记录（P14–P19）

| Commit | 任务 | 内容 |
|---|---|---|
| `a49ba17` | V10 | 非刚体过滤补齐（红线 4 全 6 类）+ lidar_mask 来源修订 |
| `e55bef4` | P14 | self_range 坐标系错位修复 |
| `e1ad190` | P15 | 逐雷达射线掩码 `--per_sensor_mask`（默认关）+ self_range ego 化 |
| `bf76cfc` | P16 | 逐雷达查询 + per-sensor max_range + sensor_id 透传 |
| `9f9daf6` | **P17** | 标签空间解耦：内部保留原始 id，learning_map 仅写盘前映射（修 dtype 陷阱） |
| `0c2aeaf` | **P18** | densify_max_range 40→80m + ICP 可观测性诊断 |
| `812e39a` | P19 | 实例运动状态深模块 `motion.py` |
| `b4bc069` | P19-B | 运动感知 ICP 静态背景 `--motion_aware`（默认关） |
| `ec05777` | **P19** | 名单收敛到 motion.py + 清理死代码（HEAD） |

## 15. 代码审查发现（H/M/L 分级）

### 🔴 高危
| # | 位置 | 问题 |
|---|---|---|
| H1 | V10:2345/2444 | `source_pc_ori.transform(accu_matrix)` 重复施加前序帧变换（应 `transform(matrix)`）；:2282/2383 死代码 |
| H2 | until.py:303–318 | `_build_occ_depth_map` 方位跨 ±π 体素被 `continue` 跳过 → 深度图偏空 → T3 10m 外过保守 |

### 🟡 中危
M1 单帧 instance 保守判 DYNAMIC（motion.py:150）· M2 `j=j+1` 在 if 内循环（V10:1807–1825）· M3 `sensor_pcs` 混帧（:1071–1076）· M4 `dict_list` 长度漂移（:1066）· M5 mask 未剔「移动刚体」（:744–754）· M6 `nuscenes_new.yaml` 未入库 + ori 缺 71 · M7 `--label_mapping` 默认硬编码（:2674）· M8 ICP 无 fitness 门控 · M9 Hessian 诊断口径错误

### 🟢 低危
死代码（`combined_points_down_sample`、`save_result` single_* 参数、`scale=1`、废弃 `icp_registration`、`icp_numpy.py`）、魔法数字、witness 统计、`np.unique`/set 热点。

> 复核：ICP 子代理报告的「lidar_pc_all 关键帧索引 vs dict_list 帧索引错位」经复核为**假阳性**（两者均为关键帧序）。

---

# Part D 全量运行与验证

## 16. 全量运行配置与执行

```bash
python3 scripts/run_parallel_generate.py \
    --script eq_generate_fusionoccupancy_nuscenes_V10_qhc.py \
    --dataroot /e-vepfs-01/perception/hongwei/data/qhc_data/qhc_gt_test \
    --save_path /e-vepfs-01/perception/hongwei/data/qhc_data/qhc_gt_v10_full_20260920_208/occ \
    --config_path /work/occ_genertor/config_ysj_smallrange.yaml \
    --label_mapping /work/occ_genertor/nuscenes.yaml \
    --keyframe_v3_fusion 1 --use_v13_sweeps 1
```

**关键默认（本次全量未显式传的都走这些）**：

| 参数 | 默认 | 含义 |
|---|---|---|
| dist_window | 8.0 m | 邻帧距离窗 |
| min/max_neighbor_frames | 2 / 8 | 邻关键帧上下限 |
| max_sweep_frames | 128 | sweep 上限 |
| mask_include_fusion | 1 | mask 射线含邻帧+sweep |
| mask_drop_nonrigid | 1 | 邻帧/sweep 剔非刚体 |
| per_sensor_mask | 0 | 单原点 mask |
| augment_empty_static | 1 | T2 增密开 |
| enable_t3 | 1 | T3 开 |
| densify_max_range | 80.0 m | T2/T3 水平上限 |
| densify_min_witness | 2 / 1 | T2/T3 见证门 |
| protect_radius | 1 | 非刚体保护膨胀 |
| knn_densify / vote_mode / radar_dedup / motion_aware / icp_keep_yaw | 0 | 均关（保持基线可复现） |
| icp_voxel_size | 0.1 m | ICP 降采样 |

**分片**：30 核 → 6 worker × 5 核，内存 111.5GB；w0:[0,44) w1:[44,87) w2:[87,130) w3:[130,173) w4:[173,216) w5:[216,259)。启动于 `2026-09-21 07:12:04`（PID 620591）。

## 17. 运行时间记录与估算

**埋点**：脚本层记录起止时间戳+总耗时+退出码（`timing.log`）；代码层逐场景打印 `程序运行时间`（`per_scene_timing.txt`）。

| 时点 | 已完成场景 | 产出帧 |
|---|---|---|
| 07:28（16min） | 1（scene0=678s=11.3min，37 帧偏小） | 196 |
| 07:42（30min） | 9 | 417 |
| 07:53（41min） | 10 | ~455 |
| 08:35（83min） | **26** | 1268 |

**估算（三口径）**：① 单帧稳态 14008×16.8s÷6 ≈ 10.9h；② 每场景归一 ~14.9min×43.2 ≈ 10.7h；③ V9 参照 19h×4/6 ≈ 12.7h。
**实测速率修正**：08:35 已 26 场景，稳态 0.32 场景/min → 剩余 233÷0.32 ≈ 12.1h → **ETA 今晚 ~20:40**（总约 13.5h，略晚于早期 18:00 估计，因早期用偏小的 scene0 校准）。

**运行健康**：无崩溃、无 BadZip；日志 Traceback 均为捕获的 `[P13] 框点拼接异常`（空框 skip，良性）。

## 18. 对比实验（Gate A：V10 vs V3）

**方法**：因 `save_result` 非原子写，直接对比会 `BadZipFile` 竞态 → 先按「mtime 空闲 >60s」过滤已完成场景、软链快照，再 `compare_vs_v3.py` 逐帧对比。

**结果（10 场景，260 共有关键帧）**：

| 指标 | 值 |
|---|---|
| V3=6744 ∩ V10=455 → common | 260 帧（only_new=195，v13 sweep 加密） |
| **occ IoU 均值** | **0.4070**（中位 0.3991 · P25 0.3225 · P75 0.5158 · min 0.2165 · max 0.5699） |
| 体素变化 | +32,785,777 / −14,292,575（净 +18.5M，V10 更密） |
| 同体素标签变化 | 148,150 |

**按 bag**：QY_QY-10（114 帧，mean 0.5024）、stm_6027（146 帧，mean 0.3325）。V9 全量参照 mean IoU=0.4756。

**解读**：V10 更密（净 +18.5M 体素，P17/P18 densify + v13 sweep 加密）；IoU 分化（QY 0.50 / stm 0.33）与历史 V9 难点包趋势一致；此对比仅 10/259 场景、2 bag，全量完成后需重跑得代表性数字。

---

# Part E 附录

## 19. 关键缺陷与改进建议

| # | 位置 | 建议 |
|---|---|---|
| H1 | V10:2345/2444 | 输出改 `transform(matrix)`；删 :2282/2383 死代码 |
| H2 | until.py:303–318 | 跨 ±π 改 `[ia0,n_az)∪[0,ia1]` 两段填充 |
| M2 | V10:1807–1825 | `j=j+1` 无条件递增 + 明确退出 |
| M5 | V10:744–754 | mask 结合 P19 分类结果排除移动刚体 |
| M7 | V10:2674 | `--label_mapping` 默认改相对仓库路径 |
| M8 | ICP | fitness<0.5 拒绝该邻帧 |
| M9 | Hessian 诊断 | 修正特征值解释 |
| — | save_result | npz 非原子写 → 临时文件 + rename |
| L | 多处 | 清理死代码 |

## 20. 结论
- 系统已具备可训练 3D 语义占用 GT 的完整生成能力：帧收集 → 动静分类 → ICP → 掩码 → T1/T2/T3 → 体素化 → KNN 增密 → 标签映射 → 写盘，覆盖 259 矿区场景。
- P17/P18/P19 完成标签解耦、增密扩展、动静分类收敛三项重构；硬伤已定位（H1/H2）。
- 全量 6 worker 并行正常，耗时记录齐全，ETA ~20:40；V10 相对 V3 更密（+18.5M 体素）、部分场景 IoU 0.33–0.50。

## 21. 附录：基于本项目的简历信息

**项目经历：矿区自动驾驶 3D 占用网格真值生成系统**（算法工程师，独立负责设计/重构/审查/全量落地）

- **动静分类深模块（P19）**：把散落 4 处的「静/动 × 刚体/非刚体」收敛为单一 `motion.py`（单一事实来源 + assert 防漂移）；用「跨帧 box 中心位移/dt 中位数」替代被剥离的 velocity，0.5 m/s 阈值经 5 场景 69 instance 标定。
- **标签空间解耦（P17）**：内部保留原始 72 类、learning_map 仅写盘前映射，72/7 类一键切换；修复 `np.result_type(float32,uint8)` dtype 陷阱。
- **增密与配准（P18/P19-B）**：KNN 增密 40→80m、地面/非地面分离传播；运动感知 ICP 静态背景。
- **逐流程代码审查**：定位 2 高危（ICP accu_matrix 重复累加、深度图方位 wrap）+ 9 中危 + 13 低危 + 1 假阳性复核。
- **全量并行落地**：6 worker 分片 + 自动核数探测；运行时间埋点 + 耗时建模（ETA ~13.5h）；Gate A 逐帧 IoU 对比（V10 vs V3：mean IoU 0.407，体素 +18.5M）。

**技术栈**：Python/NumPy/SciPy · nuScenes · ICP 点云配准 · 多传感器融合 · 3D 占用网格 · ray casting 掩码 · 并行计算 · 代码审查

**可量化产出**：259 场景/14008 关键帧全量 GT 生成，6 worker ~13.5h 跑完；3 次架构重构 + 2 高危定位 + 1 假阳性复核；相对 V3 基线体素 +18.5M、部分场景 IoU 0.50。

---

*完整技术文档完 · 代码基准 `ec05777` · 生成时间 2026-09-21*
