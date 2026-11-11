# 交接文档：ExMR 修正链路（重心 / 脊柱 / 膝跳 / 大腿防瞬转 / 正视图右倾）

更新日期：2026-11-11
范围：`H:\MyProject\toyxyz_RGBMocap` 的 `correct`（动作修正）与 `export`（Mixamo/FBX 导出）阶段；配套网页端在 `F:\Comfy-Desktop\ComfyUI-Installs\Comfy-MotionCapture`
读者：接手继续做修复开发的同学。前几轮的分析、回归验证与膝盖重建已落地到产品代码（`d968284`），**本轮新增的"正视图右倾"修复与本文档同批入库**；文档同步更新到落地后的状态，历史实验记录保留供查根因。

---

## 1. 一句话现状

四条线**全部落地**：**重心偏后**（sagittal balance）、**脊柱前倾**（Straighten Spine）、**balance 引发的膝跳**（情人节 145/200 帧）、**正视图右倾**（见第 6 节）。膝跳采用"源片极向继承 + 弯曲量恢复 + 全帧 kink 回归保护"，随后修掉膝盖重建带出的**大腿瞬间转动**，代价是 `_POLE_STRENGTH=0.25` 在"修膝跳"和"稳大腿"之间取偏稳一侧（详见 5.6 / 5.7）。正视图右倾采用**侧身感知的逐帧俯仰上限 + 限速后置**（`_LEAN_CAP_K=1.0`），把 women_dance 首尾帧右倾增量从 +7.5° / +4.2° 压到 +2.6° / +2.8°，代价是 WD 支撑面内占比 −5.3pt；`balance=False` 逐帧零差异。

---

## 2. 仓库与数据

| 项 | 值 |
| --- | --- |
| 仓库 | `H:\MyProject\toyxyz_RGBMocap`，HEAD 为本次提交（正视图右倾修复 + 交接文档入库），本地未 push |
| 已提交 | `8b10d03` 重心修正（balance_pose 初版 + 开关 + 报告字段）；`58adb0f` 脊柱拉直 + 选项/缓存同步；**`d968284`** balance 修改 1/2/3 + 膝盖重建 + 大腿防瞬转（2 文件，+193/−11）；`48fe0c5` 旧 `交接文档.md` 移入 `docs/交接文档_环境与交付.md` 并订正；**本次提交** 正视图右倾修复（`mocap/correction.py`）+ 本交接文档入库 |
| 工作区 | 代码与文档均已提交，工作区干净 |
| 网页端 | `F:\Comfy-Desktop\ComfyUI-Installs\Comfy-MotionCapture`，工作区干净，只有未跟踪的 `tmp_exmr_diag`（验证脚本与关节快照，见第 9 节） |
| 未推送 | `origin/main..HEAD` 共 6 个提交（`8b10d03`、`f414b09`、`58adb0f`、`d968284`、`48fe0c5`、本次），push 需单独确认 |
| 目标片段（"情人节"） | `projects\情人节展示222_af5dfd680d595d_project\exmr\clips\86571ae09584b5\people\a4fb75bf01d34a09b4bb64392c993774\person_0001\takes\000000000_000000301`，301 帧 @30 fps |
| 回归片段（"women_dance"） | `projects\women_dance_30_ee8f5c345be678_project\exmr`（项目根即组根），658 帧 @30 fps |
| 当前修正参数 | `balance=true, spine=false, foot_lock=false, hand_lock=false, mode=flat, preset=normal, auto_floor=true`；代码常量 `_LEAN_CAP_K=1.0`（`mocap/correction.py:27`，设 0 即退回纯限速后置） |
| 运行环境 | `H:\MyProject\toyxyz_RGBMocap\runtime\python.exe`（3.10，含 torch/smplx）；`runtime_exmr` 是 ExMR 推理用的 3.12 |

---

## 3. 线程一：侧视重心偏后（已实现）

### 3.1 现象与根因

正面单目生成的动作用侧视看，**重心落在脚跟之后**，人像往后坐。根因是单目深度歧义：正视图分不清"腿站直"和"腿略微前倾缩短"，1–2% 的腿长误差就能变成 8° 的全身俯仰；ExMR 输出本身没有"绝对前后倾"的约束。

量化口径：Dempster 节段质量权重算全身 COM，投影到脚底支撑多边形的前后区间，取 `margin = min(COM−后沿, 前沿−COM)`，`inside%` 是 margin≥0 的帧占比。

### 3.2 实现（`8b10d03`）

- `correction.body_com(positions)`：Dempster 权重 COM
- `correction.balance_pose(...)`：以支撑脚底 probe 的**平滑枢轴**为圆心、绕左右轴转全身，再用 `anatomical_ik.solve_legs` 把支撑脚踝钉回原世界位置
- 俯仰是**目标**不是累加器：COM 一旦越过支撑中心就回落，上限 `max_total=10°`，单帧限速 0.6°
- 输出前重新 FK，导出全部 22 关节局部旋转 + `global_orient`
- 报告字段：`balance_pitch_mean/max_deg`、`balance_inside_before/after_pct`、`balance_margin_before/after_mean_m`、`max_balance_ankle_slip_m`、`balance_reach_capped_frames`、`balance_total_cap_frames`、`balance_iterations`

### 3.3 已落地的修改 1/2/3（随 `d968284` 一并提交）

