# X5 Crop 用户手册

- 当前开发版本：**V4.9 bounded safe crop**
- 当前稳定发布：**v4.2.8**

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户先提供 format；系统用
片夹尺度和 count 约束在原图坐标测量照片四边、重建 polygon，并在安全合同成立时写出单张
TIFF。

## 产品目标

完成标准是“不切掉真实照片内容”，不是唯一测量真实物理边界：

- `approved_auto` 表示最终 protection 后的输出满足有界安全合同。
- 输出可以比照片更大，相邻输出可以重叠，也可以带入少量邻片像素。
- Blank、named inference、缺少可见 separator 或多个 protection 后等价的 geometry，
  都不会单独导致 review。
- `needs_review` 只用于无法吸收的具体风险，例如 ordinal 或 primary slot ownership
  无法有界、已知内容可能被内切、geometry 越出 source/lane authority，或 observed
  rotation 没有共同可行区间。
- 读取、写出或复读失败属于 terminal failure，不是 `needs_review`。

## 安装

从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。解压后运行一次：

```text
macOS:   install/X5_Crop_Mac_install.command
Windows: install/X5_Crop_win_install.bat
```

安装器检查 `numpy`、`tifffile`、`imagecodecs` 和 `Pillow`。macOS 安装器只准备当前
Release 文件夹，不建立系统级信任。

将入口、启动器和 TIFF 放在同一文件夹：

```text
X5_Crop.py
X5_Crop_Mac.command 或 X5_Crop_win.bat
*.tif / *.tiff
```

```text
macOS:   双击 X5_Crop_Mac.command
Windows: 双击 X5_Crop_win.bat
```

macOS 无法双击时，在该文件夹的 Terminal 中运行：

```bash
/bin/bash X5_Crop_Mac.command
```

## 格式、模式与 count

| 输入 | 格式 | Full 张数 | Partial |
|---|---|---:|---|
| Return / `135` | 135 | 6 | 1..6 或 auto |
| `dual` / `135 dual` / `135-dual` | 135 双条 | 12 | 不支持 |
| `half` | 半格 | 12 | 1..12 或 auto |
| `xpan` | XPan | 3 | 1..3 或 auto |
| `645` | 120-645 | 4 | 1..4 或 auto |
| `66` | 120-66 | 3 | 1..3 或 auto |
| `67` | 120-67 | 3 | 1..3 或 auto |

Format 始终由用户提供，runtime 不自动猜格式。

Count 入口规则只有一套：

- Full 规范化为 `fixed_full`；显式 count 只接受该格式的默认张数。
- Partial 输入整数时为 authoritative `explicit`。
- Partial 在命令行省略 `--count`、输入 `--count auto`，或交互时直接回车，均为 `auto`。
- 没有独立 `--auto-count` 参数。
- Auto 先唯一匹配 scan canvas，再输出该片夹对当前 format 的全部有效 slots。它不推断
  或声明真实照片张数。
- 文件名中的 `X5_<count>` 只可用于 validation，不会进入 detector、prior、score、
  Gate 或 runtime selection。

Partial slot 数表示片夹容量或用户 explicit request，不表示可见照片张数。前导、尾随与
中间 blank 均保留。`135-dual` 先匹配完整画布，再分为两个 canonical lane；输出顺序为
`lane:0/1..6`、再 `lane:1/1..6`。每个输出同时记录 global ordinal 与 lane-local
identity。

## 运行

普通命令：

```bash
python3 X5_Crop.py . --format 135 --strip full --report
```

Partial explicit：

```bash
python3 X5_Crop.py . --format 135 --strip partial --count 3 --report
```

