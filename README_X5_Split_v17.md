# X5_Split_v17

`X5_Split_v17.py` 是用于切分 X5 单条胶片 TIFF 长条图的速度优化版。

这一版的目标是：保留目前最有价值、性价比最高的检测能力，同时把 v14–v16 中耗时较高且在极端欠曝图上收益不稳定的多阶段补救链从默认流程中移除。

## 主要变化

### 1. 默认 bleed 改为 10px

每张输出图默认上下左右各额外保留 10px：

```bash
--bleed 10
```

可单独设置横向和纵向：

```bash
--bleed-x 10 --bleed-y 10
```

关闭 bleed：

```bash
--bleed 0
```

### 2. 保留 deskew，但仍可关闭

默认：

```bash
--deskew auto
```

脚本会先判断整条胶片是否倾斜；可信时先小角度旋正，再进行外框、分割线、片距和画幅尺寸检测。

完全关闭旋正：

```bash
--deskew off
```

更积极旋正：

```bash
--deskew strict
```

### 3. 保留检测专用增强图，但加入快速跳过

默认：

```bash
--analysis-enhance auto
```

v17 仍会使用检测专用增强分析图帮助 deskew 和欠曝样片判断，但新增了快速策略：

```text
如果 base 检测结果已经足够稳定，自动跳过增强候选检测管线。
```

这样普通片不会为额外候选付出多次完整检测成本。

强制继续评估增强候选：

```bash
--analysis-no-fast-skip
```

极端欠曝图可用更积极模式：

```bash
--analysis-enhance strict
```

### 4. 增强边缘候选改为按需运行

v13 之后的增强边缘候选对少数欠曝图有帮助，但它本身是一次额外完整检测。v17 默认：

```bash
--analysis-edge-candidate auto
```

只有当 base / enhanced 候选仍然证据较弱时才运行。

可选值：

```bash
--analysis-edge-candidate off
--analysis-edge-candidate auto
--analysis-edge-candidate always
```

### 5. 移除 v14–v16 的默认慢速补救链

v17 的默认流程不再启用这些后续复杂逻辑：

```text
side-refine
partial-edge-refine
partial-side-complete
partial-outer-refine
```

原因是：它们在部分极端欠曝图中并不总是优于理论位置裁切，却明显增加运行时间。v17 会接受这些旧参数作为兼容 no-op，避免旧命令直接报错，但不会执行对应慢速流程。

## 依赖安装

### macOS

```bash
python3 -m pip install -U numpy tifffile imagecodecs Pillow
```

### Windows PowerShell

```powershell
py -3 -m pip install -U numpy tifffile imagecodecs Pillow
```

## 常规使用

### macOS dry-run

```bash
python3 X5_Split_v17.py . --debug --dry-run --report
```

### macOS 正式输出

```bash
python3 X5_Split_v17.py . --debug --overwrite --report
```

### Windows dry-run

```powershell
py -3 X5_Split_v17.py . --debug --dry-run --report
```

### Windows 正式输出

```powershell
py -3 X5_Split_v17.py . --debug --overwrite --report
```

输出目录默认是：

```text
split_output/
```

debug 图位于：

```text
split_output/_debug/
```

## 胶片格式与扫描布局

v17 现在支持用 `--format` 指定胶片格式，用 `--layout` 指定扫描排列。`--count` 不再必须写；不写时会按格式使用默认每条张数。

默认 `--format auto --layout auto` 会先读取 TIFF 尺寸：`X > Y` 判为横向，`Y > X` 判为竖向；再用片夹长短边比例区分 35mm 家族和 120 家族。35mm 片夹更窄更长，120 片夹相对更宽更短；DPI 改变不会影响这个比例。

| 格式 | 单张比例 | 默认每条张数 | 自动识别 |
|---|---:|---:|---|
| `135` | `3:2` | `6` | 支持 |
| `half` | `3:4` | `12` | 手动指定 |
| `xpan` | `65:24` | `3` | 手动指定 |
| `120-645` | `4:3` | `4` | 支持 |
| `120-66` | `1:1` | `3` | 支持 |
| `120-67` | `4:5` | `3` | 支持 |

