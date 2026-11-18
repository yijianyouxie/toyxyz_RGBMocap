# PromptHMR 安装交接

本文档供接手人/agent 自包含地接手 PromptHMR 的安装、验证与后续收尾。所有路径相对仓库根 `H:\MyProject\toyxyz_RGBMocap`。配套的用户指南见 [PROMPTHMR.md](PROMPTHMR.md)。

## 1. 当前状态速览

- **运行时已装好**（2026-11-17）：`Setup_PromptHMR.cmd` 在用户自己的终端运行成功，输出 `PromptHMR ready: 6.32 GiB installed`。
- **14/14 权重 ready**：Model Manager 全部校验通过。
- **端到端可行性测试已通过**（2026-11-17）：5 个 worker stage 全部 `rc=0`，双人结果 `all_finite=True`，发布 82 个文件。
- **环境未受影响**：其它 10 个运行时目录完整，git 工作区无被跟踪改动。
- **唯一未完成待办**：把 deeplabv3 的离线 hub 缓存固化到安装流程（见第 8、9 节）——当前 GUI 正式推理仍会撞 GitHub 403，只有测试脚手架能跑通。

## 2. 前置条件与许可证

- 先跑 `install.cmd` 装好基础运行时（`runtime/python.exe`，Python 3.10）——`Setup_PromptHMR.cmd:11-15` 强制检查。
- 系统需 **Visual Studio 2022 C++ Build Tools** + **CUDA Toolkit 12.8**（SAM2 原生 CUDA 编译用）；MAMMA/PromptHMR 原生编译不能在 CodeBuddy 沙箱内跑（`reg.exe` 被列黑名单导致 `vcvars64.bat` 环境不全），必须由用户在自己的终端运行。
- 运行 setup 前**关闭 RGB MoCap 应用**（app 锁）。
- 许可证：`Setup_PromptHMR.cmd:7-11` 展示官方非商业科研许可并询问，需确认同意（参数 `--accept-licenses`）。

## 3. 安装流程与调用链

```
Setup_PromptHMR.cmd:17
  runtime\python.exe -I -X utf8 -B tools\setup_prompthmr.py --accept-licenses
    ├─ installer/engine.py             sha / clean_env / prune_runtime / atomic_json
    ├─ installer/prompthmr_adapters.py adapt_engine / install_python_source
    ├─ installer/verify_prompthmr.py   CUDA + 逐文件 RECORD 校验（3.11 目标解释器执行）
    ├─ tools/setup_mamma.py            复用 compiler / fetch_package / extract_source
    ├─ tools/support_components.py     复用 download（抓 sources 的 zip）
    ├─ tools/session_lock.py           app_lock
    └─ mocap/prompthmr_runtime.py      configure → 写注册文件
```

关键步骤（`tools/setup_prompthmr.py`）：

- `identity()`（15-18 行）：安装代次指纹 = `installer/prompthmr-runtime-lock.json`、`installer/prompthmr_adapters.py`、`installer/verify_prompthmr.py` 三文件 SHA-256 之和。**改这三个文件会让已装运行时失配，需重跑 setup**。
- 命中 `.setup/prompthmr-runtime.json` 且 `managed_id == identity()` 时（50-60 行）只做 `verify()` + `configure()` 复用，不重装。
- 离线缓存目录 `.setup/prompthmr-downloads/`：
  - 包：`<sha256>/<filename>`；源码：`<name>-<commit>.zip`。
  - 逐项 `bytes + sha256` 双校验；wheel 安装用 `uv pip install --offline --no-index --require-hashes`（83-84 行）再验一次。
  - 可从 `.setup/mamma-downloads/` 硬链接复用（74-80 行）。
- `installer/prompthmr-runtime-lock.json` 顶层 5 字段：`version=1`、`python=3.11.17`、`uv_sha256`、`packages`（204 项：199 wheel + 5 source）、`sources`（`sam2`/`prompthmr`/`detectron2`/`chumpy` 4 项，含 `url/sha256/bytes/commit/archive_root`）。**权重清单不在此 lock**，在 `mocap/prompthmr_models.py`。
- setup 期 `TORCH_HOME` 指向 `cache/prompthmr-setup/torch`（`tools/setup_prompthmr.py:25`），另设 `HF_HUB_OFFLINE=1`——与推理期的 `TORCH_HOME` 不同。

