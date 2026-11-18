# 交接文档：3ds Max Biped 头部前倾（情人节 / female）

更新日期：2026-11-18
范围：`H:\MyProject\toyxyz_RGBMocap` 的 Head Posture（`mocap/correction.py`）、BVH 导出（`mocap/source_bvh.py`、`mocap/biped_bvh.py`）与 3ds Max Biped 侧验证
读者：接手继续做头部/颈部对齐、Biped 交付或 female 骨架修复的同学

---

## 1. 一句话现状

**GUI 与导出的 BVH 一致，`.bip` 往返无损；3ds Max 里"头/颈前倾"由两部分叠加：Head Posture 留下的源片前倾 + Biped 对 Head 局部旋转的映射误差。** 本轮把 `_HEAD_PITCH_THRESHOLD` 从 10° 降到 5°、`_HEAD_PITCH_MAX` 保持 35°（已由用户提交），情人节修正后中位从 12.40° 降到 5.00°，Max 里 251 帧从约 +17° 误差降到 +3°；**117 帧仍有约 +19° 的 Biped 映射误差**，属于遗留问题。

中途尝试过在 `biped_bvh.convert` 里给 Neck/Head 加 90° 共轭，**已验证失败并回滚**（会把俯仰误差转成横向误差，表现为"往左偏"）。

---

## 2. 结论分层

| 层 | 结论 | 证据 |
| --- | --- | --- |
| GUI ↔ 导出 BVH | 一致，Head Posture 的旋转完整写入 BVH | 报告 before/after；BVH Head 世界俯仰随修正变化 |
| `.bvh` → `.bip` | 姿态无损 | BIP117 与 MC117 的位置/轴逐位相同 |
| 默认 Biped ↔ female | **Neck/Head 世界旋转逐位相同** | 117 帧骨轴 `(-0.063,0.075,0.995)` / `(-0.048,0.338,0.940)` 两边一致 |
| female 显眼的原因 | 骨架比例 + 网格几何放大同一角度 | 颈段 27.7cm vs 10.3cm；头段 3.5cm vs 5.9cm；2 节 vs 4 节脊柱 |
| man_dance 问题不大 | Head Posture 未触发（bias=0），源头部本来直立/后仰 | 报告 before=after=−8.26°；117 帧 Max 反而 −7.97° |
| 情人节 明显 | 源头修正后仍有 +12.4° 前倾，再叠 Biped 映射误差 | 报告与 Max 逐帧对比 |

---

## 3. 度量口径

- **源（GUI）**：`correction_report.json` 的 `head_pitch_*_median_deg`，即 SMPL-X 头骨上轴相对胸廓的俯仰 `p`。
- **Max**：读 `Neck`/`Head` 节点的世界矩阵；Biped 骨轴 = 局部 X（矩阵 `row1`）。体坐标俯仰/横向量：
  `up = Neck − Spine3`，`left = L UpperArm − R UpperArm`，`fwd = left × up`，
  `pitch = atan2(h·fwd, h·up)`，`lateral = atan2(h·left, h·up)`。
- 源与 Max 用**同一公式、同一帧**对比；不跨口径比较绝对值。
- 注意：3ds Max 场景是 Z-up，BVH 是 Y-up；默认 Biped 面朝 +X（左=+Y），female 面朝 −Y（左=+X）。

---

## 4. 分析证据

### 4.1 Head Posture 本身

`mocap/correction.py`：

```
_HEAD_PITCH_THRESHOLD = 5.   (原 10)
_HEAD_PITCH_MAX = 35.        (原 25)
_HEAD_NECK_SHARE = .45
bias = clip(median(head_pitch) − threshold, 0, max)
```

情人节 exmr（301 帧）报告：

| 指标 | 阈值 10 / 上限 25 | 阈值 5 / 上限 35 |
| --- | ---: | ---: |
| bias | 25.00° | **32.40°** |
| 修正前中位 | 37.40° | 37.40° |
| 修正后中位 | 12.40° | **5.00°** |
| 修正后最大 | 28.19° | **20.79°** |
| 117 帧（SMPL p） | 15.92° | **8.51°** |
| 251 帧（SMPL p） | — | **6.86°** |

注意：只把上限改成 35 只多 2.4°（bias 被 `median − threshold` 限制），真正起作用的是阈值 10→5。

### 4.2 `.bip` 往返无损