以下三项此前一直挂在工作区未提交，现已在库里；问题与验证数据保留备查。

| 编号 | 内容 | 解决的问题 |
| --- | --- | --- |
| 1 | 俯仰双向上限 + `desired=np.clip(total+theta, 0., max_total)` | 原实现只能向前纠正，COM 已经越过支撑还在继续加角度 |
| 2 | 接触权重 `weight` 高斯淡入淡出；踝朝向 slerp；`blend`/`pin` 软过渡 | 支撑遮罩是二值的，进出接触时膝盖瞬跳 |
| 3 | `raw_room` 按支撑腿长度扫可达上限，`room` 高斯平滑，最后 `min(desired, room)` | 硬封顶造成 1.5°/帧突跳 |

### 3.4 验证结果

| 场景 | 指标 | 前 → 后 |
| --- | --- | --- |
| 情人节（301 帧） | 支撑面内占比 | 34.3% → **93.6%** |
| | COM 余量均值 | −0.005 → **+0.079 m** |
| | 最大桩脚滑移 | 1.9 cm |
| 修改 1+3 回归（情人节） | 俯仰均值/最大 | 5.7°/9.7° → 5.4°/9.6°（无退步，封顶 0 帧） |
| 修改 1+3 回归（women_dance） | 最大俯仰 | 18.9° → **10.0°** |
| | 终态偏差 | −3.9° → **−1.3°** |
| | 桩脚滑移 | 8.6 → **4.4 cm** |
| 修改 2 | 接触切换处膝跳 | 4.86°→1.85°（情人节）、4.14°→0.92°（women_dance），最大 20.8°→4.3° |

### 3.5 已知残留

- 长片（658 帧）滑脚仍有 4.4 cm，报告会打 `warning: Balance correction moved a planted foot by up to X cm`
- 拉直支撑腿会引发膝跳 → 已在 `d968284` 解决，见线程三 5.6

---

## 4. 线程二：脊柱到脖子前倾（已实现，`58adb0f`）

### 4.1 现象与判定

侧视看脊柱到脖子段明显前倾，**加 balance 之前就有**，所以不是 balance 的产物；是 SMPL-X rest 的胸椎曲线 + 正面深度歧义叠加的结果。

### 4.2 方案 C：导出时拉直 bind 脊柱

`source_animation.straighten_spine(rest)` 把 Spine1/Spine2/Spine3 放回 Hips→Neck 的直线，保留各段长度占比，Hips/Neck/Head 位置不动；`source_rig(original, source_rest, straight_spine=False)` 控制启用。

**关键约束（踩过坑）**：`mixamo_data` 里 rig rest、每帧 goal rest、FBX bind 的 `neutral_rest` **三处必须用同一份拉直后的 rest**，只改一处会报 fixed-length rig 错误。

缓存：payload 记录 `spine_straight`，`current()` 比对；选项或导出代码变化即失效。

### 4.3 验证结果

- Spine1→Spine2 夹角由 **+20.5° → −9.0°**
- 勾选/取消生成**不同 BVH**，`spine_straight` 能让缓存失效，无老数据残留

### 4.4 未解决

**脖子和头部还是前倾**——方案 C 只动 Spine1/2/3，不动 Neck/Head。用户反馈"视频里没这么严重"，说明颈段本身也被 ExMR 放大。要单独做颈-头补偿（或把 Neck 纳入拉直并给一个上限），目前没做。

---

## 5. 线程三：balance 引发的膝跳（已落地，`d968284`）

### 5.1 现象

情人节**右腿 200–210 帧、左腿 145–146 帧**有跳动，勾 Balance 才有。`d968284` 后 145/200 的 turn 降到 9.6°/18.4°、200 的 step 降到 0.72 cm，两片新增 >0.5 cm 抖动帧均为 0（强度 0.25 的取值理由见 5.7）。

> 注：5.2–5.5 是**落地前的基线数据与已试方案**，数值均为"未修复"状态，保留用于查根因；其中 `correction.py:173` / `anatomical_ik.py:71,78` 等是**改动前（`58adb0f`）的行号**，当前行号见第 8 节。落地后的验收数据见 5.6。

### 5.2 量化口径

- `kink`：关节世界坐标的单帧拐折 `|p[t] - (p[t-1]+p[t+1])/2|`，平滑运动接近 0
- `step`：膝盖单帧位移
- `bow`：膝盖相对"髋→踝"轴的垂直偏移量（腿的弯曲量）
- `turn`：相邻帧 bow 单位向量夹角（膝关节摆动平面转角）

| 帧 | bow | turn | step | 邻近帧 step |
| --- | --- | --- | --- | --- |
| 源片 200 右 | 5.32 cm | 2.2° | 0.20 cm | 0.15–0.28 |
| **修正后 200 右** | **1.16 cm** | **65.0°** | **1.90 cm** | 0.12–0.44 |
| 源片 145 左 | 6.76 cm | 3.1° | 0.33 cm | 0.22–0.31 |
| **修正后 145 左** | 4.18 cm | **29.7°** | **1.88 cm** | 0.16–0.34 |

全片：情人节最大 kink 左 4.96 cm（226 帧）/ 右 2.66 cm（68 帧）；women_dance 左 2.96 / 右 3.68 cm。68/73/226 在源片里本来就有，不算本次引入。

### 5.3 根因链

