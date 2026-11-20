# 交接文档：3ds Max Biped 脚部内扣（情人节 / female）

更新日期：2026-11-18
范围：`H:\MyProject\toyxyz_RGBMocap` 的 BVH 导出（`mocap/biped_bvh.py`、`mocap/source_bvh.py`）与 3ds Max Biped 的 BVH 导入 / `.bip` 往返
读者：接手继续做脚部、Biped 交付或 female 骨架修复的同学
状态：**只做分析与离线验证，未改产品代码、未改用户的工程数据**。诊断脚本在 `temp/diag_feet/`（未跟踪）。

---

## 1. 一句话现状

**内扣不是导出、不是修正、也不是 female 的 Figure Mode rest 造成的；它是在 `biped.loadMocapFile` 把 BVH 导入 Biped 时引入的一个约 -24.5° 的常量 yaw。** 这个误差随后被 `.bip` 保存并在 female 上保留（female 的 rest 改动对动画无效），female 自身再叠加约 4–5° 的 figure 差异，所以用户看到约 -29°。

| 对象 | 第 83 帧脚 yaw（身体坐标，正=外八） |
| --- | ---: |
| 源 BVH（GUI 一致） | 左 **+10.5°**，右 **+0.1°** |
| BVH → 新建 Biped | 左 **−14.1°**，右 **−25.1°** |
| `.bip` → 新建 Biped | 左 **−20.9°**，右 **−34.4°** |
| female 场景（用户看到） | 左 **−19.3°**，右 **−29.3°** |

两个“看起来像方案”的做法都已实测无效：

1. **在导入前**把 Biped 的 Figure Mode 脚 rest 调到源 BVH 的 +20.6°/+17.3°：`loadMocapFile` 会把 rest **重置回 0°**，第 83 帧结果与不预设完全一样（−14.06°/−25.11°）。
2. **在 female 上**把 Figure Mode 脚 rest 从 +8.7° 改到 +38.2°：第 83 帧动画 yaw **完全不变**（−19.29°/−29.29°）。

所以修复位置只能是：**导入后的 Foot 动画常量 yaw 修正**，或**导出端让 Biped profile 的脚 rest 与导入器的 0° 约定一致**。详见第 6 节。

---

## 2. 结论分层

| 层 | 结论 | 证据 |
| --- | --- | --- |
| GUI ↔ 导出 BVH | 一致 | 源 BVH 的脚趾向量 / 关节位置与 SMPL-X 逐帧差约 1e-7 m；源码见 `mocap/source_bvh.py` |
| 修正阶段 | 不碰踝 | `correction_report.json` 的 `max_ankle_global_change_deg = 4.3e-6`；balance/head/spine 不改踝世界旋转 |
| 源脚姿态 | 左踝有约 12° 内倒、两脚因高跟有 20–27° 前倾 | SMPL-X 网格平面拟合；视频 f60–66 可见细高跟 |
| BVH → Biped（`loadMocapFile`） | **引入约 −24.5° 常量 yaw** | 7 帧扫描，左右差值 −23.7°～−26.8°，标准差约 1° |
| 预设 Biped 脚 rest | **无效，被导入重置为 0°** | 预设 +20.6/+17.3 → 导入后 0/0，f83 与不预设相同 |
| `.bip` 往返 | 本身无损，但把导入误差一并保存 | `.bip` → 新 Biped 与 female 都保留同一内扣；改 Figure rest 不改变动画 |
| female rest 后改 | **无效** | 8.7° → 38.2°，f83 仍 −19.29/−29.29 |
| female 比默认 Biped 更多几度 | female 的 rest/figure（外八 8.7°、踝趾斜率 35.6°）与 `.bip` 源 figure 的差异 | female −29.3° vs BVH→Biped −25.1° |

---

## 3. 度量口径

脚 yaw 一律用**身体坐标**，不用世界轴（人物会转身）：

```
hipLeft = normalize( (L Thigh.pos − R Thigh.pos) 的 horizontal 分量 )
bodyFwd = normalize( cross(hipLeft, up) )，并翻到与两脚平均前向同号
footFwd = normalize( (Toe0.pos − Foot.pos) 的 horizontal 分量 )

yawL = atan2( footFwd_L · hipLeft, footFwd_L · bodyFwd )   # 正 = 左脚外八
yawR = atan2( −footFwd_R · hipLeft, footFwd_R · bodyFwd )  # 正 = 右脚外八
```

