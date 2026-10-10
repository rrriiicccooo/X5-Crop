# X5 Crop V5 用户手册（开发预览）

- 范围：仓库 `main` 上尚未发布的 V5 源码
- 当前公开稳定版：v4.2.8；命令与行为不同，请使用该版本随包文档
- 适用输入：format 与曝光 slot 数已知的 Hasselblad / Imacon X5 片夹扫描

## 产品行为

X5 Crop 用已知 format 的设计尺寸先验建立该 source 的有界物理模板，而不是做通用照片边界识别。只有
当整张 source 的每个 slot 都有通过当前风险准入、可直接使用的裁切时，才写出正式 TIFF；否则整张进入
`needs_review`，不单独抢救部分 slot。

裁切保护输入 TIFF 中已经可见的照片内容。被片夹遮住、没有记录进 TIFF 的画面不属于恢复范围；
可见画面及其倾斜角点必须完整保留。每条源 TIFF 共用一组 W/H；每个
Frame 请求一个固定的原图坐标窗口 `1.1W × 1.1H`，四边各为固定 5% 留边。脚本只选择窗口位置，
固定留边已包含基础保护，不另加固定尺寸留边。

可信证据要求的完整物理包络若无法放入固定框，整张 source 仍进入 `needs_review`；最高评分不能强行
自动通过。共享 H 候选共用同一固定框，不能通过并集扩大窗口。真实 TIFF 边缘可以 source-clip，
内部 lane 或其它 authority 边界不能通过缩小窗口绕过。

### Format 与 count

运行时必须提供 format。Count 可省略或明确指定：

- 省略 `--count`：确认使用匹配片夹的默认完整格数；
- `--count N`：确认实际有 N 个 slot；中间空曝光格也计数；
- count 必须为正数且不超过匹配片夹容量；
- `135-dual` 只有 12 格（每 lane 6 格）可自动处理，其它 count 进入 review。

默认完整格数：135=6、half=12、XPan=3、120-645=4、120-66=3；120-67 在普通片夹为 3、短片夹为 2；
135-dual 共 12。

V5 对所有 format 使用同一物理与安全合同。当前 development gold 尚无 `xpan`、`120-645`、
`135-dual` 的真实黄金样片，因此这些 format 是“Runtime 已实现、真实样片尚未验证”，不等同于已完成
准确度覆盖，也不会因此启用特殊禁用或宽松规则。

程序不会从文件名、画面、片夹容量或空白格猜 format 与真实照片数，也不会删除、合并或重排空 slot。
V5 没有 full/partial mode。

### 自动批准与人工检查

程序根据 format/count 建立共同 W/H 的物理模板，再用整条片带和局部边缘证据确定位置。直接观察到的
照片边界保留原生坐标；缺失边界只能由已确认的共同尺寸、位置锚点和经过检查的相邻关系推导。
格式比例或外侧支撑可以参与定位，但不能冒充直接照片边界或覆盖反证。

每个待输出照片格都必须有完整的可见内容保护、足够的位置证据和安全的输出范围。内容遗漏、源内边界
越界、未知必需边界、相互冲突或无法完整核验、保护的解释，都会使整张 source 进入 `needs_review`。
评分不能替代这些条件，也不能扩大固定框。

照片归属已确定而上下边存在多个完整解释时，程序可以用同一个固定框保护全部解释；只有所有解释都通过
内容包含及整张安全检查，才可自动批准。接触或重叠照片同样使用这些检查，证据不足时保留人工检查。

分隔材料的支持来自两侧边界实际相邻的扫描线；扫描线上存在中间边界时，该处材料不为外侧边界配对
提供支持。程序分别核查局部分隔与贯穿整张源图的分隔关系，证据不足的关系保留人工检查。

Debug Analysis 展示首选、备选和保留提案及其证据、覆盖结果与阻断原因，供人工检查。报告不改变裁切坐标
或自动批准条件；当前 Runtime 尚未使用开发排序分数作裁切选择。
首选无法形成完整裁切而备选已有完整方案时，报告仍保留该备选作为可检查提案，并显示原有阻断原因。
原生提案的完整保护范围无法放入固定框时，仍保留已拟合的照片位置供人工检查；报告保留完整保护范围
和预算失败，该提案不能取得自动输出权限。
更多直接边界支持另一种位置解释但残差不相容时，报告保留该备选及歧义原因，供人工核查。

选定 placement 后，程序才判断是否铺满片夹：只检查 outer 外侧能否再容纳一个 W，不回头搜索或居中。
135-dual 两条 lane 都必须满足完整性。

## 固定原图坐标窗口、内容保护与 deskew

每条源 TIFF 使用共同 W/H。每个 Frame 的请求窗口固定为：

```text
source-space window = 1.1W × 1.1H
per-side margin = 5%
```

固定框只允许由脚本选择位置，不能因测量、残差、方向或评分调整窗口尺寸。它必须完整包含 TIFF 中可见的
照片内容，包括倾斜角点；可信证据要求的完整物理包络若无法放入固定框，整张 source 进入 `needs_review`。
只要 TIFF 中可见的照片内容完整位于固定框内，框内定位偏移不单独构成拒绝原因。

独立证据唯一确定照片上下边时，程序使用这些坐标选择固定框位置，不把实测高度改成框内推定高度。
连续 outer support 只有在可信的完整物理包络能够放入固定框时才可作为位置证据；只观察到局部支撑不能
外推整段外框，校准也不能把 support 冒充照片边界。缺少、冲突或未闭合的证据仍进入 Review。