布局可选：

```text
single-horizontal
single-vertical
```

脚本现在只处理单条横向或单条竖向，不再检测或裁切任何双条扫描。

示例：

```bash
python3 X5_Split_v17.py . --format 135 --layout single-horizontal --debug --report
python3 X5_Split_v17.py . --format half --layout single-horizontal --debug --report
python3 X5_Split_v17.py . --format xpan --layout single-vertical --debug --report
python3 X5_Split_v17.py . --format 120-66 --layout single-vertical --debug --report
python3 X5_Split_v17.py . --format 120-645 --layout single-horizontal --debug --report
python3 X5_Split_v17.py . --format 120-67 --layout single-vertical --debug --report
```

片头/片尾或特殊条数可以显式覆盖：

```bash
python3 X5_Split_v17.py . --format xpan --count 2 --layout single-horizontal --debug --report
python3 X5_Split_v17.py . --format half --count 10 --layout single-vertical --debug --report
```

自动格式识别只使用 TIFF 的片夹几何，不读取目录名提示。第一层逻辑是片夹比例：长短边比大于约 `6` 视为普通 35mm `135`，小于约 `6` 视为 120 家族。120 家族内会先按片夹比例做默认猜测，再用 `120-645` / `120-66` / `120-67` 的 full 几何竞争做保守纠偏。`half` 和 `xpan` 出现较少，为了普通 135 的速度和准确率，不参与 `--format auto`，需要手动指定。低置信结果会进入 `needs_review`，避免把片头、欠曝、弱分隔等困难样本强行裁错。

`--deskew auto` 会按布局选择目标方向：横向条带旋正到水平，竖向条带会先在转置检测图上估计倾斜，再把原图旋正到垂直。

## 条带完整性

`--strip-completeness` 控制脚本如何看待一条胶片是否填满片夹：

```text
auto
full
partial
```

- `full`：完整条。135 默认 6 张，half 默认 12 张，66 默认 3 张，645 默认 4 张。优先使用规则等距，适合高置信自动裁切。完整条几何稳定时，脚本会按格式使用更通用的 full 几何放行规则。
- `partial`：片头、片尾或不满片夹。脚本会先用 full 检测看到的分隔证据预筛可能张数，再尝试该格式允许的候选；低张数候选会更保守，低置信仍进入 `needs_review`。
- `auto`：所有格式都先试 `full`，高置信就通过；如果 full 低于阈值，再试 `partial`，仍不稳就标记待复核。`xpan` 和所有 120 格式既可能是完整条，也可能不满片夹，所以 auto 会把 full 失败自然转入 partial，而不是强行按默认张数裁切。

旧参数：

```bash
--leader-mode
```

现在作为兼容别名，等同于使用 `--strip-completeness partial`，并继续启用原来的 edge-refine learned 行为。

正常完整条会按 `full` 几何规则评估：如果框宽稳定、外框合理，并且分隔证据达到该格式的保守要求，即使部分分隔线证据较弱，也可以作为高置信自动通过。

## 高置信自动裁切 / 待复核分流

v17 默认只自动输出高置信裁切结果。每个文件会得到：

```text
approved_auto
needs_review
```

默认阈值：

```bash
--confidence-threshold 0.85
```

低于阈值时，脚本会写入 `split_report.jsonl` 和更适合人工浏览的 `split_summary.csv`，并跳过裁切 TIFF 输出。这样片头、片尾、欠曝、弱分隔、画幅宽度不稳定等困难文件会被标记出来，后续可交给专用脚本或人工处理。

如需把低置信原 TIFF 复制到待复核目录：

```bash
python3 X5_Split_v17.py . --debug --report --copy-review-files
```

默认复制到：

```text
split_output/needs_review/
```

也可指定目录：

```bash
python3 X5_Split_v17.py . --debug --report --copy-review-files --review-dir needs_review
```

如需恢复旧式行为，让低置信文件也继续导出裁切结果：

