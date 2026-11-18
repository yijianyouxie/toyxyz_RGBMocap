# MAMMA 搭建交接文档

更新日期：2026-11-13
机器：`H:\MyProject\toyxyz_RGBMocap`（fork `yijianyouxie/toyxyz_RGBMocap`）
交接范围：MAMMA 可选运行时的安装、验证、端到端可行性测试、素材位置与已知限制

**一句话现状**：MAMMA 已在本机装好，并在 RTX 3050 8GB 上跑通完整 6 阶段重建（官方双机位示例，剪 30 帧）。这是**运行时验收，不是视觉质量验收**。PromptHMR 仍未安装。

---

## 1. 先读这里：与既有文档的关系

| 文档 | 定位 |
| --- | --- |
| `docs/MAMMA.md` | 面向用户的输入要求、模型资产、GUI 操作与限制说明 |
| `docs/MAMMA_AGENT_SETUP.md` | 安装 / 原生编译 / 修复 / 独立构建的 runbook，锁文件为权威 |
| `docs/VALIDATION.md`、`docs/PERFORMANCE.md` | 上游测试机（RTX 5090 32GB）的验证与性能记录 |
| `docs/交接文档_环境与交付.md` | 2026-11-04 的全环境交接（ExMR/GVHMR/FlowHMR、BIP 交付、离线部署） |
| 本文档 | 本机 MAMMA 搭建的落地状态、实测数据、踩坑与遗留 |

**勘误（重要）**：`docs/交接文档_环境与交付.md:195` 及其第 9 节待办、第 18 节确认项写「MAMMA / PromptHMR 未安装」，是 2026-11-04 的快照，现已过时。MAMMA 于 2026-11-12 装好并跑通；**PromptHMR 仍未安装**。该文档其余内容（单视频模型、BIP 交付、离线部署、Git 更新）不受影响。

---

## 2. 环境清单

| 项目 | 值 |
| --- | --- |
| GPU | NVIDIA GeForce RTX 3050 8GB，compute capability 8.6（sm_86），驱动 610.62 |
| 内存 | 32 GB。ComfyUI 常驻占 6–7 GB，跑 MAMMA 前建议关闭，否则易触发内存不足 |
| 编译器 | Visual Studio 2022 Build Tools 17.14.45（Desktop development with C++、x64 编译器、Windows SDK） |
| CUDA Toolkit | 12.8（nvcc 12.8）。`CUDA_PATH_V12_8` 指向 v12.8；`CUDA_PATH`/`CUDA_HOME` 默认回退 v11.8，两者并存，驱动未改动 |
| 主运行时 | `runtime/python.exe` = Python 3.10（GUI、prepare/publish、运动校正） |
| MAMMA 运行时 | `runtime_mamma/9870e446087708fdd6c8-1bad37f3/python.exe` = Python 3.11.17 + torch 2.7.1+cu128、torchvision 0.22.1+cu128、numpy 1.26.4、scipy 1.17.1、smplx 0.1.28、timm 1.0.30 |
| 工具 | `tools/bin/ffmpeg.exe`、`ffprobe.exe`（FFmpeg 7.1.1）；Blender 4.5 在 `runtime_character` |

前置的 VS2022 / CUDA 12.8 由用户在自己终端安装完成。基础安装 `install.cmd`（ExMR/GVHMR/FlowHMR）先行，MAMMA 是**独立可选**运行时，`update.cmd` 不安装也不维护它。

---

## 3. 搭建过程与关键决策

时间线：

- 2026-11-02 基础 `install.cmd` 完成；2026-11-03 / 11-09 补齐单视频模型与 PEAR 资产。
- 2026-11-12 运行 `Setup_MAMMA.cmd` → 生成 version 3 managed 运行时，本机编译 SAM 2 / SDF 原生模块，通过 CUDA kernel 校验；10/10 模型资产 ready；随后完成端到端可行性测试。

关键决策与原因：