1. `balance_pose` 绕脚底转俯仰 + 钉踝 ⇒ 髋踝距离被拉长，200 帧右腿伸展率 **0.991 → 0.9996**
2. 可达上限在 `mocap/correction.py:173`：`allowed = max(length + reach_allow, 源距离)`，`reach_allow=+0.03`，**允许超伸 3 cm**，`room` 不拦
3. `mocap/anatomical_ik.py:71`：`flex = arccos(clip(desired/radius))`，插桩确认 197–203 帧右腿 `desired > radius` 恒成立 ⇒ `flex` 钳成 0
4. 完全伸直时膝关节摆动平面失去定义，只剩 `phase` 残差
5. `mocap/anatomical_ik.py:78` 的 `align(end_vector, delta)` 在两端接近共线时轴心条件数差：实测 200 帧右大腿全局朝向单帧转 **7.02°**，转轴与腿轴点积 0.02（纯摆动），源片同帧只转 2.2°

**不是俯仰不平滑**（实测最大 0.46°/帧，限速 0.6），是"腿被拉直后膝盖朝向没有唯一解"。

**插桩修正（本轮补做，`dbg.py`）**：上面第 3–5 步只对 200 帧右腿成立。实测 197–203 帧右腿 `desired > radius` 恒成立、`flex=0`、`phase` 平滑（−9.9°→−14.3°）；但 **145 帧左腿 `desired < radius`、`flex≈21°`，腿并未伸直**，phase 也平滑（−22.8°→−23.3°）。所以两处跳变**机制不同**：200 帧是 `flex` 被钳 0 后 pole 失去唯一解；145 帧是 balance 把 bow 从 6.76 压到 4.18 cm（相对源片 r=0.62）后 pole 偏离源片 26.8°。共同根源是 **IK 没有约束膝摆动平面必须跟随源片**。文档旧版把两处都归为 `flex=0` 不准确，这也正是 145 帧用绝对弯曲量门控抓不住的原因。

### 5.4 复现与回归方法（可直接复用）

准备副本——**必须 `cp -a` 保留时间戳**，否则 `people.json` 的 `media_receipt`（input.mp4 的 size+mtime_ns）对不上，报 "Person detection is out of date"：

`cd f:/Comfy-Desktop/ComfyUI-Installs/Comfy-MotionCapture/tmp_exmr_diag`，然后
`cp -a "H:/MyProject/toyxyz_RGBMocap/projects/情人节展示222_af5dfd680d595d_project" proj_fix`、
`cp -a "H:/MyProject/toyxyz_RGBMocap/projects/women_dance_30_ee8f5c345be678_project" proj_wd`

打补丁跑——不改仓库代码，monkeypatch `mocap.anatomical_ik.solve_legs` / `mocap.correction.balance_pose` 后调 `mocap.correction.run(take, emit, 'corrected_initial')`。历史变体脚本：`run_pole.py` / `run_fix3.py` / `run_soft.py`；**落地后的复核链路**：`run_landed.py`（跑修正+导出+打印 balance 报告）、`run_baseline_report.py`（monkeypatch 忽略 `reference`，得到同环境"未修复"对照）、`cmp_landed.py`（膝跳双回归）、`diag_hiprot.py` / `diag_femur.py` / `diag_thigh.py`（髋局部/全局旋转帧间转角）、`sweep_sigma.py` / `sweep_scale.py`（参数扫描）、`verify_*.py`（离线极向扫描）。

**坑一**：`correction.run()` 只写 `corrected_initial.pt` 和 `correction_report.json`，**不更新** `corrected_initial_joints.npz`；关节文件要再调 `mocap.export.export_project(Path(take),'corrected_initial')`。不调会一直拿到旧关节（我因此白跑了好几轮）。

**坑二**：沙箱里跑 export 会对 `third_party/GVHMR/inputs/checkpoints` 下的权重报 SANDBOX PERMISSION DENIED，**退出码可能非 0，但关节与报告都正常写出**，以输出文件为准，可忽略。

**坑三**：`correction.run()` 写出的 `corrected_initial.pt` 会被下一次运行覆盖。要对比"修复前/修复后"的局部旋转，必须在同一次进程里读完再跑下一种（或各存一份 `.npz`），否则拿到的是最后一次运行的姿态——本轮为此返工过一轮。

**坑四**：`solve_legs` 的 `active`（`pin`）覆盖极不连续（women_dance 右腿 ids 实测有 `30→84`、`239→265` 等跳空）。任何"回归保护"如果只检查被修复的帧，一定会漏掉邻帧跳变；必须在**全 take** 上算 kink，见 5.6。

### 5.5 已试方案与双回归

"新增抖动" = 相对基线 kink 增加 >0.5 cm 的帧数。