- 源 BVH（Y-up）和 Max（Z-up）用同一公式；`up` 分别取 +Y / +Z。
- 源 BVH 的关节名：`LeftUpLeg/RightUpLeg`、`LeftFoot/RightFoot`、`LeftToeBase/RightToeBase`。
- Max 的节点名：`Bip01 L Thigh`、`Bip01 L Foot`、`Bip01 L Toe0` 等；`.name` 前缀由 `biped.createNew` 决定（新建常为 `Bip001`）。
- Max 的 `Biped_Object` **没有 `.pos` 属性**，必须用 `node.transform.translation` 或 `.transform.row4`；这是本轮踩过的坑。

---

## 4. 证据链

### 4.1 输入与场景

| 输入 | 说明 |
| --- | --- |
| `C:\Users\liuhaibin\Desktop\balancestraightenhead.bvh` | 15:14，628,838 B，Biped profile（52 骨、ZXY、单位 m） |
| `C:\Users\liuhaibin\Desktop\balancestraightenhead.bip` | 15:15，1,301,634 B，用户在 Max 里由上述 BVH 生成 |
| `...\exmr\clips\86571ae09584b5` | 情人节 corrected_initial，301 帧 @30 fps |
| `...\Documents\3dsMax\autoback\AutoBackup01.max` | 15:51，female.max 的自动备份；**复制**到临时目录后只读打开 |

源 BVH 的静止脚参数（从 OFFSET 计算）：

- 左脚 toe-out **+20.63°**，右脚 **+17.31°**（相对身体前向）
- 踝→脚掌球下倾 **26.04° / 26.41°**
- 静止鞋底法线 +Y（平）

### 4.2 BVH → Biped：恒定的 −24.5°

用 `biped.createNew 1.64 1.0 [0,0,0]` 新建 Biped，`biped.loadMocapFile b.controller "balancestraightenhead.bvh"`，逐帧读取 `Foot`→`Toe0`：

| 帧 | 源 BVH L/R | BVH→Biped L/R | 差值 L/R |
| ---: | --- | --- | --- |
| 0 | +11.7 / −10.7 | −15.1 / −35.4 | **−26.8 / −24.7** |
| 60 | +41.3 / +0.8 | +17.1 / −21.9 | **−24.2 / −22.7** |
| 82 | +13.1 / −1.5 | −11.8 / −26.5 | **−24.9 / −25.0** |
| 83 | +10.5 / +0.1 | −14.1 / −25.1 | **−24.6 / −25.2** |
| 84 | +8.6 / +1.2 | −15.7 / −23.9 | **−24.3 / −25.1** |
| 86 | +6.3 / +1.9 | −17.4 / −21.9 | **−23.7 / −23.8** |
| 120 | +2.8 / +1.0 | −22.1 / −23.1 | **−24.9 / −24.1** |

**差值几乎恒定：左 −24.8° ± 1.0°，右 −24.4° ± 0.8°（f0 除外）。** 这正是“常量 yaw 修正”可行的依据。

### 4.3 预设 Biped rest 被导入重置

在 `loadMocapFile` 之前，于 Figure Mode 把脚 rest 从 0°/0° 转到 **+20.6°/+17.3°**（与源 BVH 的静止脚一致）：

| 阶段 | 左 rest yaw | 右 rest yaw |
| --- | ---: | ---: |
| 新建 Biped | 0.0 | 0.0 |
| 导入前手动旋转后 | **+20.6** | **+17.3** |
| `loadMocapFile` 之后 | **0.0** | **0.0** |
| 第 83 帧动画 | −14.06 | −25.11 |

**导入器把 Biped 的脚 rest 重置为 0°，动画结果与不预设完全相同。** 因此“先对齐导入 Biped 的 rest”不是修复。

### 4.4 female 上改 Figure Mode rest 无效

female 场景（`AutoBackup01.max` 副本），第 83 帧：

| 状态 | 左 rest yaw | 右 rest yaw | 左动画 yaw | 右动画 yaw |
| --- | ---: | ---: | ---: | ---: |
| 原始 | +8.70 | +8.70 | −19.29 | −29.29 |
| 在 Figure Mode 各向外转 29.5° 后 | **+38.20** | **+38.20** | **−19.29（不变）** | **−29.29（不变）** |

**Biped 在动画已存在时，改 Figure Mode 的脚 rest 不会改变关键帧的世界脚朝向。** 这也说明 `.bip` 的脚动画是“已烘焙”的，不能靠 rest 对齐补救。

### 4.5 `.bip` 与 female 的数值