1. **独立 Python 3.11 环境，不合并其它模型运行时**。上游 `installer/mamma-runtime-lock.json` 锁定全部依赖版本；`AGENTS.md` 也要求保留分离的固定运行时。
2. **原生模块按本机 GPU 架构（sm_86）现场编译**，不分发预编译二进制。MAMMA / pytorch_sdf 的许可条款禁止普通重分发，且 CUDA kernel 与 GPU 架构绑定。
3. **资产用国内镜像预填缓存**，setup 全程离线完成（本机直连 HuggingFace / Google Drive 基本不可用，见 `交接文档_环境与交付.md:207`）。
4. **可行性测试放在独立私有项目**，未触碰已有的 9 个项目，未改动其它模型运行时。

---

## 4. 运行时配置与资产清单

`.setup/mamma-runtime.json` 当前关键字段（均为本机绝对路径）：

| 字段 | 值 |
| --- | --- |
| `version` | `3`（managed 配置；不是 version 2 的独立外部配置） |
| `managed_id` | `9870e446087708fdd6c8a664d1e703a2f1d4209122a20e20de14976288238af6` |
| `compute_capability` | `[8, 6]` |
| `license_reviewed` | `true` |
| `python` / `engine` | 均在 `runtime_mamma/9870e446087708fdd6c8-1bad37f3/` 下 |
| `packages` | torch 2.7.1+cu128 等 6 个锁定版本 |

**目录布局易踩坑**：`python.exe` 在 generation 子目录 `runtime_mamma/9870e446087708fdd6c8-1bad37f3/`，**不在** `runtime_mamma/` 根目录。同目录的 `ready.json` 记录校验结果。

模型资产 10/10，全部有 `.receipt.json`：

| 资产 | 位置 | 状态 |
| --- | --- | --- |
| MAMMA checkpoint | `models/mamma/mamma_mask_full_cvpr.ckpt` | ready |
| 表面 landmarks | `models/mamma/verts_512.pkl` | ready |
| locked-head SMPL-X（Neutral / Male / Female） | `models/mamma/smplx/SMPLX_*.npz` | ready |
| SAM 2.1 Hiera Large | `models/mamma/sam2.1_hiera_large.pt` | ready |
| YOLO12x | `models/mamma/yolo12x.pt` | ready |
| OpenCLIP ViT-B/32 | `models/mamma/open_clip_model.safetensors` | ready |
| VGGT-Omega 512（与 FlowHMR 共用） | `models/flowhmr/vggt_omega_1b_512.pt` | ready |
| GeoCalib（与 PEAR 共用） | `models/pear/geocalib-pinhole.tar` | ready |

自动相机模式需要 VGGT-Omega + GeoCalib；手动相机数据可不需要 VGGT。

---

## 5. 架构要点（最容易踩坑）

### 5.1 worker 双解释器

`mocap/paths.py:19` 的 `worker_command()` 把 `mamma_prepare` 和 `mamma_publish` **排除在 3.11 之外**，让它们走基础 runtime；中间四个 stage 走 MAMMA 的 3.11：

| Stage | 解释器 | 启动路径 |
| --- | --- | --- |
| `mamma_prepare` | `runtime/python.exe`（3.10） | `worker_boot.py` → `mocap/worker_progress.py:48` → `mamma_pipeline.main()` |
| `mamma_masks` / `mamma_landmarks` / `mamma_camera` / `mamma_fit` | `runtime_mamma/.../python.exe`（3.11） | `mamma_worker_boot.py` → `mamma_pipeline.main()` |
| `mamma_publish` | `runtime/python.exe`（3.10） | 同 prepare |

**原因**：`mocap/correction.py:42` 加载的 `_motion_correction*.pyd` 只有 cp310 版本，publish 阶段的运动校正必须在 Python 3.10 运行。

**典型症状**：若把 6 个 stage 全部用 3.11 驱动，前 5 个正常、只有 `mamma_publish` 报 `DLL load failed: _motion_correction`。这是驱动方式选错解释器，**不是 app 缺陷**；用 3.10 基础 runtime 重跑 publish 即通过。

**CLI 驱动注意**：必须设 `RGB_MOCAP_MANAGED=1`（GUI 会自动设），否则 `runtime_registry.command()` 会去找不存在的开发 venv。

### 5.2 六个 STAGES