## 4. 安装产物

| 文件 | 关键字段 |
|---|---|
| `.setup/prompthmr-runtime.json` | `version=1`、`python`、`engine`、`license_reviewed=true`、`managed_id`（identity 值）、`compute_capability=[8,6]`、`packages`（torch 2.7.1+cu128 / torchvision 0.22.1+cu128 / numpy 1.26.4 / timm 0.9.0 / smplx 0.1.28）、`engine_files`（596 项相对路径→sha256） |
| `.setup/prompthmr-install-report.json` | `python=3.11.17`、`packages=207`、`verified_files=42572`、`compute_capability=[8,6]`、`cuda=12.8`、`sam2_components/torchvision_nms/native_attention=true`、`installed_bytes=6783169993`（6.32 GiB）、`runtime_id` |
| `runtime_prompthmr/<gen>/verification.json` | 同上但无 `installed_bytes/runtime_id`，由 `installer/verify_prompthmr.py` 生成 |
| `runtime_prompthmr/<gen>/ready.json` | `verification.json` + `installed_bytes` + `runtime_id` |

`engine_files` 596 条：`pipeline/` 542、`prompt_hmr/` 53、`LICENSE` 1，`data/` 0 条。

## 5. 运行时架构与校验

- **双解释器路由**（`mocap/paths.py:15-23`）：`prompthmr_prepare`/`prompthmr_publish` 走基础 runtime 3.10（`motion_correction` 的 cp310 pyd 只此一份）；`prompthmr_track`/`pose`/`world` 走 `runtime_prompthmr/<gen>/python.exe` 3.11。`prompthmr_worker_boot.py` 已设 `HF_HUB_OFFLINE=1`。
- **启动校验**（`mocap/prompthmr_runtime.py:47-58` `activate()`）：解释器路径/3.11、`PACKAGES` 版本、`torch.cuda.is_available()` 且算力匹配、`snapshot(engine) == engine_files` 全量相等。
- **`snapshot()` 扫描范围**（`mocap/prompthmr_runtime.py:10-20`）：只扫 `engine/pipeline/` 与 `engine/prompt_hmr/` 的白名单后缀（`.py/.yaml/.yml/.json/.txt`），加根 `LICENSE`；**不含 `engine/data/`**。因此往 `engine/data/` 写权重（每次推理 `link_assets()` 都这么做）不破坏指纹；往上述两个目录加文件会立即触发 "PromptHMR engine changed" 错误。
- **推理缓存 identity**（`mocap/prompthmr_pipeline.py:63-65`）：`engine_files` 与 `mocap/prompthmr_pipeline.py`/`image_io.py` 的 SHA 纳入 identity——改这些文件会让已缓存的推理结果失效（重跑即可）。

## 6. 模型权重

- **清单**：`mocap/prompthmr_models.py` 的 `ASSETS`（12 项）、`LINKS`（14 项）、`KEYS = tuple(LINKS)`。`missing('prompthmr_assets')` 校验失败会在 prepare 阶段拒绝。
- **校验**：`mocap/models.py` 的 `ready()` + 每文件 `<path>.receipt.json`（`source/drive_id/bytes/sha256/stat=[size,mtime_ns]`）；body 几何行（`smpl`/`smplx`）按 app 设计只校验大小、无 receipt。
- **来源三类**：
  1. 3 个大权重（vitpose-h-coco_25、keypoint_rcnn、sam2_hiera_tiny）走国内镜像（aifasthub / hf-mirror），`download.pytorch.org` 也被沙箱拦 TLS——需用 16 MiB 分块 Range + 块内续传、SHA 校验（候选脚本 `.setup/tmp/download_models.py`）。
  2. 8 个 Google Drive 文件（含 2.14 GiB 的 `checkpoint.ckpt`）：匿名请求被出口 IP 配额挡（2040 B "Quota exceeded" HTML），唯一可行通道是**浏览器登录 Google 账号 → FDM 截获下载 → 按精确 SHA-256 导入**。VPN 出口 IP 级配额，换工具无效，换节点才解。
  3. `smpl_mean_params` / body 几何等本地复用。
