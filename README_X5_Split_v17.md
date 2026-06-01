# X5_Split_v17

`X5_Split_v17.py` 是用于切分横向 135 胶片 TIFF 长条图的速度优化版。

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
| `--deskew` | `auto` | 自动检测倾斜并旋正 |
| `--analysis-enhance` | `auto` | 检测专用增强分析图 |
| `--analysis-no-fast-skip` | 关闭 | 强制评估增强候选，不做快速跳过 |
| `--analysis-edge-candidate` | `auto` | 增强边缘候选是否运行 |
| `--outer-x-detect` | `auto` | 初始左右外框检测策略 |
| `--outer-refine` | `auto` | 用内部片距反推外框 |
| `--grid-fit` | `auto` | 全局片距校正 |
| `--frame-size-fit` | `auto` | 同画幅尺寸校正 |
| `--equal-split` | 关闭 | 裁外框后强制等分 |

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