同一 BVH，先 `loadMocapFile` 再存 `.bip`、再 `loadBipFile` 到新 Biped：

- `BIP117` 与 `MC117` 的 Spine3/Neck/Head 位置和骨轴逐位相同（7 位小数）。
- 文件大小约 1.30 MB，与用户手工生成的 `.bip` 一致。

### 4.3 默认 Biped 与 female 的骨轴

117 帧：

| | Neck 骨轴 | Head 骨轴 |
| --- | --- | --- |
| 默认 Biped | `(-0.063, 0.075, 0.995)` | `(-0.048, 0.338, 0.940)` |
| female | `(-0.063, 0.075, 0.995)` | `(-0.048, 0.338, 0.940)` |

结论：`.bip` 的旋转在两边完全一致，**female 的差异不在旋转**。

### 4.4 female 的骨架/几何为什么放大

female.max 的 Biped（Figure Mode 实测，cm）：

| 量 | female | 默认 Biped |
| --- | ---: | ---: |
| 脊柱节数 | **2** | 4 |
| 最后一节脊柱 → Neck | **27.7** | 10.3 |
| Neck → Head | **3.5** | 5.9 |
| Figure rest：Pelvis / Spine / Spine1 / Neck / Head | 103.5 / 115.8 / 130.8 / 158.5 / 161.9 | — |
| Neck 骨轴 rest | `(0, −0.327, 0.945)`，前倾约 19° | 竖直 `(0,0,1)` |

影响：

1. **颈段杠杆 2.7 倍**：同样 10° 颈部旋转，头部位移约 4.8cm（默认 1.8cm）。
2. **Head 枢轴偏上**：Head 枢轴距骨架顶部约 2cm（默认约 6cm），头网格绕更高的点转，脸/下巴摆幅更大。
3. **2 节 vs 4 节脊柱**：装 `.bip` 时目标 Spine 取源 Spine1、Spine1 取源 Spine3，躯干弯曲被重分配，颈根位置改变。
4. 角色本身**可见脖子短、头大、带发型**，同样角度在剪影上更明显。

### 4.5 man_dance 为什么问题不大

| | 情人节 | man_dance |
| --- | ---: | ---: |
| Head Posture | 施加 25°（后改 32.4°） | **未触发，bias=0** |
| 源中位 | +12.40°（后改 +5.00°） | **−8.26°（本来就直立/后仰）** |
| 117 帧源（体坐标） | −2.65°（旧修正） | −2.97° |
| 117 帧 Max | +22.78°（旧修正） | **−7.97°（反而略后仰）** |

映射误差两段都有（头相对颈的局部角都会从约 8° 变成约 16–20°），mandance 只是**没有前倾的底子可以叠加**。

### 4.6 Biped 的 Head 映射误差

单轴对照实验（其余关节全零，只给 Head/Neck/Spine 绕单轴 +20°）：

| 输入（源语义） | 应该是 | Max 实际 |
| --- | --- | --- |
| Head 绕 X | 俯仰 | 骨轴向侧向倒（roll） |
| Head 绕 Z | 横滚 | 骨轴向前/后俯仰（pitch） |
| Head 绕 Y | 偏航 | 绕骨轴扭转 |
| Neck 绕 X | 颈前俯 | 头位置向侧向移动 5.6cm |
| Chest2 绕 X | 胸廓前俯 | 胸廓向侧向移动 1.8cm |

即 X/Z 轴被交换。但这个映射**不是固定的 90° 旋转**：双轴输入的角度会变化，误差随帧变化（俯仰 17–26°，横向 ±15°）。

### 4.7 失败的尝试：90° 共轭（已回滚）

在 `biped_bvh.convert` 里对 Neck/Head 做 `R' = Ry(90°) R Ry(−90°)`，只影响 biped 副本，按 `head_posture` 开关。

验证结果（情人节，25° 旧修正）：

| 帧 | 源（俯仰/横向） | 修复前 | 修复后 |
| ---: | ---: | ---: | ---: |
| 117 | −2.65 / +2.77 | +22.78 / −2.33 | **+2.33 / +22.78** |
| 251 | +4.35 / −11.51 | +21.21 / +3.25 | **−3.25 / +21.21** |