- **`.part` 续传经验**：进度存普通文件字节里，不依赖下载器任务状态；多源按 1 MiB 块合并取最优；已下字节绝不重下。

## 7. 端到端验证方法

脚本：`.setup/tmp/feasibility_prompthmr.py`（Python，临时脚手架，非产品代码）。

```bash
cd "H:/MyProject/toyxyz_RGBMocap"
"runtime/python.exe" -X utf8 -u .setup/tmp/feasibility_prompthmr.py
```

- 用 `tools/bin/ffmpeg.exe` 把 `.setup/mamma-test-videos/A001.mp4` 剪成 720p / 30 帧 / 1 秒片段。
- 在 `projects/PromptHMR_feasibility_<uuid>_project` 建独立私有项目，不碰既有项目。
- 顺序跑 5 个 stage：`prepare → track → pose → world → publish`，记录每个 stage 的退出码、耗时、显存/内存峰值、stdout/stderr 尾部。
- 全部成功后用 `joblib.load(results.pkl)` 检查 `people` 数量、各数组形状、全部数值 finite，并统计发布文件数；写 `feasibility_report.json`。
- **已验证结果**（项目 `PromptHMR_feasibility_d85a8b4761_project`）：

  | stage | 退出码 | 耗时 | 显存峰值 | 内存峰值 |
  |---|---|---|---|---|
  | prepare | 0 | 1.2s | — | — |
  | track | 0 | 35.7s | 3.89 GiB | 2.52 GiB |
  | pose | 0 | 70.2s | 4.33 GiB | 6.11 GiB |
  | world | 0 | 22.0s | 0.16 GiB | 1.75 GiB |
  | publish | 0 | 28.5s | — | — |

  `results.pkl`：`people=2`、`all_finite=True`、`smplx_pose [30,22,3,3]`、`keypoints_2d [30,25,3]` 等；发布 82 个文件。峰值显存 4.33 GiB < 8 GiB，RTX 3050 可行。
- 注：后台任务框架曾把该命令标为 `failed`，但那是退出码/沙箱 stderr 判定；`feasibility_report.json` 与实跑输出确认 5/5 `rc=0`，以报告为准。

## 8. 已知坑与当前 workaround（重点）

### 8.1 deeplabv3 的 GitHub 403（唯一硬阻塞）

第三方 engine 的分割/跟踪路径调用：

```python
# runtime_prompthmr/<gen>/engine/pipeline/tools.py:117 与 detector/segment.py:61
torch.hub.load('pytorch/vision:v0.10.0', 'deeplabv3_resnet50',
               weights=DeepLabV3_ResNet50_Weights.DEFAULT)
```

它先请求 GitHub API 做 fork 校验（本机出口 IP `123.119.177.112` 被 `403 rate limit`），通过后还要下载 `github.com/pytorch/vision/zipball/v0.10.0`（直连超时 000）。**与权重、CUDA 无关**。

好消息：`torch.hub` 官方的 `_get_cache_or_reload` 在 hub 缓存目录存在时 `use_cache=True`，**跳过 fork 校验与 zipball 下载**；且 `pytorch` 在 torch 的 `_TRUSTED_REPO_OWNERS` 里，不会因信任检查报错。

### 8.2 TORCH_HOME 每项目独立

`mocap/prompthmr_pipeline.py:130` 把 `TORCH_HOME` 设为**每个项目独立的** `<root>/work/torch-cache`（`work = <project>/prompthmr/inference/<token>`）。因此 hub 缓存无法全局共用，必须按项目植入。

### 8.3 当前 workaround（仅测试脚手架）

`.setup/tmp/feasibility_prompthmr.py:34-49` 的 `seed_hub_cache()` 在 `prompthmr_track` 之前把缓存植入该项目的 `work/torch-cache/hub/`：