| 方案 | 改动点 | 情人节 145 / 200 | 情人节新增 | women_dance 新增 | balance 代价 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| 基线（现状） | — | 29.7° / 65.0° | — | — | — | 问题所在 |
| A 弯曲预算 `reach_allow=−6 mm` | `correction.py:173` | 4.6° / 2.4° | 0 | 0 | 余量 0.079→**0.038**，支撑面内 93.6%→**73.2%** | 有效但代价过大 |
| B1 最小屈膝 6°（硬钳） | `anatomical_ik.py:71` | 1.4° / 5.3° | L2 / R1 | **R 17 帧**，最坏 21 帧 0.09→**1.90 cm** | 无 | 引入新抖动 |
| B2 最小屈膝 8° | 同上 | 0.9° / 4.1° | 同上量级 | 同上量级 | 膝位平均变 0.64 cm | 同上 |
| B3 最小屈膝 6°（smooth-max） | 同上 | 4.3° / 7.3° | L1 / R1 | **R 17 帧**，最坏 → **2.14 cm** | 无 | 软化无效 |
| C 伸展上限 `reach_allow=+6 mm` | `correction.py:173` | 27.3° / 56.1° | L2 / R1 | **0 / 0** | 0.0792→0.0775，滑脚 1.91→1.60 cm | **零回归但只缓解 3~4 成** |
| D1 极向限速 4°/帧（全局） | `anatomical_ik.py:78` 后 | 4.0° / 3.9° | L **14.57 cm**、R **12.91 cm** | L **11.06 cm**、R 5.91 cm | 无 | 快速摆腿被拖住后弹回 |
| D2 极向限速（近锁门控 bow<3.5 cm） | 同上 | **30.0°**（没修好）/ 3.9° | R 6 帧，最坏 215 帧 → **1.95 cm** | L 0 / **R 8 帧**，最坏 104 帧 → **1.73**、105 帧 → **2.22 cm** | 无 | 抖动被挪到别的帧 |

D 系列失败原因：限速是"先扣押、后释放"，门控在弯曲量阈值硬开关，腿一伸过阈值就停止限速，滞后在一两帧内全部释放；145 帧 bow 是 4.18 cm，落在门控外，所以完全没被处理。

**补充结论（本轮扫描）**：文档旧版 5.6 的"连续时域低通 + 相对门控"也**没有通过双回归**。相对门控（α 随 `bow/bow_src` 连续衰减）能把 145/200 的 turn 压到 0.06°/0.07°，但会在门控边界释放滞后，情人节引入 L6/R2 帧新抖动（最坏 5.14 cm）、women_dance L5/R4 帧；绝对门控零回归却完全抓不住 r=0.62 的 145 帧（turn 仍 29.7°）。根子是 IIR"先扣押、后释放"缺少绝对参考——**源片 pole 才是平滑的绝对参考**（源片 turn 全片仅 2–3°）。落地方案因此放弃"向上一帧 pole 低通"，改为直接向源片 pole 继承。

### 5.6 落地方案（`d968284`）

思路：**只改膝盖，不改髋/踝**。balance 前先快照整片姿态 `reference=pos.copy()`（`correction.py:136`），在原有 3 次俯仰迭代**全部结束后**，用最后一次迭代的输入**单独跑一次**带 `reference` 的 IK（`correction.py:271-282`）——这样回归保护的"未修复"基线恰好等于改动前的最终姿态，不会被串行迭代污染。

`anatomical_ik._rebuild_knees`（`anatomical_ik.py:50`）做两件事，且都保持在解剖铰链内（`knee_local = R_axis(φ)·original_knee` + 绕髋→踝轴 twist），所以 `max_off_axis` 等校验照常通过：

1. **弯曲量恢复**：`flex_goal = max(flex, 0.40·bow_src/|upper|)`，对应方案 A 想做的事，但只在被拉直的帧生效，代价远小于全局改 `reach_allow`
2. **源片极向继承**：目标 pole = 源片 pole 投影到当前腿轴平面，门控 `g = clip((r−0.90)/0.25, 0, 1)`（`r = bow/bow_src`）；r<0.90 完全继承源片，r>1.15 完全保留当前解，快速摆腿（r≈1）不动

**全帧 kink 回归保护**（`correction._knee_guard_beta`，`correction.py:89`）：把"未修复 / 已修复"四元数按逐帧 β 混合，任何帧 kink 相对未修复基线增加 >0.5 cm 就把 β 按 0.6 回退，迭代收敛。**必须在全 take 上做**——落地时为此返工三次：保护放在 `solve_legs` 内会因 `pin` 不连续而漏检邻帧；放在迭代内会被串行迭代污染基准；在迭代末尾单独重跑 IK 又会因 `source_world`/`delta` 不自洽让踝移动 0.8 cm。

**验收（真实链路 `correction.run` + `export_project`，两片同时）**：

| 指标 | 改动前 | 强度 1.0 | **强度 0.25（当前）** |
| --- | --- | --- | --- |
| 情人节 145 turn | 29.7° | 3.1° | **9.6°** |
| 情人节 200 turn | 65.0° | 2.3° | **18.4°** |
| 情人节 200 step | 1.90 cm | 0.55 cm | **0.72 cm** |
| 新增 >0.5 cm 抖动帧（情人节 / women_dance，L/R） | — | 0/0、0/0 | **0/0、0/0** |
| 226 帧左膝 kink | 1.21 | 1.13 | **0.85** |
| 髋/踝世界位移 | — | 0.17 cm | **0.09 cm** |

**平衡报告逐字段不变**：`balance_margin_after_mean_m` 0.0793 / 0.0991、`balance_inside_after_pct` 93.5714 / 76.0949、`max_balance_ankle_slip_m` 0.0194 / 0.0443、俯仰 5.3706/9.5719 与 3.8677/10.0、`balance_iterations=3`。唯一微差是情人节桩脚滑移 +0.3 mm（flex 恢复使 `end_vector` 长度略变），远低于 1 cm 警告阈值。

