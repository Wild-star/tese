# E2E_ENET 实习经历（数据方向）· 完整版

> 用途：简历 / 面试 / 转正材料。事实全部来自《E2E_ENET 全量技术分析》文库（定稿 §10/§11/§16、补跑 R1/R2、增补篇 §2/§5、分域报告 05），每条带 `文件:行号` 锚点可复现。
> **使用说明**：§2–§4 是可以直接抄进简历的文本；§5 是面试时展开的弹药；§10 是"不要写进简历"的边界（原报告明确列为未确认项）。

---

## 1. 基本信息

| 项 | 内容 |
|---|---|
| 岗位 | 感知算法实习（数据 / 训练管线方向） |
| 项目 | E2E_ENET —— 易控智驾露天矿无人驾驶**多任务时序 BEV 感知模型** |
| 团队 | 算法-感知 · 前景感知组（代码仓库 `guanxijia/E2E_ENET`，主分支 `hw_dev_merge_zsa`） |
| 周期 | 约 2 个月（对应 2026-09-02~09-07 冲刺期及收尾，143 提交中数据侧集中落地的窗口） |
| 我负责 | **数据侧全链路**：多 pkl 场景集构建与配比 → scene 分组与时序采样 → 类别/区域均衡 → scene 级传感器 drop 与增强 → 标签质量治理与训练-评测口径对齐 |
| 技术栈 | PyTorch · mmdetection3d / mmcv · 多机多卡（火山 MLP，H20）· ONNX/ATC → 华为 MDC610 |
| 规模量级 | 核心模型文件 7142 行、采样器 1549 行、pipeline 算子 20 个、训练集 34 条 pkl（跨 3 个仓库目录） |

---

## 2. 一段式（简历主稿，约 200 字）

> **感知算法实习 · 多任务时序 BEV 感知模型数据管线与采样体系**（2 个月）
> 负责露天矿无人驾驶多任务感知模型 E2E_ENET 的**数据侧全链路建设**：①设计/落地多 pkl 场景集配比机制 `(path, repeat)`（整份复制 + 小数部分确定性抽样，保证跨 epoch、跨机器可复现），对 34 条场景源按稀缺度完成 ×0.5 ~ ×5 配比，缓解长尾场景（破碎站、充电站、地面积水）样本不足与常规道路冗余；②维护 scene 级时序采样器：以 `idx` 切分 scene、槽位轮转保证同 scene 相邻帧落同一 batch 槽、重算 `num_samples` 并实现 pad 策略（复用末 scene 末帧 + 复用同一份增强配置，修复了早期 pad 触发 cusolver 崩溃）；③落地 **CBGS 类别均衡**（scene 级候选池、命中帧阈值、λ 由 `length_factor×N_orig/n'` 反解而非硬编码、有放回抽 scene、种子 `seed+epoch` 可复现），并处理其与 region-balance 的互斥断言；④落地 **scene 级互斥传感器 drop**（每 epoch 重建、同 scene 全帧共用一份配置、img/lidar/none 三态、逐相机掩码、保底留一相机）与 IDA 增强管线校验；⑤完成 occ 标签缺失审计与 rebind 治理（LR mask 空 39% 帧、LR+HR 双缺 76,662 帧的定位与剔除/补绑方案）。

---

## 3. 要点式简历版（推荐，5 条）

- **多 pkl 场景集与配比**：实现 `(path, repeat)` 训练集构建机制——`repeat≥1` 整份复制、`0<repeat<1` 走确定性抽样（数据集内 `np.linspace` 等距抽样 / `ann_file_list.py` 的 `md5(path)` 种子无放回抽样），`repeat≤0` 跳过；为 34 条场景源按稀缺度配比（1 ×16 条常规、3 ×7 条、5 ×3 条、2 ×2 条、0.5 ×6 条降采样），并支持跨同事/跨仓库目录路径混拼。
- **时序采样器与 epoch 预算**：基于 `idx` 做 scene 分组（`mamba_data_sequence` 分支），槽位 round-robin（`num_slots == samples_per_gpu`）+ slot-tail hold 保证同 scene 帧序连续、batch 形状固定；`num_samples = ceil(N/卡数/spg)×spg`，CBGS 开启后按均衡后总帧数 N′ 逐 epoch 重算；实现 `cycle`/`repeat_first` 两种 pad 模式并复用末 scene 末帧与同份 IDA/BDA，消除早期"pad 到 index 0 触发 cusolver 错误"。
- **类别/区域均衡**：scene 级 **CBGS**（候选池 `class_names[:11]` 剔除 `humanlike_background`/`excavator_base`、`cbgs_range_m=120m`、命中帧阈值 `min_hit=3`、每类 `n=round(λ·n_c_base)` 有放回抽 scene、上限 `max_ratio=5`、λ 由 `length_factor=1.75 × N_orig / n'` **反解**、种子 `seed+epoch`），rank0 输出逐类 scenes/ratio/n_sampled 便于调参；实现与 region-balance 的**互斥断言**（两者均改写 epoch 长度与索引分布，叠加会污染口径）。
- **scene 级传感器 drop 与增强**：每 epoch 用 `build_scene_drop_table` 重建 drop 表（`P_IMG=P_LIDAR=0.3`、`drop_all_lidar=0.3`），同 scene 全帧共用一份配置，支持 `img/lidar/none` 三态互斥、逐相机 mask、`ensure_one_camera=True` 保底；`drop_lidar_mask=None`（交 ToEgo 决定）与"空集=全保留"语义区分，并向 sweeps 帧复用同一 mask 保时序一致；核验 IDA（resize jitter `(-0.06,0.11)` + 随机 crop_w）为唯一实跑增强，识别 BDA/PMD/CrossModal/CamNoise 等 6 项"写了但恒等或未启用"。
- **标签治理与口径对齐**：审计出 LR `lidar_mask_fine` 空 22 pkl/706,821 帧（39%）、LR 完全未绑 8 pkl、HR 部分未绑 15 pkl/7,634 帧、LR+HR 双缺 8 pkl/76,662 帧；验证代码侧"HR mask 降采样兜底 LR"路径（1024²×128→512²×32，xy 2:1 / z 4:1 any，ground 命中 99.2%）；推进 HR `occ_path_hr` rebind（只补缺、dry-run 优先），并同步训练/评测口径以支撑"28 vs 43"掉点归因。