`(pitch, lateral)` 从 `(p, l)` 变成 `(−l, p)`：误差**大小没变**，只是从俯仰搬到横向——用户看到的就是"往左偏"。**结论：固定 90° 共轭不能修，已 `git checkout` 回滚，当前 `biped_bvh.py` / `export_copy.py` 无改动。**

教训：只验证 pitch 会漏掉 lateral；必须两个量一起看。

---

## 5. 本轮实施与验证

### 5.1 代码

`mocap/correction.py`：

```diff
-_HEAD_PITCH_THRESHOLD = 10.
-_HEAD_PITCH_MAX = 25.
+_HEAD_PITCH_THRESHOLD = 5.
+_HEAD_PITCH_MAX = 35.
```

（用户已提交；`biped_bvh.py`、`export_copy.py` 保持原样。）

### 5.2 重跑情人节

- `correction.run(take, 'corrected_initial')`：3.15s，报告更新为 bias 32.40°、after 中位 5.00°。
- `export_project(take, 'corrected_initial')`：8.23s，`motion.bvh`、mixamo/BVH 资产全部重写。

### 5.3 Max 验证（默认 Biped；female 骨轴与之相同）

体坐标（俯仰/横向，度）：

| 帧 | 源 | Max（新） | 误差 |
| ---: | ---: | ---: | ---: |
| 0 | +4.86 / +0.86 | +6.07 / +19.35 | 俯仰 +1.2，横向 +18.5（离群帧） |
| 117 | −4.04 / −0.38 | +15.39 / −1.89 | **俯仰 +19.4** |
| 251 | +10.82 / +2.72 | +13.81 / +2.46 | **俯仰 +3.0，横向 −0.3** |

- 251 帧（用户报告的左偏/前倾帧）已基本对齐。
- 117 帧从旧修正的 +25.4° 降到 +19.4°，仍前倾；这部分是 Biped 映射误差，阈值解决不了。
- 0 帧横向 +18.5° 是离群帧（该帧头转过去了，横向分量对坐标系敏感）。
- 渲染：`temp/diag_head/v35_female_117.png`、`v35_female_251.png`。

### 5.4 库级影响（阈值 5）

| 片段 | 中位 | 旧 bias | 新 bias |
| --- | ---: | ---: | ---: |
| 情人节 / exmr | 37.4° | 25.0° | 32.4° |
| last_year_summer / flowhmr | 14.6° | 4.6° | 9.6° |
| last_year_summer / gvhmr | 13.7° | 3.7° | 8.7° |
| last_year_summer / exmr | 10.1° | 0.1° | 5.1° |
| 其余 12 条结果 | ≤8.8° | 0° | 0–3.8° |

只有 last_year_summer 会被多回正约 5°，需要回归目检。

---

## 6. 已排除 / 不要重复

1. **不是 `.bip` 或导出数据**：默认 Biped 与 female 的 Neck/Head 世界旋转逐位相同。
2. **不是 female"模型坏了"**：是 Figure Mode 比例（颈段 27.7cm、头段 3.5cm、2 节脊柱、枢轴偏上）+ 大头短脖的几何放大。
3. **不要用固定 90° 共轭**：已实测会把 pitch 误差搬到 lateral。
4. **不要用常量角度补偿**：误差逐帧变化 17–26°。
5. **不要用默认 Biped 的观感推断 female**：火柴人没有脸，同样角度不容易看出来。
6. **不要只量俯仰**：必须同时量横向，否则会把"左偏"当成成功。

---

## 7. 遗留问题与下一步

1. **117 帧残留 +19°**：Biped 对 Head 的映射误差，需要 Max 侧逐帧烘焙 Neck/Head 世界旋转（精确、可验证），或改用 FBX/直接重定向。
2. **female 骨架**：把 `spineLinks` 改成 3、把 Neck/Head 枢轴按角色解剖下移，存 `.fig`；或直接从 female 自己的 Biped 生成 `.bip`。
3. **阈值 5 的回归**：last_year_summer 三个结果多回正约 5°，需要目检确认不过度。
4. 若未来还要在 BVH 侧修：先做完整的 3 轴 + 双轴标定，拟合导入器对 Neck/Head 的映射再求逆；不要再猜 90°。

---

## 8. 3ds Max 无头验证方法（重要）

- **必须用 desktop-commander 的 `start_process`（shell=cmd）**；在 CodeBuddy 的 Bash 沙箱里直接起 `3dsmax.exe`，即使没有其他实例也会报 `adlm -104`（Usage tracking component）。
- 命令：