**隔离性**：`balance=False` 前后关节最大差异 **0.000000 cm**（修复只在 `balance_pose` 内，`balance=False` 不调用它）；`mixamo_data.code_identity()` / `flow_correction.code_identity()` 都把 `correction.py`、`anatomical_ik.py` 列入哈希，改代码即失效，无需 bump `VERSION`。

### 5.7 第二轮：大腿瞬间转动（已修）

落地强度 1.0 后用户反馈：women_dance 223–224 帧左大腿、情人节 89 帧左腿、124 帧附近的右腿会**瞬间转动**。量化发现这不是关节位置摆动（hip→knee 方向帧间夹角在 223 帧反而 2.6°→0.6°），而是**局部髋旋转（股骨绕自身轴滚转）**的帧间突变：从 `corrected_initial.pt` 的 `body_pose`（21 关节 axis-angle）转旋转矩阵后算帧间相对转角，QRJ `R_loc` p99 从 4.2° 升到 12.0°、个别帧 27.8°。

**根因**：膝盖位置 = 髋 + `hip_world·upper`，要把膝摆动平面转回源片，就必须绕髋→踝轴转 `hip_world`；而绕股骨轴转 `hip_world` **正是**眼睛看到的"大腿拧一下"。ψ 在帧间跳变（200 帧需要约 65° 的 pole 修正）就直接变成股骨单帧滚 65°。**修 pole 与稳股骨是同一个自由度，几何上不可完全兼得**。

一个澄清：**无 balance 与改动前 balance 的股骨转角几乎完全一致**（QRJ L 21.3/25.7 vs 21.2/25.7，WD L 16.4/22.4 vs 16.4/22.2），p99 21° 是源片本身的正常快速动作，balance 不产生大腿转动——尖峰是落地引入的。

**修复**（`anatomical_ik.py:9,12,16,106-114`）：

- ψ 做**非因果时域低通**：接触间隙内 `np.interp` 填充（不把修正量衰减到 0），`gaussian_filter1d(sigma=1.0)` 把单帧尖峰摊到相邻帧，接触边界自然淡入淡出
- 新增 `_POLE_STRENGTH = 0.25`，只保留 1/4 的极向修正量

**复核**：局部髋旋转 p99/max 回到无 balance 基线（QRJ L 6.7/8.2 → 8.5/10.0、R 4.2/4.5 → 4.6/5.4；WD L 9.4/11.6 → 9.6/11.6、R 8.0/18.7 → 8.6/20.0）；用户报告帧 WD 223-224 左腿 0.9/1.0 → **0.4/0.5**、情人节 89 左腿 0.3 → 0.3、124 左腿 1.5 → 2.6。

**取舍表**（`_POLE_STRENGTH`，sigma 固定 1.0）：

| 强度 | 145T / 200T / 200 step | 局部髋 p99（QRJ L/R） | 判断 |
| --- | --- | --- | --- |
| 0.25（当前） | 9.6° / 18.4° / 0.72 cm | 8.5 / 4.6 | 大腿完全正常，膝跳改善 2–3 倍 |
| 0.5 | 8.4° / 15.7° / 0.66 cm | 9.0 / 6.6 | 大腿开始恶化 |
| 1.0 | 6.1° / 10.4° / 0.57 cm | 11.9 / 12.0，个别帧 27.8° | 膝跳最好，但重现大腿瞬转 |

当前按用户"大腿瞬间转动"的反馈选了 0.25。**若以后更看重膝跳，把 `_POLE_STRENGTH` 调到 0.5–1.0 即可**，代价是大腿重新出现转动；两者不可同时拉满。

### 5.8 仍待办

- 226 帧左膝、68/73 帧：源片自带跳变，落地后 226 帧 kink 1.21→0.85 但未根除
- women_dance 104 帧右腿（源片自带大动作）：强度 0.25 下 kink 0.95→1.14、turn 32.9→40.4，未超 0.5 cm 新增阈值，但值得在视频里再看一眼
- 脖头前倾（线程二 4.4）未动；长片滑脚在线程四落地后由 4.43 cm 降到 2.78 cm（见 6.4）
- 更新前文档 5.6 的"兜底" `reach_allow: +0.03→+0.006` 未采用；如需先止血仍可用，零回归但只缓解 3~4 成
- 未做：FBX/BVH 视觉检查、其他项目回归；GUI 端到端已由用户跑通（`corrected_initial_joints.npz` 与诊断链路逐帧 0 差异）；实验结论均来自关节数组与报告字段

### 5.9 落地后用户反馈的微抖帧（待查，非本次修复引入）

用户反馈：情人节 **140 帧左腿**、women_dance **180 帧 / 245 帧** 有"微抖"。用 `diag_micro.py` 对最终版导出关节量化，这些帧的 `kink` / `step` / `turn` 与局部髋旋转帧间转角**与改动前基线、甚至与无 balance 版本逐字段完全一致**，数值也很小：

| 帧 · 腿 | kink 前→后 | step 前→后 | turn 前→后 | 局部髋转角 nobal/raw/fix |
| --- | --- | --- | --- | --- |
| 情人节 140 · L | 0.02→0.02 cm | 0.17→0.16 cm | 0.6°→0.2° | 0.6 / 0.6 / 0.6° |
| WD 180 · L | 0.16→0.16 cm | 1.59→1.59 cm | 1.7°→1.7° | 3.5 / 3.6 / 3.6° |
| WD 180 · R | 0.11→0.11 cm | 0.85→0.85 cm | 1.7°→1.7° | 2.3 / 2.3 / 2.3° |
| WD 245 · L | 0.16→0.16 cm | 0.93→0.93 cm | 1.4°→1.4° | 2.7 / 2.9 / 2.9° |
| WD 245 · R | 0.74→0.74 cm | 0.72→0.72 cm | 2.2°→2.2° | 2.8 / 2.5 / 2.5° |