| 场景 | 第 83 帧 L/R | rest yaw | rest 踝→趾 drop |
| --- | --- | ---: | ---: |
| 新建 Biped + BVH | −14.1 / −25.1 | 0 / 0 | 0.0601（与源一致） |
| 新建 Biped + `.bip` | −20.9 / −34.4 | 0 / 0 | 0.0909（`.bip` 的 figure 斜率不同） |
| female 场景（用户） | −19.3 / −29.3 | +8.7 / +8.7 | 35.6°（6.60 cm / 9.21 cm） |

- `.bip` 的源 figure 与默认 Biped 的脚斜率不同（0.0909 vs 0.0601），所以 `.bip` → 新 Biped 的右脚步误差更大（−34.4°）。
- female 的 rest/figure 再叠加约 −4.5°，所以用户看到约 −29°。
- **共同的主项是 BVH 导入的 −24.5°**；figure 差异是次级项（0–10°）。

### 4.6 鞋底 pitch/roll 没有被 `.bip` 改坏

第 83 帧，用 Foot 骨骼轴换算鞋底法线（`sole normal = −row1`，因为 Biped 脚骨 rest 的 row1 向下）：

| | 源 BVH | female Max |
| --- | --- | --- |
| 左脚 倾角 / 前倾 / 横向 | 23.7 / 20.8 / 12.2 | 24.0 / 20.4 / 13.5 |
| 右脚 倾角 / 前倾 / 横向 | 29.7 / 25.1 / 9.3 | 29.7 / 26.8 / 11.9 |

差值都在 1–3° 内。**“脚掌不平”来自源动作本身**（细高跟的前倾 + 左脚踝内倒），不是 Max 的额外误差。female 的可见网格/鞋型不同，可能让同样的角度看起来更明显，但骨骼数据没有额外恶化。

### 4.7 视频与源姿态

- 第 83 帧正向：双脚并拢、脚尖朝前，鞋面看起来接近水平。
- 第 60/64 帧侧视：靴子是**细高跟（stiletto）**，脚踝在靴内本身就是跖屈。
- 源 SMPL-X 的 f83：左踝局部旋转约 X +14.4°（跖屈）、Z −11.9°（向内 roll）；右踝 X +14.1°、Z +16.3°。左踝的 roll 在 ExMR / FlowHMR 都存在，右脚的内倒 ExMR 更明显。
- 所以“脚掌前倾”一部分是正确的高跟拟合；“内扣”的 yaw 是 Max 导入问题，roll 是源推断问题，两者要分开处理。

---

## 5. 根因

```
源 BVH（脚 rest 外八 20.6°/17.3°；动画 world yaw ≈ +10.5°/+0.1°）
      │
      │  biped.loadMocapFile：
      │  - Biped 的脚 rest 被建为 0°（平行）
      │  - BVH 的局部踝旋转按 Biped 的 0° rest 解释
      │  - 源 rest 的 20.6°/17.3° 外八没有转成动画
      ▼
Biped（world yaw ≈ −14.1°/−25.1°；恒定 −24.5°）
      │
      │  saveBipFileSegment / loadBipFile：
      │  动画（含误差）原样保存；Figure rest 改动不影响动画
      ▼
female（world yaw ≈ −19.3°/−29.3°；figure 再叠加约 −4.5°）
```

关键点：

1. **BVH 的脚 rest 外八写在 OFFSET 里**，不在动画通道里；Biped 导入只搬局部旋转，不搬 rest 的 yaw，所以外八被丢掉，表现为内旋。
2. **导入器会把任何预设的 Figure 脚 rest 重置为 0°**（4.3 节），因此不能在导入前“摆好脚”。
3. **导入后的动画是烘焙的**：改 Figure rest 不改变世界脚（4.4 节），所以不能在导入后靠 rest 对齐补救。
4. `.bip` 保存/加载本身无损；它只是把第 2 步的误差保存下来。`交接文档_3dsMax头部前倾.md` 里“`.bip` 往返无损”的结论对 Head 成立，对 Feet 也成立——但**“BVH→Biped”这一步对 Feet 不是无损的**，那份文档当时没有量脚。

---

## 6. 修复方案

### 方案 A（现有文件的止血，推荐先做）

因为误差是常量，直接在**动画**上补偿，不要动 Figure Mode rest。

- **在导入后的中间 Biped 上（保存 `.bip` 之前）**：两只 Foot 绕**垂直轴**、绕各自枢轴，向外转 **+24.5°**，覆盖整个 0–300 帧并打关键帧。
  - 依据：4.2 节的差值（左 −24.8° ± 1°，右 −24.4° ± 0.8°）。
  - 然后保存 `.bip`；female 上的残差约 +4.5°，可按需再补一个小常量。