`mocap/mamma_pipeline.py:21` 定义严格顺序：

```
prepare → masks → landmarks → camera → fit → publish
```

| Stage | 做什么 | 日志特征 |
| --- | --- | --- |
| `mamma_prepare` | 所有相机按**同一时间轴**裁剪、重采样 30fps、缩到 ≤1920×1080 | `Prepare synchronized camera A001` / `B001` |
| `mamma_masks` | 每相机 YOLO 检人 + SAM2 双向传播分割；用第一个相机初始化身份锚点 | `mask` |
| `mamma_landmarks` | MammaNet 基于 mask ROI 预测 2D 关键点 | — |
| `mamma_camera` | **逐相机** VGGT 估位姿 + GeoCalib 重力标定 | `camera A001` → `camera B001`（按相机名依次出现） |
| `mamma_fit` | 联合多相机 mask/landmarks/camera 拟合 SMPL-X 3D 参数 | `smplx_params_body_id-*.npz`、`complete.json` |
| `mamma_publish` | 运动校正、导入项目、生成 actor/骨骼/BVH/mesh/rig、标记 `mamma_ready` | — |

### 5.3 输入硬约束

- ≥2 路**同一表演**、同步起点、固定机位、视角有重叠的视频；不是"把两个不相干视频凑一起"。
- 共用一条 30fps 时间轴，4–1800 公共帧，≤8 人；裁剪对所有相机一起生效。
- 文件名短、互不相同、无中文/空格（去扩展名即相机 ID，`mocap/mamma_pipeline.py:42`）；如 `A001.mp4` / `B001.mp4`。
- 第一个机位必须能清楚看到所有人（负责初始化身份）。
- 相机模式 `VGGT-Omega + GeoCalib (Automatic)` 时，背景需有可估重力的亮度与几何信息。

---

## 6. 验证证据（如实区分跑过与没跑过的）

### 6.1 安装层校验（实际跑过）

`.setup/logs/mamma-verify.log` 与 `runtime_mamma/.../ready.json`：

- Python 3.11.17、176 个包、**41,138 个文件**哈希校验；
- GPU `NVIDIA GeForce RTX 3050`、CUDA 12.8、`cuda_arch 8.6`；
- `sdf_error = 1.209e-08`、`sdf_gradient_error = 0.0`、`sam2_components = true`；
- 安装体积 6,642,713,171 字节（约 6.19 GiB）。

日志首行 `pytorch3d not found` 是 verifier 的可选依赖探测提示，不影响上述校验结论。

`.setup/logs/mamma-native.log`：VS2022 17.14.45 x64 / CPython 3.11.17 环境下编译 `sam-2==1.0`（56.55s）与 `pytorch-sdf==0.1.0`（2m03s）。

### 6.2 端到端可行性测试（实际跑过）

素材：官方 MPI 四机位示例 `pushing_and_lifting_from_ground` 的 `A001+B001`（公开 HTTPS GET，无需账号）：
`https://download.is.tue.mpg.de/mamma/assets/download/dataset_examples/pushing_and_lifting_from_ground/videos_light/<CAM>.mp4`

两机位 HEVC Rext / yuv444p / 3840×2160 / 30fps / 426 帧同步；剪到 **30 帧（1 秒）**；VGGT + GeoCalib 自动相机；`people=0` 自动检出 2 人。独立项目 `projects/MAMMA_feasibility_76e340d5d7d7_project`。

| Stage | 耗时 | 峰值 PyTorch 显存 | 结果 |
| --- | ---: | ---: | --- |
| `mamma_prepare` | 4.7 s | 0 | 同步裁剪成 1920×1080 / 30fps / 30 帧 |
| `mamma_masks` | 79.7 s | 2.72 GiB | YOLO 检出 2 人、SAM2 双向传播、两机位各 30 帧 mask |
| `mamma_landmarks` | 26.9 s | 0.63 GiB | MammaNet 2D 关键点 |
| `mamma_camera` | 54.0 s | **6.55 GiB** | VGGT + GeoCalib，`camera-world.json` 含 A001/B001 |
| `mamma_fit` | 281.9 s | 0.34 GiB | 2 人 SMPL-X 参数 |
| `mamma_publish` | 19.8 s | 0 | 运动校正、导出骨骼、`mamma_ready` |