---

## 4. 英文版（简历用，Short）

> **Perception Algorithm Intern — Data Pipeline & Sampling System** (2 months)
> Owned the data pipeline of a multi-task temporal BEV perception model for autonomous haulage in open-pit mines. Built and tuned the multi-pkl training-set composition mechanism `(path, repeat)` (full duplication + deterministic subsampling, fully reproducible per epoch), balancing 34 scene sources with ×0.5–×5 weights to upweight long-tail scenes (crusher station, charging station, flooded ground). Maintained the scene-level temporal sampler: scene split by `idx`, slot round-robin with slot-tail hold to keep intra-scene frame order and fixed batch shape, `num_samples` recomputation and pad strategy (reuse of last scene's last frame + shared IDA/BDA, fixing an early cusolver crash triggered by padding to index 0). Implemented scene-level CBGS class balancing (per-class candidate pool, hit-frame threshold, λ **solved** from `length_factor×N_orig/n'`, replacement sampling, seed = `seed+epoch`) with a mutual-exclusion assertion against region-balance. Implemented epoch-wise scene-level exclusive sensor drop (`img/lidar/none`, per-camera mask, keep-at-least-one-camera) and verified the IDA augmentation path. Audited OCC label coverage (39% of frames with empty LR mask; 76,662 frames missing both LR and HR) and drove the HR rebind / frame-pruning remediation.

---

## 5. 完整工作内容（六大模块）

### 模块 A · 多 pkl 场景集构建与配比

**目标**：矿山矿区场景分布极不均匀——常规道路量大且冗余，破碎站/充电站/地面积水等固定作业点稀少。需要一套**可复现、可调、可跨仓库拼装**的场景集配比机制。

**做法与实现**

| 机制 | 细节 | 锚点 |
|---|---|---|
| 入口形态 | `load_annotations` 四条分支：`pkl_list`（显式多 pkl，主配置走这条）> `ann_file`（list/tuple，元素为路径或 `(路径, 复制个数)`）> `use_pkl_list`（目录扫描）> 单文件；主配置用占位 `ann_file=''` + `pkl_list=train_pkl_list` **绕开 mmdet 的 ConcatDataset 分支** | `eq_nuscenes_temporal_multitask_mamba.py:786-817` |
| `repeat ≥ 1` | 整份复制 `round(repeat)` 份 | `_load_ann_entry_infos:760-784` |
| `0 < repeat < 1` | 确定性抽样保留 `round(n×repeat)` 帧（数据集内实现为 `np.unique(np.linspace(0,n-1,keep_n).round())` 等距抽样） | 同上 |
| `repeat ≤ 0` | 跳过该 pkl，不报错 | 同上 |
| 另一套实现 | `eacon_utils/ann_file_list.py:21-47 expand_infos_by_repeat`：分片用 `md5(pkl 路径)` 作种子的 `RandomState` 无放回抽样（**与数据集内 np.linspace 实现不同，当前未被 `load_annotations` 调用**） | `ann_file_list.py:8-18, 21-47` |
| 抽帧顺序 | 每个 pkl **先按 `load_interval` 抽帧，再复制**；`sort_datasets=False` 时不按 timestamp 重排 | `:773`, `:194`, `:809-812` |

**生产实际配比（34 条 `anno_root` 实测解析）**

| repeat | 条数 | 用途推断 |
|---|---|---|
| `1`（默认 5 + 显式 11） | 16 | 常规场景 |
| `3` | 7 | 稀缺场景升采样（ground_smoke 等） |
| `0.5` | 6 | 过量常规道路场景降采样 |
| `2` | 2 | 轻度升采样 |
| `5` | 3 | 强升采样（`posuizhan` 破碎站、`Chargingstation` 充电站） |

**路径来源**：`./data/...` 22 条（本仓内）+ `/e-vepfs/yangshujie/BEVDet_dev2-1/data/...`、`/e-vepfs/hongwei/project/Enet_hw/data/...` 12 条（跨同事机器、跨仓库目录）→ 训练集是**多人多仓各自产出的 pkl 拼起来的**。

**产出**：一套"数据配比旋钮"，用 `repeat` 同时覆盖升采样与降采样；场景类型标签（`ground_smoke` / `Chargingstation` / `posuizhan` / `kuanti` / `nte240`）成为配比依据。

---

### 模块 B · 时序采样器与 epoch 预算

**目标**：时序模型要求"同一条 batch 槽位在相邻 iteration 拿到同一 scene 的相邻帧"。数据集侧已把 pkl 压成 `key=1, sweeps=[]` 的纯关键帧形态，**时序上下文完全由模型 buffer 提供**，因此采样器成了时序连续性的唯一保障。

**做法与实现**

| 机制 | 细节 | 锚点 |
|---|---|---|
| scene 切分三分支 | `clip_sign`（需 past/future 帧）✗ ｜ **`mamba_data_sequence`（按 `info['idx']` 变化）✓ 主配置走这条** ｜ 默认（`sweeps` 为空）✗ | `_set_sequence_group_flag:432-499` |
| 为什么走 idx 分支 | 主配置 `filter_past_frame_num=0 / filter_future_frame_num=0` ⇒ `clip_sign=False` ⇒ 不执行 `_clip_data_infos`，`data_indices` 也不生效，scene 边界**完全由 `idx` 决定** | `:409`, `:376-405` |
| 采样器选择 | builder 是 **elif 链**：`group_slot_streaming_sampler` 优先于 `group_opt_sampler`；主配置两者都写 True ⇒ **实际生效 `DistributedGroupSlotStreamingOptV2Sampler`，`DistributedGroupOptSampler` 永不触发** | `builder.py:121-133`；`multitask_sampler.py:1101` |
| slot round-robin | `num_slots == samples_per_gpu`；每 slot 认领一条 scene 时间序、逐帧推进，scene 结束后立刻认领下一条；轮末用 `slot_tail`（该 slot 上一帧）回填 → **slot-tail hold 保证 batch 形状固定** | `_slot_round_robin_emit:1340-1429` |
| 时序前提 | 同一 slot 在相邻两轮吐出的就是同 scene 相邻帧 ⇒ 同一"列"跨 iteration 时序连续 | 同上 |
| num_samples（基础） | `ceil(len(dataset)/num_replicas/samples_per_gpu)*samples_per_gpu`；`total_size = num_samples × num_replicas` | `:1151-1156` |
| num_samples（CBGS） | 每 epoch 用均衡后总帧数重算：`ceil(n_prime/num_replicas/spg)*spg`，并打印 `factor ~ N'/len(dataset)` | `_refresh_cbgs_budget:1322-1337` |
| pad 策略 | OptV2 用 `"cycle"`（默认）/`"repeat_first"`；`_pad_stream_to_num_samples` **优先复用最后一个 scene 的最后一帧**，且 `keep_consistent_seq_aug=True` 时**复用同一份 IDA/BDA/occ_id** | `:1432-1487`, `:621`, `:649` |
| pad 修复的历史坑 | 早期"槽位不足时 pad 到 index 0"会触发 cusolver 错误 → 现形态为"复用末 scene 末帧 + 同份增强" | 增补篇 §2.4 |
| 边界告警 | 若 `slot_tail` 也为 None，本轮记 `placeholder_rounds` 并用 **idx 0** 垫位 + rank0 warning（提示 `len(my_scenes) >= num_slots`）——潜在噪声源 | `:1340-1429` |
| 异常样本容错 | pipeline 抛异常 → idx 记入 `error_idx` + 打印 sample_idx/scene_idx/img/past/future 诊断 → `_rand_another(idx)` 从同 scene 池（池被 error_idx 过滤、空则全库）换样本重试，该样本本轮不再被采到 | `__getitem__:683-744`, `_rand_another:613-621` |
| 时序一致增强 | `keep_consistent_seq_aug=True` 时按 slot 采样函数把元素包成 `dict(idx, ida_config, bda_config, occ_id)` ⇒ **同一 slot/occupancy 共享一套增强** | `:1356-1403`；`config:1478` |

**产出**：一个既能保时序连续、又能在 scene 数量不足时不破形状、且异常样本可自愈的流式采样器。

---

### 模块 C · 类别与区域均衡

**三套机制解决三个不同问题，且两两互斥**：

| 机制 | 解决的问题 | 关键实现 |
|---|---|---|
| `DistributedRegionClassBalancedSampler`（region sampler） | 按「类 × 区域」补**实例**样本 | 目标量来自 `target_region_class_counts[c,r]`（主配置 `cls_list`：truck 100000×4、animal 10000×4…），`dataset.region_num_info [N,C,4]`；不足则按含该 (c,r) 的帧的实例数概率重采样至达标；epoch 长度取 `max(balanced_len, N)` |
| **`CBGS`（scene 级类别均衡）** | 按类**复制整个 scene** 拉长 epoch（≈1.75×） | 见下 |
| `DistributedGroupOptSampler` | scene 内时序不乱序 + 短 scene 贪心合并减少 padding | `target_batch_size = spg × num_replicas × scene_merge_factor`，把小于目标 1.5 倍的 scene 合并成组，打印 `estimated_data_saving` |

**CBGS 完整算法（`_balance_scenes_cbgs:1253-1322`）**

1. **池类**：`cbgs_pool_classes = class_names[:11]`，**刻意剔除** `humanlike_background` / `excavator_base`；统计范围 `cbgs_range_m = 120m`。
2. **命中统计**：仅当 scene 对某类命中帧数 `n_hit ≥ cbgs_min_hit_frames(=3)` 时进入该类候选池 → `class_scene_idxs[c]`。
3. **基数**：`duplicated = Σ_c |class_scene_idxs[c]|`；`n_cls =` 非空类数；`n_c_base = duplicated / n_cls`。
4. **λ 反解（关键）**：
   ```python
   n_prime_base = sum(n_c_base * _mean_len(class_scene_idxs[c]) for c in nonempty)
   lam = (length_factor * n_orig) / max(n_prime_base, 1e-6)     # length_factor 默认 1.75
   ```
   → **λ 由"目标 epoch 长度倍率 × 原始帧数"反解得出，不是硬编码**（配置注释原文：*"λ is computed, not hardcoded"*）。改 `cbgs_length_factor` 即可线性控制 epoch 长度。
5. **每类采样数**：`n = round(lam × n_c_base)`，下限 1，上限 `len(inds) × cbgs_max_ratio(=5)`。
6. **有放回抽 scene**：`rng.choice(inds, size=n, replace=True)`，把抽中 scene 的**全部帧**展平进 balanced 列表（**保时序完整**，与 region sampler 复制单帧形成对照）。
7. **可观测性**：rank0 打印 `duplicated_samples / balanced_scenes / lambda / length_factor / min_hit / max_ratio` 及**逐类 `scenes / ratio / n_sampled` 表格**（调参依据）。
8. **随机性可控**：`rng = np.random.default_rng(self.seed + epoch)` → **按 epoch 固定种子、可复现**。
9. **互斥断言**：`if self.enable_cbgs and self.enable_balance: raise ValueError("CBGS and region-class balance are mutually exclusive")`；数据集侧同样断言 `use_cbgs_scene_balance` 与 `use_region_sampler` 互斥。

**为什么必须互斥**：两者都整体改写 epoch 长度与索引分布，叠加会让"目标实例数"与"epoch 长度"两个口径互相污染；且 CBGS 复制**整个 scene**（保时序）、region sampler 复制**单帧**（破时序）。

**当前生效状态（易误判）**：主配置 `group_opt_sampler=True` + `group_slot_streaming_sampler=True` ⇒ 实际走 OptV2；`group_opt_balanced_sampler=False` ⇒ `use_region_sampler=False`；`use_cbgs_scene_balance` 主配置未设（默认 False），**CBGS 只在 `EQDetSegOccMambaWithSegV5TemporalDepth.py` 打开**。另：CBGS 用 13 类 `clscfg.det_mapping`，14 类 ROI 配置因 `roadcone/rockfall` 进不了桶而未开 CBGS。

---

### 模块 D · scene 级互斥传感器 drop 与增强管线

**设计意图**：矿山现场相机可能被泥污遮挡、雷达可能部分失效，模型必须在**单模态缺失**下仍能出结果——这是"纯视觉检测辅助头"存在的业务支点。

**两段式实现（dataset 决策 → pipeline 消费 → ToEgo 执行）**

| 阶段 | 行为 | 锚点 |
|---|---|---|
| ① 建表（dataset） | `_rebuild_scene_drop_table:353` 调 `build_scene_drop_table(scene_ids, epoch, drop_seed, cam_names, num_lidars=7, drop_lidar_only=False, ensure_one_camera=True)`；`set_epoch:371` **每个 epoch 重建一次** ⇒ 每 epoch 随机丢弃不同 scene 的相机/雷达 | `:353`, `:371`；`pipelines/scene_sensor_drop.py:4-82` |
| ② 注入 | `_prepare_train_data:623` 按 `idx` 注入 `data['scene_drop_cfg']` ⇒ **同 scene 所有帧共用同一份 drop 配置**（"scene-level"的唯一含义）；同时注入 `data['epoch']` | `:623` |
| ③ 消费（生 drop 决策） | `PrepareImageInputsMultitaskMamba:1648-1700` 优先级：**场景级表 > 逐帧随机回退 > 强制 lidar-only**；产出 `drop_sensor_type ∈ {img, lidar, none}` + `drop_mask`（逐相机）+ `drop_lidar_mask` | `loading.py:1648-1700` |
| ④ 执行（lidar） | `ToEgoMultitaskMamba:3127-3150` **只读不重采样**（保时序一致）；必须同时满足 `is_train` + `random_drop_lidar>0` + `drop_sensor_type=='lidar'` | `transform.py:3127-3150` |
| ⑤ 时序复用 | drop 后把 `drop_lidar_mask` 回写，供 sweeps 帧**复用同一 mask**（注释：*Reuse current-frame drop_lidar_mask for temporal consistency*） | `transform.py:3196` |

**参数与语义细节（易踩）**

- `P_IMG = P_LIDAR = 0.3`，`random_drop_img = 0.3`，lidar 模式含 `drop_all_lidar = 0.3`（全丢一路）。
- `drop_lidar_mask` 的**三态语义**：`None` = "交 ToEgo 自行决定"；`set`（**含空集**）= 场景级已决策；**空集是合法决策 = 全保留**，所以代码必须显式判 `is not None`。
- **"至少留一个相机"分两处互补实现**：场景级路径在 dataset 侧（`build_scene_drop_table(ensure_one_camera=True)`，`scene_sensor_drop.py:44` 的 `if ensure_one_camera and all(drop_mask.values())` 才救回）；**逐帧回退分支**受 operator 自身 `ensure_one_camera` 约束，而该参数 `__init__` 默认 `False` 且配置未覆盖 ⇒ ⚠️ **回退路径下可能 7 路相机全黑**（潜在坑，已记录）。
- 图像的实际落地方式：`get_inputs` 内对命中相机 `Image.new('RGB', size, (0,0,0))` **置黑** + 2D seg mask 置 0；物理缺失的相机走 `Eye`/`zeros` 占位并保留 slot，从而 **`len(imgs)==7` 恒成立**（形状契约）。

**增强体系（"写着但没开"多于真正生效）**

| 增强 | 参数 | 状态 |
|---|---|---|
| **IDA（图像 resize/crop）** | `resize=(-0.06, 0.11)`、长焦只加 0.5×、`crop_h=(0,0)`、`flip=False`、`rot=(0,0)`、`crop_w` 随机 | ✅ **唯一实跑的图像增强** |
| 时序一致 IDA/BDA | `keep_consistent_seq_aug=True`，同 slot/occupancy 共享一套 | ✅ 开 |
| **BDA（BEV 旋转/缩放/flip/平移）** | `rot_lim=(0,0)`、`scale_lim=(1.0,1.0)`、`flip_dx/dy_ratio=0`、`tran_lim=[0,0,0]` | ⚠️ **代码在跑但恒等（等于关闭）**；HR BDA 同样恒等 |
| `RandomCamExtrinsicNoise` | 截断高斯 rot 0.3°/max0.6°、trans 0.05m/max0.15m、prob 0.5、per-camera、时序共享 | ⛔ 注释关闭（**实现完整可一键开**，且设计正确：GT 用真外参、ViewTransformer 用噪声外参） |
| `ComplementaryCrossModalMask` | prob 0.1、ratio 0.3、`d_range=(96,224)`；只遮"仍在用"的相机 + 同步删被遮像素上的雷达点 | ⛔ 注释关闭 |
| `RandomDropNearObjectPoints` | prob 0.2、drop_ratio 1.0、30m 内、`expand_m=1.0`；仅部分丢雷达时触发 | ⛔ 注释关闭 |
| `PhotoMetricDistortion` / `BBoxRotation` / `EQResizeCropFlipImage` | — | ⛔ 注释关闭 |
| `data_aug_conf.rand_flip/rot_lim` | `rand_flip=True, rot_lim=(-5.4,5.4)` | ⚠️ **实际未生效**：唯一消费方在当前 pipeline 被注释 |

**产出**：一个"设计完整（含跨模态互补缺失、标定扰动）+ 实际只开 IDA 与 scene 级 drop"的增强体系全貌，并明确指出可灰度开启的候选与开启顺序约束（如 `RandomCamExtrinsicNoise` 必须放在 `EQPointToMultiViewDepth` 之后，否则污染 depth GT）。

---

### 模块 E · 标签质量治理（occ GT 缺失审计与 rebind）

**这是全仓最"接地气"、也最影响上限的一块**——反映的是离线 occ 标注生产线与训练侧的绑定不一致。

| 问题 | 规模 | 后果 |
|---|---|---|
| **A 类**：`labels_new.npz` 在，但 `lidar_mask_fine` 为空 `(0,3)` | 22 pkl / **706,821 帧（39%）** | `loss_occ_fine ≈ 0`、`loss_lr_state` 无有效监督，白耗算力 |
| **B 类**：连 `occ_path` 都未绑 | 8 pkl / 76,662 帧 | loader 置 `occ_scale=0`，occ loss 走零梯度跳过 |
| **C 类**：正常 | 6 pkl | — |
| **HR 部分帧未绑** | 15 pkl / 7,634 帧 | HR 监督缺失 |
| **LR + HR 双缺** | 8 pkl / **76,662 帧** | 建议从训练集剔除 |
| 合计受影响 | **84,296 帧** | — |

**我做的治理动作**

1. **兜底路径验证**：`loading.py:3777-3808` 在 LR mask 为空时，用同 token 的 HR `labels.npz` 的 `lidar_mask` **降采样兜底**（HR 1024²×128 → LR 512²×32，xy 2:1 any、z 4:1 any），实测 ground 命中 **99.2%**；B 类无 HR 可用，兜底无效 ⇒ 必须 rebind 或剔除。
2. **HR 路径重映射链路核对**：`_resolve_occ_gt_path_hr:997-1029` 的 remap 只在数据缺 `occ_path_hr` 时生效；实测**凡有 `occ_path_hr` 的帧 100% 指向 `occ_gt_smallrange_15`（1,710,713 帧 / 95.22%）**，而旧目录 `occ_gt_smallrange_260314_hw` **0 帧在用**，但主配置 `occ_gt_root_hr` 仍写着旧目录（config:305）⇒ **配置与实际绑定已漂移**。
3. **补跑方案定型**：结论是**不需要跑 backfill 生成器**（会全跳过白跑），只需 rebind 15 pkl 的 `occ_path_hr`（约 7,634 帧），工具 `tools/rebind_hr_occ.py`（**只补缺、dry-run 优先**）。
4. **HR 语义本身的稀疏性**：HR `labels.npz` 中 wall 占 75%、Ground 仅 23%，可见地面约 **85% 未标注** ⇒ ground 头必须依赖在线多帧 fuse 兜底——这解释了 ground/geo 支线的设计必要性。
5. **兜底降级链**：HR 缺失时降级为 LR 降采样，保证训练可跑（"GT 缺失不阻塞训练"的工程取舍）。

---

### 模块 F · 口径对齐与训练/评测一致性

**背景事故「28 vs 43」**（本仓库最重要的一次质量事故）：新框架上线后指标从 43 掉到 28，最终定位为**三个叠加原因**——①解冻 SECOND backbone（破坏下游"排土位模型"依赖的特征）；②**新框架 drop 策略与 350 版本不一致**；③**评测口径未对齐**（挖机/半挂 NMS 未对齐）。修复落地提交 `c55b733`：*"挖机半挂车 nms 适配 + 根据 scene 随机 drop 传感器"* —— 其中**"根据 scene 随机 drop 传感器"正是我负责的模块 D**。

**我在口径对齐上做的事**

| 项 | 内容 |
|---|---|
| train / test pipeline 差异核对 | train **20 个算子**（含 Collect）、test **16 个**（首两算子注释、缺 PairGT/PointShuffle；`ToEgo` 开 `test_vision_only=True` 走空点云） |
| Collect keys | train **21 个 active key**（17 双引号 + 4 单引号）+ 12 个注释项；test **16 个**（OCC/vision-box 全注释） |
| 顺序即正确性的硬约束 | ①深度 GT 必须早于 `ToEgo`/传感器 drop；②类别映射必须早于名称过滤；③scene 分组必须先于采样；④`drop_lidar_mask` 必须写回供时序帧复用 |
| **采样区域 ≠ 评估区域**（重要不一致） | 采样器 r0–r3 = `(-30,30)/(-30,30)`、`(-30,50)/(-30,30)`、`(-30,80)/(-50,50)`、`(-30,120)/(-70,70)`；评估 `evaluate_difficultys` = `[-15,30,-15,15]…[-30,120,-70,70]` ⇒ **若指望 region 补样提升 r3/r4，目标区域与考核区域需先对齐** |
| 评测协议 | `final_score = 0.3·r0 + 0.2·r1 + 0.2·r2 + 0.3·r3`（BEV AP 加权，取 strict overlap 档，类内取 mean）；历史公式 `0.45/0.25/0.2/0.1` 已被注释 ⇒ **跨时期分数不可直接比较** |
| 迭代证据 | 历史最佳 `42.841 / miou 0.8866 / orient_p99 11.78°` vs 最新 `43.120 / 0.8847 / 13.30°` ⇒ 增量全来自长尾 r1/r2/r4，r0 与 mIoU 反降，orientation 退化 |
| AP 瓶颈定位 | 长尾类 `animal/rider/semitrailer*` 全程 0.00，`commandcar/truck` 已饱和（99-100）⇒ **瓶颈在长尾类与远距离区（r3/r4），而 final_score 的 0.3 权重正压在 r3 上** |

---

## 6. 量化成果汇总表（简历可直接引用）

| 维度 | 数字 |
|---|---|
| 场景集规模 | 34 条 pkl 条目，跨 3 个仓库/同事目录；配比覆盖 ×0.5 ~ ×5 |
| repeat 分布 | `1`:16 条 ｜ `3`:7 条 ｜ `0.5`:6 条 ｜ `2`:2 条 ｜ `5`:3 条 |
| 采样器规模 | 1549 行 / 7 个采样器类 / 当前主线 `OptV2` |
| epoch 预算 | `num_samples = ceil(N/卡数/spg)×spg`；CBGS 目标 epoch 长度 ≈ **1.75×N** |
| CBGS 参数 | `cbgs_range_m=120m`、`min_hit_frames=3`、`max_ratio=5`、池类 `class_names[:11]` |
| sensor drop | `P_IMG=P_LIDAR=0.3`、`drop_all_lidar=0.3`、每 epoch 重建、`ensure_one_camera=True` |
| 增强开启率 | 注释/未启用 **6 项**（CamNoise / CrossModalMask / DropNearObjPoints / PMD / BBoxRotation / RCF），实跑 **1 项**（IDA），BDA 恒等 |
| 标签治理 | 定位受影响 **84,296 帧**；A 类 39% 帧（706,821）LR mask 为空；双缺 76,662 帧；rebind 目标 ≈7,634 帧；兜底 ground 命中 **99.2%** |
| 训练/评测 | 20 vs 16 算子、21 vs 16 Collect key；`final_score = 0.3/0.2/0.2/0.3` |
| 性能观测 | H20 96GB，`spg=2`，1.66–2.26 s/iter，显存 26.4/96 GB，GPU 利用率 ~50%，数据加载非瓶颈（0.03–0.2s） |

---

## 7. 技术难点与解决（面试展开用）

**难点 1：时序连续性 vs batch 形状固定，二者天然冲突。**
scene 长度参差、且每帧必须按时间序推进，但 batch 形状必须固定（`spg` 行）。解法是"槽位绑定 scene + slot-tail hold + pad 复用末 scene 末帧"三层：槽位不足时用该 slot 上一帧回填而非 index 0，长度不足时用最后一条 scene 的最后一帧补齐，并**复用同一份 IDA/BDA 配置**避免 pad 帧引入无意义时序跳变。早期"pad 到 index 0"会触发 cusolver 错误——**时序类 bug 的修复形态往往就藏在 padding/边界的细节里**。

**难点 2：类别不均衡且必须保时序完整。**
常规做法（单帧重采样）会打断 scene 内时序。解法是 scene 级 CBGS：以"整条 scene"为最小复制单元、按类命中帧数筛候选池、并**反解 λ** 使 epoch 长度可控（1.75×）——λ 反解而非硬编码，使"目标长度"成为输入而不是猜测；再以 `seed+epoch` 固定种子保证逐 epoch 可复现、可复现地做 A/B。

**难点 3：配置与生效不一致（本仓最隐蔽的坑）。**
两处实例：①`group_opt_sampler` 与 `group_slot_streaming_sampler` 都写 True，但 builder 是 elif 链 ⇒ 只有 OptV2 生效；②`conv_mamba` 时序融合在 V5 配置里**自创建起即为注释行**，实跑三层卷积。方法论结论：**读这个仓库的配置，"写了什么"永远要再用 builder/源码验一遍"最后用了什么"**。落地动作：把"配置声明 vs 实际生效"做成核对清单，避免调参打空靶。

**难点 4：scene 级 drop 的语义边界。**
`drop_lidar_mask` 的 `None`（待定）与 `set()`（空集=全保留）语义不同，必须显式判 `is not None`；"至少留一个相机"的保护在场景级与逐帧回退两条路径上**实现位置不同**，且回退路径受默认 `False` 的开关约束 ⇒ 若漏判，回退路径可能 7 路相机全黑而**不报错**。

**难点 5：标签缺失不是模型问题，但决定模型上限。**
39% 帧 LR mask 为空、76,662 帧双缺——这些帧照样参与训练，白耗算力还可能污染 loss 统计。做法是"先审计清单、再分型处置"：能兜底的兜底（HR 降采样，ground 命中 99.2%）、能 rebind 的只补缺 rebind（dry-run 优先、不跑会全跳过的 backfill）、双缺的直接剔除。**标签治理的收益高于继续调参**。

---

## 8. 交付物清单

| 交付物 | 说明 |
|---|---|
| 多 pkl 场景集配比机制 | `(path, repeat)` 语义落地 + 34 条生产配比核定 + 跨仓库路径混拼 |
| scene 级时序采样器 | slot round-robin + slot-tail hold + pad 复用策略 + 异常样本自愈（error_idx / `_rand_another`） |
| epoch 预算与 CBGS | `num_samples` 双公式 + λ 反解 + 逐类 rank0 可观测表格 + 互斥断言 |
| scene 级互斥传感器 drop | 每 epoch 重建表 + 三态互斥 + 逐相机 mask + 保底留相机 + 时序帧 mask 复用 |
| 增强体系核对表 | 逐项"是否真开"清单（IDA/BDA/6 项注释态），含开启顺序约束 |
| occ 标签审计与治理方案 | A/B/C/HR/双缺分类清单 + 兜底路径验证 + rebind 工具与方案 |
| 口径对齐要点 | 训练/评测分区不一致清单 + 21/16 key 差异 + 顺序约束 4 条 |

---

## 9. 面试追问准备（Q&A）

**Q1：`repeat=0.5` 的"一半"是怎么抽的？可复现吗？**
A：`repeat≥1` 整份复制 `round(repeat)` 份；`0<repeat<1` 走确定性抽样、保留 `round(n×repeat)` 帧。仓库里有**两套实现**：数据集内 `_load_ann_entry_infos` 用 `np.linspace` 等距抽样；`eacon_utils/ann_file_list.py` 用 `md5(pkl 路径)` 作种子的 `RandomState` 无放回抽样。两套都不依赖全局随机状态 ⇒ 同输入同结果、跨 epoch 跨机器可复现。当前 `load_annotations` 走的是数据集内那套。

**Q2：为什么采样器"两个开关都开着"却只有一个生效？**
A：`builder.py` 是 **elif 链**，`group_slot_streaming_sampler` 分支（:121）在 `group_opt_sampler`（:130）之前 ⇒ OptV2 抢先命中，`DistributedGroupOptSampler` 永不构建。这是"配置写了什么 ≠ 最后用了什么"的典型，改采样器要改 elif 顺序而不是改开关。

**Q3：CBGS 的 λ 为什么要反解？**
A：如果 λ 硬编码，加/减一个 pkl 或改 `min_hit` 都会让 epoch 长度不可预期地漂移，实验不可比。反解 `λ = length_factor × N_orig / n_prime_base` 后，`length_factor` 就是"目标 epoch 长度倍率"这个**业务可解释的旋钮**（默认 1.75×），改它线性控制长度；再配合 `seed+epoch` 固定种子，逐 epoch 可复现。

**Q4：CBGS 和 region-balance 为什么必须互斥？**
A：两者都整体改写 epoch 长度与索引分布——CBGS 改的是"帧数预算"、region 改的是"实例数目标"，叠加会互相污染口径；而且 CBGS 复制**整条 scene**（保时序），region 复制**单帧**（破时序）。所以两侧都做了硬断言。

**Q5：pad 为什么不能用 index 0？**
A：pad 到 index 0 会引入一个与当前时序上下文无关的帧，早期实测会触发 cusolver 错误；而且会让同一 slot 的时序在 pad 处跳变。现在改成"复用最后一条 scene 的最后一帧 + 复用同一份 IDA/BDA/occ_id"，既保形状又不破时序。

**Q6：sensor drop 为什么必须做在 scene 级？**
A：若逐帧随机 drop，同一 scene 相邻帧的模态会在训练中不断跳变，模型学不到"模态缺失下的时序一致性"；scene 级意味着"这个 scene 就是这种缺失模式"，跨帧一致，才能逼出真正的单模态鲁棒性。而 drop 配置每 epoch 重建，保证整个训练期各种缺失模式都被覆盖。

**Q7：`drop_lidar_mask` 为什么要有"空集=全保留"这种语义？**
A：`None` 表示"还没有场景级决策，交给 ToEgo 逐帧决定"；而"场景级已决策 = 全保留"是**合法决策**，必须能和"未决策"区分开，否则会退回逐帧随机。所以代码必须显式判 `is not None` 而不是判真假。

**Q8：MAMBA 那个说法有什么问题？**
A：配置里 `temporal_fusion_type="conv_mamba"` 在 V5 四份配置中**自创建起就是注释行**，实跑是 3 层 ConvModule；而 `ConvMamba2D` 本身也不是 SSM（docstring 写着 *"avoids any MatMul/Gemm/Attention"*），引入它的提交 `867f20a` **同一笔就带着 ONNX 导出** ⇒ 这是**板端算子规避**，从第一天起就是部署驱动。对外表述不应说"用了 Mamba 做时序"。

**Q9：怎么证明你的 drop 改动有效？**
A：可复现证据链：①事故复盘里"drop 策略与 350 不一致"是三大原因之一；②修复提交 `c55b733`（*挖机半挂车 nms 适配 + 根据 scene 随机 drop 传感器*）落地；③drop 表每 epoch 重建、`seed` 可配 ⇒ 可做"开/关 drop"的可比实验；④配合 rank0 打印的逐类采样表与 `error_idx`/`placeholder_rounds` 告警做数据侧监控。

**Q10：为什么训练没有 val 指标？**
A：`tools/train.py:315` 仅在 `len(cfg.workflow)==2` 时构建 val，而 V5 四份配置均为 `workflow=[("train",1)]` ⇒ 训练期无验证，只能靠 `test_multi_v*.sh` 事后逐 epoch 评测。这也是"选点指标口径必须固定"（公式版本 + 区间版本）的原因。

**Q11：采样区域和评估区域不一致，影响是什么？**
A：采样器用的 r0–r3 与评估配置 `evaluate_difficultys` **数值不同**（如 r0 是 `(-30,30)/(-30,30)` vs `[-15,30,-15,15]`）。若指望 region 补样提升 r3/r4，补样目标区与考核区必须先对齐，否则"补了但没考、考了但没补"。

**Q12：如果重来一次，你会先做什么？**
A：先做标签治理。39% 帧 LR mask 为空 + 双缺 76,662 帧，意味着相当比例的算力和 loss 统计是浪费的，且这直接卡住模型上限——**治理的边际收益高于继续调模型**。

---

## 10. 诚实边界（这些**不要**写进简历）

原报告明确列为"未解决/未确认"的项，简历与面试中都应表述为"我审计到/我上报/建议确认"，而非"我解决了"：

1. pkl 内 info 的**真实字段全集**未实测（本地无 `data/`，字段清单来自代码实证）。
2. `test_vision_only=True` 是**设计还是遗留**——只能证明"何时生效"，不能证明"是否有意"（训练融合、评测纯视觉，口径不一致）。
3. 350/330 与本框架的**对齐清单是否成文**——无文档，需问作者。
4. `ann_file_list.py` 的 `repeat` 语义与生产列表**未做交叉验证**（两套实现并存）。
5. 文件名尾串 `cleaned_rmpass_slow0.9_clean0.2_rad20m_step1_ts1e-06` 各字段精确语义（生产脚本不在本仓）。
6. `group_opt_sampler=True` 是**有意保留还是复制残留**——需作者确认。
7. `placeholder_rounds > 0` 时 idx 0 垫位带来的噪声量——需实测采集该 warning。
8. **occ 7 类通道顺序**（映射表 8 类含 rider，但 `occ_num_classes=7`）静态读不出。
9. `work_dirs_eval_summary` 的生成脚本与统计的 `work_dirs` **属上一代命名**，与本仓 V5 是否同批实验未确认。
10. `tools/rebind_hr_occ.py` 的实际执行结果（补跑是否已完成 7,634 帧）——需看落盘记录。

> 另：MAMBA 名不副实、occ ONNX 为随机权重导出、导出端到端对齐未做等，都是**团队既有状态**，宜表述为"我发现并上报/推动对齐"。

---

## 11. 附录 · 文件:行号索引与复现命令

### 11.1 关键锚点

| 功能 | 位置 |
|---|---|
| 数据集类 `EQNuScenesTemporalMultitaskMambaDataset` | `datasets/eq_nuscenes_temporal_multitask_mamba.py`（2667 行） |
| `load_annotations` / `_load_ann_list` / `get_data_info` | `:786` / `:819` / `:840` |
| `(path, repeat)` 展开 `_load_ann_entry_infos` | `:760-784` |
| `_rebuild_scene_drop_table` / `set_epoch` | `:353` / `:371` |
| R0–R3 采样分区 `_get_region_info` | `:376-405` |
| `_set_sequence_group_flag`（scene 三分支） | `:432-499` |
| `_prepare_train_data`（软窗口 + drop 注入） | `:623-681` |
| `__getitem__` 容错 / `_rand_another` | `:683-744` / `:613-621` |
| `occ_path` / `occ_path_hr` 解析与重映射 | `:993` / `_resolve_occ_gt_path_hr:997-1029` |
| 采样器家族（7 类） | `samplers/multitask_sampler.py`（1549 行）：`18 / 101 / 266 / 599 / 871 / 1101` |
| `num_samples` 基础 / CBGS 重算 | `:1151-1156` / `_refresh_cbgs_budget:1322-1337` |
| CBGS `_balance_scenes_cbgs` | `:1253-1322` |
| 互斥断言 | `:1147-1149`（采样器）/ `eq_..._mamba.py:335-337`（数据集） |
| slot round-robin | `_slot_round_robin_emit:1340-1429` |
| pad 策略 | `_pad_stream_to_num_samples:1432-1487` |
| 采样器选择 elif 链 | `datasets/builder.py:121-133`（完整链 `:105-140`） |
| 增强配置（IDA / BDA / drop / 注释态） | 主配置 `:1032-1035`（IDA）、`:275-284`（BDA 恒等）、`:1482-1486,1037-1039`（drop）、`:1101-1108`（注释态） |
| 互斥 drop 决策 | `pipelines/loading.py:1648-1700`（landing `:1802-1807`） |
| lidar drop 执行 | `pipelines/transform.py:3127-3150`（mask 复用 `:3196`，清理 `:3217-3219`） |
| 深度 GT 顺序约束 | `pipelines/loading.py:5055-5066`（docstring） |
| HR 降采样兜底 LR mask | `pipelines/loading.py:3777-3808` |
| 评测 `final_score` | `datasets/eacon_utils/eval_task.py:1286` |
| 训练期无 val | `tools/train.py:315` |

### 11.2 复现命令

```bash
cd ~/.eagent/workspace/repos/E2E_ENET_hw_dev_merge_zsa

# 行数（勿用 wc，本环境 wc 低估 3-8 倍）
python3 -c "print(open('projects/mmdet3d_plugin/datasets/samplers/multitask_sampler.py','rb').read().count(b'\n'))"

# num_samples / CBGS / pad
sed -n '1147,1160p;1253,1335p;1432,1460p' projects/mmdet3d_plugin/datasets/samplers/multitask_sampler.py
# 采样器选择（谁真正生效）
sed -n '105,140p' projects/mmdet3d_plugin/datasets/builder.py
# scene 分组 + 采样 R0-R3
sed -n '376,405p;432,470p' projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py
# scene 级 drop 表
sed -n '350,375p' projects/mmdet3d_plugin/datasets/eq_nuscenes_temporal_multitask_mamba.py
# 互斥 drop 决策
sed -n '1646,1700p' projects/mmdet3d_plugin/datasets/pipelines/loading.py
# 生产 pkl 全景（repeat 分布）
python3 - <<'EOF'
import re, collections
p='projects/configs/EaconTemporalMultiTask/TemporalModelV5/EQDetSegOccMambaWithSegV5TemporalDepth_full-data.py'
s=open(p).read(); i=s.find('anno_root = ['); j=s.find(']', i)
rows=[l.strip() for l in s[i:j].split('\n')[1:] if l.strip() and not l.strip().startswith('#')]
rep=collections.Counter(re.search(r",\s*([0-9.]+)\)", r).group(1) if re.search(r",\s*([0-9.]+)\)", r) else '1' for r in rows)
print('pkl 条目:', len(rows), 'repeat 分布:', dict(rep))
EOF
```

---

> 配套材料：`E2E_ENET_全量分析/`（定稿 + 4 册 + 14 份域报告）、`E2E_ENET-hw_dev/`（仓库快照 + ONBOARD.md）。
> 本文件仅用于个人经历整理，涉及团队内部细节请勿外发。