Partial auto：

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --count auto --report
```

垂直片条可以显式指定：

```bash
python3 X5_Crop.py . --format 120-66 --strip partial --layout vertical --report
```

`--layout auto` 是默认值。并发默认 `--jobs 2`；普通运行可显式提高到最多 3 个 worker，
诊断最多 4 个。`--jobs 3` 适合内存充足且一次处理至少三张 TIFF 的机器；它会提高峰值
内存压力，因此不作为默认值。正式性能认证仍固定使用 `--jobs 2`。

```bash
python3 X5_Crop.py --help
```

## 检测与安全包络

每张 TIFF 只建立一次 base gray 和 image statistics。Scan canvas 先按 format 与容量筛选，
再根据像素长宽比唯一匹配；不会选择“最近 profile”。Long/short px/mm 由
`ScanCanvasEvidence` 分别拥有，TIFF DPI/PPI 只作为输出 metadata。

当前片夹 catalog：

| Profile | 物理尺寸 | 适用格式与最大张数 |
|---|---:|---|
| `135_standard` | `232 × 32.22 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_narrow` | `232 × 25.4 mm` | 135 ≤ 6；half ≤ 12；XPan ≤ 3 |
| `135_dual` | `232 × 63.44 mm` | 135-dual ≤ 12 |
| `120_standard` | `226 × 60 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_224_5` | `224.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_223` | `223 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 3 |
| `120_wide_188_5` | `188.5 × 63.44 mm` | 645 ≤ 4；66 ≤ 3；67 ≤ 2 |

Pixel observation、physical constraint 与 search proposal 是三层不同权限：

- 二维 pixel measurement 产生 transition、line、support、residual、angle 与 measurement
  uncertainty；
- format、count、scale、`±0.5 mm` aperture tolerance、lane 与邻接只筛选或推断；
- Grid、outer 与 corridor 只限定查询域和顺序，不能成为照片边。

Top/bottom 在 ScanCanvas 与 format 给出的窄 corridor/完整 halo 中测量，每帧独立拥有
intercept、support 与 uncertainty。Start/end 通过覆盖全部允许平移的无缝 query tiles
寻找；系统可以从任意内部边或 trailing edge 向前/向后重建序列，不要求 outer 先找到第一
张。Content 只帮助 ownership 和 containment，不创建边。

每张非空照片形成 source-coordinate polygon。候选先完成物理兼容连接，再组成完整
`FrameGeometryState`、去重和 dominance；超过两个 observed non-dominated states 时在
截断前 unresolved。Ordered DP 每帧最多保留两个 observed states 和一个 model-only/blank
state，不枚举 auto occupancy。

照片安全包络按以下顺序生成：

1. measurement uncertainty 或 inference uncertainty；
2. 1 source-pixel interpolation allowance；
3. 固定毫米 protection；
4. source/lane clipping。

Partial auto 的空 slot 使用独立 `grid_inferred_blank` geometry，不冒充照片 observation。
Deskew 只由 selected observed top/bottom lines 的共同 angle interval产生；零角度有共同
证据时使用 identity，否则在 `2°` 内使用 observed rotation。每个 approved ROI 最终从原
TIFF 做一次 inverse-affine sampling。

## Gate、状态与原因

`CandidateGate` 固定检查十项候选事实：

```text
scan_canvas_authority
source_content_measurement
grid_search_coverage
output_slot_count
slot_ordinal_assignment
slot_ownership
known_content_containment
source_lane_geometry
output_protection
output_transform
```

只有 `DecisionGate` 创建 `approved_auto`、`needs_review` 和 typed reasons。常见 review
原因包括：

- `scan_canvas_authority_unavailable`
- `requested_count_unfulfilled`（fixed/explicit）
- `capacity_output_slot_count_unfulfilled`（auto）
- `grid_search_coverage_outcome_risk`
- `slot_ordinal_assignment_unresolved`
- `slot_ownership_unbounded`
- `known_content_containment_unbounded`
- `source_lane_geometry_invalid`
- `output_protection_unavailable`
- `output_transform_unavailable`

## 输出、report 与诊断

普通自动批准会生成：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  ...
  _debug_analysis/
  needs_review/
  x5_crop_report.jsonl
  x5_crop_summary.csv
  x5_crop_run_manifest.jsonl