```
cd /d "C:\Program Files\Autodesk\3ds Max 2016" && 3dsmax.exe -q -silent -mip -U MAXScript "<脚本绝对路径>"
```

- 脚本规则：
  - 整个脚本包在 `( ... )` 里，**顶层不能出现 `local`**；
  - 末尾必须 `quitMAX #noPrompt`；
  - `L "text" + x` 会解析成 `(L "text") + x`，**必须写成 `L ("text" + x)`**；
  - `animationRange.end` 是 ticks（30fps 下 300 帧 = 48000），转帧号用 `(animationRange.end as integer)/160`；
  - 成功以**结果文件**为准，不看退出码（`quitMAX` 可能返回 0xC0000409）。
- 组合脚本（先建 Biped 再 `loadMaxFile female.max`）偶尔在 `loadMaxFile` 后停住；建议把"导入 BVH"和"打开 female"拆成两次运行。
- female.max：`F:\Comfy-Desktop\ComfyUI-Installs\Comfy-MotionCapture\3DModelTemplate\female\female.max`，单位厘米，Biped 2 节脊柱、164cm、面朝 −Y。

---

## 9. 产物与复现

全部在 `temp/diag_head/`（`temp/` 未跟踪，不入库）：

| 文件 | 用途 |
| --- | --- |
| `bvh_head3.py` | BVH 解析 + FK（52 关节） |
| `sagittal2.py` / `v35_pitch.py` / `lateral.py` | 源与 Max 的俯仰/横向对比 |
| `err_model.py` | 误差与头局部旋转的相关性 |
| `gen_variants.py` / `gen_chain.py` / `gen_neck.py` / `gen_spine.py` | 单轴/双轴/链条合成 BVH |
| `gen_real_fix.py` / `gen_fix2.py` | 真实片段的补偿变体（已证实失败） |
| `max_variants.ms` / `max_chain.ms` / `max_fix.ms` / `max_v35.ms` / `max_female.ms` / `render_v35.ms` | Max 侧测量与渲染 |
| `rerun_correct.py` / `rerun_export.py` | 重跑 correction + export |
| `prep_v35.py` | 把 `motion.bvh` 转成 biped 版 `v35.bvh`，并打印源头部俯仰/横向 |
| `max_v35.txt` / `max_corr_init.txt` / `max_variants.txt` / `max_female.txt` | 原始测量输出 |
| `v35_female_117.png` / `v35_female_251.png` | 新修正后的侧视渲染 |

桌面上的输入：`C:\Users\liuhaibin\Desktop\Person 1_3.bvh/.bip`（= 情人节修正版）、`rbgtest_nofixed.bvh`、`mandance.bvh/.bip`。

复现步骤：

1. 用 `runtime/python.exe` 跑 `rerun_correct.py`（correction）和 `rerun_export.py`（export）；
2. `prep_v35.py` 把 `motion.bvh` 转成 biped 版 `v35.bvh`；
3. 通过 desktop-commander 跑 `max_v35.ms`（测量 + 存 `v35.bip`）和 `render_v35.ms`（female 渲染）；
4. `v35_pitch.py` 汇总俯仰/横向。

---

## 10. 变更清单

| 文件/数据 | 状态 |
| --- | --- |
| `mocap/correction.py` | **已提交**：阈值 10→5、上限 25→35 |
| `mocap/biped_bvh.py`、`mocap/export_copy.py` | 90° 共轭实验已 `git checkout` 回滚，无 diff |
| 情人节 exmr take | `corrected_initial.pt`、`motion.bvh`、mixamo/BVH 资产已按新阈值重跑 |
| 文档 | 本文 |

---

## 11. 关键数字速查

- 情人节：301 帧 @30fps；源 head p 中位 37.40° → 5.00°（bias 32.40°）。
- 117 帧：SMPL p 15.92° → 8.51°；Max 体坐标 +15.39°（源 −4.04°，误差 +19.4°）。
- 251 帧：SMPL p 6.86°；Max +13.81°（源 +10.82°，误差 +3.0°）。
- 默认 vs female 骨轴：117 帧完全相同。
- female：颈段 27.7cm、头段 3.5cm、2 节脊柱；默认：10.3cm / 5.9cm / 4 节。
- man_dance：bias 0，源 −8.26°，117 帧 Max −7.97°。