- **直接在当前 female 场景上**：两只 Foot 向外转 **+29°**（f60–f120 的差值约 +24.6°～+30.1°，平均约 +29°），覆盖全帧并打关键帧。
  - 第 83 帧修正后应接近源 BVH 的 +10.5°/+0.1°；抽查 f60/f82/f84/f86/f120，残差应在 ±2–5° 内。
- **不要**用 Figure Mode 改 rest（已验证无效）。
- **注意**：方案 A 的 +24.5° / +29° 是从“源 vs 目标”的测量差值得到的修正量；本轮**没有在 Max 里对动画 Foot 实际打关键帧后再复测**。落地时必须按第 7 节在 f0/60/82/83/84/86/120 上复测，确认轴、符号和残差。

### 方案 B（导出端，长期推荐）

在 `mocap/biped_bvh.py` 的 Biped profile 里输出**Biped 中性脚 rest**：

1. 把 Biped 副本的脚 OFFSET 的 yaw 改成 **0°（平行前向）**，同时把源 rest 的外八（20.6°/17.3°）**烘进踝的局部旋转**，保证在任何播放器里世界脚朝向不变。
2. 这样 `loadMocapFile` 看到的 rest 是 0°，与它自己重置出的 0° 一致，就不会再丢外八。
3. 目标 figure 的残差只剩 0–5°；如需完全一致，再按目标 figure 做一次常量校准。
4. 在 `export.json` 里增加 `rest_foot_yaw_deg` / `rest_foot_slope_deg`，方便 Max 侧核对。

> 方案 B 需要代码改动和真实 Max 回归；本轮只验证了“导入器会重置 rest、误差恒定”，没有实现/验证 B 的代码。

### 方案 C（替代链路）

- 使用 FBX（显式 rest 变换）或世界空间重定向，而不是 BVH 的局部旋转；BVH 不能表达任意 rest roll（`docs/USER_GUIDE.md:640-646` 已有说明）。
- 如果必须用 `.bip`，建议在 Max 侧用脚本按世界矩阵重定向，而不是依赖 `loadMocapFile` 的默认映射。

### 方案 D（脚掌不平，单独处理）

- `.bip` 没有加重 pitch/roll；源动作本身是高跟前倾 + 左脚踝内倒。
- 目标 female 若穿平底鞋：用 correction 的“脚底放平”方案（见上一轮的脚部分析）或在 Max 里单独压平脚踝；若穿高跟则保留。
- 这与 yaw 修正互不影响，建议分开验证。

---

## 7. 验证清单

1. **源 vs 修正后的 Biped**：f0/60/82/83/84/86/120，两脚 yaw 差 < 2°（方案 A 的常量修正后）。
2. **确认修正点在动画上**：再次进入 Figure Mode 改 rest，f83 的世界 yaw 不应改变（Biped 的特性）；确保关键帧确实写进了 Foot 的旋转轨迹。
3. **female 端**：第 83 帧两脚 yaw 接近源 BVH 的 +10.5°/+0.1°；抽查 f60/f120，残差 < 5°。
4. **鞋底**：pitch/roll 与源一致（倾角约 24–30°，前倾约 20–27°），没有被 yaw 修正带偏。
5. **接触**：脚在地面的高度/滑移不因旋转出现穿插或滑动；如果 female 有 foot IK，先关掉再验证。
6. **另一条 take**：用 `mandance.bvh/.bip` 复测，确认导入的常量差是否仍约 −24.5°；若是，方案 A/B 的常量可以复用；若不是，需要按 rig/片段校准。

---

## 8. 3ds Max 无头验证方法（本轮实测可用）

```bat
"C:\Program Files\Autodesk\3ds Max 2016\3dsmax.exe" -q -silent -mip -U MAXScript "<脚本绝对路径>"
```

- 本轮直接 `3dsmax.exe` 的方式在 PowerShell 下可运行；`3dsmaxcmd` 有时会停在 “Unregistered Version” 对话框（脚本已经写完输出，但进程不退出），需要 `TaskStop` 清理，不要误杀用户的会话。
- 脚本规则（沿用 `交接文档_3dsMax头部前倾.md` 第 8 节）：
  - 整个脚本包在 `( ... )` 里；顶层不要出现 `local`（放在第一个 `(` 后的块内可以）。
  - 末尾必须 `quitMAX #noPrompt`。
  - 用 `System.IO.File.AppendAllText` 写输出，避免 `format to:` 的缓冲导致看不到中间结果。
  - `Biped_Object` 没有 `.pos`，用 `node.transform.translation`。
  - `biped.createNew 1.64 1.0 [0,0,0]`；`biped.loadMocapFile ctrl "x.bvh"`；`biped.loadBipFile ctrl "x.bip"`；`figureMode = true/false`；关键操作后 `sleep 0.4–1.0`。