真实 TIFF 外缘可以 source-clip，并在报告中明确记录；源边缘裁剪只针对实际存在的源像素，不会扩大或
缩小内部照片边界。内部 lane 或其它 authority 越界继续进入 review，不能通过缩小窗口绕过。固定框不能
通过并集扩大。

二维内容只在最终固定框上作保守否决：可靠内容越过固定框边界会阻止自动输出，框内偏移不单独改变位置。
通过一侧边界与共同宽度推导另一侧时，完整允许的位置范围用于选择固定框位置，不能因此调小窗口或绕过
内容保护。采样点较少但已有坐标依据的局部边界仍会保留。

Deskew 是自动批准后的可选整理，不参与检测或 Gate。`--deskew auto` 仅在两侧共同支持稳定的小角度时
旋转；证据不足、冲突或超出清理范围时保持原始方向。`--deskew off` 完全跳过观测。旋转时，图像与已
确认安全的 polygon 使用同一 affine transform，再取轴对齐包络，因此角落可能出现少量黑色 no-data，
但不能切掉已保护内容。Deskew 的轴对齐包络、真实 TIFF 边缘 clipping 和整数取整都可能改变最终输出的
像素宽高；固定尺寸指原图坐标窗口。

## 安装开发源码

请取得完整仓库 checkout；不要只复制 `X5_Crop.py`，也不要把 GitHub 自动生成的 Source code 压缩包
当作稳定发布包。普通用户应下载 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases)
中的 v4.2.8。

V5 开发源码支持 Python 3.12–3.14：

- macOS：`tools/install/X5_Crop_Mac_install.command`
- Windows：`tools/install/X5_Crop_win_install.bat`

未来 V5 Release 包中的相同安装器位于 `install/`，不带 `tools/` 前缀。

安装器寻找 64-bit Python 3.12–3.14，复用符合版本要求的依赖，并通过已识别的包管理器补齐或更新
其余依赖；来源不明时会在修改前停止。Homebrew 不是前置条件，也不会建立私有虚拟环境。

## 输入合同

V5 production 输入必须满足：

- 单页 TIFF；
- unsigned 16-bit；
- RGB 三通道、contiguous planar configuration；
- `NONE`、`LZW`、`DEFLATE` / `ADOBE_DEFLATE` 或 `ZSTD` 无损压缩；
- TIFF Orientation 1–8。

域外文件成为 `runtime_error`，不会静默转换。读取时规范化 Orientation，正式输出写
`Orientation=1`。

## 运行

在仓库根目录运行命令，输入可以是一个 TIFF 或扫描目录。交互模式使用
`python3 X5_Crop.py --interactive`，处理当前目录中的 TIFF。未来 V5 Release 包提供 macOS 和 Windows
双击启动器。

命令行示例：

```bash
python3 X5_Crop.py /path/to/scans --format 120-66 --count 2
```

主要选项：

- `input`：一个 TIFF 或目录，默认当前目录；
- `--output PATH`：全新输出目录；
- `--format`：`135`、`135-dual`、`half`、`xpan`、`120-645`、`120-66` 或 `120-67`；
- `-n, --count N`：显式 slot 数；省略表示确认默认完整 count；
- `--layout`：`auto`、`horizontal` 或 `vertical`；
- `--deskew`：`auto`（默认）或 `off`；
- `--jobs N`：source 并发，默认 1、上限 3；
- `--debug-analysis`：写 1,800 px 宽、高度自适应的三联诊断 JPG、开发报告和摘要，不写正式 TIFF；
- `--interactive`：交互确认 format、count、deskew 与 Debug Analysis。

没有 `--overwrite`。目标目录必须不存在；Debug Analysis 与正式裁切应使用不同的新目录，正式运行始终
重新读取原 TIFF。
运行期间若其他操作创建了同名目标，程序会保留它并报告输出错误；请选择新的目录重试。
文件系统无法保证原子不覆盖时也会停止发布。
macOS 上请将输出写入支持原子不覆盖操作的 APFS/HFS+ 卷；如需存放到 exFAT，完成后复制整个输出目录。

## 状态、输出与退出码

每个输入只有一个终态：

- `approved_auto`：写出完整的一组正式 TIFF；
- `needs_review`：不写照片，保留最小缺失事实与建议操作；
- `runtime_error`：该输入失败，其它输入继续。

Debug Analysis 显示模板、实际观察、winner/runner、画幅比例原始/保护区间及推导 H、固定原图坐标窗口的
尺寸与位置、内容保护证据和首个阻断原因。页面并标明
`DESKEW APPLIED`、`ROTATION NOT NEEDED` 或 typed `DESKEW SKIPPED`。它只读取同次检测事实，不会
重新求解。

开发报告另记录外侧区域的颜色连续性、弱信号和测量可用状态。这些观测用于核查外侧材料；
测量可用不代表已经识别为片夹，也不单独授权裁切。

默认输出：

```text
x5_crop_output/
  原文件名_01.tif
  原文件名_02.tif
  needs_review/
  _debug_analysis/
  x5_crop_report.jsonl
  x5_crop_summary.csv
```

退出码：

- `0`：成功发布且没有 `runtime_error`；
- `1`：已发布但含 `runtime_error`，或全部输入失败；
- `2`：命令行、输入集合或运行前检查失败；
- `3`：全新输出目录无法安全发布。

正式 TIFF 只由 `tifffile + imagecodecs` 读写，并检查位深、通道、ICC、resolution、支持的 metadata、
无损压缩和 `Orientation=1`。程序先写 staging，全部完成后一次 rename；已有目标不会被遍历、覆盖或
删除。

License: MIT — [GitHub LICENSE](https://github.com/rrriiicccooo/X5-Crop/blob/main/LICENSE)