```

只有启用相应选项时才写 Debug 或 report：

- `--report`：写 current JSONL/CSV。
- `--debug-analysis`：在 `_debug_analysis/` 写四层 JPG，依次展示 source/lane authority、
  pixel measurement 与 selected observed lines、selected source photo geometry，以及
  protected product output。Review 候选只作 audit，并明确标记 `NOT EXPORTABLE`。
- `--diagnostics`：只读诊断；隐含 report、Debug Analysis 与不复制 review 文件。它保留
  同一 DecisionGate 结果和 final boxes，但不写 frame TIFF。
- `--no-copy-review-files`：不复制需要 review 的原 TIFF。

Current report：

```text
schema_id       = detection_report
schema_revision = source_coordinate_photo_geometry_v1
```

Report 保存 count policy、selected profile、measurement coverage、search proposals、
global/lane-local slot identities、observed/inferred provenance、完整 states 与竞争证据、
两种 translation assessment、query/DP/memory receipt、safe/protected envelopes、两级
Gate、transform、final boxes 与 TIFF fidelity receipt。全量 raw transitions 和 content
components/row runs 不逐项展开，只保存 coverage、数量、canonical row-run digest 与
component derivation；selected observations 和完整候选 states 仍可审计。Report 是审计
产物，不是 cache。

## TIFF 保真与错误

原 TIFF 永不修改。每个 approved ROI 只从原图采样一次；写出后立即复读，并检查：

- dtype、axes、shape 与通道结构；
- Photometric、BitsPerSample、SampleFormat 与 planar configuration；
- ICC profile/色彩空间；
- resolution 与 resolution unit；
- description、datetime、software 和支持的 metadata tags；
- 像素逐值相同；
- `same` 保持源 NONE/LZW 等已知无损压缩，`none` 写无压缩 TIFF。

读取、写出、原子替换或复读失败会记录独立 `FailedInput` 与 terminal stage；不会改写已经
得到的 DecisionGate 判断，也不会生成成功 receipt。

## 验证声明边界

当前 accuracy completion 只由九张 source-SHA-bound、用户确认 geometry 的黄金样片支撑，
展开为 14 个 fixed/explicit/auto 场景。八张 nominal 用于参数冻结并参与最终验收；S098
必须通过安全验收，但不参与 nominal calibration。Approved 场景检查 source footprint
完整包含 confirmed polygon、零 inward loss、可重算 extra area 和正式 TIFF 复读。S055
review 场景必须保存黄金安全 state 与 protection 后仍不等价的竞争 state，且正式 TIFF
数为零。

111-source cohort 是 `diagnostic_unreviewed`，不产生 accuracy verdict。Filename
`pass/unknown` 与 filename count 不产生 expectation。全部记录必须 terminal，但只由
crash、hang、非法 schema、消费未完成 query、无界 query/DP/memory、正式 TIFF 损坏或
source/lane authority 逃逸阻断工程验收。
单输入临时内存按 `10 × source pixels + 32 MiB` 的线性上界验收。

正式性能固定 24 张真实 TIFF、`--jobs 2` 和 168 个 status-independent I/O tasks。每版先
完成真实 detection/decision，再做同一冻结 sampling/write/readback workload；不得导出
review candidate。V4.9 三组 paired total-wall 的中位数必须 `<=5.0 秒/输入`，并在 MAD
噪声之外快于固定 V4.2.8 commit。

`real_holdout = unavailable`。未覆盖的 XPan、120-645 只具有 physical-rule 与 synthetic
contract coverage，不据此制造 runtime review。

## 移除与许可

删除 X5 Crop 文件夹即可移除程序和该文件夹中的输出。安装的 Python packages 可能被其它
程序共用，X5 Crop 不提供批量卸载脚本。

许可证：MIT。发布包根目录包含 `LICENSE`；GitHub 上也可查看
[完整文本](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)。