- **不要**在用户的 `female.max` 上直接跑；复制 `AutoBackup01.max` 到临时目录再打开。本轮没有保存任何场景。

---

## 9. 产物与复现

诊断脚本与输出在 `temp/diag_feet/`（`temp/` 未跟踪，不入库）：

| 文件 | 作用 |
| --- | --- |
| `yaw_hip.py` | 解析源 BVH，按髋线/身体坐标算两脚 yaw |
| `bvh_feet.py` / `feet22.py` | 52/22 骨 BVH 的脚向量、鞋底法线、倾角 |
| `smplx_feet.py` / `render_views.py` | SMPL-X 网格鞋底平面拟合与多视角渲染 |
| `max_foot3.ms` / `max_foot3.txt` | female 场景逐帧脚 yaw/脚骨轴 |
| `max_rest.ms` / `max_rest.txt` | female 的 Figure Mode 脚 rest |
| `max_fix_test.ms` / `max_fix_test.txt` | 改 female rest 8.7°→38.2° 后动画不变的实验 |
| `max_final.ms` / `max_final.txt` | BVH→新建 Biped vs `.bip`→新建 Biped |
| `max_final2.ms` / `max_final2.txt` | 导入前预设 rest 被重置的实验 |
| `max_final3.ms` / `max_final3.txt` | BVH→Biped 的 7 帧扫描 |
| `max_scene.txt` | 自动备份场景的对象清单 |

复现步骤：

1. 复制 `AutoBackup01.max` 到临时目录；
2. 用 `yaw_hip.py` 得源 BVH 的 yaw；
3. 用 `max_final*.ms` 在新建 Biped 上复现导入/`.bip`；
4. 用 `max_foot3.ms` + `max_rest.ms` 在 female 副本上复现 rest 与动画；
5. 对比第 4.2 / 4.4 节的表。

注意：脚本里的绝对路径是本轮的临时路径（`C:\Users\liuhaibin\AppData\Local\Temp\bvh_diag`）；复制到别处后需改路径。

---

## 10. 变更清单

| 文件/数据 | 状态 |
| --- | --- |
| `docs/交接文档_3dsMax脚部内扣.md` | **新增（本文）** |
| `temp/diag_feet/` | 新增诊断脚本/输出（未跟踪） |
| `mocap/biped_bvh.py`、`mocap/export_copy.py` | **未改** |
| 用户工程 / `female.max` / 桌面 `.bvh/.bip` | **未改**；只读副本在临时目录 |
| 用户的 Max 会话 | 未触碰；批处理进程已清理 |

---

## 11. 关键数字速查

- 源 BVH f83：L **+10.5°** / R **+0.1°**；静止外八 **+20.6° / +17.3°**；踝→趾下倾 **26.0° / 26.4°**。
- BVH→Biped f83：L **−14.1°** / R **−25.1°**；常量差 **−24.6° / −25.2°**；7 帧扫描左 −24.8°±1.0°，右 −24.4°±0.8°。
- 预设 rest：20.6/17.3 → 导入后 **0/0**，f83 不变。
- female rest：**+8.7°**；改成 +38.2° 后 f83 **不变**（−19.29/−29.29）。
- `.bip`→新 Biped f83：**−20.9° / −34.4°**（`.bip` 的 figure 斜率 0.0909 vs 源 0.0601）。
- female f83：**−19.3° / −29.3°**；相对源约 **−29°**。
- 鞋底倾角：源 23.7/29.7，female 24.0/29.7；前倾/横向差 1–3°。
- 方案 A 常量：导入后 **+24.5°**；当前 female **+29°**。

---

## 12. 不要重复的尝试

1. **不要在 `loadMocapFile` 之前调 Biped 的 Figure Mode 脚 rest**：会被导入重置为 0°，实测结果逐位相同（`max_final2.ms`）。
2. **不要在 female 加载 `.bip` 之后改 Figure Mode 脚 rest**：动画世界脚完全不变（`max_fix_test.ms`）。
3. **不要怀疑导出/BVH 转换**：源 BVH 的脚 yaw 正常，Generic/Biped 转换逐位一致。
4. **不要说 `.bip` 往返丢了脚**：`.bip` 本身无损；误差是 **BVH→Biped 导入**造成的，`.bip` 只是保存了它。
5. **不要用固定的 90° 共轭**（Head 文档的教训）：脚部是常量 yaw，不是轴交换；先量再补。
6. **不要只量 `Foot` 的位置**：必须量 `Foot`→`Toe0` 的 yaw，否则会把内扣当成正常。