- `pytorch_vision_v0.10.0/hubconf.py`：一行 `from torchvision.models.segmentation import deeplabv3_resnet50`。本地 torchvision 0.22.1 的签名 `deeplabv3_resnet50(weights=DEFAULT, ...)` 与 engine 调用完全匹配——比真下载 v0.10.0 的旧 hubconf（用 `pretrained=`，不接受 `weights=`）更正确。
- `checkpoints/deeplabv3_resnet50_coco-cd0a2569.pth`：官方权重，168,312,152 B，SHA-256 `cd0a25694c4a0f7…`，前缀 `cd0a2569`，`load_state_dict_from_url` 命中本地即不联网。
- 已做**断网离线验证**（代理指向无效端口）：`torch.hub.load` 成功返回 `DeepLabV3`，4200 万参数，零下载。

`.setup/tmp/fetch_deeplab.py` 用 16 MiB 分块 Range 从 `download.pytorch.org` 预取该权重到 `.setup/tmp/hub_assets/checkpoints/`，逐块续传、SHA 校验（注意：该域名被沙箱拦 TLS，需 `dangerouslyDisableSandbox`）。

### 8.4 明确边界

2026-11-17 正式 GUI 推理在 `情人节展示222_af5dfd680d595d_project` 复现同一 403，已修复并固化（见第 9 节）。核心思路不变：engine 的 `torch.hub.load` 保持原样，靠预置 hub 缓存目录绕过联网，不改数值处理。

其它已确认不会联网的点：`static_cam=True` 时 `camera_motion_estimation` 跳过 ZoeD 的 `torch.hub.load`（`engine/pipeline/pipeline.py:167-171`）；camcalib 用 `resnet50(pretrained=False)` + 本地 `camcalib_sa_biased_l2.ckpt`，不下载。

## 9. 待办与接手建议

**已固化（2026-11-17，采用方向 1 的变体）：**

- **稳定资产**：`assets/prompthmr_torch_hub/` —— `pytorch_vision_v0.10.0/hubconf.py`（一行导入，随仓库版本管理）+ `checkpoints/deeplabv3_resnet50_coco-cd0a2569.pth`（官方权重，168,312,152 B，SHA-256 前缀 `cd0a2569`；`.pth` 被 `.gitignore` 忽略，属本地资产，换机重装需重新预取，见 `.setup/tmp/fetch_deeplab.py`）。
- **推理期植入**：`mocap/prompthmr_pipeline.py:106` 新增 `ensure_hub_cache(work)`，在 `inference()` 设 `TORCH_HOME` 后、`from pipeline import Pipeline` 前调用；对每个新 work 目录把上面两文件硬链接（跨盘则复制）进 `<work>/torch-cache/hub/`。engine 与数值处理零改动。
- **效果**：GUI / CLI 新建任意项目都不再联网做 fork 校验或下载 zipball。改 `prompthmr_pipeline.py` 会改变 `identity.code`，已缓存推理会失效重算（可接受）。
- **另一条候选（未采用）**：monkeypatch 重定向 `torch.hub.load`（参考 ExMR/DINOv3 先例 `mocap/exmr_backend.py:62-69`、`mocap/flow_backend.py:73-80`），可绕开每项目 TORCH_HOME 限制，但需改引导代码，粒度和风险都更大。

**验证记录**：代理指向 `127.0.0.1:9`（任何联网立即失败），在全新 work 目录调用 `ensure_hub_cache()` 后 `torch.hub.load('pytorch/vision:v0.10.0','deeplabv3_resnet50',weights=DEFAULT)` 成功返回 `DeepLabV3`（42,004,074 参数，0.6 s），零下载；`py_compile` 在 3.10 / 3.11 两个解释器均通过。

**剩余待办**：把 deeplab 权重的预取纳入 `Setup_PromptHMR.cmd` 安装流程，使换机重装后 `assets/prompthmr_torch_hub/checkpoints/` 自动就位（当前靠 `.setup/tmp/fetch_deeplab.py` 手动预取）。可选：跑一次完整 5-stage 端到端确认仅靠安装产物即可全绿（去掉脚手架里的 `seed_hub_cache()` 调用）。

**注意**：改 `installer/prompthmr-runtime-lock.json`、`installer/prompthmr_adapters.py`、`installer/verify_prompthmr.py` 会改变 `managed_id`，需重跑 setup；改 `engine/pipeline/` 或 `engine/prompt_hmr/` 下的白名单文件会破坏 `engine_files` 指纹。