6 个 stage 全部 exit 0。当前产物（本次交接时复核）：generation `f990d6e489ed72761f38ac1b` 下 `inputs.json` / `complete.json` / `camera-world.json`（键 `A001`、`B001`）/ `fit/motion/smplx_params_body_id-00.npz` 与 `-01.npz` 齐全；2 个 actor，各 45 个结果文件，原始与校正运动（BVH/mesh/rig）都在；拟合参数全部 finite。

### 6.3 未做的验证（不要对外宣称）

- **没有在 GUI 里目检预览** → 姿态、相机对齐、遮挡处理的视觉质量**未验收**；
- 没有导出 FBX / BVH / Blender 并回导验证；
- 没有测长片段、多人、4 机位、60 秒全时长（8GB 显存下）；
- 没有 clean Windows / 其它 GPU 验证（上游文档仅测 RTX 5090 32GB）；
- 没有做 retargeting 验证；PromptHMR 未安装。

---

## 7. 素材与产物位置

| 路径 | 内容 |
| --- | --- |
| `.setup/mamma-test-videos/A001..D001.mp4` | 官方 4 机位原文件（4K HEVC，30fps/426 帧），**重建用** |
| `.setup/mamma-test-videos/preview/*.mp4` | 4 个 H.264 / 1080p / yuv420p 预览副本，仅用于普通播放器看画面 |
| `.setup/clips/*.mp4` | 本次会话裁出的 5 秒副本，当前 2 个：`jilei_5s.mp4`、`情人节展示222_5s.mp4` |
| `.setup/logs/mamma-*.log` | 安装 / 编译 / 校验日志 |
| `projects/MAMMA_feasibility_76e340d5d7d7_project/` | 可行性测试的独立私有项目（含可打开的结果） |
| `.tmp_verify/` | 视角核对用的 6 张 jpg 帧，确认不再需要后可删 |

**关于 HEVC 编码**：官方 4 机位是 HEVC Rext + yuv444p + `hev1` 标签，Windows 自带播放器与很多第三方播放器都打不开，但**文件没坏**——全片 426 帧解码零错误，且 app 的 `cv2.VideoCapture(..., CAP_FFMPEG)`（`mocap/mamma_ui.py:54`）实测能正常读取。RGB MoCap 里预览/重建不受影响，无需重下。