结论：这些帧的骨骼输出与基线逐字段一致，说明膝盖重建**没有改变它们**，balance 的骨骼输出里也测不出跳变。视觉上的"微抖"更可能来自**网格蒙皮、`source_pose_fit` 导出拟合或播放插值**，也可能只是邻帧动作本身细碎（WD 181 帧 kink 0.97、244 帧 1.00，源片自带）。要定位必须看导出的 FBX/BVH 或视频；本轮只做记录，未改代码。

---

## 6. 线程四：正视图右倾（已落地，本次提交）

### 6.1 现象

勾选 balance 后，women_dance 在**固定正视图**里 f1 附近、f656 附近相对源视频"向右歪斜"；情人节"倒还好"，用户判断"单脚直立时更突出"。只在勾选 balance 时出现，与线程三的膝盖跳变无关。

### 6.2 根因：俯仰旋转轴随人物 yaw

`balance_pose.axes()`（`mocap/correction.py:140-151`）用**每帧髋连线** `P[:,1]-P[:,2]` 的水平投影定义人体左右轴 `lat`，`:245` 用 `lat[t]` 作俯仰旋转轴。`lat` 随人物朝向（yaw）转动，人物侧身时带 Z 分量。绕它转 φ 的位移场 `Δp = φ·lat×(p−pivot)` 在世界 X 上的分量为 `Δp_x = −φ·lat_z·(p_y−pivot_y)`，**随高度线性**：脚（近 pivot）几乎不动，头/躯干被整体横移，在固定正视图里就是右倾。

量化式 `Δroll_w ≈ −Δpitch·lat_z` 实测：WD 相关系数 0.975 / 斜率 1.07，情人节 0.9999 / 1.003。人体自身冠状面侧倾 `Δroll_person` 最大仅 1.75° / 0.39° —— **人体自身没歪，是旋转轴投影问题**。

| 帧 | 右倾增量（勾选−不勾选） | 头部横移 | yaw（左右轴偏离世界 X） |
| --- | --- | --- | --- |
| WD f0 / f1 | **+7.53° / +7.54°** | +14.0 / +13.9 cm | −138° / −138.5°，`abs(lat_z)`≈0.67 |
| WD f656 / f657 | +4.19° / +4.29° | +9.8 / +9.9 cm | −148° / −147° |
| 情人节 f0 / f1 | +0.84° / +0.41° | +2.4 / +1.2 cm | −171° / −175°，`abs(lat_z)`≈0.15 |

- **为什么是首尾帧**：WD 首尾同时满足「侧身约 40°」+「单脚直立」（两脚踝间距 11.6–17.4 cm，情人节 21.8–28.3 cm）。单脚支撑多边形窄 → COM 偏差角最大 → 累积俯仰打满 `max_total=10°`（实测 9.7–9.9°），横移 ∝ `pitch × abs(lat_z)` 最大。用户"单脚直立突出"的判断对，但它放大的是 pitch；让歪斜**出现在正视图**的必要条件是侧身。
- **排除项**：未启用膝盖重建的 balance 输出（`J_base_rep_wd.npy`）与落地版头部横移逐帧差 **0.0000 cm**，与 `d968284` 无关；俯仰本身平滑（限速 0.6°/帧）、COM 与脚钉住均正常。

### 6.3 落地方案（本次提交）

只改 `mocap/correction.py`，挂在 `balance` 内、无新选项：

1. `_LEAN_CAP_K = 1.0`（`:27`）：循环外用初始 `lat` 算逐帧上限 `cap = max_total*(1 − k·abs(lat_z))`（`:223`）。用初始 `lat` 是因为绕 `lat` 俯仰不改变其水平方向，跨迭代稳定。
2. `desired` 顺序改为 `clip(cap)` → `minimum(room)` → **限速循环放最后**（`:243-248`）。原代码 `minimum(room)` 在限速之后，硬裁剪能突破 0.6°/帧（实测 2 帧 0.63°）；后置后两片均 0 帧超限。
3. `balance_total_cap_frames` 改按 `cap` 统计（`:305`），否则逐帧 cap 下该字段恒为 0、失去意义。

**设 `_LEAN_CAP_K=0` 即退回"纯限速后置"**：已实测 WD `inside=76.0949`、`pitch=3.8677/10.0`、`iterations=3` 与改动前逐字段一致，且 `Δtotal` 绝对值最大 0.600°、0 帧超限 —— 限速后置本身是零代价的稳健性修复。

### 6.4 验证（真实链路 `correction.run` + `export_project`，两片同时）

