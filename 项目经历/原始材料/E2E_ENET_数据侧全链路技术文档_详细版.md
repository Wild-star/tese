# E2E_ENET 数据侧全链路技术文档（完整详版）

| 项 | 内容 |
|---|---|
| 文档范围 | E2E_ENET 感知模型的**数据侧全链路**：数据生产 → 数据集构造 → 采样与均衡 → pipeline 算子 → 增强与传感器 drop → 标签质量治理 → 评测数据口径 → 数据侧时间线与风险 |
| 代码基线 | `E2E_ENET` 分支 `hw_dev_merge_zsa`，HEAD `fdbc658`（143 提交，2026-03-11 ~ 2026-09-16） |
| 证据等级 | **A** = 逐行读代码核实 ｜ **B** = grep/结构确认 ｜ **C** = 文档或推断 |
| 证据来源 | ①全量代码 ②仓库内 20 篇设计文档 ③飞书群 757 条讨论 ④14 份分域报告（`分域报告/01~07`、`补跑报告/R1~R7`） |
| 核验方式 | 所有行号可用 `sed -n '<行号>p' <文件>` 复现；**文件规模一律用 `python3` 数 `\n`，勿用 `wc`（本环境低估 3–8 倍）** |
| 成文日期 | 2026-09-21 |

> **阅读提示**：本文只讲"数据"。模型结构、多头 loss、ONNX 导出只在与数据有接口契约处提及。

---

## 目录