```bash
python3 X5_Split_v17.py . --debug --report --export-low-confidence
```

## 欠曝图建议命令

先测试默认 v17：

```bash
python3 X5_Split_v17.py . --debug --dry-run --report
```

如果默认仍有个别欠曝图不准，再试更强但仍相对克制的参数：

```bash
python3 X5_Split_v17.py . \
  --debug --debug-analysis --dry-run --report \
  --analysis-enhance strict \
  --analysis-edge-candidate auto \
  --outer-x-detect auto \
  --outer-refine strict \
  --grid-fit strict \
  --frame-size-fit strict \
  --frame-size-min-samples 1 \
  --frame-size-tolerance-ratio 0.02
```

Windows PowerShell：

```powershell
py -3 X5_Split_v17.py . ^
  --debug --debug-analysis --dry-run --report ^
  --analysis-enhance strict ^
  --analysis-edge-candidate auto ^
  --outer-x-detect auto ^
  --outer-refine strict ^
  --grid-fit strict ^
  --frame-size-fit strict ^
  --frame-size-min-samples 1 ^
  --frame-size-tolerance-ratio 0.02
```

如果某些欠曝图“追局部弱边缘”反而变差，可以主动回到更理论、更稳定的裁切：

```bash
python3 X5_Split_v17.py . \
  --debug --dry-run --report \
  --analysis-enhance off \
  --grid-fit strict \
  --frame-size-fit strict
```

或直接强制等分：

```bash
python3 X5_Split_v17.py . --debug --dry-run --report --equal-split
```

## 常用参数

| 参数 | 默认 | 说明 |
|---|---:|---|
| `--bleed` | `10` | 每张输出图四周额外保留像素 |
| `--format` | `auto` | 胶片格式：`135` / `half` / `xpan` / `120-645` / `120-66` / `120-67` |
| `--layout` | `auto` | 扫描布局：单条横向、单条竖向 |
| `--strip-completeness` | `auto` | 条带完整性：先试完整条，低置信再试片头/片尾或不满片夹候选 |
| `--count` | 按格式 | 每条胶片中的张数；可用于片头/片尾覆盖默认值 |
| `--deskew` | `auto` | 自动检测倾斜并旋正 |
| `--analysis-enhance` | `auto` | 检测专用增强分析图 |
| `--analysis-no-fast-skip` | 关闭 | 强制评估增强候选，不做快速跳过 |
| `--analysis-edge-candidate` | `auto` | 增强边缘候选是否运行 |
| `--outer-x-detect` | `auto` | 初始左右外框检测策略 |
| `--outer-refine` | `auto` | 用内部片距反推外框 |
| `--grid-fit` | `auto` | 全局片距校正 |
| `--frame-size-fit` | `auto` | 同画幅尺寸校正 |
| `--equal-split` | 关闭 | 裁外框后强制等分 |
| `--confidence-threshold` | `0.85` | 自动裁切最低置信度，低于阈值标记为 `needs_review` |
| `--copy-review-files` | 关闭 | 将低置信原 TIFF 复制到待复核目录 |
| `--review-dir` | `split_output/needs_review` | 待复核复制目录 |
| `--export-low-confidence` | 关闭 | 低置信也继续导出裁切 TIFF |

## 输出保持策略

检测图只用于分析坐标。最终输出仍使用源 TIFF 或 deskew 后 TIFF 数据裁切，不使用增强图像素。脚本会尽量保持：

```text
dtype / 位深 / PhotometricInterpretation / SamplesPerPixel / ICC / 分辨率 / Orientation
```

写出后会重新打开输出 TIFF 校验关键属性。

## 什么时候用 v17

适合：

```text
日常批量处理
普通曝光片
轻微倾斜片
偶发欠曝片
需要更快运行速度的批量任务
```

如果某批图极端欠曝且默认 v17 不理想，优先尝试：

```bash
--analysis-enhance strict
--grid-fit strict
--frame-size-fit strict
```

如果追踪弱边缘仍不理想，建议接受理论位置或使用：

```bash
--equal-split
```