| 指标 | `d968284` | 本次落地 |
| --- | --- | --- |
| WD `Δtotal` 绝对值最大 / 超 0.6° 帧数 | 0.63° / **2** | **0.600° / 0** |
| WD 右倾增量 f0 / f1 | +7.53° / +7.54° | **+2.57° / +2.60°** |
| WD 右倾增量 f656 / f657 | +4.19° / +4.29° | **+2.76° / +2.75°** |
| WD 右倾增量 全片绝对值均值 / 最大 | 1.54° / 7.54° | **1.10° / 3.92° @f89** |
| 情人节 右倾增量 绝对值均值 / 最大 | 0.86° / 3.18° | **0.78° / 2.63°** |
| WD `balance_inside_after_pct` | 76.0949 | 70.8029（−5.3pt） |
| WD `balance_margin_after_mean_m` | 0.0991 | 0.0897 |
| WD 桩脚滑移 | 4.43 cm | **2.78 cm** |
| 情人节 `balance_inside_after_pct` | 93.5714 | **93.5714（零影响）** |
| `balance_iterations` | 3 | 3 |
| `balance=False` 前后关节差异 | — | **0.000000 cm** |

- **不会跳帧**：`cap` 是逐帧连续数组、`total` 是累积角、`max_step=0.6°/帧` 限速放在所有硬裁剪之后；实测 WD f99 处 cap 5 帧内 1.5→9.23°，`total` 仍 `1.18→0.58→0→0→0`。WD f99/f100 右倾增量为 0（cap 把俯仰压到 0）。头部横移帧间差分 p99 2.92→2.25 cm、超 2cm 帧 32→11。
- **硬门控不可用**：实测二值门控虽仍被限速护住累积角，但会在边界产生持续 0.6°/帧的回退斜坡（与 5.5 的 D 系列同因）；若把门控加在限速之后则会真跳帧。
- 限速后置还把 cap 变体在 WD f193 右膝的新增 kink 从 +2.32 cm 降到 +1.60 cm。

### 6.5 取舍与残留

- `_LEAN_CAP_K` 是唯一旋钮：`k=0.5` → WD `inside=73.54`（只掉 2.5pt），但 f656 横移几乎不改善；`k=1.0` 是首尾帧改善更完整的一侧。
- 代价：WD 支撑面内占比 −5.3pt、margin −1 cm；情人节零影响。
- 残留：WD 全片仍有 41 帧右倾增量 >3°，最大 3.92° @f89（已不在首尾帧）；相对 `d968284` 新增 kink WD L 4 帧 / R 9 帧（max +1.60 cm @f192）、情人节 L/R 各 1 帧，需看导出 FBX/BVH 视频确认（同 5.9）。
- 备选（未采用）：把俯仰轴固定为世界 X 可让横移归零、balance 报告几乎不退化，但引入人体自身冠状面侧倾 WD 7.28° / 情人节 3.23°，肩线一高一低比现状更明显 —— **横移与侧倾是同一自由度的两面，几何上不可两全**（同 5.7 的取舍）。

---

## 7. 选项与缓存的一致性（用户的硬要求）

> "修改选项后，Apply Correction 或 Reconstruct 3D 后看到的就是对应选项的效果，不要残留。"

实现要点：

- `correction_settings.store_options(projects, options)`：把修正块**一次写进组根 + 所有 take**，幂等，返回实际改动的项目
- `gui.correction_targets()`：从 manifest 的 `people_root` 解析组根，不依赖场景是否已加载
- 缓存失效：`code_identity`（代码指纹）+ payload 比对（`spine_straight`、`options`）；`d968284` 的膝盖重建挂在 `balance` 内、无新选项，两个改动文件都在 `code_identity()` 哈希列表里，改代码即自动失效，不需要 bump `VERSION` 或手动清缓存
- `gui.prepare_target_preview()`：结果过期时排 `correct+export`，不再静默跳过
- `gui.input_jobs()`：`people_state is None` 时先 `sync_people`
- `scene_floor.binding()`：项目等于组根时返回 identity 绑定；非 actor 抛明确 `ValueError`（原来是 `StopIteration`）

历史坑（都已修）：`StopIteration` 崩溃、fixed-length rig 报错（三处 rest 不一致）、预览静默跳过导致"点了一次没反应、第二次才生效"。

---

## 8. 开关与代码地图

| 功能 | 选项键 | 网页端 | 桌面端 |
| --- | --- | --- | --- |
| 重心修正 | `balance`（默认 true） | `exmrBalance`（`templates/index.html:480`、`app.py`、`exmr_pipeline.py --balance`） | `workspace_ui.py:471` |
| 拉直脊柱 | `spine`（默认 true） | `exmrSpine`（`index.html:488`、`exmr_pipeline.py --spine`） | `workspace_ui.py:476` |
| 膝盖重建 / 大腿防瞬转 | 随 `balance` 生效，**无独立开关**（`_POLE_STRENGTH` 是代码常量） | — | — |
| 正视图右倾抑制 / 限速后置 | 随 `balance` 生效，**无独立开关**（`_LEAN_CAP_K` 是代码常量，设 0 关闭） | — | — |