**关于用户自己的素材**：`H:\MyProject\Video2Motion\` 下的「情人节展示」正/侧视视频（960×960、24fps、241 帧、同步）已核实为两个不同视角、参数一致，但画面高度疑似 3D 渲染 / 虚拟角色。`masks` 阶段的 YOLO+SAM2 是为真人训练的，对风格化虚拟形象可能检不出或分割错误；需先在 GUI 里跑 `masks` 看能否正确框出人物，再判断是否适合 MAMMA。中文文件名也需改成短英文名（如 `A001.mp4` / `B001.mp4`）。

**写入位置限制**：本机 agent 工具会话对 `H:\MyProject\`（项目目录之外）的写入被安全策略拦截，所以裁剪 / 转码副本只能落在项目内 `.setup/`。需要放回用户原目录时手动复制即可。

---

## 8. 如何复现 / 使用

### GUI（推荐）

1. `RGBMoCap.cmd` → **AI Motion Model** 选 **MAMMA** → **Model Manager** 应显示 Runtime Ready + 10 个资产齐备。
2. **File → Open Video...** 一次性**多选**全部机位（或一起拖进窗口）；选 MAMMA 时该对话框是多选的，分两次打开会替换掉前一个。
3. 共用时间轴裁剪，**首次建议裁到约 1 秒（30 帧）**；相机模式保持 `VGGT-Omega + GeoCalib (Automatic)`，`People` 保持 0。
4. **Reconstruct 3D**。
5. 看已跑通的结果：**File → Open Project...** → `projects/MAMMA_feasibility_76e340d5d7d7_project/project.json`。

### CLI（排障用，非官方 API）

```bat
set RGB_MOCAP_MANAGED=1
runtime\python.exe -I -X utf8 -u worker_boot.py mamma_publish --request cache\mamma-jobs\<request>.json
```

stage 序列见 `mocap/mamma_pipeline.py:21`；解释器由 `mocap/paths.py:worker_command()` 自动选择（见 5.1）。**不要**自己把全部 stage 都指到 3.11。

### 重跑 / 重建条件

| 改动 | 需要做什么 |
| --- | --- |
| 只改接触 / 修正参数 | **Apply Correction**，不重跑推理 |
| 改相机模式、人数、参考身高、裁剪范围、替换视频 | **Reconstruct 3D**（会重算） |
| 换 GPU 架构、升级依赖或原生模块 | 重跑 `Setup_MAMMA.cmd` 重新编译，并重做 CUDA kernel 校验 |

---

## 9. 已知限制与风险

1. **显存是硬瓶颈**：RTX 3050 8GB，`camera` 阶段峰值 6.55 GiB 已逼近上限。短剪辑（30 帧 / 2 机位）已验证可行；4 机位 / 长片段 / 多人很可能在 VGGT 相机阶段 OOM，未验证也不承诺。
2. 上游文档只验证过 RTX 5090 32GB；本机结论是"短剪辑运行时可行"，不是硬件下限或全时长保证。
3. **运行时验收 ≠ 视觉质量验收**（见 6.3）。
4. 虚拟角色 / 动画渲染素材对 `masks` 检测有风险（见第 7 节）。
5. **许可**：MAMMA、pytorch_sdf、locked-head SMPL-X 有各自独立的限制使用条款，不可重分发；源码与原生模块是本机编译产物，注册权重 / body data / 原生 `.pyd` / 日志 / 视频**不要提交进 git**。含绝对路径的配置与日志对外报告需脱敏。
6. **本机 agent 工具会话限制**：安全策略禁用 `reg.exe`，`vcvars64.bat` / `nvcc` 编译必须由**用户在自己的终端**完成；这只作用于 agent 的工具会话，不影响 app 本身，也不影响用户自己的 CMD/PowerShell。
7. `pytorch3d not found` 出现在 verify 日志首行，是可选依赖探测提示，不是安装失败。
8. PromptHMR 未装（C++/CUDA 工具已具备，需单独运行 `Setup_PromptHMR.cmd`）。

---

## 10. 运维红线

- 不要删除 `runtime_mamma/`、`models/mamma/`、`.setup/mamma-runtime.json`、`.setup/mamma-*.log` 或可行性项目目录。
- 不要把 MAMMA 运行时与 ExMR/GVHMR/FlowHMR/PEAR 的运行时合并，也不要用 `install.cmd` 的 overlay 去"升级"它。
- 不要手改 `.setup/mamma-runtime.json` 伪造 `version: 3`、`managed_id`、校验结果或包版本；重跑 `Setup_MAMMA.cmd` 是唯一支持的重建路径。
- 复制 / 备份时保留 mtime：`*.receipt.json` 依赖 `[size, mtime_ns]` 判定资产状态（见 `交接文档_环境与交付.md:474`）。
- `update.cmd` 只维护基础运行时，**不安装也不维护 MAMMA**。
- 测试素材与结果都在独立项目 / `.setup/` / `cache/`，属于用户数据，勿提交源码仓库。

---

## 11. 交接确认清单

- [ ] 在 GUI 打开可行性项目，目检姿态与相机对齐（补上视觉质量验收）
- [ ] 决定是否需要 4 机位测试；如需要，先裁 30 帧并盯住 8GB 显存
- [ ] 确认「情人节展示」虚拟角色素材在 `masks` 阶段能否检出人物
- [ ] 决定是否补装 PromptHMR
- [ ] 确认不再需要后清理 `.tmp_verify/` 等临时核对帧
- [ ] 若换 GPU 或升级依赖，重跑 `Setup_MAMMA.cmd` 并重做 CUDA kernel 校验
- [ ] 更新或标注 `docs/交接文档_环境与交付.md` 中「MAMMA 未安装」的过时表述（以本文档为准）