- [0. 数据侧一图总览](#0-数据侧一图总览)
- [1. 数据生产与资产](#1-数据生产与资产)
- [2. 数据集构造](#2-数据集构造)
- [3. 多 pkl 与配比（`(path, repeat)`）](#3-多-pkl-与配比path-repeat)
- [4. scene 切分与样本构造](#4-scene-切分与样本构造)
- [5. 采样体系（核心章）](#5-采样体系核心章)
- [6. 类别与区域均衡](#6-类别与区域均衡)
- [7. pipeline 逐算子](#7-pipeline-逐算子)
- [8. 增强与 scene 级传感器 drop](#8-增强与-scene-级传感器-drop)
- [9. 标签质量治理](#9-标签质量治理)
- [10. 评测数据口径](#10-评测数据口径)
- [11. 数据侧时间线（提交级考古）](#11-数据侧时间线提交级考古)
- [12. 性能与资源](#12-性能与资源)
- [13. 配置开关速查表](#13-配置开关速查表)
- [14. 风险与技术债（数据侧专用）](#14-风险与技术债数据侧专用)
- [15. 未知项与验证方法](#15-未知项与验证方法)
- [16. 上手路线与复现命令](#16-上手路线与复现命令)
- [17. GT 构建与监督契约（数据侧的输出规格）](#17-gt-构建与监督契约数据侧的输出规格)
- [18. 需求与决策背景（飞书讨论 × 代码）](#18-需求与决策背景飞书讨论--代码)
- [19. 采样与配比的定量分析](#19-采样与配比的定量分析)
- [20. 数据侧改动影响面矩阵](#20-数据侧改动影响面矩阵)
- [21. 数据侧自检清单（上线前 SOP，14 项）](#21-数据侧自检清单上线前-sop14-项)
- [22. 与 350/330 量产线的口径对齐清单](#22-与-350330-量产线的口径对齐清单)
- [23. 数据侧关键数字面板（一页速览）](#23-数据侧关键数字面板一页速览)
- [附录 A 文件:行号总索引](#附录-a-文件行号总索引)
- [附录 B 提交哈希索引](#附录-b-提交哈希索引)
- [附录 C 术语表](#附录-c-术语表)
- [附录 D 常量与几何速查](#附录-d-常量与几何速查)
- [附录 E 数据缺陷 × 修复提交 × 证据文件](#附录-e-数据缺陷--修复提交--证据文件)
- [附录 F 全文结论速览（24 条）](#附录-f-全文结论速览24-条)

---

## 0. 数据侧一图总览

### 0.1 数据侧在整条链路中的位置

```
┌─ 数据生产（离线，仓库外为主）────────────────────────────────────┐
│ raw → clean_pkl.py → refine_pkl.py → statistics_pkl.py          │
│      → opt_pkl_mamba_list_only_sample.py（压成 key=1, sweeps=[]）│
│      → <scene>.pkl（infos[] + metadata{}）                      │
│      → occ GT：labels_new.npz (LR) / labels.npz (HR)             │
│      → lidarseg bin（7 路逐点语义）                              │
└──────────────────────────────────────────────────────────────────┘
                             ↓
┌─ 数据集构造（dataset）───────────────────────────────────────────┐
│ load_annotations:786  ← pkl_list / ann_file / 目录扫描 / 单文件  │
│   └ _load_ann_entry_infos:760  ← (path, repeat) 展开             │
│ _set_sequence_group_flag:432  ← 按 idx 切 scene（flag）          │
│ _get_region_info:376          ← 采样用 r0–r3 分区                │
│ _precompute_cbgs_frame_cat_ids:604                               │
│ _rebuild_scene_drop_table:353 ← 每 epoch 重建 drop 表            │
└──────────────────────────────────────────────────────────────────┘
                             ↓
┌─ 采样（sampler，1549 行）────────────────────────────────────────┐
│ builder.py:105-140 elif 链 → DistributedGroupSlotStreamingOptV2  │
│   → scene 分组 → rank 取模 → slot round-robin:1340               │
│   → CBGS:1253 / region-balance / GroupOpt                        │
│   → num_samples:1151 → pad:1432                                  │
└──────────────────────────────────────────────────────────────────┘
                             ↓
┌─ pipeline（train 20 算子 / test 16 算子）────────────────────────┐
│ 1 LoadEQOccGTFromFileOptimizedMamba:3694   （LR occ GT）        │
│ 2 LoadAnnotationsLidarOccOptimizedMambaFix:4312 （occ BDA）     │
│ 3 PrepareImageInputsMultitaskMamba:1302    （图像 + 互斥 drop） │
│ 4 EQLoadPointsFromFileMultitaskMamba:2882  （7 路雷达点云）     │
│ 5 EQPointToMultiViewDepth:5055             （多视图深度 GT）    │
│ 6 ToEgoMultitaskMamba:2930                 （统一 ego + lidar drop）│
│ 7 LoadAnnotationsMultitaskMamba:4785       （框 + 点级 seg）    │
│ 8-11 过滤族（ego 范围/非法框/点云范围/框范围）                  │
│ 12 MapDetectionClassMamba:5626             （细类→粗类）        │
│ 13-15 名称/可见性过滤                                            │
│ 16-18 PairGT / PointShuffle / PointSegClassMapping              │
│ 19 EQNuScenesSparse4DAdaptorMultitaskMamba:797 （T_global 产出）│
│ 20 Collect:649                             （21 key 白名单）    │
└──────────────────────────────────────────────────────────────────┘
                             ↓
      模型（本文不展开） → 推理 → 评测（evaluate:2077 / eval_task:1286）
```

### 0.2 数据侧 9 个环节与本文对应章节

| # | 环节 | 关键产物 | 章节 |
|---|---|---|---|
| 1 | 数据生产 | `*.pkl`、`labels_new.npz`、`labels.npz`、`lidarseg*` | §1 |
| 2 | 数据集构造 | `data_infos`、`flag`（scene 序列号） | §2 §4 |
| 3 | 多 pkl 配比 | `(path, repeat)` 展开后的帧表 | §3 |
| 4 | scene 切分 | `flag` | §4 |
| 5 | 采样与均衡 | 每 rank 的样本流（含 slot 结构） | §5 §6 |
| 6 | pipeline 加工 | `results` 字典 → `Collect` 后 batch | §7 |
| 7 | 增强与 drop | `img_inputs`、`drop_*`、`scene_drop_cfg` | §8 |
| 8 | 标签质量 | 缺失清单、rebind、兜底 | §9 |
| 9 | 评测口径 | `final_score`、mIoU、误差分位 | §10 |

### 0.3 数据侧三个"必须先知道"的事实

1. **时序不靠 sweeps**——训练 pkl 已被压成"全 keyframe"（`key=1, sweeps=[]`），时序上下文**完全由模型侧的 BEV buffer 提供**，数据侧只负责"保证同 scene 相邻帧能落进同一条 batch 槽位"（§5）。这是理解整套设计的**前提**。
2. **配置写了什么 ≠ 最后用了什么**——`group_opt_sampler` 与 `group_slot_streaming_sampler` 都写 True，但 builder 是 elif 链，只有 OptV2 生效（§5.2）；BDA 配置在跑但**恒等**（§8.4）。
3. **标签质量是上限约束，不是模型问题**——LR `lidar_mask_fine` **39% 帧为空**、LR+HR 双缺 **76,662 帧**（§9）。

---

## 1. 数据生产与资产

### 1.1 生产脚本链

`datasets_pkl.sh` 是转换入口，链路为：

```
clean_pkl.py → refine_pkl.py → statistics_pkl.py
```

- `tools/data_tools/tool.md` 是 pkl 全生命周期（clean / refine / merge / cut / statistics / …）的官方语义清单（A）。
- **时序数据的关键改造**是 `tools/data_tools/opt_pkl_mamba_list_only_sample.py`：把 pkl 整理成 `key=1, sweeps=[]` 的"只有 keyframe"形态（详见 §1.5）。

### 1.2 pkl 顶层结构

```python
{'infos': [ <frame_info>, ... ], 'metadata': {...}}
```

`load_annotations` 读 `data["infos"]`、`data["metadata"]`，并把 `metadata["version"]` 写入 `self.version`（`eq_nuscenes_temporal_multitask_mamba.py:786-817`；写回同结构的生成侧见 `opt_pkl_mamba_list_only_sample.py:135-141`）。

### 1.3 单帧 info 顶层字段（18 类，A 级）

| # | 字段 | 含义 | 读取位置 | 强依赖 |
|---|---|---|---|---|
| 1 | `token` | 样本唯一 id → `input_dict['sample_idx']` | `get_data_info:846`；`get_history_data_info:1037` | ✔ |
| 2 | `lidar_path` | 前向主 lidar 点云路径 | `:847` | ✔ |
| 3 | `lidar_path_r` / `_l` / `_b` | 右/左/后 lidar 路径 | `:848-850` | ✔ |
| 4 | `lidar_path_top_aux` / `_mid_left` / `_mid_right` | 新增 3 路雷达（`in info` 判定，**可选**） | `:898-902` | ✘ |
| 5 | `sweeps` | 该帧累积的 sweep 列表；**默认分支用它判 scene 边界**（主配置不用） | `:851`；`_set_sequence_group_flag:457` | ✔（可为空） |
| 6 | `timestamp` | 微秒时间戳，÷1e6 转秒；排序 key | `:852`；`_load_ann_entry_infos:772` | ✔ |
| 7 | `idx` | **场景 id（同 idx = 同 scene），不是样本下标** | `:853` | ✔ |
| 8 | `lidar2ego_translation{,''}` / `lidar2ego_rotation{,''}` | lidar→ego 外参（含 `_l/_r/_b` 后缀） | `:861-864, 875-876` | ✔ |
| 9 | `ego2global_translation{}` / `ego2global_rotation{}` | ego→global（`key=True` 时用） | `:863-880` | ✔ |
| 10 | `ego2global` | **仅 `key=False`（sweep 帧）** 的 4×4 矩阵（旧格式） | `:873, 893` | 条件 |
| 11 | `key` | 是否关键帧；`info.get('key', True)`，**缺失默认 True** | `:872` | — |
| 12 | `cams` | `cam_name → {data_path, cam_intrinsic, sensor2lidar_rotation{suffix}, sensor2lidar_translation{suffix}}` | `:917-946, 976` | ✔ |
| 13 | `lidarseg{suffix}` | dict，取 `['filename']`（7 个 lidar 后缀） | `:906-911` | 7 路 |
| 14 | `ann_infos` | 多任务标注列表（检测 + 分割 + occ） | `:978, 983-988`；`evaluate:2023` | — |
| 15 | `auto_scores` | 自动标注置信度（可选） | `:980-981` | ✘ |
| 16 | `occ_path` | **LR** occ GT 目录（`labels_new.npz` 所在） | `:993`；`get_ann_info:1216` | — |
| 17 | `occ_path_hr` | **HR** occ GT 目录（可选；优先于字符串重映射） | `_resolve_occ_gt_path_hr:1006` | ✘ |
| 18 | `scene` / `version` | 场景名 / 数据版本（`metadata` 侧） | `get_ann_info:1219`；`:786` | — |

### 1.4 标注字段（9 类，只在关键帧读，A 级）

`get_ann_info:1221` 读取，仅 `key=True` 时生效：

| 字段 | 含义 | 位置 |
|---|---|---|
| `valid_flag` | 标注有效掩码（`use_valid_flag=True` 时作 mask） | `:1224`；`get_cat_ids:571` |
| `num_lidar_pts` | 每框点数；`use_valid_flag=False` 时 `>0` 生成 mask | `:1226` |
| `gt_boxes` | 3D 框 (N,7) | `:1237`；`_get_region_info:395`；`get_cbgs_cat_ids:574` |
| `gt_names` | 类别名 (N,) | `:1238` |
| `gt_velocity` | 速度 (N,2)，拼到 `gt_bboxes_3d` 第 8-9 位；**NaN 置 0** | `:1246-1251` |
| `instance_inds` | 实例 id，**用于框去重**（重复 id 的框 mask 置 False） | `:1228-1234, 1275` |
| `visibility_flag` | 可见性（可选） | `:1254-1255` |
| `num_radar_pts` | radar 点数（`with_attribute` 时） | `:1257` |
| `scene` / `token` | `gold_metric` 分支拼 gold 路径 | `:1219` |

`get_history_data_info:1031` 字段集几乎一致，但**不含** `key` / `ann_infos` / `auto_scores` / `occ_path`，且强制写 `ego2global`（`:1120`），末尾补 `input_dict['key'] = info.get('key', True)`。历史帧标注版为 `get_history_ann_info:1153`。

### 1.5 时序改造：为什么 pkl 里没有 sweeps

`tools/data_tools/opt_pkl_mamba_list_only_sample.py:118-121` 对每帧做：

```python
sample_info['sweeps'] = []
sample_info['key'] = 1
```

后果（这是整套设计的**前提**）：

- 训练侧**不再展开历史上采样帧**，时序上下文改由**模型侧 BEV feature buffer** 提供（单帧递归，实质 1 步历史）。
- `get_data_info` 仍兼容 BEVDet 风格：`is_key = bool(info.get('key', True))`，非 key 帧只给一个 `ego2global` 矩阵（`:882-887`）。
- 数据集仍在建"序列"（`mamba_data_sequence=True`），但序列的作用变成**给采样器分组**，而非给模型喂历史帧。

### 1.6 occ GT 资产：两套 npz，名字不同、接错静默拿 None

| 轨 | 目录字段 | GT 文件名 | 加载类 | 几何 |
|---|---|---|---|---|
| **LR（稠密 512）** | `occ_path` → `occ_gt_path` | **`labels_new.npz`**（`loading.py:3456`） | `LoadEQOccGTFromFileOptimizedMamba:3694` | `[512,512,32]` @0.3/0.3/0.4m |
| **HR（1024）** | `occ_path_hr` → `occ_gt_path_hr` | **`labels.npz`**（`loading_optimized_HR.py:1177`） | `LoadEQOccGTFromFileOptimizedHR` | `[1024,1024,128]` @0.15/0.15/0.1m |

- `occ_path_hr` **只有 Mamba 这一个 dataset 类读**（其余 8 个 0 命中）；非 Mamba 类接 HR pipeline 只会**静默拿到 `None`**。
- OccTop 配置自己也承认这点（`...TemporalEntityOccTop.py:837` 注释「pkl 通常只有 occ_path，无 occ_path_hr」），因此实际依赖 `occ_gt_root_hr` 的**LR→HR 路径字符串重映射**（`eq_nuscenes_temporal_multitask_mamba.py:708-740`）。
- LR mask 的降采样兜底逻辑见 §9.2。

**HR `labels.npz` 的键语义（B 级，部分为 docstring）**：`occ_v5_utils.py:119` 称 `labels_new_hd['semantics_fine']` 为 `(N,5)=[x,y,z,h_frac,cls]`，而 dense 路径只取列 `[0,1,2,4]`。**恒为 5 列否、`labels_new_hd` 是否存在，均需读真实数据验证**（未确认项，见 §15）。

**HR 语义稀疏性（A 级）**：`docs/train_pipeline_gt_outputs_guide.md:216-217` 记录 HR `labels.npz` 中 **wall 占 75%、Ground 仅 23%**，可见地面约 **85% 未标注** ⇒ ground 头必须依赖在线多帧 fuse 兜底。

### 1.7 lidarseg 资产

- 7 路逐点语义 bin，路径字段 `lidarseg{suffix}`（`get_data_info:906-911`）。
- 消费在 `LoadAnnotationsMultitaskMamba._load_semantic_seg_3d:4589`：读 per-point 语义（int8），必要时读 `.bin.conf` 置信度，产出 `pts_semantic_mask` / `pts_semantic_conf`，并随 `points` 一起做 BDA 变换。
- 标签体系：**原始 72 类 → 粗类 1..7**（`seg_label_mapping`，config:82-93）；训练侧 8 类含背景（`cls_num=8`，注意该类**不用** config 里的 `num_classes` 键，见 `pointseg_opt_head.py:96`）。
- ⚠️ 新数据（TKX 260712+ collect 批次）扩到 **73 类**：新增 `71=dumppile(料堆)`、`72=dumppilegroup(料堆组)`；`72` 越界曾导致 `np.take(mapping_array[0..71], 72)` 崩溃（`docs/fix_note_seg_id72_and_loss_diag.md:14-30`），修复为 mapping 表补 `72:3` + `EQPointSegClassMapping` 增加 clip 防护（`:47-57`）。

### 1.8 occ GT 生产侧（仓库外，但决定数据质量）

- 生成目录：`/e-vepfs-01/occ_gt/E2E_ENET`、`/e-vepfs-01/occ_gt/qwen3.8`；HR 实际在用 `/e-vepfs-01/occ_gt/occ_gt_smallrange_15`（**46455 scenes**，是旧目录 `occ_gt_smallrange_260314_hw`（28114 scenes）的**超集**，多 18341 个新场景）。
- ⚠️ **环形伪影（ring artifact）根因在生成器**：`get_mask.py::_process_visible_voxels_numba`（:29-43）的"固定 100 采样 + `np.round` 落格 + `np.random.rand()<0.5` 随机丢射线"导致以车体为圆心的同心环 + 放射 spoke。可控复现：旧算法 ringiness **1.080**，改体素 DDA 后 **0.448**；服务器实测原始 mask ringiness≈0.74、导出 state≈0.72 ⇒ **E2E 侧只是读取，无法根治**，修复指向重新生成 `labels.npz`；E2E 侧只能缓解（3–5px 膨胀压不掉宽环）。
- 观测掩码语义：离线 occ 由 **±20 帧多帧 ray-cast** 生成观测掩码 `lidar_mask`，未观测区必须显式标 UNKNOWN 而非臆断 free/occ ⇒ **这是 LR/HR 标签不可替代的原因**。

### 1.9 数据资产缺失统计（A 级，全量审计结论）

见 §9 详表。核心三行：

| 类别 | 规模 | 后果 |
|---|---|---|
| LR `lidar_mask_fine` 为空 | 22 pkl / **706,821 帧（39%）** | `loss_occ_fine ≈ 0`、`loss_lr_state` 无有效监督 |
| LR 完全未绑（无 `occ_path`） | 8 pkl / 76,662 帧 | loader 置 `occ_scale=0`，occ loss 零梯度跳过 |
| LR + HR 双缺 | 8 pkl / **76,662 帧** | 建议从训练集剔除 |
| 合计受影响 | **84,296 帧** | — |

---

## 2. 数据集构造

### 2.1 类与注册

- 数据集类：**`EQNuScenesTemporalMultitaskMambaDataset`**（`datasets/eq_nuscenes_temporal_multitask_mamba.py`，**真实 2667 行**）。
- 同族另有多套 dataset 类（`EaconE2EDataset` / `EQ2DDataset` / `EQNuScenes3DDetTrackDataset` / `EQNuScenesDatasetDetSegOcc` / `EQNuScenesFlowTemporalDataset` / `...ByFrameDataset` / `...MambaDataset` / `...MovingStatusDataset`），但**数据侧目标配置只走 Mamba 这一套**。
- ⚠️ `EQNuScenesTemporalMultitaskMULTIPKLTestDataset`（`eq_nuscenes_multi_pkl_test.py:53`）是**死类**：未被 `datasets/__init__.py` 导入，也无 config 引用。真正 multi-pkl 评测走普通 dataset + `test_multiPkl_sampler`。

### 2.2 `load_annotations` 的四条分支（`:786-817`）

| 优先级 | 入口 | 行为 |
|---|---|---|
| 1 | **`pkl_list`** | 显式多 pkl 列表，**主配置走这条** |
| 2 | `ann_file` 为 list/tuple | 元素可为路径或 `(路径, 复制个数)`，走 `_load_ann_list` |
| 3 | `use_pkl_list=True` | 目录扫描（`os.listdir` 拼 `data["infos"]`），**绕过 `sort_datasets` / `load_interval`** |
| 4 | 其它 | 单 pkl 文件 |

**`pkl_list` 为什么被引入（有完整书面动机，A 级）**：提交 `412fda2`（2026-09-04 00:19，洪伟）记录——原先 `ann_file=train_pkl_list`（35 项，含 `(pkl, 复制个数)` 元组）被 mmdet `build_dataset` 判为 list → 走 `_concat_dataset`，把元组元素当独立 dataset/文件路径 → 报 **`TypeError: file must be a filepath str`**。修复方式：新增 `pkl_list` 参数，`load_annotations` 优先合并 `pkl_list`（复用 `_load_ann_entry_infos`），**绕开 mmdet 的 ConcatDataset 分支**。提交同时注明"全量 load 因节点内存受限无法本机验证，交由 GPU 训练节点实测"。

配套：`dc53bab`（2026-09-03）等脚本保证单 pkl 训练时把 `use_pkl_list` 置 `False`（避免 config 由 EntityGeoDual 派生后默认走目录扫描）。

### 2.3 初始化顺序（`__init__:158`，A 级）

```
load_annotations
  → his_data_infos = data_infos                     # :282 历史索引基准
  → 若 filter_past/future != 0: clip_sign=True + _clip_data_infos()   # :409
  → with_seq_flag: _set_sequence_group_flag()        # :432
  → use_region_sampler: _get_region_info()           # :376
  → _precompute_cbgs_frame_cat_ids()                 # :604
  → error_idx = set()
```

### 2.4 `results` 初始字段（pipeline 之前的 `input_dict`）

`get_data_info:844-995` 逐一赋值得到初始 keys（节选）：

```
sample_idx, pts_filename, pts_filename_r/_l/_b, sweeps, timestamp, idx,
use_sweeps_byframe(硬编码 False), lidar2ego_translation{,_l,_r,_b},
lidar2ego_rotation{...}, ego2global_translation{...}, ego2global_rotation{...},
lidar2global{...}, img_filename, lidar2img, lidar2img_l/_r/_b, cam_intrinsic,
lidar2img_top_aux/_mid_left/_mid_right, cams, ann_infos, auto_scores,
gt_bboxes_3d, gt_labels_3d, gt_names, gt_velocity, instance_inds,
occ_gt_path, occ_gt_path_hr, key
```

（另有 `pts_filename_top_aux/_mid_left/_mid_right`、`lidarseg*` 为条件注入。）

---

## 3. 多 pkl 与配比（`(path, repeat)`）

### 3.1 核心展开逻辑 `_load_ann_entry_infos:760-784`

```python
if factor >= 1.0:            # 整份复制 round(factor) 份
    reps  = int(round(factor)); infos = infos * max(1, reps)
elif 0.0 < factor < 1.0:     # 按比例确定性抽样（np.linspace 取整）
    keep_n = max(1, min(n, int(round(n * factor))))
    idxs = np.unique(np.linspace(0, n - 1, keep_n).round().astype(np.int64))
else:                        # factor <= 0：跳过该 pkl
    infos = []
```

**两条易被忽略的规则**：

1. **每个 pkl 先按 `load_interval` 抽帧，再复制**（`:773`）；
2. `sort_datasets=False` 时**不按 timestamp 重排**（`:194`, `:809-812`）——顺序即 `os.listdir`/配置顺序。

**⚠️ 实现不一致（重要）**：仓库另有一份 `eacon_utils/ann_file_list.py:21-47` 的 `expand_infos_by_repeat`，语义相同但分片用 **`md5(pkl 路径)` 作种子的 `RandomState`** 做无放回随机子采样（`:8-18`），与数据集内 `np.linspace` 等距抽样**实现不同**。当前 `load_annotations` **未调用** `ann_file_list.py`（`:786-838` 无 import），故生效的是数据集内那套。两套都对同一 pkl 给出**确定性、可复现**的结果，但抽到的帧不同。

### 3.2 生产实际配比（34 条 `anno_root` 实测解析，A 级）

| repeat | 条数 | 用途推断 |
|---|---|---|
| `1`（默认 5 + 显式 11） | 16 | 常规场景 |
| `3` | 7 | 稀缺场景升采样（如 `ground_smoke`） |
| `0.5` | 6 | 过量常规道路场景降采样（如 `simData_animal_260419`） |
| `2` | 2 | 轻度升采样 |
| `5` | 3 | 强升采样（`posuizhan` 破碎站、`Chargingstation` 充电站） |

> 另一份配置（`EQDetSegOccMambaWithSegV5TemporalDepth.py`）的 `train_pkl_list` 为 **36 项**；本文以 full-data 配置实测的 **34 条可解析条目**为准。

**路径来源（跨人跨仓库）**：

| 来源 | 条数 |
|---|---|
| `./data/...`（本仓内） | 22 |
| `/e-vepfs/yangshujie/BEVDet_dev2-1/data/...` | — |
| `/e-vepfs/hongwei/project/Enet_hw/data/...` | 合计 12 |

⇒ **训练集是多人、多仓库各自产出的 pkl 拼起来的**。

**文件名里的场景类型标签（业务线索）**：`ground_smoke`（地面积水/扬尘）、`Chargingstation`（充电站）、`posuizhan`（破碎站）、`kuanti`（矿体/矿田）、`nte240`、`xde130`。⇒ "充电站""破碎站"这类**固定作业点被单独采样并加权**，与"可通行性判断"的业务定位一致。

**文件名尾串语义（C 级推断，需向数据生产方确认）**：
`cleaned_rmpass_slow0.9_clean0.7_v0.2_rad20m_step1_ts1e-06` —— 疑似"清洗 / 去重 pass / 抽帧（slow 0.9）/ 速度阈值 0.2 / 半径 20m / 步长 / 时间阈值"的一串离线过滤参数。

### 3.3 `repeat` 的工程意义

- `repeat` 同时承担**升采样与降采样**两种角色：稀缺场景 3~5 倍、过量场景 0.5 倍 ⇒ 团队把它当作"**数据配比旋钮**"。
- 因为展开在 dataset 构造期完成，`repeat` 改动**直接改变 `len(dataset)`** ⇒ 进而改变 `num_samples`（§5.5）与 epoch 长度，属于"牵一发动全身"的参数。
- 可复现性：`repeat≥1` 是纯复制（确定性）；`0<repeat<1` 两套实现均为确定性抽样 ⇒ **同配置同结果**。

---

## 4. scene 切分与样本构造

### 4.1 `_set_sequence_group_flag:432-499` 的三分支

| 分支 | 触发条件 | 判据 | 主配置是否走 |
|---|---|---|---|
| `clip_sign` | `filter_past_frame != 0 or filter_future_frame != 0` | `data_indices[idx] - data_indices[idx-1] != 1`（用**被裁剪后的原始下标**） | ✗ |
| **`mamba_data_sequence`** | `mamba_data_sequence=True` | `data_infos[idx]['idx'] - data_infos[idx-1]['idx'] != 0`（用**场景 id**） | ✅ **走这条** |
| 默认 | 以上都不满足 | `len(data_infos[idx]['sweeps']) == 0` | ✗ |

- `_clip_data_infos:409` 会按 `idx` 分组、丢弃每组首 `pre` 与末 `post` 帧（`len(items) <= pre+post` 的 scene **整组丢弃**），并同步产出 `data_indices`（原始下标）。主配置 `filter_past_frame_num=0 / filter_future_frame_num=0` ⇒ **整个裁剪与 `data_indices` 都不生效**，scene 边界**完全由 `idx` 决定**。
- 产出 **`self.flag`（每帧所属 sequence 号）**，是采样器 `_build_scene_groups` 的**唯一输入**。
- 主配置 `with_seq_flag=True, mamba_data_sequence=True`。

### 4.2 `_prepare_train_data:623-681` 的注入逻辑（A 级）

| 注入项 | 条件 | 行为 |
|---|---|---|
| **硬时序** `pastframe_{i+1}` / `futureframe_{i+1}` | `filter_past_frame / filter_future_frame > 0` | 主配置均为 0 ⇒ **不产生** |
| **geo 软历史** `pastframe_{i+1}` | `geo_online_past_num > 0 且 filter_past_frame == 0` | 从 `idx-1-i` 往前取，遇 `past_i < 0` **或** `data_infos[past_i]['idx'] != cur_scene` **立即 break**（不跨 scene、不填充）；附 `ida_config` / `bda_config`；用于冷启动在线几何 GT（`n_avail <= 4`） |
| **ground 窗口** `groundframe_past_{i+1}` / `groundframe_future_{i+1}` | `geo_ground_past_num / future_num > 0` | 同为 scene 内 + 越界 break；配置 `past5 + cur + future1`；注释明确"仅 points+seg metadata，key 命名避开 image pipeline" |
| 增强配置 | 总注入 | `aug_config` / `ida_config` / `bda_config` |
| **drop 配置** | `scene_level_drop and scene_drop_table is not None` | `data['scene_drop_cfg'] = scene_drop_table.get(int(data.get('idx', idx)))` 且 `data['epoch'] = self.epoch` |

**关键语义**：`scene_drop_cfg` 按 `idx` 取 ⇒ **同 scene 所有帧共用同一份 drop 配置**——这是 "scene-level" 的**全部含义**。

### 4.3 `__getitem__:683-744` 的容错（A 级）

- 入参可为 `int` 或 `dict`（`{idx, ida_config, bda_config, aug_config, occ_id}`，来自 `keep_consistent_seq_aug` 的 slot 包装）。
- 训练态 `while True`：若 `idx in error_idx` → `data=None`；否则 try pipeline，`except` 打印 **dataset_idx / sample_idx / scene_idx / img_filename / past_frames / future_frames + traceback**，`error_idx.add(idx)`，置 `data=None`。
- `data is None` → `idx = self._rand_another(idx)`（`:613`，**从同 scene 池随机**，池被 `error_idx` 过滤；池空则全库随机）并重新采样增强，继续循环。
- **工程含义**：单帧数据异常**不会中断训练**，但会**静默降低该 scene 的有效样本量**（该帧本轮不再被采到）。监控 `error_idx` 大小是数据健康度的一个免费指标。

### 4.4 `idx` 的三处用法（贯穿数据侧与模型侧）

| 用途 | 位置 |
|---|---|
| dataset 分组（scene 切分） | `_set_sequence_group_flag:432` |
| geo 软窗口越界判定 | `_prepare_train_data:640-651` |
| drop 表注入 | `_prepare_train_data:677` |
| 模型侧时序复位 `reset_sign` | `bevfusion_query_head.py:1007`（`torch.ne(idx_infos, self.reset_vector)`；`True` 时清 `history_memory_*` / `history_bbox` / `max_id`，`:1042-1050`） |

⇒ **`idx` 是数据侧与模型侧时序语义的唯一契约**。改 `idx` 语义 = 同时改 scene 切分、软窗口、drop 注入、时序复位四件事。

---

## 5. 采样体系（核心章）

### 5.1 采样器家族全景（7 个类，文件真实 **1549 行**）

| # | 类 | 行号 | 用途 | 配置开关 |
|---|---|---|---|---|
| 1 | `DistributedSingleFrameSampler` | 18 | 单帧采样（多帧已在 dataset 内对齐时用） | `single_sampler` |
| 2 | `DistributedRegionClassBalancedSampler` | 101 | 按「类 × 区域」补**实例**样本 | `use_region_sampler` / `group_opt_balanced_sampler` |
| 3 | `DistributedGroupOptSampler` | 266 | 按 scene 分组 + 短 scene 贪心合并 | `group_opt_sampler` |
| 4 | `DistributedGroupSlotStreamingSampler` | 599 | scene 分组 + 槽位轮转 | `group_slot_streaming_sampler` |
| 5 | `DistributedGroupSlotStreamingOptSampler` | 871 | 上一代（builder 里已注释） | — |
| 6 | **`DistributedGroupSlotStreamingOptV2Sampler`** | **1101** | **当前主线**：slot round-robin + slot-tail hold + CBGS | `group_slot_streaming_sampler`（实际命中）/ `group_opt_cbgs_sampler` |

### 5.2 builder 的选择逻辑（`:105-140`，**elif 链**）

```python
builder.py:93   if balanced_sampler
builder.py:103  elif single_sampler
builder.py:112  # elif group_slot_streaming_sampler          ← 已注释的旧版
builder.py:121  elif group_slot_streaming_sampler  → DistributedGroupSlotStreamingOptV2Sampler  ("OPTV2")
builder.py:130  elif group_opt_sampler             → DistributedGroupOptSampler  ("Mamba")
```

**⚠️ 优先级陷阱**：主配置 `group_opt_sampler=True`（`config:147`）与 `group_slot_streaming_sampler=True`（`config:151`）**同时为真**，而 `:121` 在 `:130` 之前命中 ⇒ **实际生效的是 OptV2，`DistributedGroupOptSampler` 永不触发**。读 config 的人会误以为走的是 GroupOpt。

另一处：`builder.py:139`（shuffle 分支）早于 `:154` ⇒ **`shuffle=True` 时 `test_multiPkl_sampler` 永不可达**（评测时若没关 shuffle，multi-pkl 采样静默失效）。

前置分流：若 `runner_type == 'IterBasedRunner'`，会优先用 `GroupInBatchSampler` / `GroupInBatchNoSkipSampler`，**两者不经过 OptV2**（主配置为 `EpochBasedRunner`，不触发）。

### 5.3 `__iter__:1489` 的六步流程（A 级）

1. **双随机源**：`torch.Generator` + `np.random.default_rng(seed + epoch)`；
2. **取 scene 列表**：CBGS 时用 `self._cbgs_scenes`（必要时先 `_refresh_cbgs_budget(epoch)`）；否则 `_balance_scenes(rng)` 做 region-class 场景级过采样，并在 rank0 打印 per-class / per-region 的 orig / resample 实例数表；
3. `perm = torch.randperm(len(scenes))` 打乱，再 `my_scenes = [scenes[i] for i if i % num_replicas == rank]` **按 rank 取模切分**（只 shuffle scene 顺序，**scene 内保持原始时间序**，`:1509-1513`）；
4. `keep_aug = dataset.keep_consistent_seq_aug and not test_mode`（主配置 True）；
5. `_slot_round_robin_emit(my_scenes, num_slots=samples_per_gpu, ...)`；
6. `_pad_stream_to_num_samples(stream, num_samples, my_scenes, ...)` → `iter(stream)`。

### 5.4 slot round-robin 详解（`_slot_round_robin_emit:1340-1429`）

**结构**：`q = deque(seq_lists)`（每条是一条 scene 的帧下标序列），`slots = [None] * num_slots`。

**每轮**对每个 slot 调 `step(i)`：

1. 无持有 scene → `q.popleft()` 认领一条；
2. 吐出该 scene 序列的下一帧下标并推进 `pos`；
3. 序列耗尽 → 继续认领新 scene（**递归 `step`**）；
4. 队列空 → 释放 slot。

**轮末**：

- 空 slot 用 `slot_tail[i]`（该 slot 上一帧）回填 → **"slot-tail hold"**，保证 batch 形状固定；
- 若 tail 也为 `None` → 本轮记 `placeholder_rounds` 并用 **idx 0** 垫位（rank0 侧 `logger.warning`，提示 `len(my_scenes) >= num_slots`）。

**`keep_consistent_seq_aug=True` 时**：按 slot 采样 IDA/BDA，并把每个元素包成 `dict(idx, ida_config, bda_config, occ_id)`；同一 slot 内共享同一份 aug；`slot_occ` 计数器递增，供 pad 复用。

**slot 与时序的关系（核心机制）**：`num_slots == samples_per_gpu`，一个 slot 在相邻两轮吐出的就是**同 scene 的相邻帧** ⇒ **同一"列"（batch 内固定位置）跨 iteration 保持时序连续**。这正是模型侧 mamba/递归 buffer 状态所需的前提。

> **副作用提示**：一个 batch 内**不同行可能属于不同 scene**（不同 slot 各持一条 scene）；时序一致性是"按列"而非"按 batch"。

### 5.5 epoch 长度 `num_samples` 的权威公式

```python
# :1151-1156  基础值
self.num_samples = int(math.ceil(len(dataset) / self.num_replicas / self.samples_per_gpu)) * self.samples_per_gpu
self.total_size  = self.num_samples * self.num_replicas
self._base_num_samples = self.num_samples

# :1326-1332  CBGS 打开后，每个 epoch 用 N' 重算
n_prime = sum(len(s) for s in self._cbgs_scenes)          # 均衡后总帧数
self.num_samples = int(math.ceil(n_prime / self.num_replicas / self.samples_per_gpu)) * self.samples_per_gpu
self.total_size  = self.num_samples * self.num_replicas
```

- 语义：`num_samples` 是**每 rank 的样本数**，向上取整到 `samples_per_gpu` 的整数倍；
- 开 CBGS 后**随 epoch 变化**（`set_epoch` → `_refresh_cbgs_budget:1543-1549`），并打印 `factor ~ N'/len(dataset)`；
- 主配置 `samples_per_gpu=2`（注释："HR(1024) state+ground 共享金字塔显存大，调低 batch"）、`workers_per_gpu=8`、`max_epochs=12`。
- V5 四件套的 `samples_per_gpu`：`...V5Temporal`=12（标称）、`...Entity`=8、`...EntityOccTop`=4、`...EntityGeoDual`=4（后两者注释写明"OccTop 1024 + per-class height"、"halved for larger geo ray budget"）。

### 5.6 pad 策略（不足时怎么补）

| 采样器 | `pad_mode` | 行为 |
|---|---|---|
| **OptV2（主线）** | `"cycle"`（默认）/ `"repeat_first"` | 循环本 rank 已生成流 / 用首个样本索引填充（`:621`, `:649`） |
| Opt | `"last_frame"` | 用最后一帧填充（`:880`） |

`_pad_stream_to_num_samples:1432-1487` 细节：

1. stream 超长 → **直接截断**；
2. 不足 → 用 **`my_scenes[-1][-1]`（最后一个 scene 的最后一帧）** 作为 `pad_idx` 反复复制；
3. `keep_consistent_seq_aug=True` 时，优先找"**属于最后 scene 且 `occ_id` 最大**"的流内元素复用其 IDA/BDA/occ_id，找不到才新采样。

**历史坑与修复形态（重要）**：早期"槽位不足时 pad 到 index 0"会触发 **cusolver 错误**，且会让同一 slot 的时序在 pad 处跳变。现形态 = "复用末 scene 末帧 + 复用同一份增强配置" ⇒ **时序类 bug 的修复方式往往体现在 padding/边界的细节里**（增补篇 §2.4）。

**注意**：pad 用最后 scene 的帧、且 slot-tail hold 复用同 scene ⇒ batch 内 `idx` 相同的行会连续推进时序，**仅在真正换 scene 时才触发模型侧 reset**——这是"数据侧 patch 与模型侧 reset 语义必须一致"的隐性契约。

### 5.7 region-class balanced sampler 详解（`101-262`）

- 输入：`dataset.region_num_info [N, C, 4]`（每帧每类在 4 个分区的实例数，来自 `_get_region_info:376`）。
- 目标：`target_region_class_counts[c, r]`，来自主配置的 `cls_list`（如 truck 100000×4、animal 10000×4…）。形状必须与 `(num_classes, num_regions)` 一致，否则 **raise**。
- 算法 `_build_balanced_indices:180-209`：若现有实例数 < 目标，按"含该 (c,r) 的帧"的实例数做**概率重采样**直到达标；epoch 长度取 `max(balanced_len, N)`（`:164-171`）。
- **代价**：复制的是**单帧** ⇒ **破坏 scene 内时序**（这也是它与 CBGS 互斥的根本原因，见 §6.4）。
- 主配置 `group_opt_balanced_sampler=False` ⇒ `use_region_sampler=False`（**未启用**）。

### 5.8 GroupOpt sampler（`266-596`）

- **不按类补**，而是按 scene（`flag`）分组 + **短 scene 贪心合并**：`target_batch_size = samples_per_gpu × num_replicas × scene_merge_factor`，把 size 小于目标 **1.5 倍**的 scene 合并成一个组再 padding（`_build_merged_groups:482-511`），并打印 `estimated_data_saving`（`:410-417`）。
- 目的是减少"每个短 scene 都 pad 到整 batch"的浪费。
- 它同时支持 region 补样（`:316-341, 425-455`）。
- **但如前所述，主配置下该类永不触发**（§5.2）。

### 5.9 采样侧风险与监控点

| # | 风险 | 证据 | 影响 |
|---|---|---|---|
| 1 | **`placeholder_rounds` 用 idx 0 垫位** | `:1340-1429` + rank0 warning | 引入与该 slot 时序无语义关系的假样本；`samples_per_gpu=2` 时 slot 只有 2 个，`my_scenes` 在 8 卡下是否恒 `>= num_slots` **未用真实数据校验** |
| 2 | `error_idx` 静默降低有效样本量 | `__getitem__:683-744` | 无显式统计，需自行采集 |
| 3 | **采样区域 ≠ 评估区域** | `_get_region_info:378-388` vs `det13Cseg8C_config_260624.py:10` | region 补样的目标区与考核区不同（§10.3） |
| 4 | `region_num_info` 用 `clscfg.det_mapping[name]` **直接下标** | `:399` | 遇映射表外新细类会 `KeyError`；建议改 `.get(name, -1)` |
| 5 | 单帧 sampler 不分组 | `:18-97` | 时序会跨 scene 乱序（当前未启用，但开关存在） |
| 6 | `shuffle=True` 使 `test_multiPkl_sampler` 不可达 | `builder.py:139` 早于 `:154` | 评测 silent 失效 |

---

## 6. 类别与区域均衡

### 6.1 三套机制解决三个不同问题

| 机制 | 解决的问题 | 复制单元 | 是否保时序 | 主配置状态 |
|---|---|---|---|---|
| region-class balance | 某些「类 × 区域」实例数不足 | **单帧** | ✗ | 未启用 |
| **CBGS（scene-level）** | 按类**拉长 epoch**（≈1.75×），提升稀有类曝光 | **整条 scene** | ✔ | 仅在部分配置启用 |
| GroupOpt（短 scene 合并） | 减少短 scene 的 padding 浪费 | 组（多 scene） | ✔ | 永不触发（被 elif 链抢占） |

### 6.2 CBGS 九步算法全解（`_balance_scenes_cbgs:1253-1322`，A 级）

1. **池类**：`cbgs_pool_classes = class_names[:11]`，**刻意剔除 `humanlike_background` / `excavator_base`**；统计范围 `cbgs_range_m = 120`（m）。
2. **命中统计**：对每个 scene 统计池内各类的**命中帧数**；仅当 `n_hit >= cbgs_min_hit_frames`（**默认 3**）时，该 scene 才进入该类候选池 → `class_scene_idxs[c]`。
3. **基数**：`duplicated = Σ_c |class_scene_idxs[c]|`（"类-场景"总对数）；`n_cls =` 非空类数；`n_c_base = duplicated / n_cls`。
4. **λ 反解（关键数学）**：

   ```python
   n_prime_base = sum(n_c_base * _mean_len(class_scene_idxs[c]) for c in nonempty)
   n_orig       = max(len(dataset), 1)
   lam          = (length_factor * n_orig) / max(n_prime_base, 1e-6)   # length_factor 默认 1.75
   ```

   ⇒ **λ 由"目标 epoch 长度倍率 × 原始帧数"反解得出，不是硬编码**（配置注释原文：*"λ is computed, not hardcoded"*）。工程含义：改 `cbgs_length_factor` 就能**线性控制 epoch 长度**；加/减 pkl、改 `min_hit` 都不会让长度不可预期地漂移，实验可比。

5. **每类采样数**：`n = round(lam × n_c_base)`，下限 1，上限 `len(inds) × cbgs_max_ratio`（**默认 5**）。
6. **有放回抽 scene**：`rng.choice(inds, size=n, replace=True)`；把抽中 scene 的**全部帧**展平进 balanced 列表 ⇒ **保时序完整**。
7. **可观测性**：rank0 打印 `duplicated_samples / balanced_scenes / lambda / length_factor / min_hit / max_ratio` 及**逐类 `scenes / ratio / n_sampled` 表格**——这是调参依据。
8. **随机性可控**：`rng = np.random.default_rng(self.seed + epoch)`（`:1324`）⇒ **按 epoch 固定种子，可复现**（可做 A/B）。
9. **预算刷新**：`_refresh_cbgs_budget:1322-1337` 每 epoch 用 `N'` 重算 `num_samples`（§5.5）。

### 6.3 CBGS 现状与版本适配

| 项 | 事实 |
|---|---|
| 开关 | `use_cbgs_scene_balance` + `group_opt_cbgs_sampler`（`:1187-1200`） |
| dataset 默认 | `use_cbgs_scene_balance=False`（`eq_nuscenes_temporal_multitask_mamba.py:219`）⇒ **只有显式打开的配置生效** |
| 主配置 | `group_opt_cbgs_sampler=True` 出现在 `..._roi_new.py:219`；参数经 `:1456-1461` 传进 dataset |
| 14 类兼容 | CBGS 用 **13 类** `clscfg.det_mapping`；14 类 ROI 配置因 `roadcone/rockfall` 进不了桶**暂不开 CBGS**（`docs/cbgs_pairgt_seq_aug_changelog.md:91`），`fdbc658`（09-16）"CBGS 策略适配 14c"改 dataset 21 行 |
| 源出处 | changelog 提到"从源仓库配方合入三项"，但**未记录源仓库名/commit**，无法本地验证（未确认项） |

### 6.4 互斥矩阵

| 组合 | 是否允许 | 断言位置 | 原因 |
|---|---|---|---|
| CBGS × region-balance | ✗ **互斥** | `multitask_sampler.py:1147-1149`（采样器）+ `eq_..._mamba.py:335-337`（数据集） | 两者都整体改写 epoch 长度与索引分布（CBGS 改"帧数预算"、region 改"实例数目标"），叠加会互相污染口径；且 CBGS 复制整 scene（保时序）、region 复制单帧（破时序） |
| GroupOpt × OptV2 | 配置上可同时写 True | `builder.py:121` 先于 `:130` | 实际只有 OptV2 生效（§5.2） |
| CBGS × OptV2 | ✔ 组合使用 | — | CBGS 由 OptV2 内部消费 `_cbgs_scenes` |

---

## 7. pipeline 逐算子

### 7.1 train_pipeline（20 个算子，含 Collect，A 级）

| # | 算子 | 实现 | 读的 key | 写/新增的 key | 关键参数 | 设计意图 |
|---|---|---|---|---|---|---|
| 1 | `LoadEQOccGTFromFileOptimizedMamba` | `loading.py:3694` | `occ_gt_path` | `occ_scale`、`voxel_semantics_fine`(512×512×32 int32)、`mask_lidar_fine`、`occ_eval` | `cache_data=False` | 读 LR（`*_fine`）occ 标签；`cache_data=False` 注释"禁用缓存避免内存累积"；失败置 `occ_scale=0` 早退 |
| 2 | `LoadAnnotationsLidarOccOptimizedMambaFix` | `loading.py:4312` | `ann_infos`、`img_inputs`、`occ_scale`、`voxel_semantics_fine` | 改写 `gt_bboxes_3d`/`gt_labels_3d`/`bda_rot`/`img_inputs`(+bda)/`ego2img`/`voxel_semantics_fine`/`mask_lidar_fine` | `bda_aug_conf`、`occ_size=[512,512,32]` | 采样 BDA（旋转/缩放/flip）并施加到 box + OCC 体素；`occ_scale==0` 直接 return |
| 3 | `PrepareImageInputsMultitaskMamba` | `loading.py:1302` | `cams`、`scene_drop_cfg`、`ida_config` | `img_inputs`(7 元组)、`cam_names`、`canvas`、`2d_seg_maps`、`2d_seg_maps_mask`、`2d_seg_edge_maps`、**`drop_sensor_type`、`drop_mask`、`drop_lidar_mask`**、`sweep_cams_infos` | `is_train=True, edge_width=3, mapping=ORIGINAL_TO_TRAIN_ID, ignore_index=255, use_remap=True` | 7 路相机读图 + 增强 + 归一化；算 2D seg 图与边缘图；**drop 决策在此诞生** |
| 4 | `EQLoadPointsFromFileMultitaskMamba` | `loading.py:2882` | `pts_filename*` | `points_t/_l/_r/_b`（+`_top_aux/_mid_left/_mid_right`）、`points`（拼接） | `coord_type=LIDAR, load_dim=4, use_dim=4, enable_new_lidars` | 逐雷达读 bin；`points` = 多雷达拼接（**仍在各自雷达坐标系**） |
| 5 | `EQPointToMultiViewDepth` | `loading.py:5055` | `img_inputs[0..5]`、`points_*`、`drop_mask` | `gt_depth`(7,H,W)；可选 `gt_depth_obj_mask` | `downsample=1, with_obj_mask=False, is_train=True` | 多雷达 → 多视角 gt_depth（§7.3） |
| 6 | `ToEgoMultitaskMamba` | `transform.py:2930` | `points_*`、`drop_sensor_type`、`drop_lidar_mask`、`cams[...]` | 改写 `points`（合并到 ego/camego 系）、`kept_indices`、`drop_lidar_mask`；**pop 全部 `points_*`** | `is_train=True, random_drop_lidar=0.3, drop_all_lidar=0.0` | 7 路雷达统一到"参考相机 ego"系并合并；执行 lidar drop |
| 7 | `LoadAnnotationsMultitaskMamba` | `loading.py:4785` | `ann_infos`、`points`、`img_inputs`、`cams` | 改写 box/label/`gt_names`/`num_lidar_pts`/`num_radar_pts`/`valid_flag`/`visibility_flag`/`gt_velocity`/`instance_inds`/`pts_semantic_mask`/`pts_semantic_conf`/`img_inputs`(+bda) | `with_seg_3d=True, with_autolabel=False, classes` | 把 box/点级 seg 标注落到 ego 系；`_load_semantic_seg_3d:4589` 读 `lidarseg*` |
| 8 | `EgoPointsFilterMultitaskMamba` | `transform.py:3444` | `points`、`pts_*_mask` | 改写四者 | `filter_range=ego_filter_range` | 过滤自车车体上的点 |
| 9 | `InvalidBoxFilterMultitaskMamba` | `transform.py:2185` | `gt_bboxes_3d`、`gt_labels_3d` | 改写 box/label + 全部并行数组 | — | 剔除非法框（尺寸/朝向无效） |
| 10 | `PointsRangeFilter` | `transform.py:1788` | `points`、`pts_*_mask` | 改写 | `point_cloud_range` | 点云裁剪到 BEV 范围 |
| 11 | `ObjectRangeFilterMultitaskMamba` | `transform.py:1603` | box/label/并行数组 | 改写全部 | `point_cloud_range, filter_z=True` | 按 BEV 范围裁剪 GT 框 |
| 12 | **`MapDetectionClassMamba`** | `loading.py:5626` | `key`、`gt_names`、`gt_labels_3d` | 改写 `gt_labels_3d`（细→粗 + ignore 剔除），连带裁剪全部并行数组 | `ignore_index=-1, keep_fine_labels=True(死参数)` | **必须在名称过滤之前**（§7.3） |
| 13 | `ObjectNameFilterMultitaskMamba` | `transform.py:2056` | `gt_labels_3d` | 改写 box/label + 并行数组 | `classes` | 按类别名白名单过滤 GT |
| 14 | `InstanceNameFilterMamba` | `transform.py:1332` | `gt_labels_3d` | 同上 | `classes` | 同上（多一层 instance 一致性处理） |
| 15 | `CameraVisibleFilterMamba` | `transform.py:3644` | `key`、`visibility_flag`、`gt_bboxes_3d` | `gt_bboxes_3d_vision`、`gt_labels_3d_vision`、`instance_inds_vision` | `visible_classes=['1','2','3','']` | 按 7 路可见性筛出"视觉 GT"分支 |
| 16 | `PairGTEnsureVisionGT` | `pairgt_vision_gt.py:7` | `gt_bboxes_3d` | 兜底 deepcopy 出 vision 键 | — | 防 vision 键缺失导致下游 KeyError |
| 17 | `PointShuffleMultitask` | `transform.py:1757` | `points`、`pts_*_mask` | 改写三者（随机打乱） | — | 打散点序，防数据集顺序偏置 |
| 18 | `EQPointSegClassMapping` | `transform.py:3696` | `pts_semantic_mask` | 改写 | `seg_label_mapping=None` | 原始语义类 → 合法类 id（含 id 72 clip 防护） |
| 19 | `EQNuScenesSparse4DAdaptorMultitaskMamba` | `transform.py:797` | box/label/points/`instance_inds` | **`T_global`、`T_global_inv`**、`focal`、`instance_id(_vision)`、`train_ins_id(_vision)`；box/label/points → `DC(...)` | `with_gt=True` | 训练框架入口：统一张量化 + **产出时序对齐矩阵** |
| 20 | **`Collect`** | `config:649` | — | 打包 batch | `meta_keys=[T_global, T_global_inv, timestamp]` | 白名单化输出（§7.4） |

### 7.2 test_pipeline（16 个算子）与 train 的差异

| # | 差异 | 说明 |
|---|---|---|
| 1 | 首两算子（`LoadEQOccGTFromFileOptimized` / `LoadAnnotationsLidarOccOptimized`）**注释掉** | test 不需要 OCC GT/BDA |
| 2 | `PrepareImageInputsMultitaskMamba`：`is_train=False, test_lidar_only=False` | **无 drop 决策** |
| 3 | `EQLoadPointsFromFileMultitaskMamba`：无 `use_sweeps_byframe` | — |
| 4 | `EQPointToMultiViewDepth`：`is_train=False`，未传 `with_obj_mask`；`eval_gt_depth=False` 时**直接返回全零** `gt_depth`（`loading.py:5265`） | 下游需自行判零 |
| 5 | `ToEgoMultitaskMamba`：`is_train=False, test_vision_only=True` → `_transform_single_frame_to_ego` **立即返回空点云** | ⚠️ **纯视觉推理**；导致点分割 pred/GT 同时为空、**该指标失效** |
| 6 | `LoadAnnotationsMultitaskMamba`：`is_train=False` | — |
| 7 | `PairGTEnsureVisionGT` / `PointShuffleMultitask` **不存在** | — |
| 8 | `Collect`：**16 key**（无 vision box、无 OCC 三件套） | — |

### 7.3 顺序即正确性的硬约束（每条都对应一次踩坑）

1. **深度 GT 必须早于 `ToEgo` / 传感器 drop**。`EQPointToMultiViewDepth` 的 docstring 原文：
   > *"Intended to run after PrepareImageInputs + EQLoadPointsFromFile and **before ToEgo / LoadAnnotations so depth GT is not affected by BDA or lidar drop**."*
   配置里另有注释：*"Depth GT must be built before ToEgo pops points_*"*——因为 `ToEgoMultitaskMamba:3217-3219` 会 `pop` 掉全部 `points_*`。
2. **类别映射必须早于名称过滤**（`MapDetectionClassMamba` 在 `ObjectNameFilter` 之前，配置注释）。
3. **scene 分组必须先于采样**（时序连续性的前提）。
4. **`drop_lidar_mask` 必须写回供时序帧复用**（`transform.py:3196`，注释 *"Reuse current-frame drop_lidar_mask for temporal consistency"*）。

### 7.4 `Collect` 的 21 个 active key（A 级，17 双引号 + 4 单引号）

| # | key | 类型 | 目标形状 | 下游 |
|---|---|---|---|---|
| 1 | `img_inputs` | tuple(7) | imgs `(7,3,H,W)`、sensor2ego/ego2global `(7,4,4)`、intrins `(7,3,3)`、post_rot/trans `(7,3,3)/(7,3)`、(7,)=bda 3×3 | 图像 backbone / ViewTransformer / BDA |
| 2 | `points` | DC | `(N,4)`（已并入 ego/camego 系） | Voxel encoder（N 已扣 ego filter + range filter + lidar drop） |
| 3 | `timestamp` | meta | 标量 | 时序对齐 / `meta_keys` |
| 4 | `idx` | meta | 标量 | 场景 id / 模型侧 reset |
| 5 | `focal` | np/tensor | `(7,)` = `|intrins[:,0,0]|` | 多焦距相机深度缩放 |
| 6 | `canvas` | list | 7×`(H,W,3)` uint8 | 仅可视化/调试 |
| 7 | `T_global` | np(4,4) | — | 时序 ego→global |
| 8 | `T_global_inv` | np(4,4) | — | global→ego |
| 9 | `gt_depth` | tensor | `(7,H,W)` float32 | 深度监督 |
| 10 | `gt_bboxes_3d` | list[DC] | `(M,9)` | 3D 检测头 |
| 11 | `gt_labels_3d` | list[DC] | `(M,)` | 3D 检测头（已粗化） |
| 12 | `gt_bboxes_3d_vision` | list[DC] | `(Mv,9)` | 视觉辅助分支 |
| 13 | `gt_labels_3d_vision` | list[DC] | `(Mv,)` | 同上 |
| 14 | `pts_semantic_mask` | DC | `(N,)`（与 `points` 同序） | 点云语义分割头 |
| 15 | `voxel_semantics_fine` | list[DC] | `(512,512,32)` int32 | OCC 监督 |
| 16 | `mask_lidar_fine` | list[DC] | `(512,512,32)` | OCC 评估掩码 |
| 17 | `occ_scale` | list/scalar | 0/1 | OCC loss 有效性门控（0=丢弃本帧 OCC） |
| 18 | `2d_seg_maps` | list[DC] | 7×`(H,W)` long，缺失处 255 | 2D 分割头 |
| 19 | `2d_seg_maps_mask` | list[DC] | 7×标量 0/1 | 2D 分割 loss 有效位（drop 相机为 0） |
| 20 | `2d_seg_edge_maps` | list[DC] | 7×`(H,W)` long | 边界辅助监督 |
| 21 | `key` | meta bool | 标量 | **关键帧总开关**，贯穿所有 GT 过滤算子 |

**被注释的 12 项**：`instance_id` / `instance_id_vision`、`occ_eval`、`sweeps_points_infos` / `sweep_cams_infos` / `sweeps_num` / `sweep_ego2global`（时序 sweeps 系列）等 ⇒ 再次印证 **Sparse4D 实例传播与 sweeps 已退出主线**。

**Collect 行为**：list 型 key 走 `DC(..., stack=False)` → `list[DataContainer]`；`meta_keys` 走 `DC(cpu_only=True)`。

### 7.5 命名不一致清单（同名不同义 / 同义不同名）

| 现象 | 位置 |
|---|---|
| `occ_path`（history，`:924`）vs `occ_gt_path`（current，`:988`） | 6 个 dataset 类均如此分叉 |
| `occ_size` 一名两义：**形状** `[512,512,32]`（config:108）vs **体素边长** `[0.3,0.3,0.4]`（config:231） | config |
| `voxel_semantics_fine` 语义漂移：loader 阶段稀疏 N×4（`loading.py:3512`）→ MambaFix 后稠密 (512,512,32)（`:4347`） | pipeline |
| 同一文件两个 gold 根：`"./data/occ_gt_gmd/..."`（history）vs `"/e-vepfs/lijincheng/..."`（current） | `..._multitask.py:742` vs `:806` |
| 四套体素几何并存：`[0.2,0.2,0.1]` / `[0.4,0.4,0.4]`（`eacon_utils/eq_occ_metrics.py:67,383`）、`[0.15,0.15,0.2]`、模型默认 `[0.15,0.15,0.1]` | 多处 |
| `use_sweeps_byframe` 三处全 False（dataset 构造默认 True → 实例属性 True → `get_data_info:568` **硬编码 False** 覆盖；pipeline 两处 False） | `..._mamba.py:114, 210, 568`；config:800/809 |
| `sort_datasets` 行为不一：生效 / 接受但忽略 / 完全不存在 | `..._mamba.py:543` / `_byframe.py:115`（恒排序） / `flow_temporal.py` 无 |
| `history_pipeline` 被 6 个 dataset 类接受但**从不存储/使用** | `..._mamba.py:108` 等 |

### 7.6 三件套几何闭合性（改数据必查）

```
voxel_size        = [0.15, 0.15, 0.2]
point_cloud_range = [-31.8, -76.8, -4.4, 121.79, 76.79, 8.39]
full_point_cloud_range = [-31.8, -76.8, -4.4, 121.8, 76.8, 8.4]
dense_shape       = [1024, 1024, 64]
```

| 轴 | `point_cloud_range` 跨度 | `dense_shape × voxel_size` | 闭合? |
|---|---|---|---|
| X | 153.59 | 153.60 | ❌ 差 0.01m |
| Y | 153.59 | 153.60 | ❌ 差 0.01m |
| Z | 12.79 | 12.80 | ❌ 差 0.01m |
| 用 `full_point_cloud_range` | 153.60 / 153.60 / 12.80 | 同上 | ✅ **闭合** |

> **关键细节**：`point_cloud_range` 是"收窄 0.01m"的版本，**真正闭合的是 `full_point_cloud_range`**，而 view transformer 恰好用后者第 4 参数（config:404）。**改三件套时两者必须同改**，否则差 0.01m 会引起栅格边界错位。

其余栅格一致性（实测均闭合）：

| 栅格 | 缩放 | 尺寸 | 闭合 |
|---|---|---|---|
| 稠密 occ | `occ_size=[0.3,0.3,0.4]` | `[512,512,32]` | 512×0.3=153.6 ✅、32×0.4=12.8 ✅ |
| BEV 特征 | `x=[-31.8,121.8,0.6]`, `y=[-76.8,76.8,0.6]` | 256×256 | (121.8+31.8)/0.6=256 ✅ |
| OccTop HR | `occ_size=[0.15,0.15,0.1]` | `occ_vox_shape_hr=[1024,1024,128]` | ✅ |
| GeoDual | `geo_voxel_size=[0.15,0.15,0.1]` | `geo_grid_size_fine=[1024,1024,128]` | ✅ |

> ⚠️ **双约定陷阱**：BEV 特征 256×256 @0.6m，两套 occ 轨都是 1024×1024 @0.15m。`det_occ_aug_swap_xy` 存在的唯一原因就是 det BEV 与 occ 柱面的 **H/W 轴约定不一致**（`migration_occ_top_dual_track.md:329` 记为"历史坑"）。另 `occ_ground_top.py:14` 明确 ground head 布局是 `[H(y),W(x)]`，与 occ 的 `[W(x),H(y)]` 需转置对齐。

### 7.7 传感器实际加载量（数据层门控）

| 项 | 事实 | 证据 |
|---|---|---|
| 相机 | **7 路全部加载，无门控** | `choose_cams()` 仅在 `Ncams < len(cams)` 时随机子采样（`loading.py:1348-1357`），而 config `Ncams=7 == len(cams)=7` ⇒ 该分支永不进入 |
| 雷达声明 | 7 路（`top`/`top_aux`/`left`/`mid_left`/`right`/`mid_right`/`back`） | config:243-255 |
| 雷达实际 | 取决于 `enable_new_lidars`；为 False 时**只加载 4 路**（前主/左/右/后），`loading.py:2926 if self.enable_new_lidars:` 整块跳过 | `config:254`（某配置）|
| 另一配置 | `enable_new_lidars=True`（注释即 **"4/7 雷达混合训练"**），基础 4 路 + 新增 3 路（仅当 info 里存在对应 `lidar2ego_rotation{suffix}` 才启用） | config:316-328；`transform.py:2940-2946` |
| **合并行为** | 多路点云被 `cat` 成 **1 份**，模型只见单一点云 | `loading.py:2938 merged_points = points_list[0].cat(points_list)` |
| 模型的雷达感知 | **零 per-lidar 概念**（`grep points_t\|points_l\|points_r\|points_b` 在 `models/` 下 0 命中） | ⇒ 模型无法区分点来自哪路雷达，也无各路独立外参参与 |
| `is_required` 装饰性 | 缺失路径**静默跳过**，不报错不告警；真正门控是 `if lidar_path_key in frame_info:` | `loading.py:2917` |

⇒ "4 路雷达"的准确表述是：**数据层按最多 4 路（或 7 路）读取并拼接为单一 ego 点云；模型侧是单雷达输入**。要真正用多雷达（分路 BEV、各路独立体素化）需在 `loading.py:2938` 之后保留 per-lidar 张量并新增模型消费点——**当前架构不具备**。

---

## 8. 增强与 scene 级传感器 drop

### 8.1 设计意图

矿山现场相机可能被泥污遮挡、雷达可能部分失效，模型必须在**单模态缺失**下仍能出结果——这是"纯视觉检测辅助头"存在的业务支点。因此增强体系的核心不是"加噪声"，而是"**制造真实会发生的模态缺失**"。

### 8.2 两段式实现链路（五阶段，A 级）

| 阶段 | 行为 | 锚点 |
|---|---|---|
| ① **建表（dataset）** | `_rebuild_scene_drop_table:353` 调 `build_scene_drop_table(scene_ids, epoch, drop_seed, cam_names, num_lidars, drop_lidar_only=False, ensure_one_camera=True)`；`set_epoch:371` **每个 epoch 重建一次** ⇒ 每 epoch 随机丢弃**不同 scene** 的相机/雷达 | `:353`, `:371`；`pipelines/scene_sensor_drop.py:85`（模块默认 `P_IMG=P_LIDAR=0.3`，`:4-5`） |
| ② **注入** | `_prepare_train_data:623,677` 按 `idx` 注入 `data['scene_drop_cfg']` 与 `data['epoch']` ⇒ **同 scene 所有帧共用同一份 drop 配置** | `:677` |
| ③ **消费（生决策）** | `PrepareImageInputsMultitaskMamba:1648-1700`，优先级 **场景级表 > 逐帧随机回退 > 强制 lidar-only**；产出 `drop_sensor_type ∈ {img, lidar, none}` + `drop_mask` + `drop_lidar_mask` | `loading.py:1648-1700` |
| ④ **执行（lidar）** | `ToEgoMultitaskMamba:3127-3150` **只读不重采样**（保时序一致）；门控必须同时满足 `is_train` + `random_drop_lidar>0` + `drop_sensor_type=='lidar'` | `transform.py:3127-3150` |
| ⑤ **时序复用** | drop 后把 `drop_lidar_mask` 回写，供 sweeps 帧**复用同一 mask** | `transform.py:3196` |

**决策代码（原文，`loading.py:1650-1666`）**：

```python
drop_sensor_type = 'none'
drop_mask = {}
drop_lidar_mask = None          # None = "ToEgo 自行决定"; set(含空集) = 场景级已决策
scene_drop_cfg = results.get('scene_drop_cfg') if self.is_train else None

if scene_drop_cfg is not None:
    drop_sensor_type = scene_drop_cfg['drop_sensor_type']
    drop_mask = dict(scene_drop_cfg.get('drop_mask', {}))
    drop_lidar_mask = set(scene_drop_cfg.get('drop_lidar_mask', []))
elif self.is_train and self.data_config.get('random_drop_img', None) is not None:
    rand_val = random.random()          # 回退：逐帧随机
    if rand_val < 0.3:   drop_sensor_type = 'img'
    elif rand_val < 0.6: drop_sensor_type = 'lidar'
    if self.drop_lidar_only: drop_sensor_type = 'lidar'
```

### 8.3 参数与语义细节（易踩）

| # | 细节 | 说明 |
|---|---|---|
| 1 | `P_IMG = P_LIDAR = 0.3` | 模块级默认（`scene_sensor_drop.py:4-5`） |
| 2 | `drop_lidar_mask` **三态语义** | `None` = "交 ToEgo 自行决定"；`set`（**含空集**）= 场景级已决策；**空集是合法决策 = 全保留** ⇒ 代码必须显式判 `is not None` 而不是判真假 |
| 3 | **"至少留一个相机"两处互补实现** | ① **场景级路径**在 dataset 侧：`build_scene_drop_table(..., ensure_one_camera=True)`，`scene_sensor_drop.py:44` 的 `if ensure_one_camera and all(drop_mask.values())` 才救回一个；② **逐帧回退分支**受 operator 自身 `ensure_one_camera` 约束，而该参数 `__init__` **默认 `False`** 且配置未覆盖 ⇒ ⚠️ **回退路径下可能 7 路相机全黑**（已知风险） |
| 4 | 图像落地方式 | `get_inputs`（`loading.py:1802-1807`）对命中相机 `Image.new('RGB', img.size, (0,0,0))` **置黑** + 2D seg mask 置 0；`test_lidar_only` 同样置黑 |
| 5 | 形状契约 | 物理缺失/文件不存在走 `Eye`/`zeros` 占位并**保留 slot**（`loading.py:1693-1701`）⇒ **`len(imgs)==7` 恒成立** |
| 6 | lidar 落地 | `filtered = [(i, pts) for i, pts in all_points if i not in drop_lidar_mask]`；`test_vision_only` 或 filtered 为空 → 返回空点云 |
| 7 | mask 越界防护 | 场景级 mask 会被过滤到 `0 <= i < num_lidars`（`transform.py:3131-3132`） |

### 8.4 增强清单（"写着但没开"多于真正生效，A 级）

| 增强 | 作用/参数 | 状态 | 证据 |
|---|---|---|---|
| **IDA（图像 resize/crop）** | `resize=(-0.06, 0.11)`、长焦只加 0.5×；`crop_h=(0,0)`、`flip=False`、`rot=(0,0)`、**crop_w 随机** | ✅ **开（唯一实跑的图像增强）** | config:1032-1035；`loading.py:1420-1450` |
| 时序一致 IDA/BDA | `keep_consistent_seq_aug=True` 时同 slot/occupancy 共享一套 | ✅ 开 | config:1478；`multitask_sampler.py:1356-1403` |
| **BDA（BEV 旋转/缩放/flip/平移）** | `rot_lim=(0,0)`、`scale_lim=(1.0,1.0)`、`flip_dx/dy_ratio=0.0`、`tran_lim=[0,0,0]` | ⚠️ **代码在跑但恒等（等于关闭）** | config:275-284；`loading.py:4795-4843` |
| HR BDA | `bda_aug_conf_hr` 同样恒等，`occ_size=[0.15,0.15,0.1]` | ⚠️ 恒等 | config:290-299 |
| `data_aug_conf` 的 `rand_flip/rot_lim` | `rand_flip=True, rot_lim=(-5.4,5.4), rot3d_range=[-0.3925,0.3925]` | ⚠️ **实际未生效**：唯一消费方 `EQResizeCropFlipImage` 在当前 pipeline 被注释 | config:1444-1450；`augment.py:88-98`；config:1101-1103 |
| **scene-level sensor drop** | 每 scene 固定一套；img 模式逐相机按 `random_drop_img` 丢、保底留 1 相机；lidar 模式可含 `drop_all_lidar` | ✅ 开 | config:1482-1486, 1037-1039；`scene_sensor_drop.py:4-82`；`loading.py:1646-1689` |
| 互斥约束 | `drop_sensor_type ∈ {img, lidar, none}` 每帧互斥；ToEgo 只在 `'lidar'` 时丢雷达、`ComplementaryCrossModalMask` 只在 `'img'` 时生效 | ✅ 开（设计约束） | `transform.py:3124-3138, 4197-4204` |
| `PhotoMetricDistortionMultiViewImage` | 亮度/对比度/饱和度/色调 | ⛔ 注释关闭 | config:1108 |
| `BBoxRotation` / `EQResizeCropFlipImage` | 3D box 旋转、图像 RCF | ⛔ 注释关闭 | config:1101-1107 |
| `RandomCamExtrinsicNoise` | 截断高斯：rot_std 0.3°/max 0.6°、trans_std 0.05m/max 0.15m、prob 0.5、per_camera、时序共享（`share_across_temporal=True`）；`fix=True` 时取 ±max 固定极值；写 `gt_ext_noise` | ⛔ 注释关闭（**实现完整，可一键开**） | config:582-591；`loading.py:5375-5459` |
| `ComplementaryCrossModalMask` | prob 0.1、ratio 0.3、`d_range=(96,224)`；仅在 `drop_sensor_type=='img'` 时触发，对**仍在用**的相机生成 GridMask 乘到 `imgs` 与 `gt_depth`，并把落在被遮像素上的 lidar 点**删掉**（含 bda 逆变换 + 投影 + 投票） | ⛔ 注释关闭 | config:611-618；`transform.py:4052-4204` |
| `RandomDropNearObjectPoints` | prob 0.2、drop_ratio 1.0、`max_range=30m`、`expand_m=1.0`；门控 `_should_run`：必须 `drop_sensor_type=='lidar'` **且非全丢** | ⛔ 注释关闭 | config:633-640；`transform.py:3924-3984` |
| `PointShuffleMultitask` / 各类过滤 / `CameraVisibleFilter` / `MapDetectionClass` | 点序打乱、范围/无效框过滤、可见性过滤、细→粗映射 | ✅ 开 | config:1100-1140 |

### 8.5 三个注释态增强的**开启顺序约束**（重要）

- `RandomCamExtrinsicNoise` **必须放在 `EQPointToMultiViewDepth` 之后**（docstring 明说），否则 depth GT 会被污染；其设计是"**GT 用真外参、ViewTransformer 用噪声外参**"（`loading.py:5376-5384`），是正确的做法；`drop_mask` 命中的相机不施加噪声。
- `ComplementaryCrossModalMask` 会同步裁剪 `pts_semantic_mask`，**长度不匹配直接 `ValueError` 抛错**（严格校验，不是静默）。
- `RandomDropNearObjectPoints` 同步裁 `pts_semantic_mask` / `pts_instance_mask`。

### 8.6 drop 参数的**提交级演进**（现实：初值过大，之后两次下调）

| 提交 | 日期 | 内容 |
|---|---|---|
| `c55b733` | 09-04 15:28 | 新建 `datasets/pipelines/scene_sensor_drop.py`（`build_scene_drop_table:85`）+ dataset 接线（`:343/350-374/677`）；同提交含"挖机半挂车 nms 适配" |
| `183de3d` | 09-07 19:38 | **"修改 drop 概率"**（仅改一个配置 4 行） |
| `7625b58` | 09-07 | **`drop_all_lidar=0`（关闭"整帧丢雷达"）；保留 `random_drop_lidar=0.3`** |
| `92f4c1c` | 09-07 | **`random_drop_img=0`（不丢图像）** |
| `fdbc658` | 09-16 | **"drop 概率降低"**（配合 CBGS 14c 适配） |

⇒ **当前实际口径与模块默认 `P_IMG=P_LIDAR=0.3` 已不同**：图像不再丢、整帧丢雷达关闭、仅保留部分雷达丢（0.3）。这解释了为什么 `Test` 侧 `ToEgo` 的 `drop_all_lidar=0.0`。

**工程含义**：drop 概率是"训练早期需要、后期需要收窄"的**课程型超参**，且与类别数改造（13→14）耦合，需重新标定。

### 8.7 增强体系评估（数据侧结论）

- **实跑增强极弱**：只有 IDA + scene 级 drop + 各类过滤；BDA 恒等、PMD/CrossModal/CamNoise 全关。
- **后果**：模型对**相机外参误差**与**跨模态遮挡**的鲁棒性只能靠 scene 级 sensor drop 覆盖；建议至少灰度开启 `RandomCamExtrinsicNoise`（实现已具备正确设计）。
- **"配置写了但没开"的治理价值**：这些注释态增强是**现成的、已实现、已门控**的候选，开启成本只是改配置 ⇒ 属于"低成本高杠杆"的待办。

---

## 9. 标签质量治理

### 9.1 缺失全景（全量审计结论，A 级）

| 类别 | 规模 | 后果 |
|---|---|---|
| **A 类**：`labels_new.npz` 在，但 `lidar_mask_fine` 为空 `(0,3)` | 22 pkl / **706,821 帧（39%）** | `loss_occ_fine ≈ 0`、`loss_lr_state` 无有效监督 ⇒ **白耗算力** |
| **B 类**：连 `occ_path` 都未绑 | 8 pkl / 76,662 帧 | loader 置 `occ_scale=0`，occ loss 零梯度跳过 |
| **C 类**：正常 | 6 pkl | — |
| **HR 部分帧未绑** | 15 pkl / 7,634 帧 | HR 监督缺失 |
| **LR + HR 双缺** | 8 pkl / **76,662 帧** | 建议从训练集**剔除** |
| 合计受影响 | **84,296 帧** | — |

（对应文档：`docs/lr_mask缺失审计_反馈数据生产方.md`、`docs/不可用数据收集清单_LR_HR双缺.md`、`docs/D类HR绑定补跑_生产执行说明.md`。）

### 9.2 兜底路径：HR mask 降采样补 LR（A 级）

`loading.py:3777-3808`（提交 `99bf85d`，09-05 01:33，"LR lidar_mask_fine 缺失时由 HR labels 降采样兜底"）：

- LR mask 为空时，用**同 token 的 HR `labels.npz` 的 `lidar_mask` 降采样**：HR `1024²×128` → LR `512²×32`，**xy 用 2:1 any、z 用 4:1 any**；
- 实测 **ground 命中 99.2%**（一致性验证）；
- ⚠️ **B 类（无 HR）兜底无效** ⇒ 必须 rebind 或剔除。

同时 `load_labels_npz` 有一条**安全加固**：解析失败**只告警、永不删除源 npz**（`067fdf2`，"彻底关闭 HR labels.npz 解析失败删源"）。历史上曾有 `fbf9ac4`（09-03 17:37）修复"三返回值解开为 2 导致 HR labels.npz 解析必失败"。

### 9.3 HR 路径解析与配置漂移

- `_resolve_occ_gt_path_hr:997-1029`：优先用 pkl 的 `occ_path_hr`；缺失时用 `occ_gt_root_hr` + `occ_gt_lr_name` 对 `occ_path` 做**字符串重映射**（把路径里的 `occ_gt_smallrange` 段替换为 `occ_gt_root_hr`）。
- **实测绑定**：凡有 `occ_path_hr` 的帧 **100% 指向 `/e-vepfs-01/occ_gt/occ_gt_smallrange_15`**（1,710,713 帧 / **95.22%**）；旧目录 `occ_gt_smallrange_260314_hw` **0 帧在用**。
- ⚠️ **但配置里的 `occ_gt_root_hr` 仍写着旧目录**（config:305）⇒ **配置与实际绑定已经漂移**；因 remap 分支在数据有 `occ_path_hr` 时不触发，所以当下无影响，但**将来一旦走 remap 会指向错误目录**（建议同步配置）。
- HR `labels.npz` **磁盘存在性完整**：指向 smallrange_15 的帧 **0 缺失**；真正问题是 8 pkl 整文件未绑 + 15 pkl 部分帧未绑。

### 9.4 审计工具与提交链（证据可追）

| 提交 | 日期 | 内容 |
|---|---|---|
| `99bf85d` | 09-05 01:33 | LR mask 缺失时由 HR labels 降采样兜底 |
| `b903704` | 09-05 01:55 | LR `lidar_mask_fine` 缺失**全量审计报告**（反馈数据生产方） |
| `be6785f` | 09-05 01:56 | 记录 LR mask 缺陷 / HR 绑定检查 / LR state 可视化修复要点 |
| `8a9c871` | 09-05 01:59 | HR `occ_path_hr` 绑定**审计工具**（全量 pkl 高分 occ 指向核查） |
| `f20b0cc` | 09-05 02:08 | HR 绑定最终结论 + grep 核查工具 |
| `667f5b5` | 09-05 02:24 | **全帧审计权威结论**：95.22% 指向 smallrange_15，0 旧目录 |
| `1f65791` | 09-05 04:47 | HR `labels.npz` 磁盘存在性核查（target15 下 0 缺失，95.31% 完整） |
| `9c146f1` | 09-05 04:48 | 追加结论式名单（转数据生产方最终版） |
| `86fe72a` | 09-05 09:35 | **双缺（LR+HR）数据收集清单 + HR rebind 工具** |
| `8947229` | 09-05 09:40 | D 类 HR 绑定补跑脚本与生产执行说明 |

### 9.5 rebind 方案（结论型）

- **不需要跑 backfill 生成器**——会**全跳过白跑**；
- 只需 **rebind 15 pkl 的 `occ_path_hr`（约 7,634 帧）**；
- 工具：`tools/rebind_hr_occ.py`，**只补缺、dry-run 优先**；
- 双缺的 8 pkl（76,662 帧）**直接从训练集剔除**。

### 9.6 `occ_supervision_lost` 卡死防护哨兵（提交 `0dd095d`，09-08 12:40）

- **背景**：09-07 起长训中，HR/LR occ **双丢**的帧触发 loader `raise RuntimeError("point_occ_label build failed.")` 并**打断整个训练任务**（"卡死"）。
- **修复**：
  - loader 侧（`loading_optimized_HR.py:1939-1948`）：不再 raise，改为 `point_occ_label=None` + 新增 **`occ_supervision_lost`** 标志（条件 = HR GT 缺失 + lidar scatter 兜底失败 + LR dense GT 也不可用）；
  - detector 侧（`:2749-2820`）：把该帧 6 路 occ GT 置**无效哨兵**（mask=0 / lr_state=hr_state=-1 / g_cls=2(unknown) / g_valid=False / fb_bits=0）⇒ **只丢 occ 族梯度，不丢样本**。
- **证据文件**：同提交新增 `docs/occ_loss_zero_gate_0908.diff`（155 行改动存档）、`docs/mon_occgate.sh`（轮询共享盘最新 log，命中 `point_occ_label build failed|RuntimeError|Traceback` 即停的监控脚本）、新旧日志快照（`occgate_old_full.txt` 895 行等）。
- **工程范式**：把"报错/丢帧"改成"保留样本、置零 loss"——这是**数据缺失不阻塞训练**的统一策略（与 LR mask 兜底、HR 缺失降级同源）。

### 9.7 另一条静默丢样本路径（OccTop，⚠️ 需监控）

`LoadAnnotationsLidarOccOptimizedTopCls.__call__` 在 `_build_occ_top_labels` 返回 False 时 **`return None`**（`loading_optimized_HR.py:1935-1936`）：

- mmcv 的 `Compose` 遇到 `None` 会**丢弃该样本**；
- 而 `__getitem__` 的异常重采样（`..._mamba.py:468-513`）**不会触发**（因为没抛异常）；
- 判据：`occ_scale_hr==0` 且无 point 回退，或 `occ_scale not in (0,1)`（`:2033-2071`）；
- ⇒ 在 HR 覆盖率低的 pkl 上，**OccTop 支线有效 batch 会静默缩水，日志不报错**。这是 OccTop 训练最需要监控的点（建议在 pipeline 里加计数器）。

### 9.8 数据缺陷修复史（汇总）

| 缺陷 | 现象 | 修复 |
|---|---|---|
| LR `lidar_mask_fine` 空 | 22/36 pkl mask 全空 ⇒ `loss_occ_fine≈0` | HR mask 降采样兜底（`99bf85d`，ground 命中 99.2%） |
| seg id=72 越界 | 新数据 73 类 ⇒ `np.take(mapping_array[0..71], 72)` 崩溃 | mapping 补 `72:3` + `EQPointSegClassMapping` clip 防护 |
| HR 解析必失败 | `load_labels_npz` 三返回值解开为 2 | `fbf9ac4` 修复；`067fdf2` 改为"解析失败只告警、永不删源" |
| HR state 学"LR 放大拷贝" | `loss_hr_state` 监督是 `F.interpolate` 最近邻拷贝，HR 语义没用上 | 删 fallback，改走 0.1m 真判据（`10c04fc`） |
| ground 静默整批降级 | 原逻辑要求**整批** `occ_scale_hr==1`，任一帧无 HR 就全批退点投票中位数 | 改**逐帧门控**（有 HR 走列顶、无 HR 该帧 coltop 兜底） |
| fine-binary loss 恒 0 | v2 门控 + 在线点路径把监督退化成"OCC ⇒ 16 子体素全占" | v3 射线自算 → v4 直读 HR `labels.npz`（见 §9.9） |
| 环形伪影 | 同心环 + 放射 spoke | ⚠️ 根因在上游生成器，**E2E 侧只能缓解** |
| 数据换血 | smalltest 4 份训练 pkl 需带 `occ_path_hr` | 全换为带 HR 的 pkl |

### 9.9 fine-binary 的 GT 数据源演进（v2 → v3 → v4，是**降级链**不是并存）

| 版本 | GT 来源 | 状态 |
|---|---|---|
| v2 | LR occ-state 门控 + 在线点/6 帧融合 | **被否**：`docs/loss_fine_binary_zero_diagnosis.md` 实测 `loss_fine_binary` 从 **iter80 起恒 `0.0000`**；根因是"v2 门控内 lidar 命中的子体素几乎全是实体表面 ⇒ `occ_bits≈valid_bits`，BCE 几十 iter 饱和"；门控内 **99.8% 观测单元被占用** |
| v3 | 从 `ground_fuse_points`（T..T-5）**在线射线自算** HR occ-state：定步长 marching + 近表壳钉 OCC + 命中前空位 carve FREE | 兜底（不依赖离线键，对缺 `mask_lidar_fine_hr` 的 pkl 同样成立） |
| **v4** | 直接读离线 HR `labels.npz`：`observed & solid→OCC`、`observed & empty→FREE`、`mask 外→UNKNOWN` | **默认主路**（`fb_use_hr_labels` 缺省 True） |

- 优先级链：`_occ_ground_fine_binary_gt:2204-2215` 依次尝试 **v4 → v3 → v2**。
- **保留在线兜底的原因**：约 **5% 帧无 HR 标签**。
- 两者共用同一套位域契约（`occ_bits`/`valid_bits`）与同一个 `head.loss_fine_binary` ⇒ **切换数据源不需要改 head 或 ONNX**。
- ⚠️ 配置里的 `fb_gate_lr_occ` 只属 v2 兜底，**配置注释已过期**。

---

## 10. 评测数据口径

### 10.1 评估入口与协议

- 入口：dataset 的 `evaluate():2077-2272`，**同时算 3D seg、det、occ**，末尾调 `eacon_eval_with_errors:2249-2250`。
- **`final_score`（主线唯一口径，活跃）**：

  ```python
  final_score = 0.3*mAPbev[:,0,0].mean() + 0.2*mAPbev[:,1,0].mean() \
              + 0.2*mAPbev[:,2,0].mean() + 0.3*mAPbev[:,3,0].mean()   # eval_task.py:1286
  ```

  即 **r0 权重 0.3 / r1 0.2 / r2 0.2 / r3 0.3**，只取第 1 个 overlap 档（**strict**），类内取 mean。
- **归口澄清（重要更正）**：`eval.py:867` 的 `0.45/0.25/0.2/0.1` **只服务 track/flow/旧 e2e 数据集**，且 **mamba 数据集第 30 行已把 `eval.py` 注释掉** ⇒ 不是"并存冲突"，是**按数据集分流**。
- 历史公式被注释保留（`:1284-1285`）⇒ **评估权重改过多次，跨时期分数不可直接比较**。

### 10.2 r0–r3 边界（**两套**，且不一致 ⚠️）

| 来源 | r0 | r1 | r2 | r3 |
|---|---|---|---|---|
| **采样器**（`eq_..._mamba.py:378-388`） | `(-30,30)/(-30,30)` | `(-30,50)/(-30,30)` | `(-30,80)/(-50,50)` | `(-30,120)/(-70,70)` |
| **评估器**（`det13Cseg8C_config_260624.py:10`） | `[-15,30,-15,15]` | `[-20,50,-30,30]` | `[-25,80,-50,50]` | `[-30,120,-70,70]` |

- 评估器分区是 **ego 系 (x,y) 矩形开区间**（`is_in_difficulty_ring`，`eval_task.py:197-246`），**不是径向环**；命中判据要求 GT 或 DT 中心在区内，否则标 ignored。
- overlap 阈值按类：车辆类 0.5，`pedestrian/rider/SmallTarget/animal/humanlike_background` 0.3。
- **r4 仅以注释存在**（`det13C...py:11` 保留 5 区间注释行），**不参与指标**；`work_dirs_eval_summary.md` 里出现 r4 ⇒ 该 summary 来自更早的 5 区配置。
- ⚠️ **采样补样区域 ≠ 评估考核区域**：若指望 region 补样提升 r3/r4，**两者必须先对齐**。

### 10.3 mIoU 与误差统计

- **3D seg**：`seg_eval(gt, pred, clscfg.seg_class, 0)`；`ignore_index=0` ⇒ 输出表里 BackGround 为 `nan`；当前 8 类定义含 `Cyclist`，而 summary 表只有 7 列（无 Cyclist）⇒ **又一次印证两代配置混用**。
- **OCC**：`evaluate_occ:1937-2075` 支持 `mAP`（7 类 `Metric_mIoU`，frame_by_frame 用混淆矩阵累加）、`occ_2.5`（5 类 + 高度）、`mAP_exc`（8 类，按 GT box 把 body 类重标为 Excavator）；用 `nanmean(mIoU[1:])` **显式排背景**。
- **距离分档**：`seg_eval_muti_distance`，分档 `['all','0-20','20-40','40-80','80-120']`；可选按 `[-3.13,7.28,-2.57,2.57]` 过滤自车区域。
- **误差指标**（`calculate_errors`，`eval_task.py:13-61`）：`trans` = xy 欧氏距离；`size` = (w,l,h) 逐维绝对误差；`orient` = yaw 绝对差折到 `[0,π]`；dataset 侧聚合成 **mean / p90 / p99** 并按 r0–r4 分档打印（`eq_..._mamba.py:2274-2436`），`pedestrian/SmallTarget` 不参与 orient。
- ⚠️ **`print_error_stats:2274` 硬编码 5 个类名** ⇒ 类数变更（13→14）时 `j=4` 有 **KeyError 风险**。
- entity 另有逐点评测：`eacon_utils/entity_eval.py:63 aggregate_entity_point_metrics`。

### 10.4 `work_dirs_eval_summary` 的来源与迭代证据

- **来源已定位**：`tools/analyze_test_logs.py:8-16` —— 用正则 `r'final_score[^\n]*\n.*?(\{.*?\})'` 从测试日志抓 `final_score` 后第一个 JSON，汇总成 summary ⇒ **它不是评测脚本产出，而是日志后处理产物**。
- ⚠️ **但其生成脚本不在本仓库**（三份拷贝均无生产者），且其 `work_dirs` 根为 `/e-vepfs/guanxj/ENetQuery/work_dirs`、目录名全是上一代命名（`EQDetSegOccTemporal{Dense,Frozen,...}`）⇒ 与本仓 V5 是否同批实验**未确认**。
- 规模：`eligible_dirs=14`、`num_eval_groups=145`，**全部目录 `use=ema`**（选点一律取 `*_ema.pth`）。
- **迭代证据**：

  | | 目录/ckpt | final_score | miou | trans_p99 | orient_p99 |
  |---|---|---|---|---|---|
  | 历史最佳 | `EQDetSegOccTemporalDenseSingleSampler70w/epoch_6_ema.pth` | **42.841** | **0.8866** | 1.094 | **11.78°** |
  | 最新 | `EQDetSegOccTemporalMamba_resume/epoch_12_ema.pth` | **43.120** | 0.8847 | 1.0308 | **13.30°** |

- **结论**：final_score 略优（+0.279）且 trans_p99 优（−0.063m），**但 miou / orient_p99 / size_p99 均由历史最佳胜**；单项最佳分散在三个不同目录 ⇒ **没有单一 checkpoint 全面占优**。
- **AP 表**：r0 从 48.16 → 47.48（**降**）；r4 从 24.49 → 26.19（升）；长尾类 `animal/rider/semitrailer*` **全程 0.00**；`commandcar/truck` 已饱和（99–100）⇒ **瓶颈在长尾类与远距离区（r3/r4），而 final_score 的 0.3 权重正压在 r3 上**。

---

## 11. 数据侧时间线（提交级考古）

### 11.1 阶段划分

| 阶段 | 时间 | 数据侧主要工作 | 代表提交 |
|---|---|---|---|
| master 基线期 | 03-11 ~ 06-23 | `pkl_list` 参数雏形（init） | `1f939ce` |
| 实虚体预研 | 06-23 ~ 07-22 | entity 头与时序 finetune（数据侧无大改） | `10d829c`, `a51a46d` |
| **冲刺期** | **09-02 ~ 09-07** | 数据侧集中落地：pkl_list、scene drop、CBGS、14 类 yaml、HR 数据链、LR mask 兜底 | `412fda2`, `c55b733`, `ae7ac57`, `b903704` |
| 收尾与全量 | 09-08 ~ 09-16 | occ 卡死防护、pairGT、预训练替换、CBGS 适配 14c | `0dd095d`, `1f02fc1`, `fdbc658` |

**节奏异常**：09-03:39 / 09-04:46 / 09-05:17 提交（三天 102 条 = 全仓 71%）——典型**冲刺式攻坚**。

### 11.2 数据侧特性表（引入提交 / 日期 / 状态 / 动机是否可证）

| # | 数据侧特性 | 引入提交 | 日期 | 状态 | 动机可证 |
|---|---|---|---|---|---|
| 1 | `pkl_list` 显式多 pkl（绕 ConcatDataset） | `412fda2` | 09-04 | 启用 | **能**（提交信息含报错链） |
| 2 | `expand_infos_by_repeat` / `ann_file_list.py` | `ae7ac57` | 09-07 | 启用 | 部分 |
| 3 | scene 级 CBGS | `ae7ac57` → `1f02fc1` → `fdbc658` | 09-07 / 09-15 / 09-16 | 启用 | **能**（changelog） |
| 4 | scene 级传感器 drop | `c55b733` → `183de3d` / `7625b58` / `92f4c1c` → `fdbc658` | 09-04 ~ 09-16 | 启用 | 部分（两次调概率） |
| 5 | 14 类 yaml（`roadcone`/`rockfall`） | `ae7ac57` → `dc2c2b2` | 09-07 | 启用 | 部分 |
| 6 | HR occ 链（`occ_path_hr`） | `cd1086d` | 09-02 | 启用 | 未说明 |
| 7 | HR state GT 真判据 | `10c04fc` | 09-05 | 启用 | **能**（自述修正"监督造假点"） |
| 8 | LR mask 缺失审计 + HR 降采样兜底 | `99bf85d` / `b903704` | 09-05 | 启用 | **能**（附审计报告） |
| 9 | HR rebind 工具与 D 类补跑说明 | `86fe72a` / `8947229` | 09-05 | 已交付 | **能** |
| 10 | `occ_supervision_lost` 卡死防护 | `0dd095d` | 09-08 | 启用 | **能**（附 diff + 监控脚本） |
| 11 | PairGT（`PairGTEnsureVisionGT`） | `1f02fc1` | 09-15 | 启用 | 能 |
| 12 | 时序数据增强（`keep_consistent_seq_aug`） | `1f02fc1` | 09-15 | 启用 | 能 |
| 13 | 预训练权重替换 | `1f02fc1` | 09-15 | 启用 | 能 |
| 14 | 单 pkl 训练时 `use_pkl_list=False` | `dc53bab` | 09-03 | 启用 | 能 |
| 15 | fine_binary 数据源切 v4 | `10c04fc` / `8e46b63` | 09-04~05 | 启用 | **能**（有归因文档） |

> **重要**：15 项中 **12 项落在 09-02~09-07**，且**全部是 `hw_dev_merge_zsa` 独有**（对照 master 完全不含 CBGS、scene drop、14 类拆分、`expand_infos_by_repeat`）⇒ 本节时间线即该分支在数据侧的净增量史。

### 11.3 冲刺期提交逐条（数据侧相关，节选）

| 日期 | 提交 | 内容 |
|---|---|---|
| 09-02 | `cd1086d` | 引入 `occ_path_hr`（train occTop） |
| 09-03 | `dc53bab` | 单 pkl 训练时同时置 `data.train.use_pkl_list=False` |
| 09-03 15:44 | `27ea159` | docs+tools：踩坑说明（无 GPU import / **BDA 双采样** / fine_binary 数据限制）+ 真实 train_pipeline xyz 导出 |
| 09-03 17:01 | `3162e7e` | config 接入 HR occ-top loader + 安全加固（解析失败默认不删源 npz） |
| 09-03 17:13 | `067fdf2` | **彻底关闭"HR labels.npz 解析失败删源"——仅告警，永不删除** |
| 09-03 17:37 | `fbf9ac4` | 修复 `load_labels_npz` 三返回值解开为 2 导致 HR 解析必失败 |
| 09-04 00:19 | `412fda2` | **`ann_file` 多 pkl 列表改 `pkl_list` 显式参数，绕开 mmdet ConcatDataset** |
| 09-04 11:52 | `4e071fd` | 小批量测试版（4 份 pkl ~270MB，2 epoch） |
| 09-04 13:10 | `ce6562f` | prof：occ_ground GT builder 分项计时（lrsem/state_lr/state_hr/ground/fb） |
| 09-04 15:28 | `c55b733` | **挖机半挂车 nms 适配 + 根据 scene 随机 drop 传感器** |
| 09-04 17:35 | `8e46b63` | collect `mask_lidar_fine_hr` 让 fb 走 HR labels 路径 |
| 09-04 17:44 | `b356717` | HR loader rows 稀疏 (N,7) 时跳过 dense 3-state 路径 |
| 09-04 17:57 | `e618e85` | handover notes（state、perf findings、open HR-state design） |
| 09-05 00:37 | `10c04fc` | HR state/ground/fb 监督真吃离线高分 labels（grill v5） |
| 09-05 01:33 | `99bf85d` | **LR `lidar_mask_fine` 缺失时由 HR labels 降采样兜底** |
| 09-05 01:55~04:48 | `b903704`…`9c146f1` | LR mask 缺失审计 → HR 绑定审计 → 磁盘存在性核查 → 结论名单 |
| 09-05 09:35~09:40 | `86fe72a` / `8947229` | **双缺清单 + HR rebind 工具 / D 类补跑脚本与生产执行说明** |
| 09-07 10:50 | `ae7ac57` | **"全量数据训练适配"**：一次塞进 14 类 yaml + CBGS + `expand_infos_by_repeat` + `no_rot_classes` |
| 09-07 11:55 | `dc2c2b2` | Phase-1 检测 14 类（det 输出 16 通道）继承式 config |
| 09-07 | `68a6b92` / `d0cb482` | Phase-1.5 14cls16out + roi_refine；GT 侧用 yaml14 修复 MapDetection 断言 |
| 09-07 18:53 | `536e524` | merge sa 修改 && lss 模型初版（合并带入 CBGS） |
| 09-07 19:38 | `183de3d` | **修改 drop 概率** |
| 09-07 | `7625b58` / `92f4c1c` | `drop_all_lidar=0`（保留 `random_drop_lidar=0.3`）/ `random_drop_img=0` |
| 09-08 12:40 | `0dd095d` | **修复高分低分 occ 缺失造成任务卡死**（`occ_supervision_lost`） |
| 09-15 13:48 | `1f02fc1` | **pairGT + CBGS + 时序数据增强 + 预训练权重替换**（正式合入 + changelog） |
| 09-16 | `fdbc658` | **CBGS 策略适配 14c**（改 dataset 21 行）+ drop 概率降低 |

---

## 12. 性能与资源

### 12.1 GPU 性能观测（H20 96GB 单卡，smalltest 4 pkl = 75,601 帧，`spg=2`）

来源：`docs/gpu_perf_observation_20260905.md`

| 项 | 值 |
|---|---|
| 单 iter 耗时 | **1.66 ~ 2.26 s**（fwd 1.1–1.4s + bwd/step 0.83–0.96s） |
| **`data_time`** | **0.03 ~ 0.2 s** ⇒ **数据加载已非瓶颈** |
| GPU 利用率 | ~50%（9%–95% 波动） |
| 显存 | 26.4 / 96 GB（余 ~70GB） |
| 前向最大项 | **occ_ground 塔 331ms（28%）**、`extract_feat` 174ms（15%）、**GT 构建合计约 15–18%** |

**结论**：性能健康；瓶颈是"1024² 上 4 路输出的本质成本" + `occ_state_hr_gt` 的**逐样本 python 循环**造成 CPU↔GPU 同步间隙。

**低风险候选优化**：预计算 zmap/onehot 常量；`spg 2→4`（显存余 70GB）。

### 12.2 数据侧性能热点与已完成的优化

| 段 | 优化前 | 优化后 | 手段 |
|---|---|---|---|
| `occg_gt_fb` | 711–803 ms | **4–14 ms** | 位域打包：`unique(lin*16+sub)` + `scatter_add_` 替代慢 10–50× 的 `np.bitwise_or.at` |
| `occg_gt_ground` | 62–206 ms | **14–30 ms** | torch 向量化孪生版 `build_ground_gt_full_t` 用 `scatter_reduce_(amax)` 替代 lexsort |
| `geo_gt_targets` | 199–316 ms | 预期 **~50–80 ms** | 融合 CUDA kernel（一 thread 一射线 + `atomic_min_float` CAS 位级真 min）替代"全局最长射线 pad + last-write-wins" |
| `geo_dual` | ~263–385 ms | 预期 ~100 ms | 同上 |

- **GT 构建计时埋点**：`occg_head_fwd` / `occg_gt_build` / `occg_gt_state_lr` / `occg_gt_state_hr` 分别计时（提交 `ce6562f`）⇒ **GT 构建本身是被重点优化的段落**。
- **CUDA kernel 正确性保障（数据侧范式）**：kernel 不自算采样原点、直接读 torch 预计算的 `offsets[]/stops[]` 保证逐位一致；验证门 `GEO_RAY_VALIDATE_FRAMES`（默认 3 帧）内与 torch 参考对照，容差超限则**自动回退**。实测：torch 参考 vs 独立 oracle 766 射线/26908 自由格 **0 mismatch**；kernel vs 参考 known 翻转 36/67.1M 格（**0.54 ppm**）、mind 267/67.1M（~4 ppm）。

### 12.3 资源纪律（实录）

- 训练平台：火山 MLP 多机多卡；**集群 GPU 紧张，实习生配额降到 10%**。
- **全量 occ 重构需 8 节点 × 4 天**，需提前占位。
- 开发机统一**纯 CPU**，GPU 走 worker ⇒ 数据侧改动"本地无法验证全量 load"是常态（`412fda2` 亦注明）。
- 数据平台：`dclp-self.eqfleetcmder.com`（dataManage / lockDataDetail，badcase 回放）。

---

## 13. 配置开关速查表

### 13.1 数据集 / 数据组织

| 开关 | 含义 | 主配置 |
|---|---|---|
| `pkl_list` / `ann_file` | 多 pkl 入口（`ann_file=''` 占位） | 走 `pkl_list` |
| `use_pkl_list` | 目录扫描模式 | 视脚本置 False |
| `load_interval` | 抽帧步长（**先抽帧再复制**） | 1 |
| `sort_datasets` | 是否按 timestamp 重排 | 行为不一致（见 §7.5） |
| `filter_past_frame_num` / `filter_future_frame_num` | 硬时序帧数 | **0 / 0** |
| `mamba_data_sequence` | 按 `idx` 切 scene | **True** |
| `with_seq_flag` | 是否产出 `flag` | True |
| `sequences_split_num` | 序列再切分 | 1（不生效） |
| `enable_new_lidars` | 是否加载新增 3 路雷达 | 视配置（True = 4/7 混合） |
| `Ncams` | 相机路数门控 | 7（= 全量，不抽样） |
| `occ_gt_root_hr` | HR GT 根目录（remap 用） | ⚠️ 仍写旧目录（漂移） |
| `occ_gt_lr_name` | LR→HR 文件名映射名 | — |
| `use_valid_flag` | 用 `valid_flag` 作标注 mask | — |

### 13.2 采样与均衡

| 开关 | 含义 | 主配置 |
|---|---|---|
| `single_sampler` | 单帧采样 | False |
| `group_slot_streaming_sampler` | slot 流式（**实际生效**） | True |
| `group_opt_sampler` | scene 分组（**被抢占，永不触发**） | True（无效） |
| `group_opt_balanced_sampler` | region-class 均衡 | False |
| `group_opt_cbgs_sampler` | CBGS | 仅在部分配置 True |
| `use_cbgs_scene_balance` | dataset 侧 CBGS 开关 | 默认 False |
| `use_region_sampler` | region 补样 | False |
| `target_region_class_counts` / `cls_list` | region 补样目标量 | truck 100000×4 等 |
| `cbgs_pool_classes` | CBGS 池类 | `class_names[:11]` |
| `cbgs_range_m` | CBGS 命中统计范围 | 120 |
| `cbgs_min_hit_frames` | 进池最小命中帧数 | 3 |
| `cbgs_length_factor` | **目标 epoch 长度倍率** | 1.75 |
| `cbgs_max_ratio` | 每类复制上限倍率 | 5 |
| `samples_per_gpu` | batch / 同时决定 slot 数 | 2（V5 四件套 12/8/4/4） |
| `workers_per_gpu` | dataloader workers | 8 |
| `max_epochs` | 训练轮数 | 12 |
| `seed` | 采样种子（实际用 `seed + epoch`） | — |
| `keep_consistent_seq_aug` | 同 slot 共享 IDA/BDA | True |
| `pin_memory` / `persistent_workers` | dataloader | True / True |

### 13.3 增强与 drop

| 开关 | 含义 | 现状 |
|---|---|---|
| `scene_level_drop` | scene 级 drop 总开关 | True |
| `drop_seed` | drop 表种子 | 0 |
| `drop_lidar_only` | 强制只丢雷达 | False |
| `num_lidars` | 参与 drop 的雷达数 | 7 |
| `P_IMG` / `P_LIDAR`（模块级） | scene 丢图/丢雷达概率 | 0.3 / 0.3（**实际配置已下调**，见 §8.6） |
| `random_drop_img` | 逐帧回退：丢图概率 | **0（09-07 起不丢图像）** |
| `random_drop_lidar` | 逐帧回退：部分丢雷达概率 | **0.3** |
| `drop_all_lidar` | 整帧丢全部雷达概率 | **0（已关闭）** |
| `ensure_one_camera` | 保底留一相机 | 场景级 True；operator 默认 **False**（风险） |
| `ida_config` / `bda_aug_conf` | 图像/ BEV 增强 | IDA 生效；BDA **恒等** |
| `bda_aug_conf_hr` | HR 侧 BEV 增强 | 恒等 |
| `data_aug_conf.rand_flip` / `rot_lim` | 图像翻转/旋转 | **未生效**（消费方被注释） |
| 注释态增强 6 项 | 见 §8.4 | 全部关闭 |

### 13.4 数据侧其他关键路径

| 项 | 值 |
|---|---|
| `point_cloud_range` | `[-31.8,-76.8,-4.4,121.79,76.79,8.39]` |
| `full_point_cloud_range` | `[-31.8,-76.8,-4.4,121.8,76.8,8.4]`（**真正闭合**） |
| `voxel_size` / `dense_shape` | `[0.15,0.15,0.2]` / `[1024,1024,64]` |
| `pcd_limit_range` | `[-41.8,-86.8,-10,131.8,86.8,10]` |
| occ LR / HR 几何 | `[512,512,32]`@0.3/0.3/0.4 ｜ `[1024,1024,128]`@0.15/0.15/0.1 |
| BEV 特征 | 256×256 @0.6m |
| 相机 | 7 路，源 1080×1920 → 384×704（长焦原始 2160×3840） |
| 雷达声明 / 基础 / 新增 | 7 路 ｜ `points_t/_l/_r/_b` ｜ `_top_aux/_mid_left/_mid_right` |
| 深度 GT | `(7,H,W)`，`D=99`（RCSample BCE，只算 fg，权重 0.1） |

---

## 14. 风险与技术债（数据侧专用）

| 等级 | 风险 | 证据 | 影响 |
|---|---|---|---|
| 🔴 | **LR mask 39% 帧为空 + 双缺 76,662 帧** | 全量审计（§9.1） | 模型上限受制于数据；算力与 loss 统计浪费 |
| 🔴 | **`test_vision_only=True` 使点分割指标失效** | `transform.py:3006` → 点云与 `kept_indices` 全空 | 纯视觉评测的 seg 数字**无意义**，须在流程里显式排除 |
| 🔴 | **`print_error_stats` 硬编码 5 个类名** | `:2274` | 类数变更（13→14）时 `j=4` KeyError，**评估输出随时可能崩** |
| 🟠 | **"至少留一个相机"保护只在回退分支** | `ensure_one_camera` 默认 False | 极端情况下可能 7 路相机全黑且**不报错** |
| 🟠 | **无 `reset_temporal_state`** | 全仓 grep 无定义；唯一复位是 scene 跳变 | **跨 pkl 长跑评测**存在 buffer 残留；数据侧 pad 复用同 scene 会放大影响 |
| 🟠 | **`placeholder_rounds` 用 idx 0 垫位** | `:1340-1429` | 引入无语义的假样本；`spg=2` 时 slot 仅 2 个，8 卡下 `my_scenes >= num_slots` 未验证 |
| 🟠 | **采样区域 ≠ 评估区域** | `:378-388` vs `det13C...py:10` | region 补样可能"补了没考、考了没补" |
| 🟠 | **OccTop 静默丢样本** | `loading_optimized_HR.py:1935-1936 return None` | HR 覆盖率低时有效 batch 缩水，**日志不报错** |
| 🟠 | **`error_idx` 静默降低样本量** | `:683-744` | 无显式统计 |
| 🟡 | **`occ_gt_root_hr` 配置漂移** | config:305 vs 审计（0 帧在用旧目录） | 将来走 remap 会指向错误目录 |
| 🟡 | **`occ_size` 一名两义** | config:108（形状）vs :231（体素边长） | 误用即错 |
| 🟡 | **硬编码栅格 `(672,672,32)`** 与 V5 occ `[512,512,32]` 不匹配 | 5 个 dataset 文件的 `evaluate_occ` | 该分支只在非默认几何下自洽；且用了废弃 `np.int` |
| 🟡 | **废弃 numpy 别名散布**（`np.int`/`np.float`/`np.bool`） | `loading.py:3451,3452,3475,3476,3489,3490,3608,3609,3632,3633`（**均在 Mamba 可用路径**）、`transform.py:1652,1659,1663`、dataset `:984,1745,1772` | numpy ≥1.24 将 AttributeError |
| 🟡 | **活 `pdb.set_trace()` 断点** | `loading.py:4557, 4814`（后者在 `except:` 内） | 触发会**挂住整个 dataloader worker** |
| 🟡 | **`CameraVisibleFilterMamba.__repr__` 必崩** | `transform.py:3631` 设 `self.visible_classes`，`:3672` 引用 `self.classes`（从未赋值） | 任何打印该 transform 都会 AttributeError |
| 🟡 | **`self.occ_size` 在 dataset 类从未赋值却被使用** | `..._mamba.py:1745,1772` 等 5 个文件 | 潜在运行期崩溃；同行还用废弃 `np.float` |
| 🟡 | **`gt_depth` 是哑值** | `loading.py:4937` 只写 `torch.zeros((4,1,1))`（同文件有真实现 `points2depthmap:4915`） | 深度监督实际未启用；test 且 `eval_gt_depth=False` 时全零 |
| 🟡 | **死键 `gt_bboxes_3d_vision` / `gt_labels_3d_vision`** | `CameraVisibleFilter` 会写，但 V5 `Collect` 里已注释 | 白算 |
| 🟡 | **死参数** | `keep_fine_labels`（`__init__` 赋值、`__call__` 未用）；`pointseg downsample=4` | 配置误导 |
| 🟡 | **模块级 `sys.path.insert(0,'/e-vepfs/guanxj/ENetQuery')`** | `eq_nuscenes_multi_pkl_test.py:8-9` | import 即污染 sys.path |
| 🟡 | **`MapDetectionClassMamba` 硬断言** | `loading.py:5003` `assert self.classes == clscfg.CLASS_NAMES` | 改 `class_names` 必须同步改全局，否则启动即断言失败 |
| 🟡 | **`region_num_info` 直接下标** | `:399` uses `clscfg.det_mapping[name]` | 遇映射表外新细类 KeyError |
| 🟡 | **330 个文件硬编码 `/e-vepfs/<人名>/...`** | 全仓 | 可移植性差 |
| 🟡 | **`EaconE2EDataset` pkl schema 自相矛盾** | 嵌套 `info["boxes_info"]["gt_boxes"]:344` vs 扁平 `info["valid_flag"]:270` | 该 dataset 是否可用存疑 |

---

## 15. 未知项与验证方法

| # | 事项 | 为何无法从代码确认 | 验证方式 |
|---|---|---|---|
| 1 | pkl 内 info 的**真实字段全集** | 本地**无 `data/`**（实测不存在）；字段清单来自代码实证 | `python3 -c "import mmcv;d=mmcv.load('x.pkl');print(d['infos'][0].keys())"` |
| 2 | `ann_file_list.py` 的 `repeat` 语义与生产列表**是否一致** | 两套实现并存且未交叉验证 | 用同一 pkl 分别跑两套展开，比对帧集合 |
| 3 | `labels_new.npz` / `labels.npz` 的**真实 key 与列语义** | `occ_v5_utils.py:119` 只是 docstring（称 `semantics_fine` 为 `(N,5)`），dense 路径只取列 `[0,1,2,4]` | 读 1 个真实 npz 的 `files` 与 shape |
| 4 | **occ 7 类的确切通道顺序** | `entity_label_mapping` 有 8 键（含 rider=7），但 `occ_num_classes=7`、评测只打 7 类（无 rider） | 跑一帧 dump argmax 通道，或读 `eacon_utils/eq_occ_metrics.py` 类名表 |
| 5 | **`2d_seg_maps` 是否为死负载** | Entity config 的 `Collect` 收了 3 张 2D GT 图，但 model dict 里**无 head 消费**（唯一消费者 `models/mmseg_heads/pid_head.py:139` 未构建） | grep head 构建 + 运行期统计 |
| 6 | `max_sweeps=4` 是否**完全未生效** | 训练路径确认只用 1 帧 buffer；dataset 侧仍在建序列 | 运行期打印 `buffer_feats` 长度 |
| 7 | `use_sweeps_byframe` 的三处 False 是**有意还是覆盖 bug** | dataset 构造默认 True，`get_data_info:568` 硬编码 False 覆盖 | 问作者 |
| 8 | `placeholder_rounds > 0` 的**实际发生频次** | 需真实数据 + 8 卡 | 采集 rank0 warning |
| 9 | OccTop **实际丢了多少样本** | `return None` 静默丢弃，丢弃率取决于 pkl HR 覆盖率 | 在 pipeline 加计数器实测 |
| 10 | **`error_idx` 的实际规模** | 无统计输出 | 训练日志/加计数器 |
| 11 | `work_dirs_eval_summary` 统计的 work_dirs **是否与本仓 V5 同批** | 目录名为上一代命名；生成脚本不在本仓 | 问作者 / 比对 ckpt 路径 |
| 12 | 文件名尾串 `cleaned_rmpass_slow0.9_...` 的**精确语义** | 生产脚本不在本仓 | 查 `tools/data_tools/create_eacon_data*.py` 或问数据生产方 |
| 13 | `pkl_list_only_sample/` 内 pkl 是否**真按 `idx` 连续** | `use_pkl_list=True` 走 `os.listdir` 拼 `infos`，**绕过 sort_datasets/load_interval** | 对真实目录做 `idx` 单调性检查 |
| 14 | `group_opt_sampler=True` 是**有意保留还是复制残留** | 实测被 elif 链抢占 | 问作者 |
| 15 | `occurrence of det_occ_aug_swap_xy` 是否正确处理了轴约定 | 双约定陷阱仅由文档记录 | 对比 det BEV 与 occ 柱面的 H/W 轴是否一致 |

---

## 16. 上手路线与复现命令

### 16.1 数据侧上手顺序（P0–P5）

| 阶段 | 目标 | 入口 | 验收（能回答什么） |
|---|---|---|---|
| **P0 数据从哪来** | pkl 是怎么产的 | `datasets_pkl.sh` → `tools/data_tools/tool.md` → `opt_pkl_mamba_list_only_sample.py` | 为什么 pkl 里 `sweeps=[]`、`key=1`；info 有哪些字段 |
| **P1 数据怎么组** | 一条样本从 pkl 到 batch | `eq_nuscenes_temporal_multitask_mamba.py:786 → 432 → 623 → 683` | `idx` 是什么、scene 怎么切、`(path,repeat)` 怎么展开、drop 在哪注入 |
| **P2 数据怎么采** | epoch 里怎么取样本 | `samplers/multitask_sampler.py:1101 → 1151 → 1253 → 1340 → 1432` | slot 是什么、`num_samples` 怎么算、CBGS 的 λ 从哪来、pad 怎么补 |
| **P3 数据怎么加工** | 20 个算子依次加了什么 | `pipelines/loading.py` + `transform.py` + `config:649` | 顺序约束 4 条、`Collect` 21 key、drop 三态 |
| **P4 数据质量** | 标签缺在哪、怎么治 | `docs/lr_mask缺失审计_反馈数据生产方.md` → `不可用数据收集清单_LR_HR双缺.md` → `D类HR绑定补跑_生产执行说明.md` | A/B/C 类、兜底路径、rebind 方案 |
| **P5 数据口径** | 指标怎么算 | `work_dirs_eval_summary.md` → `eacon_utils/eval_task.py:1286` | final_score 公式、r0–r3 两套分区、mIoU 实为 7 类 |

### 16.2 必读文档（数据侧，按信息密度）

1. `docs/train_pipeline_gt_outputs_guide.md`（pipeline 输出与 HR 语义稀疏性）
2. `docs/lr_mask缺失审计_反馈数据生产方.md` + `docs/不可用数据收集清单_LR_HR双缺.md`（数据缺陷权威清单）
3. `docs/D类HR绑定补跑_生产执行说明.md`（rebind 方案）
4. `docs/cbgs_pairgt_seq_aug_changelog.md`（CBGS / PairGT / 时序增强）
5. `docs/migration_occ_top_dual_track.md`（dual-track 与轴约定坑）
6. `docs/fine_binary_v3_raycast_design.md` + `docs/loss_fine_binary_zero_diagnosis.md`（一次完整的"loss 恒 0"归因）
7. `docs/occ_state_ring_artifact_diagnosis.md`（上游生成器缺陷）
8. `docs/gpu_perf_observation_20260905.md`（性能与数据瓶颈）
9. `tools/data_tools/tool.md`（pkl 全生命周期）
10. `2026-09-07-temporal-v5-feature-changelog.md`（V5 全景功能表）

### 16.3 复现命令

```bash
cd ~/.eagent/workspace/repos/E2E_ENET_hw_dev_merge_zsa

# ── 行数（勿用 wc，本环境低估 3-8 倍）──
python3 -c "print(open('projects/mmdet3d_plugin/datasets/samplers/multitask_sampler.py','rb').read().count(b'\n'))"   # 1549
python3 -c "print(open('projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py','rb').read().count(b'\n'))"  # 2667
python3 -c "print(open('projects/mmdet3d_plugin/datasets/pipelines/loading.py','rb').read().count(b'\n'))"   # 5715
python3 -c "print(open('projects/mmdet3d_plugin/datasets/pipelines/transform.py','rb').read().count(b'\n'))"  # 4245

# ── 数据集构造 ──
sed -n '158,300p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # __init__ 顺序
sed -n '768,830p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # (path,repeat) / load_annotations
sed -n '376,405p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # 采样 R0-R3
sed -n '409,499p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # _clip_data_infos / _set_sequence_group_flag
sed -n '623,690p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # _prepare_train_data 注入
sed -n '683,750p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # __getitem__ 容错
sed -n '350,375p'   projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py   # scene drop 表

# ── 采样体系 ──
grep -n "^class \|^    def " projects/mmdet3d_plugin/datasets/samplers/multitask_sampler.py
sed -n '1147,1160p;1253,1335p;1340,1490p' projects/mmdet3d_plugin/datasets/samplers/multitask_sampler.py
sed -n '105,160p'   projects/mmdet3d_plugin/datasets/builder.py        # elif 链（谁真正生效）

# ── pipeline ──
sed -n '1646,1700p' projects/mmdet3d_plugin/datasets/pipelines/loading.py   # 互斥 drop 决策
sed -n '5055,5070p' projects/mmdet3d_plugin/datasets/pipelines/loading.py   # 深度 GT 顺序约束 docstring
sed -n '3770,3810p' projects/mmdet3d_plugin/datasets/pipelines/loading.py   # HR mask 兜底
sed -n '3127,3200p' projects/mmdet3d_plugin/datasets/pipelines/transform.py # lidar drop + mask 复用
sed -n '680,800p'   projects/configs/EaconTemporalMultiTask/TemporalModelV5/EQDetSegOccMambaWithSegV5TemporalDepth.py  # Collect

# ── 生产 pkl 全景（repeat 分布）──
python3 - <<'EOF'
import re, collections
p='projects/configs/EaconTemporalMultiTask/TemporalModelV5/EQDetSegOccMambaWithSegV5TemporalDepth_full-data.py'
s=open(p).read(); i=s.find('anno_root = ['); j=s.find(']', i)
rows=[l.strip() for l in s[i:j].split('\n')[1:] if l.strip() and not l.strip().startswith('#')]
rep=collections.Counter(re.search(r",\s*([0-9.]+)\)", r).group(1) if re.search(r",\s*([0-9.]+)\)", r) else '1' for r in rows)
print('pkl 条目:', len(rows), 'repeat 分布:', dict(rep))
EOF

# ── 数据侧特性时间线 ──
git log --oneline --date=short --pretty='%h|%ad|%an|%s' origin/hw_dev_merge_zsa \
  | grep -Ei "pkl|cbgs|drop|aug|repeat|occ|labels|mask|data" | head -60

# ── 评测口径 ──
grep -n "final_score" projects/mmdet3d_plugin/datasets/eacon_utils/eval_task.py projects/mmdet3d_plugin/datasets/eacon_utils/eval.py
```

---

## 17. GT 构建与监督契约（数据侧的输出规格）

> 数据侧的最终交付物不是"文件"，而是**每帧一组的 GT 张量**。本节把"数据侧产出什么、以什么形状 dtype 交给模型"钉死。

### 17.1 当前主配置的监督全景（9 项启用 / 3 项关闭）

| # | 任务 | head | 监督键 | GT 来源 | 状态 |
|---|---|---|---|---|---|
| 1 | 检测主头 | `dense_det_head` = `CenterHeadRotDense` | `task0.loss_heatmap/xy/z/whl/yaw/rot_dense` | `gt_bboxes_3d` + `gt_labels_3d`（ann pkl）；**高斯热图在线生成** | ✅ 开 |
| 1b | 纯视觉 aux 检测 | `vision3d_det_aux_head`（同 head，`aux=True`） | `task0.aux_loss_*` | 同上（用 image-BEV 特征） | ✅ 开 |
| 2 | RoI refine | `pts_roi_refine_head` = `BevRoIAlignRotatedRefineHead` | `loss_roi_cls`、`loss_roi_bbox` | stage-1 解码框 vs `gt_bboxes_3d`（在线 IoU 分配） | ✅ 开 |
| 3 | 8 类逐点分割 | `bev_semantic_seg_head` = `PointSegOptHead` | `semantic_seg_loss` | `pts_semantic_mask`（lidarseg 经 `seg_label_mapping`） | ✅ 开 |
| 4 | entity 2 类 | `entity_pick_head` = `PointSegHead` | `entity_pick_semantic_seg_loss` | `pts_entity_semantic_mask`（`EQPointSegClassMappingEntity`） | ✅ 开（**配置相关**：`..._14cls16_roi_new.py` / `..._full-data.py` 启用；`...TemporalDepth.py` 未启用） |
| 5 | **LR 稠密 OCC** | `bev_occ_head`（历史 `TinyOccHeadv3`） | `loss_occ_fine` | `voxel_semantics_fine` / `mask_lidar_fine`（`labels_new.npz`） | ⛔ **关** |
| 6 | 金字塔 occ/state/ground | `occ_ground_head` = `TinyOccStateGroundHead` | `loss_lr_sem` / `loss_lr_state` / `loss_hr_state` / `loss_ground_cls` / `loss_ground_height` / `loss_fine_binary` | LR npz + HR `labels.npz` + 多帧点云 coltop | ✅ 开 |
| 7 | **OccTop** | `OccTopClsHead` = `TinyOccTopHeadPerClassHeight` | `loss_occ_top_cls`、`loss_occ_top_height[_c0..c6]` | `voxel_semantics_fine_occ_top` 稀疏列 | ⛔ **关**（仅 EntityOccTop 配） |
| 8 | **geo dual** | `bev_geo_dual_head` = `TinyOccGeoDualHead` | `loss_geo_known`、`loss_geo_occ` | `geo_points` / `geo_entity` 在线 CUDA ray-cast | ⛔ **关** |
| 9 | 深度 | `img_view_transformer` = `ViewTransformerRCSample` | `loss_depth` | `gt_depth`（`EQPointToMultiViewDepth`） | ✅ 开 |

**三项关闭的书面动机**：

| 关闭项 | 动机（原文） | 证据 |
|---|---|---|
| LR 稠密 OCC | *"历史 occ-sem 关（与金字塔 lr_sem 同 GT 重复, 部署单金字塔）"* | config:709；detector `:1739-1741`；提交 `4b32bcf` |
| geo dual | *"职责与金字塔 HR 塔重复, 关闭"*；监督口径未审计；当前 log 中无 `loss_geo_*` | config:712；`docs/report_heads_supervision_inputs_20260905.html:492` |
| OccTop | 注释 *"Frozen plan T1: no OccTop"* | 主配置无 `OccTopClsHead` |

### 17.2 逐任务 GT 契约（形状 / dtype / 生成函数 / 不监督条件）

**① 检测主头 `CenterHeadRotDense`**

| 项 | 内容 |
|---|---|
| 监督信号 | 每类一张高斯热图（dense focal 分类）+ 中心点 8 维回归（yaw 用 `sin/cos`）+ 邻域 **3×3 稠密 rot**（sin/cos）回归 |
| GT 来源 | `data['gt_bboxes_3d']`（`LiDARInstance3DBoxes`）+ `data['gt_labels_3d']`，来自 ann pkl；**热图/回归靶子全部在线生成，无磁盘 GT** |
| 形状/dtype | 热图 `[num_class, 256, 256]` float32（`feature_map_size = 1024//4 = 256`；det 用 **16 通道 = 14 类 + 2 pad**）；`anno_box [max_objs=500, 8]` float32；`ind/mask [500]` int64/uint8；`rot_target [1,2,256,256]`、`rot_weight [1,1,256,256]`、`rot_obj_mask [500]` |
| 生成函数 | `get_targets_single`（`centerpoint_opt_head_dense.py:279`）：热图高斯半径 `gaussian_radius((l,w), min_overlap=0.1)`、`max(min_radius=2, int(radius))`、`draw_heatmap_gaussian`；回归编码 `center=(x/y - pc_range)/voxel/out_size_factor`、`z` 原值、`dim` 取 `log`（`norm_bbox=True`）、`rot` 取 `sin/cos`（`:320-332`）；dense rot 由 `_draw_rot_dense_target_single:26`，sigma `(2r+1)/6`，邻域 3×3，`rot_weight = max(rot_weight, gaussian)` |
| **`no_rot_classes=['roadcone']` 的完整代码链** | ① `centerpoint_opt_head_dense.py:314` `supervise_rot = cls_name not in self.no_rot_classes`；② 不监督时 `rot_obj_mask[new_idx]=0` 且**跳过** dense rot 写入（`:326`）；③ `_zero_rot_bbox_weights`（`centerpoint_head.py:358`）把 `bbox_weights[...,6:8]` 乘 0 后传入 L1。⇒ **是"改权重"不是"改 GT"**；配置 `rot_dense_disable_center_rot_loss=False`，故未从 `code_weights` 全局抹掉 idx6/7 |
| 不监督条件 | 中心落在 `feature_map_size` 外 → `continue`（对象被丢）；`width<=0 or length<=0` → 不进内层；非 key 帧 |

**② RoI refine 头 `BevRoIAlignRotatedRefineHead`**（`bev_roi_align_rotated_refine_head.py`，610 行）

| 项 | 内容 |
|---|---|
| 监督信号 | proposal 二分类（`CrossEntropyLoss(use_sigmoid=True)`）+ 8 维残差回归（xy/z 除以 proposal 尺寸、lwh 取 `log` 并 clamp、yaw → `sin/cos`） |
| GT 来源 | **stage-1 自身解码输出**作为 proposal（`get_bboxes` 在 `dense_det_train` 内 `torch.no_grad()` 调用，detector `:1421-1428`）；GT 用同帧 `gt_bboxes_3d/gt_labels_3d`。**与纯视觉 GT 无关**（未用 `gt_bboxes_3d_vision`） |
| 形状/dtype | `rois [Np,6]`（batch_idx + `x,y,z,w,h,yaw`）、`targets [Np,8]` float32、`cls_targets [Np]`（1/0/−1）、`reg_weights [Np,8]`；`code_weights=[1,1,1,1,1,1,2,2]`（yaw 两维权重 2） |
| 生成函数 | `loss():385` 内在线构造：`_select_proposals:366`（`score_thr=0.1`、`max_rois_per_img=128` topk）；`_bev_rotated_iou:33`；`_encode_residuals:242` |
| 掩码三分 | `max_iou >= pos_iou_thr(0.5)` → 1；`neg_iou_thr(0.25) <= iou < 0.5` → **−1（ignore，不进 RoI pool/BN）**；其余 → 0；再加类内一致性约束（`labels==gt_lab[gt_inds]`，否则降 0）；`detach_proposals=True`（proposal 不回传梯度） |
| **数据侧相关约束** | `_roi_refine_keep_mask`（detector `:1466`）按 `data['key']` **只保留 key=True 帧** ⇒ 非 key 帧不参与 RoI loss。因为本仓数据侧只留 sample 帧（`key=1`），等价于全开 |
| 不监督条件 | `use_roi_refine=False` 或 head 为 None；`prop.shape[0]==0`；全 batch 无 RoI → 返回 `_zero_refine_loss(bev_feat)`（**触碰参数保证 DDP 图连通**） |

**③ 逐点 8 类分割 `PointSegOptHead`**

| 项 | 内容 |
|---|---|
| 监督信号 | **体素级 8 类 CE，但只采样有点的体素**（等价于点级监督）；预测 reshape 为 `[B,W,H,D=32,C=8]` |
| GT 来源 | `data['pts_semantic_mask']`（每帧 `[N_pts]`，lidarseg 经 `seg_label_mapping` → 8 粗类） |
| 形状/dtype | `pre_point [N_total, 8]` float（logits）、`gt_point [N_total]` int64、`valid_mask [B]` bool |
| 生成函数 | `build_targets:131`：按 `detection_range`（= `point_cloud_range`）6 面裁剪 → `point_x/y = (xy-range)/voxel_xy` 取 floor（**`voxel_size=[0.6,0.6,0.4]`**）→ `point_z = ((z-z_min)/height_min_size).floor()` 再经 `height_mapping` 映射到 32 层 |
| **非均匀高度分箱** | `height_distribution = [0.6]*5 + [0.2]*16 + [0.6]*11`（共 32，`height_min_size=0.2`）⇒ **近处 Z 密、远处 Z 疏** |
| ⚠️ 死参数 | **`downsample=4` 只被存进 `self.downsample`，在 `forward`/`build_targets` 中从未使用**；有效下采样由 `voxel_size=0.6` 承担（256×0.6=153.6m ≈ 点云 x 跨度） |
| loss + 权重 | `CrossEntropyLoss(reduction='mean', loss_weight=3.0)`，键 `semantic_seg_loss`；**无 ignore_index**；**批级重加权** `loss_seg *= (B / num_valid)` 补偿空帧 |
| 不监督条件 | detector 侧仅在 `data['key'][i]` 且 `pts_semantic_mask[i].numel()!=0` 时取真实点，否则传 `_empty_points`（空 `(0,4)`）⇒ `valid_mask[i]=False`；帧内范围裁剪后为空 → 跳过；全 batch 无有效点 → 返回 `torch.tensor(0.0, requires_grad=True)`（**⚠️ 此分支脱离计算图**） |

**④ entity 二分类 `PointSegHead`**

| 项 | 内容 |
|---|---|
| GT 来源 | `data['pts_entity_semantic_mask']`，由 `EQPointSegClassMappingEntity`（`transform.py:3753`）生成：先 `mapping_array` fine seg → coarse 8 类，再 `entity_mapping_array` coarse → entity 标签存新键 |
| **正类定义（关键）** | `entity_label_mapping`（主配置 `:124`）= `{0:0, 1:1, 2:1, 3:1, 4:1, 5:1, 6:0, 7:1}` ⇒ coarse **0=Background、6=Dust → 0（虚体）**，其余 → 1（实体）；`entity_positive=1`。⇒ **`0=虚体、1=实体`**，多份 config 注释写反（`..._full-data.py:48` 的注释才是对的） |
| 与 8 类的差异 | 两个 head 文件 99% 相同；`PointSegHead.loss` 多 `loss_key` 参数、CE 前 `.float()`（fp16 logits 防 NaN）、**没有** 8 类版的 `B/num_valid` 批级重加权 |
| loss | `CrossEntropyLoss(..., loss_weight=3.0)`，键 `entity_pick_semantic_seg_loss`（detector `:1570` 显式改名） |
| 不监督条件 | head 为 None → `entity_train` 返回 `{}`；帧级 `data['key'][i]==0` 或 mask 为空 → 传空点跳过；全 batch 无点 → 返回 `seg_pred.sum()*0.0`（保图） |

**⑤ 金字塔 `TinyOccStateGroundHead`（6 个子任务，最重的一段）**

| 子任务 | GT 键 | 形状 | 生成函数 | 判据 / 权重 |
|---|---|---|---|---|
| **LR sem**（7 类） | `voxel_semantics_fine` | `[B,512,512,32]` long | 直接取键（`occ_ground_train:2577-2597`），无额外构造 | `F.cross_entropy(valid)`，`valid=(gt∈[0,7)) & (mask>0)`；`w_lr_sem=1.0` |
| **LR state**（3 类） | 由 `voxel_semantics_fine`+`mask_lidar_fine` 现场构建 | `[B,512,512,32]` int64 | `_occ_ground_gt_state`（detector `:2053`） | `observed(mask>0) & sem∈occ_sem_ids(1..5)` → OCC；`observed & sem∈free_sem_ids(0=Bg,6=Dust)` → FREE；其余 → UNKNOWN。**Ground(2) 算 OCC**；`w_lr_state=1.0`，`unknown` 类权重 `state_unknown_weight=0.05` |
| **HR state**（3 类 × 64 非均匀 bin） | `voxel_semantics_fine_hr` + `mask_lidar_fine_hr` | `[B,1024,1024,64]` int64 | `build_hr_state_gt_64_per_sample`（`occ_state_hr_gt.py:194`），`wh=(1024,1024)`、`fine_z=128`、`height_distribution=[0.3]*10+[0.1]*32+[0.3]*22`（配置未覆盖） | 在 **HR 原始 0.1m 层算一次判据**再多对一聚合进 64 bin；**确定性用置位集合并（OCC>FREE>UNKNOWN），禁 last-write-wins**；无 HR 帧给全 UNKNOWN（贡献≈0）；`w_hr_state=1.0`。**"LR→HR 最近邻放大"降级已删** |
| **ground cls（3 类）+ height（1）** | 由 HR occ-top 列顶构建 | `cls [B,1024,1024]` int64∈{0,1,2}；`z [B,1024,1024]` norm float；`hv [B,1024,1024]` bool | `_occ_ground_hr_top_gt:2103` → `build_ground_gt_full[_t]`（`occ_ground_top.py`）：逐 0.15m BEV 列取**最高 Ground 体素 z**；无 HR 帧走 `build_ground_bev_from_points(coltop)`（多帧融合点云兜底） | 列内有 cls==2 → GROUND + 高度；只有其他语义 → NOT_GROUND；否则 UNKNOWN；**当前帧 GT bbox 投影框内强制 NOT_GROUND 并清高度**；`loss_ground` 用 `ignore_index=2`（UNKNOWN 忽略），`w_ground_cls=1.0`；高度 L1 仅 `(gt==GROUND)&(hv>0)`，`w_ground_h=1.0` |
| **fine-binary**（16 子体素二分类） | HR `labels.npz` 的 `semantics`+`lidar_mask` 折 16 bit | `occ_bits/valid_bits [B,512,512,32]` int32 打包；pred `[B,512,512,32,16]` | `_occ_ground_fine_binary_gt:2204` 分派（v4→v3→v2） | BCE，`pos_weight_clamp=(0.5,10)`，`w_fine_binary=1.0`；见 §9.9 |

**v2/v3/v4 分派的代码原文（detector `:2204-2215`）**：

```
if cfg.get('fb_use_hr_labels', True):   # → v4  (_occ_ground_fine_binary_gt_hr_label, :2217)
if cfg.get('fb_v3_raycast',  True):     # → v3  (_occ_ground_fine_binary_gt_v3,       :2278)
return v2                               #       (_occ_ground_fine_binary_gt_v2,       :2322)
```

主配置**未设置** `fb_use_hr_labels` / `fb_v3_raycast` ⇒ 两者取缺省 True ⇒ **v4 是主路径**；v3 仅在"本批没有 HR 标签"时逐帧兜底；v2 是最后兜底。
**⚠️ 配置注释已过期**：`fb_gate_lr_occ` 仅被 v2 路径读取（`detector:2346`），**v4 不读**（v4 只读 `fb_free_sem_ids=[0,6]`）⇒ 配置对 v4 有效的键**只有 `fb_free_sem_ids`**。

**⑥ 深度（`ViewTransformerRCSample`）**

| 项 | 内容 |
|---|---|
| 监督信号 | LiDAR 深度 BCE（多分类 one-hot 形式） |
| GT 来源 | `EQPointToMultiViewDepth:5055`（主配置 `:1107`，`downsample=1`）：多雷达点按真值外参投到 7 路相机 → `results['gt_depth'] = torch.stack(depth_map_list)` |
| 形状/dtype | GT `[7,384,704]` float32；经 `get_downsampled_gt_depth:466` 按 `downsamples[-1]=8` 做 **8×8 块内最小深度** → `[B*N,48,88]`；再 one-hot 到 **`D=99`**（`depth_cfg=(1.0,100.0,1.0)`、`depth_mode='sid'` **对数分箱**）→ `[B*N*48*88,99]`；预测 `depth_preds [B*N,99,48,88]`（已 softmax） |
| loss | `F.binary_cross_entropy(...).sum() / max(1, fg_mask.sum())` × `loss_depth_weight=0.1`；`depth_preds` 先 `clamp(1e-6,1-1e-6)`；**`fg_mask = max(labels,dim=1)>0`（只算有效雷达像素）**；`autocast(enabled=False)` 保 fp32 |
| ⚠️ 数据侧注意 | `with_obj_mask=False` ⇒ 不产出 `gt_depth_obj_mask`；`obj_mask` 参数在 `get_depth_loss` 中被 `del` 显式忽略；test 且 `eval_gt_depth=False` 时 GT 为**全零占位**，下游需自行判零 |

### 17.3 监督权重总表（A 级）

| loss 键 | head | 类型 | 权重（含内部乘子） | 启用 |
|---|---|---|---|---|
| `task0.loss_heatmap` | `CenterHeadRotDense` | GaussianFocalLoss | 1.0（`avg_factor`=正样本数） | 是 |
| `task0.loss_xy` / `loss_z` / `loss_whl` / `loss_yaw` | 同上 | L1Loss | 0.25 × `code_weights=[1]*8`（roadcone 的 yaw 两维 →0） | 是 |
| `task0.loss_rot_dense` | 同上 | 加权 L1(sin/cos) | 0.25，focal-like 再调制 τ=1 / γ=2 / clamp max=1.5 | 是 |
| `task0.aux_loss_*` | `vision3d_det_aux_head` | 同上 | 同上（`aux=True`） | 是 |
| `loss_roi_cls` | `BevRoIAlignRotatedRefineHead` | CE(sigmoid) | 1.0 | 是 |
| `loss_roi_bbox` | 同上 | L1Loss | 0.25 × `code_weights=[1,1,1,1,1,1,2,2]`（仅正样本） | 是 |
| `semantic_seg_loss` | `PointSegOptHead` | CE | **3.0**（再 ×`B/num_valid`） | 是 |
| `entity_pick_semantic_seg_loss` | `PointSegHead` | CE | 3.0 | 是 |
| `loss_lr_sem` | `TinyOccStateGroundHead` | CE | 1.0 | 是 |
| `loss_lr_state` | 同上 | CE | 1.0（unknown 类 ×0.05） | 是 |
| `loss_hr_state` | 同上 | CE | 1.0（unknown 类 ×0.05） | 是 |
| `loss_ground_cls` | 同上 | CE（`ignore_index=2`） | 1.0 | 是 |
| `loss_ground_height` | 同上 | L1(MAE) | 1.0（仅 ground & valid） | 是 |
| `loss_fine_binary` | 同上 | BCE（16 子体素，pos_weight clamp 0.5–10） | 1.0 | 是 |
| `loss_depth` | `ViewTransformerRCSample` | BCE（one-hot D=99，仅 fg） | 0.1 | 是 |
| `loss_occ_fine` | `bev_occ_head` | CE | 1.0 | **否** |
| `loss_occ_top_cls` | `OccTopClsHead` | CE | 1.0 | **否** |
| `loss_occ_top_height[_c0..c6]` | 同上 | L1 | 1.0（7 类均值） | **否** |
| `loss_geo_known` / `loss_geo_occ` | `TinyOccGeoDualHead` | CE / BCE | 1.0 / 2.0 | **否** |
| `loss_voxel_ce` / `_sem_scal` / `_geo_scal` / `_lovasz` | `MultiLossBevOccHead` | focal/CE/scal/lovasz | — | **否** |

**关键常量汇总**：

```
train_cfg.pts = gaussian_overlap=0.1, max_objs=500, min_radius=2,
                dense_reg=1, out_size_factor=4, code_weights=[1]*8
occ_ground_loss_cfg = {w_lr_sem, w_lr_state, w_hr_state, w_ground_cls, w_ground_h,
                       w_fine_binary 全 = 1.0, state_unknown_weight=0.05,
                       fb_free_sem_ids=[0,6]}          # 默认空 dict ⇒ 全走代码内默认
geo_dual_loss_cfg   = {known 1.0, occ 2.0, pos_weight_scale 1.0}
depth_cfg           = (1.0, 100.0, 1.0), depth_mode='sid', loss_depth_weight=0.1
```

### 17.4 GT 缺失时的**四种处置策略**（数据侧最重要的工程范式）

| 策略 | 含义 | 实例 | 位置 |
|---|---|---|---|
| **① 兜底（borrow）** | 用另一来源重建缺失项 | LR `lidar_mask_fine` 空 → 用同 token HR `lidar_mask` 降采样（xy 2:1 any / z 4:1 any，ground 命中 99.2%） | `loading.py:3777-3808` |
| **② 降级（degrade）** | 换一个可用的低配来源 | HR 缺失 → LR 降采样；ground 无 HR → 多帧点云 coltop；fine-binary v4 → v3 → v2 | `occ_ground_train`；`occ_ground_bev.py:97-111`；detector `:2204-2215` |
| **③ 哨兵（sentinel）** | 保留样本、把 loss 置零 | `occ_supervision_lost` 帧：6 路 occ GT 置哨兵（mask=0 / state=−1 / g_cls=2 / g_valid=False / fb_bits=0）⇒ **只丢 occ 族梯度，不丢样本** | loader `loading_optimized_HR.py:1939-1948`；detector `:2749-2820` |
| **④ 剔除（drop data）** | 从训练集移除 | LR+HR 双缺 8 pkl / 76,662 帧从训练集剔除 | `docs/不可用数据收集清单_LR_HR双缺.md` |

> **范式总结**：这套系统的原则是"**数据缺失绝不阻塞训练，但必须显式标记**"——要么借、要么降、要么置哨兵，最后才是删数据。这也是 `occ_scale` / `occ_scale_hr` / `mask_lidar_fine` / `key` / `occ_supervision_lost` 这一整套"门控字段"存在的理由。

### 17.5 GT 键 ↔ `Collect` key 对照

| GT 键（pipeline 产出） | Collect key | 消费方 |
|---|---|---|
| `gt_bboxes_3d` / `gt_labels_3d` | ✅ 同名单数形式进 list | 检测主头 + RoI refine |
| `gt_bboxes_3d_vision` / `gt_labels_3d_vision` | ✅ | 视觉辅助头 |
| `pts_semantic_mask` | ✅ | 8 类点分割 |
| `pts_entity_semantic_mask` | ⚠️ **配置相关**：在 `..._14cls16_roi_new.py` 的 Collect 中存在（`:1257`），在本文 §7.4 那份 `...TemporalDepth.py` 的 21 key 中**不存在** | entity 头 ⇒ **不同配置的 Collect 集不同**，entity 只在"配了 head + 保留了该 key"的配置里生效 |
| `voxel_semantics_fine` / `mask_lidar_fine` / `occ_scale` | ✅ | OCC 族（LR sem / LR state） |
| `gt_depth` | ✅ | 深度 |
| `2d_seg_maps` / `2d_seg_maps_mask` / `2d_seg_edge_maps` | ✅ | ⚠️ **无 head 消费**（唯一消费者 `models/mmseg_heads/pid_head.py:139` 未构建）⇒ 疑似只付带宽 |
| `T_global` / `T_global_inv` / `timestamp` / `idx` | ✅（meta_keys） | 时序 warp / scene reset |
| `key` | ✅ | 所有 GT 过滤算子的总开关 |

> **数据侧自检点**：**"head 存在 + GT 键不在 Collect"** 或 **"GT 键在 Collect 但无 head 消费"** 都是静默错误。上线前应做一次"Collect key ↔ head 消费"双向核对。

---

## 18. 需求与决策背景（飞书讨论 × 代码）

> 本章解释"数据侧为什么长成这样"。✅ = 讨论与代码一致；➕ = 讨论补充代码未表达；⚠️ = 二者不一致。

### 18.1 组织与任务优先级（权威需求来源）

| 组 | 成员 | 与本仓关系 |
|---|---|---|
| 自动标注组 | 赵海飞、王礼明、李珂、李金城 | **提供 GT（occ/seg/det 标签）** ⇒ 数据侧的上游 |
| 环境理解组 | 王海罗、吴尚坤 | 2D 模型、道路边界、排土线 |
| **前景感知组** | 洪伟、杨书杰；2026-06-30 起赵申奥、方文涛（导师杨书杰） | **E2E_ENET 归属组** |
| 通用模型与后处理组 | 钟敏、赵海飞0、胡伟辰、关喜嘉 | 长时序 backbone、pretrain、两段式端到端（代码重叠） |

**前景感知组 · 26 年 Q3 的 P0（10 台 8 卡 H20）**：

| 优先级 | 任务 | 落到数据侧 |
|---|---|---|
| P0 | 业务模型迭代（badcase 修复、新增识别需求） | 14 类拆分（`roadcone`/`rockfall`）、多 pkl 配比 |
| P0 | **occ 模型研发（高分辨率）** | HR occ 数据链、LR 兜底、标签审计与 rebind |
| P0 | **纯视觉** | `test_vision_only` 评测口径、scene 级 drop（制造单模态缺失） |
| P0 | 刚卡&宽体车模型统一、时序一体化、多模态盲区 | 多 pkl 拼装、scene 级时序采样、"大一统模型" |

### 18.2 数据侧相关"谜团"的答案

| # | 代码事实 | 讨论证据（原话） | 判定 |
|---|---|---|---|
| 1 | **为什么突然要做 scene 级 sensor drop / CBGS？** | 2026-09-04 11:20 赵申奥：*"drop 策略优化之后，指标提升了一些，但**距离之前版本还是差距很大（28 vs 43）**"*；09-04 11:15 杨书杰：*"还有**新框架视觉掉点**的那个问题"*；09-07 19:28 赵申奥：*"你把红框里面三行 drop 几率都改成 0.3，因为训练数据配置会读 `data_config` 来做 **scene 级的 drop 传感器**"*；提交 `c55b733`：*"挖机半挂车 nms 适配 + 根据 scene 随机 drop 传感器"* | ➕ **事故驱动，不是先验设计**。scene drop 与选择性 NMS 都是为修复"28 vs 43"引入 |
| 2 | **为什么标签质量成为瓶颈、为什么"先用 LR 兜底 HR"？** | 09-04 10:45 洪伟：*"**occ-gt 估计也要重弄。会比较麻烦**"*；09-04 23:48 洪伟：*"occ gt 估计不好搞，因为**全量重做估计没一周不行**"*；*"我建议**先训练一个版本，然后同步搞 occ-gt 再出一个版本**"*；09-04 11:09 杨书杰：*"除了仿真数据，带动物的 scene 非常少，**可以只针对那些重新生成 occ-gt**"* | ➕ **生产节奏妥协**，不是技术偷懒。与"标签质量卡上限"结论完全互证 |
| 3 | **为什么 SECOND backbone 默认 `frozen=False` 却要求不解冻？** | 09-04 11:44 洪伟：*"那个 **second 实际训练时候不要解冻，因为排土位模型要拿这个特征**"* | ⚠️ **跨模型依赖**，代码默认值与团队要求**相反**（`frozen=False` 易误开）⇒ "28 vs 43"的直接诱因之一 |
| 4 | **14 类为什么拆 `roadcone`/`rockfall`？为什么 `no_rot_classes`？** | 09-04 11:11 王文凯：*"大家 gt **不能仅着眼于目前的需求，随着社会道路会越来越多，标注需要逐步拉齐社会道路的标注类别**"*；09-01 09:17 杨书杰：*"大概率是 **350 新增的动物类型强转出的行人**"*；09-04 11:12 杨书杰：*"最早有 **plant** 这类，后面反馈**标注效率低给砍了**"* | ✅➕ **业务需求 + 标注成本的折中**；路锥近旋转对称 ⇒ yaw 无标注意义 |
| 5 | **entity 头的业务定义** | 06-24 13:36 王文凯：*"特别是**扬尘检测实体**，case2\case6"*；09-10：*"这个靠目前的点云分割大概率搞不定，**需要滚落下来就得分割为实体**"* | ✅➕ **扬尘必须判虚体**（否则规划被"灰尘墙"逼停）、**滚落物必须判实体**（否则漏障碍） |
| 6 | **`test_vision_only=True` 是设计还是遗留？** | 09-02 洪伟：*"350 det 漏了，你去复测一下，**顺便看看纯视觉**"*；赵申奥：*"纯视觉检出了，但前半段朝向有点飘"* | ✅ **有意设计**（Q3 的独立 P0 线）—— 前几册标"需确认"的项，**答案在飞书** |
| 7 | **为什么时序模块被反复简化（连卷积版 Mamba 都不用）？** | 09-10 洪伟：*"之前你们看过 **om 的耗时**吗"*；09-11：*"耗时上 **dev-900 肯定是卡点，因为还有时序**"*；*"目前每次可以读取 **64 位缓存**，理论上可以包裹住 16 个 fp16"*；*"现在这种做法会**多一个 transData 和 256×256 的带宽**"* | ✅➕ **部署耗时驱动**，精度让位于板端可行性 |
| 8 | **occ 为什么从 7 类语义加到三态 + HR + ground + fine-binary？** | 09-01 09:53 洪伟：*"目前我理解下来：1、**occ-state** 2、视觉 det 优化 3、新增的业务数据…"* | ✅ **occ-state 是独立技术方向**（不是 det 附属），HR 是 Q3 P0 |
| 9 | **"大一统模型"是什么？** | 09-10 14:38 杨书杰：*"这个 case **大一统那版模型**测试时重点关注"*；09-16 14:42 洪伟：*"我初步看了这个**大一统模型效果还是不错的，哥们就等你分支了**"* | ✅ = **多任务 + 多车型 + 时序一体化的统一模型**，V5 全量配置是其载体 |

### 18.3 "28 vs 43"掉点事件（数据侧视角的完整时间线）

| 时间 | 事件 |
|---|---|
| 09-01 09:52 | 洪伟：*"我们要基于**时序训练代码迁移训练功能**"* |
| 09-01 09:54 | 洪伟：*"那个是 **350 版本的，不是时序的**"* ⇒ **基线口径不同** |
| 09-02 17:48 | 赵申奥上传改动说明文档 |
| 09-04 11:15 | 杨书杰：*"还有**新框架视觉掉点**的那个问题"* |
| 09-04 11:20 | 赵申奥：*"drop 策略优化之后指标提升了一些，但**距离之前版本差距很大（28 vs 43）**"* |
| 09-04 11:22 | 赵申奥：*"**我解冻了**，训练的时候"* |
| 09-04 11:23 | 杨书杰：*"会不会是**评测的问题**？**挖机和半挂的 nms 对齐了吗**"* |
| 09-04 11:44 | 洪伟：*"second 实际训练时候不要解冻，因为排土位模型要拿这个特征"* |
| 09-04 15:28 | 提交 `c55b733`：**"挖机半挂车 nms 适配 + 根据 scene 随机 drop 传感器"** ← 修复落地（**数据侧 drop 就在这一笔**） |
| 09-04 17:28 | 赵申奥改版重跑 |
| 09-04 23:48 | 洪伟：*"occ-gt 全量重做估计没一周不行，先训一版，同步搞 occ-gt 再出一版"* |
| 09-07 19:26 | 洪伟给训练 shell，让盯 loss；19:28 指示*"三行 drop 几率都改成 0.3"* |
| 09-08 12:06 | 洪伟：*"开一个小龙虾的 agent 跟一下 log"* ⇒ 引入 AI agent 盯训练 |

**三个叠加原因**：①解冻 SECOND（破坏下游排土位模型依赖的特征）；②**新框架 drop 策略与 350 不一致**；③**评测口径未对齐**（挖机/半挂 NMS）。
**教训**：训练策略与评测协议必须**逐项对齐**，否则"掉点"可能只是口径差异。

### 18.4 由讨论反推出的隐性架构约束（数据侧相关）

1. **SECOND 特征是跨模型的公共契约**——解冻 = 破坏下游排土位模型。任何改 LiDAR backbone/点云预处理的行为必须先与下游对齐。
2. **时序模块的首要约束是板端耗时，而非精度**——om 耗时、transData 数量、256×256 带宽、64 位缓存对齐是设计一等公民 ⇒ **数据侧的时序简化（全 keyframe、无 sweeps）服务于同一目标**。
3. **评测口径与训练口径必须成对演进**——"掉点"至少三次被怀疑是评测问题；代码里确实存在两套 `final_score`。⇒ **建议把评测协议本身纳入版本管理**。

### 18.5 数据管理基础设施（讨论暴露的实况）

| 设施 | 地址 | 用途 |
|---|---|---|
| 数据管理平台 | `dclp-self.eqfleetcmder.com`（dataManage / dataSpace / lockDataDetail） | **数据锁定**、仿真任务、badcase 回放 |
| 训练平台 | 火山 MLP `console.self-drive.volcengine.com/ml-platform` | 多机多卡 + 实时 log |
| occ GT 生成 | `/e-vepfs-01/occ_gt/E2E_ENET`、`/e-vepfs-01/occ_gt/qwen3.8` | 离线 GT 全量重建 |
| 训练入口 | `cd /e-vepfs-01/occ_gt/E2E_ENET && CONFIG=... WORK_DIR=... bash Train_OccStateGround.sh`（支持 `MAX_EPOCHS=1` / `BS=4`） | 与仓库脚本对应 |
| 板端/仿真 | MDC 227、`dev-900`、`eq-sim/test_sil`、`registry.eqfleetcmder.com` | 编译与耗时测试 |

**资源纪律（原话）**：*"集群 gpu 资源比较紧张，实习生的 gpu 用量调整到 10%"*（08-13）；*"我要训练一个全量 occ 重构模型，得需要 **8 个节点 4 天**，大家暂时先不要提任务"*（08-20）；*"不要起带 gpu 的开发机，统一申请**纯 cpu 远程开发机**"*（09-10）。
⇒ 直接解释了为什么"**数据侧改动本地无法验证全量 load**"是常态（`412fda2` 亦注明）。

---

## 19. 采样与配比的定量分析

### 19.1 公式汇总

```python
# ① 帧数展开
N_pkl_i = round(n_i × repeat_i)                      # repeat≥1：整份复制
N_pkl_i = round(n_i × repeat_i)  （np.linspace 等距抽样，repeat<1）
N = Σ_i N_pkl_i                                       # dataset 总帧数（先按 load_interval 抽帧，再复制）

# ② 每 rank 每 epoch 样本数
num_samples = ceil(N / num_replicas / samples_per_gpu) × samples_per_gpu
total_size  = num_samples × num_replicas
iters_per_epoch = num_samples / samples_per_gpu

# ③ CBGS 后的 epoch 长度
N'          = Σ_{s ∈ 抽中 scene} len(s)                # 含跨类重复抽中的 scene
n_c_base    = (Σ_c |class_scene_idxs[c]|) / n_cls
n_prime_base= Σ_c (n_c_base × mean_len_c)
λ           = (length_factor × N) / n_prime_base       # 反解
n_c         = clip(round(λ × n_c_base), 1, |inds_c| × max_ratio)
⇒ N' ≈ λ × n_prime_base = length_factor × N            # 目标：epoch ≈ 1.75 × N
num_samples = ceil(N' / num_replicas / samples_per_gpu) × samples_per_gpu

# ④ pad 量
pad_frames ≈ num_samples × num_replicas − (实际可用帧数)
# 因 pad 优先复用"最后一个 scene 的最后一帧"，pad 帧数通常 < num_slots
```

### 19.2 算例（用已知真实数字：smalltest 4 pkl / 75,601 帧 / `spg=2`）

| 场景 | 计算 | 结果 |
|---|---|---|
| 单卡 | `ceil(75601/1/2)×2` | `num_samples = 75,602`；**37,801 iter/epoch** |
| 8 卡 | `ceil(75601/8/2)×2 = ceil(4725.06)×2` | 每 rank `9,452`（total 75,616）；**4,726 iter/epoch** |
| pad 量（8 卡） | `75,616 − 75,601` | **15 帧**（≈0.02%，每 rank 约 2 帧 ⇒ **正好是 num_slots−1 量级**） |
| CBGS 开启（8 卡，`length_factor=1.75`） | `N' ≈ 1.75 × 75,601 ≈ 132,302` | 每 rank `ceil(132302/8/2)×2 = 16,540`；**8,270 iter/epoch（≈1.75×）** |
| CBGS 收缩上界 | 每类 `n_c ≤ |inds_c| × 5` | 稀有类若候选 scene 少，实际 N' 会低于 1.75×N |

> **工程结论**：`length_factor` 是**线性旋钮**；`samples_per_gpu` 同时决定 batch 大小与 **slot 数量**（`num_slots == spg`）⇒ 从 2 提到 4 会让 episode 内并发 scene 数翻倍，也会让 `placeholder_rounds` 概率下降（对 `len(my_scenes) >= num_slots` 更宽裕）。

### 19.3 采样区 vs 评估区的**面积定量对比**（新发现，量化）

两套 r0–r3 都是 ego 系矩形（半开区间，宽度 = upper − lower）：

| 档 | 采样区 x / y | 采样面积 (m²) | 评估区 x / y | 评估面积 (m²) | 采样/评估 |
|---|---|---|---|---|---|
| r0 | `[-30,30)` / `[-30,30)` | **3,600** | `[-15,30)` / `[-15,15)` | **1,350** | **2.67×** |
| r1 | `[-30,50)` / `[-30,30)` | 4,800 | `[-20,50)` / `[-30,30)` | 4,200 | 1.14× |
| r2 | `[-30,80)` / `[-50,50)` | 11,000 | `[-25,80)` / `[-50,50)` | 10,500 | 1.05× |
| r3 | `[-30,120)` / `[-70,70)` | 21,000 | `[-30,120)` / `[-70,70)` | 21,000 | 1.00× |

**结论**：

- 不一致**几乎只发生在 r0**：采样 r0 是 60×60 的完整近场正方形，而评估 r0 是 x∈[−15,30) 的**偏前近场窄条**（车后 15m 内不计）⇒ 采样补样区域比考核区大 **2.67 倍**。
- r1/r2/r3 相对接近（1.14× / 1.05× / 1.00×），r3 完全一致。
- 由于 `final_score` 中 **r0 权重 0.3**（与 r3 并列最高），这一档的口径错位最值得关注：**在自车后方 15–30m 区间补样，考核时不计分**。

### 19.4 采样侧"预算守恒"检查（建议纳入 CI）

```
① len(my_scenes) >= num_slots                    # 否则 placeholder_rounds > 0，引入 idx 0 假样本
② error_idx 占 len(dataset) 比例                 # 静默降样本量
③ pad_frames / total_size                        # pad 占比异常说明 scene 太碎
④ CBGS: N' / (length_factor × N) ≈ 1             # 若明显 <1 说明被 max_ratio 收缩
⑤ 每 epoch 实际 iter 数 vs 预期                    # CBGS 下应随 epoch 在小范围波动
```

---

## 20. 数据侧改动影响面矩阵

> 改数据侧任意一项前，先在此表查"会波及什么"。左列 = 你要改的；右列 = 必须同步检查/修改的。

| 改什么 | 直接波及 | 必须同步 | 风险等级 |
|---|---|---|---|
| `pkl_list` / `repeat` | `len(dataset)` → `num_samples` → **epoch 长度** | 采样器预算、CBGS 的 `N_orig` | 🟠 中（实验不可比） |
| `samples_per_gpu` | batch 形状 + **slot 数** + 显存 | `find_unused_parameters`、`placeholder_rounds` 概率 | 🟠 中 |
| **`idx` 语义** | scene 切分（`flag`）+ geo 软窗口 + drop 注入 + **模型侧 `reset_sign`** | 四处必须同时改，否则时序错乱 | 🔴 高 |
| `class_names` | `MapDetectionClassMamba` 的 `assert self.classes == clscfg.CLASS_NAMES`（`loading.py:5003`） | yaml 14 类、`clscfg`、head `num_class`（16 通道）、CBGS 池类、NMS 类表、`print_error_stats` 的硬编码 5 类名 | 🔴 高（启动即断言失败/评测 KeyError） |
| `point_cloud_range` | 点云裁剪、GT 框裁剪、voxel 栅格 | **`full_point_cloud_range`**（真正闭合）、`voxel_size`/`dense_shape`、`occ_size`、`bda_aug_conf.occ_size`、head 输出尺寸 | 🔴 高（0.01m 边界错位） |
| occ 分辨率/几何 | LR `[512,512,32]@0.3/0.4`、HR `[1024,1024,128]@0.15/0.1` | `occ_vox_shape_hr`、`bda_aug_conf_hr`、HR loader、`det_occ_aug_swap_xy`（H/W 轴约定） | 🔴 高 |
| `scene_level_drop` 概率 | 训练期模态缺失分布 | **与旧版本（350）口径**、评测基线可比性 | 🔴 高（28 vs 43 教训） |
| 开 BDA（非恒等） | occ GT 也做 BDA 重采样 | **时序 warp 对齐**（`T_global` **不含** BDA！）、深度 GT 顺序约束 | 🔴 高（时序与 GT 不一致） |
| 开注释态增强 | 数据分布变化 | `RandomCamExtrinsicNoise` **必须在 `EQPointToMultiViewDepth` 之后**；`ComplementaryCrossModalMask` 会同步裁 `pts_semantic_mask`（长度不匹配直接 `ValueError`） | 🟠 中 |
| `occ_gt_root_hr` | remap 分支 | 与实际 `occ_path_hr` 绑定一致性（当前配置漂移） | 🟡 低（当前被数据掩盖） |
| 新增/改 pipeline 算子 | `results` 字段流 | **`Collect` key 必须成对改**（head 读的 key 不在 Collect 里会 KeyError） | 🟠 中 |
| 改类别数（13→14） | 检测头通道、`MapDetection`、CBGS、NMS | `print_error_stats` 硬编码 5 类名（j=4 KeyError）、`work_dirs_eval_summary` 口径 | 🟠 中 |
| `use_pkl_list=True`（目录扫描） | `infos` 拼接顺序 | **绕过 `sort_datasets`/`load_interval`** ⇒ 需自行校验 `idx` 连续性与时间序 | 🟠 中 |
| `keep_consistent_seq_aug` | 同 slot 共享 IDA/BDA | pad 复用逻辑、显存 | 🟡 低 |
| `avail_gt_depth` / 深度开关 | `gt_depth` 是否哑值 | 消费方需判零（test 时全零占位） | 🟡 低 |

---

## 21. 数据侧自检清单（上线前 SOP，14 项）

| # | 检查项 | 命令/方法 | 通过标准 |
|---|---|---|---|
| 1 | **文件规模**（勿信 `wc`） | `python3 -c "print(open(f,'rb').read().count(b'\n'))"` | 与预期量级一致（采样器 1549 / dataset 2667 / loading 5715 / transform 4245） |
| 2 | 帧数展开 | 打印 `len(dataset)` 与逐 pkl `(path, repeat, n_before, n_after)` | 与 `Σ round(n_i×repeat_i)` 一致 |
| 3 | scene 分组 | 打印 `flag` 的取值数（scene 数）与单调性 | 同 `idx` 连续落在同一 `flag` |
| 4 | **`idx` 连续性** | 对每个 pkl 检查 `idx` 是否单调/成块 | 走 `use_pkl_list` 时尤其重要（绕过 sort） |
| 5 | epoch 预算 | 打印 `num_samples`、`iters_per_epoch`（CBGS 下逐 epoch） | 与公式一致；CBGS `factor ~ N'/len(dataset)` ≈ 1.75 |
| 6 | **`placeholder_rounds`** | 采集 rank0 warning | **= 0**（>0 说明 `len(my_scenes) < num_slots`，引入 idx 0 假样本） |
| 7 | **`error_idx` 规模** | 训练末打印 `len(error_idx)` | 占比 < 0.1%，且逐 epoch 不再增长 |
| 8 | LR occ 有效性 | 统计 `occ_scale==1` 的帧占比 | ≥ 60%（当前 39% 帧 mask 空是已知缺陷） |
| 9 | HR 覆盖率与指向 | 统计 `occ_scale_hr` 与 `occ_path_hr` 的目标目录分布 | 100% 指向 `occ_gt_smallrange_15`；旧目录 0 帧 |
| 10 | **`occ_supervision_lost` 计数** | detector 侧计数/日志 | 比例稳定且低；突增说明 HR/LR 同时恶化 |
| 11 | **OccTop 丢样本率** | 在 pipeline 加计数器（`return None` 处） | 若 HR 覆盖率低，需评估有效 batch 缩水 |
| 12 | 增强实际开关 | 逐项打印 `drop_sensor_type` 分布 + IDA 参数 + BDA 矩阵是否恒等 | 与配置意图一致（当前：IDA 开 / BDA 恒等 / 6 项注释） |
| 13 | **Collect key ↔ head 消费**双向核对 | 列出 21 key 与各 head 读键的交集 | 无"有 head 无 key"、无"有 key 无 head" |
| 14 | 几何闭合 | 校验 `point_cloud_range` vs `full_point_cloud_range` vs `dense_shape×voxel_size`，以及 occ/BEV 栅格 | **全部闭合**（用 `full_point_cloud_range`） |
| 附 | 采样区 vs 评估区 | 比对两套 r0–r3 | 明确差异并确认是否接受（当前 r0 差 2.67×） |

---

## 22. 与 350/330 量产线的口径对齐清单

> 依据"28 vs 43"事故的教训：**训练策略与评测协议必须逐项对齐**。以下清单可直接作为跨版本对齐的 checklist（当前**无成文文档**，属未确认项）。

| 类别 | 项 | E2E_ENET 现状（本仓） | 需与 350 核对 |
|---|---|---|---|
| 训练策略 | LiDAR backbone 冻结 | `frozen` 字段存在，默认 `False`（易误开） | 350 是否冻结；下游排土位模型的特征契约 |
| 训练策略 | 传感器 drop | **scene 级互斥**（img/lidar/none），每 epoch 重抽，现概率已下调（图像不丢、整帧丢关闭、部分丢雷达 0.3） | 350 的 drop 粒度与概率 |
| 训练策略 | BDA | **恒等（等于关闭）** | 350 是否启用旋转/缩放增强 |
| 训练策略 | 图像增强 | 仅 IDA（`resize=(-0.06,0.11)` + 随机 `crop_w`） | 350 的增强组合 |
| 数据 | 类别体系 | 13 类 / 14 类（拆 `roadcone` + `rockfall`），模型 16 通道含 2 pad | 350 的类别数与映射 |
| 数据 | 类别映射 | 算子级 yaml + 全局双回退 + 强断言；`no_rot_classes=['roadcone']` | 350 是否为同一映射 |
| 数据 | occ GT 版本 | LR `labels_new.npz` + HR `labels.npz`（`occ_gt_smallrange_15`） | 350 用的 occ GT 版本/几何 |
| 数据 | 预处理链 | 全 keyframe（`sweeps=[]`）、`load_interval`、`sort_datasets` 行为不一 | 350 的 pkl 口径 |
| 评测 | `final_score` 公式 | **0.3/0.2/0.2/0.3**（`eval_task.py:1286`；旧公式 0.45/0.25/0.2/0.1 已注释） | 350 用的版本 |
| 评测 | r0–r3 区间 | 评估器 `[-15,30,-15,15]…[-30,120,-70,70]`；采样器另一套 | 350 的区间版本 |
| 评测 | NMS 策略 | `selective_nms_bev`：挖机/挖机底座/半挂车头/半挂车厢**4 类类内**，其余 9 类跨类 | 350 的 NMS（**事故直接原因**） |
| 评测 | overlap 阈值 | 车辆类 0.5；`pedestrian/rider/SmallTarget/animal/humanlike_background` 0.3 | 350 的阈值 |
| 评测 | ignore 类 | 点分割 `ignore_index=0`（BackGround 变 NaN，**实为 7 类**）；OCC `nanmean(mIoU[1:])` | 350 的处理 |
| 评测 | 选点方式 | 全部取 `*_ema.pth` | 350 的选点规则 |
| 评测 | 纯视觉口径 | `test_vision_only=True` ⇒ **点分割指标失效**，须显式排除 | 350 是否同口径 |

**建议**：把"公式版本 + 区间版本 + NMS 版本 + 增强/drop 配置摘要"作为**评测协议指纹**写进每次评测输出与 `work_dirs_eval_summary`，避免跨时期比分失真（当前 summary 已混入上一代命名与 r4）。

---

## 23. 数据侧关键数字面板（一页速览）

| 维度 | 数字 |
|---|---|
| 训练集 pkl 条目 | **34**（full-data 配置 `anno_root` 实测）／另一配置 36 |
| 路径来源 | `./data` **22** 条 + 跨同事/跨仓 **12** 条（共 3 个目录树） |
| `repeat` 分布 | `1`:16 ｜ `3`:7 ｜ `0.5`:6 ｜ `2`:2 ｜ `5`:3 |
| 核心文件规模 | dataset **2667** 行 ｜ sampler **1549** 行 ｜ loading **5715** 行 ｜ transform **4245** 行 ｜ detector **7142** 行 |
| pipeline 算子 | train **20** ／ test **16** |
| `Collect` keys | train **21** active（+12 注释）／ test **16** |
| 采样器家族 | **7** 个类，主线 `OptV2`（`:1101`） |
| CBGS 参数 | `range=120m`、`min_hit=3`、`length_factor=1.75`、`max_ratio=5`、池类 `class_names[:11]` |
| epoch 长度 | `num_samples = ceil(N/卡数/spg)×spg`；CBGS 下 ≈ **1.75×N** |
| slot 数 | = `samples_per_gpu`（主配置 **2**；V5 四件套 12/8/4/4） |
| sensor drop | `P_IMG=P_LIDAR=0.3`（模块默认）；**实配：图像不丢、整帧丢关闭、部分丢雷达 0.3** |
| 增强开启率 | 实跑 **1**（IDA）／恒等 **2**（BDA、HR BDA）／注释关闭 **6** |
| **标签缺陷** | LR mask 空 22 pkl / **706,821 帧（39%）**；双缺 8 pkl / **76,662 帧**；HR 部分未绑 15 pkl / **7,634 帧**；合计受影响 **84,296 帧** |
| 兜底效果 | HR→LR mask 降采样：**ground 命中 99.2%** |
| HR 绑定 | **95.22%**（1,710,713 帧）指向 `occ_gt_smallrange_15`；旧目录 **0 帧** |
| HR 语义稀疏 | wall **75%** / Ground **23%** ⇒ 可见地面约 **85% 未标注** |
| 评测 | `final_score = 0.3·r0+0.2·r1+0.2·r2+0.3·r3`；mIoU 名义 8 类**实为 7** |
| 迭代 | 42.841 → 43.120；r0 48.16→47.48（↓）；orient_p99 **11.78°→13.30°**（↓） |
| 采样区/评估区（r0） | **3,600 m² vs 1,350 m² = 2.67×** |
| 性能 | `data_time` **0.03–0.2s**（非瓶颈）；occ_ground 塔 331ms（28%）；GT 构建 **15–18%**；`occg_gt_fb` 711–803ms → **4–14ms** |
| 资源 | 全量 occ 重构需 **8 节点 × 4 天**；实习生 GPU 配额 **10%** |
| 数据侧提交 | 冲刺 3 天（09-03~05）**102** 条提交（全仓 71%）；数据侧 15 项特性中 **12** 项落在此窗口 |

---

## 附录 A 文件:行号总索引

| 主题 | 文件 | 关键行 |
|---|---|---|
| 数据集类 | `datasets/eq_nuscenes_temporal_multitask_mamba.py`（2667 行） | `__init__:158`、`his_data_infos:282`、`_rebuild_scene_drop_table:353`、`set_epoch:371`、`_get_region_info:376`、`_clip_data_infos:409`、`_set_sequence_group_flag:432`、`get_cbgs_cat_ids:569`、`_precompute_cbgs_frame_cat_ids:604`、`_rand_another:613`、`_prepare_train_data:623`、`__getitem__:683`、`_load_ann_entry_infos:760`、`load_annotations:786`、`_load_ann_list:819`、`get_data_info:840`、`_resolve_occ_gt_path_hr:997`、`get_history_data_info:1031`、`get_history_ann_info:1153`、`get_ann_info:1221`、`format_results:1721`、`evaluate:2077`、`evaluate_occ:1937`、`print_error_stats:2274` |
| 采样器 | `datasets/samplers/multitask_sampler.py`（1549 行） | class `18 / 101 / 266 / 599 / 871 / 1101`；`num_samples:1151`、`_balance_scenes:~1253`、`_balance_scenes_cbgs:1253-1322`、`_refresh_cbgs_budget:1322-1337`、`_slot_round_robin_emit:1340-1429`、`_pad_stream_to_num_samples:1432-1487`、`__iter__:1489` |
| 采样器选择 | `datasets/builder.py` | 链 `:105-140`；`single:103`、`streaming:121`、`group_opt:130`、`shuffle:139`、`test_multiPkl:154` |
| pipeline loading | `datasets/pipelines/loading.py`（5715 行） | `PrepareImageInputs:1302`（互斥 drop `1648-1700`）、`EQLoadPoints:2882`、`load_labels_npz:3456`、`LoadEQOccGT:3694`、`LR mask 兜底:3777`、`_load_semantic_seg_3d:4589`、`LoadAnnotations:4785`、`points2depthmap:4915`、`gt_depth 哑值:4937`、`EQPointToMultiViewDepth:5055`、`RandomCamExtrinsicNoise:5375`、`MapDetectionClassMamba:5626` |
| pipeline transform | `datasets/pipelines/transform.py`（4245 行） | `EQNuScenesSparse4DAdaptor:797`（`T_global:818-824`）、`InstanceNameFilter:1332`、`ObjectRangeFilter:1603`、`PointShuffle:1757`、`PointsRangeFilter:1788`、`ObjectNameFilter:2056`、`InvalidBoxFilter:2185`、`ToEgo:2930`（lidar drop `3127-3150`、mask 复用 `3196`、pop `3217`）、`EgoPointsFilter:3444`、`CameraVisibleFilter:3644`（`__repr__:3672`）、`PointSegClassMapping:3696`、`PointSegClassMappingEntity:3753`、`RandomDropNearObjectPoints:3924`、`ComplementaryCrossModalMask:4052` |
| HR loader | `datasets/pipelines/loading_optimized_HR.py` | `load_labels_npz:1177`、`LoadEQOccGTFromFileOptimizedHR:1124`、`occ_supervision_lost:1939-1948`、`TopCls return None:1935-1936`、`判据:2033-2071` |
| scene drop | `datasets/pipelines/scene_sensor_drop.py` | `P_IMG/P_LIDAR:4-5`、`ensure_one_camera:44`、`build_scene_drop_table:85` |
| 多 pkl 工具 | `datasets/eacon_utils/ann_file_list.py` | `md5 种子:8-18`、`expand_infos_by_repeat:21-47` |
| 评测 | `datasets/eacon_utils/eval_task.py` / `eval.py` | `final_score:1286` / `867`；`calculate_errors:13-61`；`is_in_difficulty_ring:197-246` |
| 配置（数据段） | `TemporalModelV5/EQDetSegOccMambaWithSegV5TemporalDepth*.py` | `Collect:649`、`bda_aug_conf:275-284`、`occ_size:108/231`、`occ_gt_root_hr:305`、`train_pipeline:547-690`、`test_pipeline:692-813`、`samples_per_gpu:24`、`workers_per_gpu:25` |
| 训练入口 | `tools/train.py` | `set_detect_anomaly:44`、`val 构建:315`、采样开关 `347-382` |

## 附录 B 提交哈希索引

| 提交 | 日期 | 主题 |
|---|---|---|
| `1f939ce` | 03-11 | init（带入 `pkl_list` 参数雏形） |
| `dc53bab` | 09-03 | 单 pkl 训练时置 `use_pkl_list=False` |
| `412fda2` | 09-04 | **`ann_file` 多 pkl 列表改 `pkl_list`（绕 ConcatDataset）** |
| `c55b733` | 09-04 | **挖机半挂 nms 适配 + 按 scene 随机 drop 传感器** |
| `4e071fd` | 09-04 | 小批量测试版（4 份 pkl / 2 epoch） |
| `8e46b63` | 09-04 | collect `mask_lidar_fine_hr`（fb 走 HR labels） |
| `b356717` | 09-04 | HR loader 稀疏行跳过 dense 3-state |
| `ce6562f` | 09-04 | occ_ground GT builder 分项计时 |
| `10c04fc` | 09-05 | **HR state/ground/fb 监督真吃离线高分 labels（grill v5）** |
| `99bf85d` | 09-05 | **LR `lidar_mask_fine` 缺失由 HR labels 降采样兜底** |
| `b903704` | 09-05 | LR mask 缺失全量审计报告 |
| `8a9c871` / `f20b0cc` / `667f5b5` | 09-05 | HR `occ_path_hr` 绑定审计工具与权威结论（95.22%） |
| `1f65791` | 09-05 | HR `labels.npz` 磁盘存在性核查 |
| `9c146f1` | 09-05 | 结论式名单（转数据生产方最终版） |
| `86fe72a` / `8947229` | 09-05 | **双缺清单 + HR rebind 工具 / D 类补跑执行说明** |
| `ae7ac57` | 09-07 | **全量数据训练适配**（14 类 yaml + CBGS + `expand_infos_by_repeat`） |
| `183de3d` / `7625b58` / `92f4c1c` | 09-07 | **drop 概率三次下调** |
| `536e524` | 09-07 | merge sa 修改 && lss 模型初版 |
| `0dd095d` | 09-08 | **occ 卡死防护（`occ_supervision_lost`）** |
| `1f02fc1` | 09-15 | **pairGT + CBGS + 时序数据增强 + 预训练替换** |
| `fdbc658` | 09-16 | **CBGS 策略适配 14c** + drop 概率降低 |
| `867f20a` | 05-25 | add MambaConv and convert and VisionSeg（部署驱动的起点） |
| `4ea51b4` | 06-23 | V5 配置建立（`conv_mamba` 自始即为注释） |

## 附录 C 术语表

| 术语 | 含义 | 易误解点 |
|---|---|---|
| **`idx`** | 场景 id（同 idx = 同 scene） | **不是样本下标**；贯穿分组/软窗口/drop 注入/模型 reset |
| **`flag`** | 每帧所属 sequence 号，采样器分组唯一输入 | 由 `idx` 变化切出，不是时间戳 |
| **`(path, repeat)`** | 多 pkl 的复制/抽样系数 | `round(n×repeat)`；小数走**确定性**抽样 |
| **slot / slot streaming** | 采样器槽位（batch 内固定列位绑定一条 scene 时间序） | **不是** instance/query 传播；`num_slots == samples_per_gpu` |
| **slot-tail hold** | 轮末用该 slot 上一帧回填空位 | 保 batch 形状，不引入新语义 |
| **`num_samples`** | 每 rank 每 epoch 的样本数 | 向上取整到 `samples_per_gpu` 整数倍；CBGS 下逐 epoch 变 |
| **CBGS** | scene 级类别均衡采样 | λ **反解**得到；复制**整条 scene**；与 region-balance 互斥 |
| **λ（cbgs lambda）** | `length_factor × N_orig / n_prime_base` | 由目标长度反解，不是硬编码 |
| **region-balance** | 按「类 × 区域」补**实例**样本 | 复制**单帧** ⇒ 破时序；与 CBGS 互斥 |
| **scene-level drop** | 同 scene 全帧共用一份互斥传感器 drop 配置 | 每 epoch 重建一次 |
| **`drop_lidar_mask`** | 雷达丢弃索引集合 | `None`=待定；**空集=全保留**（合法决策） |
| **IDA** | 图像 resize jitter + 随机 crop | 唯一实跑的图像增强 |
| **BDA** | BEV 域旋转/缩放/flip/平移增强 | 当前配置**恒等 = 等于关闭** |
| **LR / HR** | 低分辨率 512²×32 / 高分辨率 1024²×128 occ | HR 需离线 `labels.npz`；文件名分别是 `labels_new.npz` / `labels.npz` |
| **`occ_scale` / `occ_scale_hr`** | occ GT 有效性门控（0 = 本帧无 GT） | 双轨**独立**，避免互相覆盖 |
| **`occ_supervision_lost`** | 批次哨兵：occ 双丢时置零 loss 而不丢样本 | 09-08 引入的卡死防护 |
| **`error_idx`** | 抛异常样本的 idx 集合 | 该帧本轮不再被采到（静默降样本量） |
| **`placeholder_rounds`** | slot 无 tail 可回填时用 idx 0 垫位的轮次 | 潜在噪声源，有 rank0 warning |
| **`lidar_mask`** | 离线 ±20 帧 ray-cast 的**观测掩码** | 界定 free/unknown；不可用单帧在线射线替代 |
| **fine-binary** | 16 子体素二值占用 | v2/v3/v4 是**降级链**（v4→v3→v2），非并存 |
| **`dumppile`** | 料堆（seg id 71）/ 料堆组（72） | 新数据新增类，曾致 id 72 越界崩溃 |
| **ringiness** | 环形伪影量化指标 | 旧生成算法 1.080 → 体素 DDA 0.448 |

## 附录 D 常量与几何速查

### D.1 传感器与分辨率

| 项 | 值 |
|---|---|
| 相机路数 | **7**（FRONT_LEFT / FRONT_FISHEYE / FRONT_RIGHT / BACK_LEFT / BACK_FISHEYE / BACK_RIGHT / FRONT_LONGFOCUS） |
| 相机分辨率 | 源 **1080×1920** → 输入 **384×704**；长焦原始 2160×3840 |
| `Ncams` | 7（= 全量，`choose_cams` 不抽样） |
| 雷达声明 | **7** 路：`top` / `top_aux` / `left` / `mid_left` / `right` / `mid_right` / `back` |
| 基础 4 雷达后缀 | `''` / `_l` / `_r` / `_b` → `points_t/_l/_r/_b` |
| 新增 3 雷达后缀 | `_top_aux` / `_mid_left` / `_mid_right`（仅当 info 存在对应 `lidar2ego_rotation{suffix}` 才启用） |
| 多雷达处理 | 全部 `cat` 成 **1 份** ego 点云；**模型侧无 per-lidar 概念** |
| 参考相机 ego | `CAM_FRONT_LONGFOCUS`（`ToEgo` 与 `T_global` 都基于它） |

### D.2 点云与栅格（三件套必须同改）

| 项 | 值 | 闭合性 |
|---|---|---|
| `voxel_size` | `[0.15, 0.15, 0.2]` | — |
| `dense_shape` | `[1024, 1024, 64]` | 153.60 / 153.60 / 12.80 |
| `point_cloud_range` | `[-31.8, -76.8, -4.4, 121.79, 76.79, 8.39]` | ❌ 差 0.01m（**收窄版**） |
| **`full_point_cloud_range`** | `[-31.8, -76.8, -4.4, 121.8, 76.8, 8.4]` | ✅ **真正闭合**（view transformer 用这个） |
| `pcd_limit_range` | `[-41.8, -86.8, -10, 131.8, 86.8, 10]` | 更宽的输入限幅 |
| BEV 特征 | 256×256 @0.6m（`x=[-31.8,121.8,0.6]`、`y=[-76.8,76.8,0.6]`） | ✅ |
| occ LR | `[512,512,32]` @0.3/0.3/0.4m | ✅ |
| occ HR | `[1024,1024,128]` @0.15/0.15/0.1m | ✅ |
| 点分割预测栅格 | `voxel_size=[0.6,0.6,0.4]`、`D=32`（`height_min_size=0.2`） | 256×0.6=153.6 |
| ground/occ-top 栅格 | 0.15m BEV 列，head 布局 **`[H(y),W(x)]`**（与 occ 的 `[W(x),H(y)]` 需转置） | ⚠️ 历史坑 |

### D.3 分箱与判据常量

```
height_distribution（HR state，64 bin）  = [0.3]*10 + [0.1]*32 + [0.3]*22
height_distribution（点分割，32 层）      = [0.6]*5  + [0.2]*16 + [0.6]*11   （height_min_size=0.2）
SOLID_SEM_IDS   = (1,2,3,4,5)          # 计入占用（含 Ground=2）
FREE_SEM_IDS    = (0,6)                # 背景 + Dust ⇒ 虚体 / FREE
fb_free_sem_ids = [0,6]
OCC_COLUMN_PRIORITY = (0,3,2,4,5,6,1)  # ped>veh>wall>smalltarget>ground>dust>bg
ground 3 类映射  : top_cls==2 → GROUND(0)；cls∈{1,3..5} → NOT_GROUND(1)；否则 UNKNOWN(2)
depth_cfg        : (1.0, 100.0, 1.0)，depth_mode='sid'（对数分箱），D=99
entity_label_mapping = {0:0, 1:1, 2:1, 3:1, 4:1, 5:1, 6:0, 7:1}   # 0=虚体、1=实体
```

### D.4 类别表

| 来源 | 顺序 | 数量 |
|---|---|---|
| det（`class_names`） | truck, loader, excavator, commandcar, othervehicle, pedestrian, rider, SmallTarget, animal, semitrailerhead, semitrailerbody, humanlike_background, excavator_base | **13** |
| det（14 类 yaml） | 上式把 `SmallTarget` 拆为 `roadcone` + `rockfall`（模型 16 通道 = 14 + 2 pad） | **14** |
| 点分割粗类（`seg_label_mapping` 值域） | 1..7（+ignore 0） | **8**（cls_num=8） |
| occ 语义 | 0 Bg, 1 SmallTarget, 2 Ground, 3 Wall, 4 Veh, 5 Pedestrian, 6 Dust, 7 rider | 映射表 **8**，但 `occ_num_classes=7`（评测 7 类无 rider）⚠️ |
| 2D seg（`ORIGINAL_TO_TRAIN_ID`） | 0 sky … 18 unknown | **19** |
| lidarseg 原始细类 | 0..72（新数据 73：新增 `71=dumppile`、`72=dumppilegroup`） | **73** |

### D.5 训练超参（数据侧相关）

| 项 | 值 |
|---|---|
| `samples_per_gpu` | 主配置 **2**（注释：HR 1024 显存大）；V5 四件套 12/8/4/4 |
| `workers_per_gpu` | 8 |
| `max_epochs` | 12 |
| 优化器 | AdamW `lr=4e-4`、`wd=0.01`；`grad_clip max_norm=20`；cyclic `target_ratio=(10,1e-4)`、`step_ratio_up=0.4` |
| `find_unused_parameters` | True |
| dataloader | `pin_memory=True`、`persistent_workers=True` |
| 训练钩子 | `MEGVIIEMAHook(init_updates=10560)`、`SyncbnControlHook(syncbn_start_epoch=2)` |
| `workflow` | `[("train",1)]` ⇒ **训练期无 val**（`tools/train.py:315`） |
| fp16 | 配置中被注释（注释即"崩溃"）⇒ 整体 fp32 |

---

## 附录 E 数据缺陷 × 修复提交 × 证据文件

| # | 缺陷 | 规模 | 修复手段 | 提交 | 证据文件 |
|---|---|---|---|---|---|
| 1 | LR `lidar_mask_fine` 为空 `(0,3)` | 22 pkl / 706,821 帧（39%） | 同 token HR `lidar_mask` 降采样兜底（xy 2:1 any / z 4:1 any，ground 命中 99.2%） | `99bf85d` | `docs/lr_mask缺失审计_反馈数据生产方.md` |
| 2 | LR 完全未绑（无 `occ_path`） | 8 pkl / 76,662 帧 | loader 置 `occ_scale=0`，occ loss 零梯度跳过 ⇒ 需 rebind 或剔除 | — | 同上 |
| 3 | **LR + HR 双缺** | 8 pkl / 76,662 帧 | 从训练集剔除 | — | `docs/不可用数据收集清单_LR_HR双缺.md` |
| 4 | HR 部分帧未绑 | 15 pkl / 7,634 帧 | rebind `occ_path_hr`（**不跑 backfill**，只补缺、dry-run 优先） | `86fe72a` / `8947229` | `docs/D类HR绑定补跑_生产执行说明.md` |
| 5 | HR 路径重映射配置漂移 | 配置写旧目录（0 帧在用） | 需同步为 `occ_gt_smallrange_15` | — | `docs/HR occ_path_hr 全帧审计`（`667f5b5`） |
| 6 | **seg id=72 越界崩溃** | 新数据 73 类 | mapping 补 `72:3` + `EQPointSegClassMapping` clip 防护 | — | `docs/fix_note_seg_id72_and_loss_diag.md` |
| 7 | HR `labels.npz` 解析必失败 | — | `load_labels_npz` 三返回值解开为 2 的修复；**改为解析失败只告警、永不删源** | `fbf9ac4` / `067fdf2` | — |
| 8 | HR state 学"LR 放大拷贝" | 监督造假 | 删 `F.interpolate` fallback，改走 0.1m 真判据 | `10c04fc` | `docs/occ_state_ground_migration_diff.md:20` |
| 9 | ground 静默整批降级 | 任一帧无 HR → 全批退点投票中位数 | 改**逐帧门控**（有 HR 走列顶、无 HR 该帧 coltop 兜底） | `10c04fc` | 同上 `:23` |
| 10 | **fine-binary loss 恒 0** | v2 起 iter80 恒 `0.0000` | v3 射线自算 → **v4 直读 HR `labels.npz`**（默认） | `13b5365` / `10c04fc` | `docs/loss_fine_binary_zero_diagnosis.md`（99.8% 观测单元被占用） |
| 11 | **环形伪影（ring artifact）** | 同心环 + 放射 spoke | ⚠️ **根因在上游生成器**（`get_mask.py::_process_visible_voxels_numba`：固定 100 采样 + round + 50% 丢射线）；E2E 侧只能缓解（3–5px 膨胀无效） | — | `docs/occ_state_ring_artifact_diagnosis.md`（ringiness 1.080 → 0.448） |
| 12 | occ 双丢导致训练卡死 | 长训中断 | 新增 `occ_supervision_lost` 哨兵（保留样本、置零 occ loss）+ 监控脚本 | `0dd095d` | `docs/occ_loss_zero_gate_0908.diff`、`docs/mon_occgate.sh` |
| 13 | 4 份 smalltest pkl 无 HR | 无法验证 v4 | 全换为带 `occ_path_hr` 的 pkl | — | `docs/fine_binary_v3_raycast_design.md:110-112` |
| 14 | mmdet 把 `ann_file` list 判为 ConcatDataset | 启动即 `TypeError` | 新增 `pkl_list` 参数绕开 | `412fda2` | 提交信息内含报错链 |
| 15 | `occ_type`/dataset 里 `self.occ_size` 未赋值 | 潜在运行期崩溃（5 个文件） | **未修**（仍在使用，同行还用废弃 `np.float`） | — | 见 §14 风险表 |
| 16 | 活 `pdb.set_trace()` 断点 | 触发即挂住 dataloader worker | **未修** | — | `loading.py:4557, 4814` |
| 17 | `CameraVisibleFilterMamba.__repr__` 必崩 | 打印 pipeline 即 AttributeError | **未修** | — | `transform.py:3631` vs `:3672` |
| 18 | `gt_depth` 是哑值 | `torch.zeros((4,1,1))` | **未修**（同文件有真实现未被调用） | — | `loading.py:4937` vs `:4915` |
| 19 | 硬编码栅格 `(672,672,32)`（5 个 dataset） | 与 V5 occ `[512,512,32]` 不匹配 | **未修** | — | `..._mamba.py:1569` 等 |
| 20 | OccTop 静默丢样本（`return None`） | 取决于 HR 覆盖率 | **未修**（建议加计数器） | — | `loading_optimized_HR.py:1935-1936` |

---

## 附录 F 全文结论速览（24 条）

**关于数据管线本质**

1. 训练 pkl 已被压成**全 keyframe**（`key=1, sweeps=[]`），时序上下文**完全由模型侧 BEV buffer 提供**，数据侧只负责"帧序连续 + 落对槽位"。
2. `idx`（场景 id）是**数据侧与模型侧时序语义的唯一契约**：scene 切分、geo 软窗口、drop 注入、模型 `reset_sign` 四处都依赖它。
3. 多 pkl 配比靠 `(path, repeat)`：`repeat≥1` 整份复制、`0<repeat<1` 确定性抽样、`≤0` 跳过；34 条源在 ×0.5 ~ ×5 之间配比，**训练集是跨 3 个目录树拼起来的**。

**关于采样（最易误判的一章）**

4. **builder 是 elif 链**：`group_slot_streaming_sampler`（`:121`）抢在 `group_opt_sampler`（`:130`）之前 ⇒ 主配置两个都开但**只有 OptV2 生效**。
5. `num_slots == samples_per_gpu`；**slot round-robin + slot-tail hold** 保证"同一 batch 列跨 iteration 时序连续"，batch 内不同行可能属于不同 scene。
6. `num_samples = ceil(N/卡数/spg)×spg`；CBGS 下用 `N'` 每 epoch 重算，**epoch 长度 ≈ 1.75×N**。
7. pad **不用 index 0**（会触发 cusolver 错误），而是"复用末 scene 末帧 + 复用同一份 IDA/BDA" —— **时序 bug 的修复形态藏在 padding 细节里**。
8. `placeholder_rounds > 0` 时会用 **idx 0 垫位**（rank0 warning）⇒ 是潜在噪声源，需监控至 0。

**关于均衡**

9. CBGS 的 **λ 是反解出来的**（`length_factor × N_orig / n_prime_base`），不是硬编码 ⇒ 改 `length_factor` 线性控制 epoch 长度，且 `seed+epoch` 保证可复现。
10. CBGS 复制**整条 scene**（保时序），region-balance 复制**单帧**（破时序）⇒ 两者**互斥且有断言**。
11. CBGS 用 **13 类** `clscfg.det_mapping`；14 类 ROI 配置因 `roadcone/rockfall` 进不了桶而**未开 CBGS**。

**关于增强与 drop**

12. 实跑增强只有 **IDA**；**BDA 恒等（等于关闭）**；`PhotoMetricDistortion`/`BBoxRotation`/`RCF`/`CamExtrinsicNoise`/`CrossModalMask`/`DropNearObjectPoints` **全部注释关闭**（实现完整、可一键开）。
13. **scene 级 drop = dataset 建表（每 epoch 重建）+ 同 scene 全帧共用 + pipeline 消费 + ToEgo 执行**；`drop_lidar_mask` 有 `None`（待定）与 **空集（全保留）** 之分，必须显式判 `is not None`。
14. "至少留一个相机"保护在**场景级路径**由 dataset 侧 `ensure_one_camera=True` 完成；**逐帧回退分支**依赖 operator 自身默认 `False` ⇒ 回退路径可能 **7 路相机全黑且不报错**。
15. drop 概率**三次下调**（`183de3d` / `7625b58` / `92f4c1c` / `fdbc658`）：现状是**图像不丢、整帧丢关闭、只保部分丢雷达 0.3**，与模块默认 `P_IMG=P_LIDAR=0.3` 已不同。

**关于标签质量（决定上限）**

16. LR `lidar_mask_fine` **39% 帧为空**（706,821 帧）、LR+HR **双缺 76,662 帧**、合计受影响 **84,296 帧**。
17. 兜底链：HR `lidar_mask` 降采样补 LR（**ground 命中 99.2%**）；HR 缺失 → LR 降采样；ground 无 HR → 多帧点云 coltop；fine-binary v4 → v3 → v2。
18. HR 绑定 **95.22%** 指向 `occ_gt_smallrange_15`，旧目录 **0 帧**；但配置 `occ_gt_root_hr` **仍写旧目录** ⇒ 漂移。
19. **HR 语义本身稀疏**：wall 75% / Ground 23% ⇒ 可见地面约 **85% 未标注** ⇒ ground 头必须靠在线多帧 fuse。
20. 缺失处置的**四种策略**：兜底 / 降级 / 哨兵（`occ_supervision_lost`，只丢梯度不丢样本）/ 剔除 —— 原则是"**不阻塞训练，但必须显式标记**"。
21. **环形伪影根因在上游 occ GT 生成器**，E2E 侧只读无法根治。

**关于评测与口径**

22. `final_score = 0.3·r0+0.2·r1+0.2·r2+0.3·r3`（主线唯一口径）；**r0–r3 有"采样器版"与"评估器版"两套区间**，r0 面积差 **2.67 倍**（3,600 vs 1,350 m²）。
23. mIoU 名义 8 类、因 `ignore_index=0` **实为 7 类**；`print_error_stats` **硬编码 5 个类名** ⇒ 类数变更时 KeyError 风险；`work_dirs_eval_summary` 的**生成脚本不在本仓**且混入上一代命名与 r4。

**关于动机（来自飞书）**

24. **scene 级 drop 与选择性 NMS 是为修复"28 vs 43"掉点而引入的**（不是先验设计）；occ-gt 降级兜底是"全量重做要一周、先训一版"的**生产节奏妥协**；时序简化与"全 keyframe"是**板端耗时驱动**。⇒ 三条隐性约束：**SECOND 特征是跨模型公共契约**、**时序首要约束是板端耗时**、**评测口径必须与训练口径成对演进**。

---

> **配套材料**：`E2E_ENET_全量分析/`（定稿 + 4 册分册 + 14 份域报告）、`E2E_ENET-hw_dev/`（仓库快照 + ONBOARD.md）。
> 本文由代码与文档证据合成，**每条结论标注 `文件:行号`**；凡无法从代码或讨论确证的，一律进入 §15「未知项」而非猜测。