| 代码 | 作用 |
| --- | --- |
| `mocap/correction.py` | `body_com:52`、`_blend_quat:82`、`_knee_guard_beta:89`、`balance_pose:114`（`reference` 快照 `:136`）、可达上限 `:206`、循环内 IK `:266`、**末尾单次膝盖重建 `:271-282`**、报告字段 `:295`、balance 调用点 `:716` |
| `mocap/anatomical_ik.py` | `_POLE_SMOOTH_SIGMA:12` / `_POLE_STRENGTH:16`、`_rebuild_knees:50`（ψ 低通 `:114`）、`solve_legs:120`（新增可选 `reference=None`）、flex 计算 `:148`、align 对准 `:155` |
| `mocap/source_animation.py` | `straighten_spine:26`、`source_rig(...)` |
| `mocap/mixamo_data.py` | rest/goal/FBX bind 三处一致性、`spine_straight` 缓存校验 `:35` |
| `mocap/correction_settings.py` | `correction_options`（默认值）、`store_options:43` |
| `mocap/gui.py` | `correction_targets:1063`、`save_correction_options:1087`、预览/队列 |
| `mocap/people_ui.py` | 场景修正时追加组根的 correct+export |
| `mocap/scene_floor.py` | `binding`：组根 identity / 非 actor 报错 |
| `mocap/worker.py` | `--balance`、`--spine` 透传 |
| `mocap/correction.py`（本次新增） | `_LEAN_CAP_K:27`、逐帧 `cap` `:223`、`desired` 顺序 `clip(cap)→minimum(room)→限速` `:243-248`、`balance_total_cap_frames` `:305` |

> 注：上表 `correction.py` 行号基于 `d968284`；本次提交在文件头部 +4 行、`:218` 附近 +3 行、`:240` 附近 +2 行，精确位置以当前文件为准（新增位置见 6.3）。

---

## 9. 临时产物

`F:\Comfy-Desktop\ComfyUI-Installs\Comfy-MotionCapture\tmp_exmr_diag` 目录下：`J_*.npy`（各变体的关节数组 (T,22,3)，可直接对拍）、`run_pole.py` / `run_fix3.py` / `run_soft.py`（历史变体打补丁跑修正）、`cmp_*.py`（指标对比）、`verify_*.py`（离线极向扫描）、`run_landed.py` / `run_baseline_report.py` / `cmp_landed.py` / `diag_hiprot.py` / `diag_femur.py` / `diag_thigh.py` / `sweep_sigma.py` / `sweep_scale.py` / `diag_micro.py`（落地后的真实链路复核与参数扫描）、`femur_*.npz` / `hiprot_*.npz`（旋转指标快照）。均为未跟踪文件，可随时删；复现时用 `cp -a` 重建 `proj_fix` / `proj_wd`。网页端仓库本身只有这个未跟踪目录，**不要提交**。

**本轮（线程四）新增**：`diag_lean.py`（歪斜量化 + 旋转轴机制检验）、`run_axisfixed.py`（固定俯仰轴变体）、`sweep_cap.py` / `cmp_cap.py`（`k` 参数扫描与取舍）、`draw_lean.py` / `lean_front_compare.png`（正视图三版本对比）、`diag_transition.py` / `cmp_transition.py`（逐帧 cap 与硬门控的衔接跳帧诊断）、`verify_landed.py` / `verify_cap0.py`（落地后真实链路复跑与 `_LEAN_CAP_K=0` 回退验证）、`quant_rightlean.py` / `rightlean_compare.png`（勾选/不勾选右倾角度量化）、`J_axisfixed_*` / `J_cap0.5_*` / `J_cap1.0_*` / `J_landed2_*` / `J_nobal_current_*`（关节快照）。GUI 真实项目 10:54 的 WD `corrected_initial_joints.npz` 与 `J_landed2_wd.npy` 逐帧 0 差异，可作用户侧结果对照。

---

## 10. 注意事项

1. 实验一律在副本上跑，**不要直接在 `H:\MyProject\toyxyz_RGBMocap\projects` 里跑**，`correction.run` 会覆盖 `corrected_initial.*`
2. 任何修复都要挂到已有复选框下（膝盖重建挂在 `balance` 内），并保证取消勾选后重新 Apply Correction 拿到的是不带该修复的结果；`balance=False` 前后关节差异实测 0.000000 cm
3. 结论必须两个视频同时看：情人节是目标场景，women_dance 是回归场景，单看一个必然在另一处翻车（前几轮多个方案都这么失败）
4. 评估膝盖/大腿跳变要**同时看三类量**：关节位置 `kink`/`step`/`turn`、局部髋旋转帧间转角（股骨滚转，`diag_hiprot.py`）、balance 报告字段。只盯关节位置会漏掉"大腿瞬间转动"——腿伸直时 `hip→knee` 方向对绕轴滚转完全不敏感；若三类量都正常但视觉仍抖（见 5.9），往网格蒙皮 / 导出拟合 / 播放插值层查，别在骨骼数值里空转
5. `corrected_initial.pt` 含 `smpl_params_global.body_pose`（21 关节 axis-angle），可直接算局部旋转帧间转角；`corrected_initial_joints.npz` 只有位置，且要 `export_project` 之后才更新（见 5.4 坑一）
6. 改 `_POLE_STRENGTH` 前先跑 `sweep_scale.py` 看取舍曲线：修膝跳与稳大腿是同一个自由度，只有折中、没有两全
7. 评估"正视图右倾"要用**固定世界正视图**的右倾角（`atan2(head_x−pelvis_x, head_y−pelvis_y)`）并取**勾选减不勾选的增量**，不要看绝对角：源片人物侧身 + 前倾，绝对投影角本就有 ±30°。调 `_LEAN_CAP_K` 前先跑 `sweep_cap.py` 看取舍；改 `desired` 计算顺序时务必保持限速循环在最后，否则 `room` 硬裁剪会突破 0.6°/帧
