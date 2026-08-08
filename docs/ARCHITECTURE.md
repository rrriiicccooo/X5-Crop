# X5 Crop V5 当前架构

本文只描述仓库唯一 active V5 runtime 的运行流、数值合同和源码 owner。V4.9 仅存在于 Git
history 与更新日志；当前源码没有旧 schema reader、fallback、shim、feature flag 或并行
producer。版本变化见 [CHANGELOG.md](CHANGELOG.md)，按需交接见
[PROJECT_MEMORY.md](PROJECT_MEMORY.md)。

## 1. 产品合同

用户提供 format。Full 使用格式固定张数；partial explicit 严格使用用户 count；partial
auto 使用唯一匹配片夹对该 format 的容量。Runtime 不猜 format、真实照片张数或 filename
count。

检测采用固定格式模板放置模型。令 `P` 为所有满足正式像素证据、格式尺寸、source-wide
geometry、count/order、局部卷片关系、共同方向和 source/lane authority，且未被机械合同排除
的完整摆放：

```text
approved_auto 当且仅当：
  P 非空且每个 output slot 均有完整摆放
  direction、source geometry、ordinal、lane 与 transform 成立
  SafeCropEnvelope 包含 P 的全部 full safety footprints
  ActualOutput 位于每个 retained physical placement 的合法输出窗口内
```

逐边合法窗口固定为：

```text
start/end  每边 = frame_width_mm  × 5%
top/bottom 每边 = frame_height_mm × 3%
```

四边分别为闭区间硬上限：刚好达到上限通过，任意正超量失败。Canonical 只负责代表性
geometry、deskew、minimum guard 与报告排序，无权删除会改变安全 union 的摆放。

## 2. 唯一运行流

```text
format / count / ScanCanvas / lane authority
→ one TIFF decode and registered measurements
→ sequence profile + provisional cross profile
→ complete template proposals and phase groups
→ template-bound top/bottom evidence
→ SharedStripDirection
→ exact materialization
→ SourceFrameGeometry + NominalPitch + LocalAdvanceRelation
→ retained complete FormatPlacements
→ canonical representative
→ SafeCropEnvelope + direct-use assessment
→ CandidateGate → DecisionGate → Finalization
→ one chunked lane-safe inverse-affine sampling
→ validated TIFF / report / optional Debug Analysis
→ run manifest → journaled flat-output publication
```

权限只沿这条路径前进。不存在旧 sequence DP、short-candidate 笛卡尔积、best-score
placement、blank geometry、旧 schema reader、feature flag 或并行 producer。

## 3. Format、片夹与 source geometry

### 3.1 唯一物理 owner

`FramePhysicalSpec` 只拥有：

- `frame_width_mm` / `frame_height_mm`；
- aperture component；
- nominal gap 与允许的 local gap interval。

`ScanCanvasPhysicalSpec` catalog 单独拥有扫描画布、format fit 与有效最大容量；
`FrameCountRequest` 单独拥有 full、partial explicit 与 partial auto 的 count authority。Runtime
configuration 只在入口解析，然后以 typed input 传入下层。照片尺寸、扫描画布、count 与配置
不得合并为一个 registry owner。

格式尺寸 tolerance 只有一个全局 owner：

```text
frame width separation tolerance  = 1.25%
frame height separation tolerance = 0.40%
```

Tolerance 只判断观测边是否能属于同一设计模板，并在缺边推导时进入 full interval。它不是
search allowance、padding 或 direct-use budget。

### 3.2 联合 SourceFrameGeometry

每个 source 只有两个旋转等价 axis states：width 与 height。每个 state 联合保存 scale
`s` 和 normalized extent `q`：

```text
factor_min × s ≤ q ≤ factor_max × s
observed_extent_min / design_mm ≤ q ≤ observed_extent_max / design_mm
```

Scale 与真实尺寸 factor 始终相关，不能拆成可自由组合的独立区间。完整内部 opposite-edge
pair 可以收紧 source-wide state；第一张 start 或最后一张 end 的片夹遮挡只改变可见位置
约束，不改变真实照片尺寸。所有 frame 和双 lane 共享同一 source state，不存在逐帧或逐
lane scale。

120 的 54/56 mm component 分别保留。即使它们产生相同采样输出，也必须保留各自的物理
budget 约束。

### 3.3 NominalPitch 与局部卷片

理论节距直接消费联合 width state：

```text
frame_width_px(q) = frame_width_mm × q
pitch_px(q,s)     = frame_width_mm × q + nominal_gap_mm × s
```

相邻关系为：

```text
start[i+1] = start[i] + NominalPitch + confirmed_delta[i]
```

默认 `delta=0`。非零 delta 只能由一组相互一致的边缘事实证明；它只在该 adjacency 应用
一次，使后续相位整体平移，后续间隔恢复 NominalPitch。观测 gap 必须先与 format 拥有的
local gap interval 在同一 joint width scale 下求交；无交集的摆放违反硬物理合同。未确认的
宽 interval 不得逐格累积。

## 4. 测量与 template-first producer

### 4.1 一次测量

每个 TIFF 只建立一份 `source_gray`。所有 query 在执行前登记；未完整执行的 measurement
不能被消费。Search corridor、Grid、outer 与 expected position只决定 query band 和顺序，
不能创建首个照片位置或缩短 placement truth。

每个 lane 构建一份：

```text
sequence_profile  # start/end/separator
cross_profile     # top/bottom
```

Profiles 复用相同 pixel measurements，不增加 decode、第二次全图扫描或 image-sized evidence
field。Cross profile 保留固定分段的逐 trace runs；未知方向时不会先把整条 lane 平均成一条
线。方向建立后，同一批 registered transitions 可按方向投影到两个错开半格的固定物理 bin；
每个 trace 在每个 bin 最多保留一个确定 transition，所有满足 support/continuity 的 bins 全部
保留。该 multi-trace aggregate 回收了 v4.2.8 多段 profile 的有效能力，但不恢复候选评分、
top-K 或全图 evidence cache。

`SideTransitionRegion` 不拥有 slope。它保存 reciprocal-nearest tracking 得到的 transition
IDs、proposal interval、support、continuity、residual 与方向性 evidence；start/end 最终严格
正交于共同 top/bottom 方向。

### 4.2 PlacementAnchor

首个模板锚点必须同时满足：

- region 非 ambiguous；
- transition IDs 独立；
- trace count/fraction、continuity 与 missing-step 合同；
- gradient 和 tone/texture 合同；
- role interval 与模板相交；
- source/lane/order 无硬矛盾。

Grid、holder edge 或 expected position不能单独成为锚点。该 authority 是经后续真实样片验证
的检测假设，不声称对完全漏检的边缘作数学证明。

### 4.3 Phase groups

每个 profile run 对可能模板 role 投票：

```text
phase interval = observed run interval - template role relative position
```

单次 endpoint sweep 形成少量完整 template groups。Runs 按 coordinate 排序；每个 group/role
通过 `bisect` 查询一次，每个 phase vote 最多匹配一次。不存在 top-K 或通用 path DP。

一个 group 获得排除孤立错误相位的权限，除共同 component、source geometry、pitch、ordinal
与 authority 一致外，还必须满足：

```text
两个独立 observed roles 的模板坐标间距 ≥ 一个 frame width 下界
或
一个通过联合尺寸合同的完整 start/end opposite-edge pair
```

相邻 separator 两侧只能证明 local advance，不能单独取得全局 phase 排除权。一个或多个完整
opposite-edge pair 可排除与其 source geometry 相容、只有一个独立 role、无 opposite pair、无
confirmed delta 的孤立冲突；多个完整 pair 自身全部保留，2-vs-2 等同强度冲突也全部保留。

### 4.4 Provisional cross 与 direction

共同方向未知时，每个 cross transition 投影到 lane reference：

```text
raw coordinate interval
± |trace-reference| × tan(maximum_search_angle)
± numeric uncertainty
```

该 interval 只生成 proposal，不能用 0.40% tolerance 提前删除摆放或进入安全输出。
Template 绑定 transitions 后，每个 top/bottom role 最多拟合一条 raw line。Robust fit 产生
canonical center 与较窄的 fit angle interval；transition coordinate interval、peak width、
residual 与采样误差进入独立的 full angle interval。Fit interval 只判断多个 observed roles 是否
能共享一个代表方向，完整安全角度保存全部 full intervals 的 hull。只有 fit hull 不超过冻结上限
时才形成 `SharedStripDirection`，然后重新投影已有 observations、收紧 source height state 并
materialize。水平与垂直 lane 使用同一 source-coordinate rotation 符号合同，旋转等价输入不得
因 axis 交换而翻转 slope。

每个 lane 只需一个合格的 top 或 bottom 像素锚点即可建立完整 height placement；缺失的
opposite edge 只能由同一个联合 source-height state 推导。只有同时观测到合格的 top/bottom
pair 时，才允许用其 separation 收紧 source-wide 真实高度。

Sampling-equivalent direction classes可以合并，但必须保存完整 angle safety hull。存在多个
非等价 transform class 时，`shared_strip_direction=nonunique`，下游 geometry 和 budget
unavailable，正式输出为零。

Sequence template 完整 materialize 后，可以在其 full sequence support 内重新组织已经执行的
top/bottom transitions，形成 staged height templates。该步骤复用注册 query 的 transition IDs，
不读取新像素、不扩大 validation domain，也不创建新的 phase 或 count authority。完整 opposite
polarity edge pair 可收紧 joint height；普通 fit 只选 canonical center，full intervals 继续进入
retained safety。这样保留后期版本 photo-edge ridge 与片段内长边拟合的有效部分，同时仍只有一条
template-first production path。

### 4.5 EnhancedEvidence

Basic 已产生 placements 且每条 sequence placement 都具有正式 exclusion authority 时，该 lane
不执行 registered role enhancement。无 placement 或只有未闭合 singleton phase 的 lane 才存在
typed structural gap；enhanced work 复用相同 decode、measurement cache、role band 与按 trace
排序的 coordinate index，每个 query ID 最多执行一次。完整 opposite-edge pair 可确认或收紧
已存在的 template seed；单个 role 不能取得排除权限。Enhanced 不能创建 basic 不存在的新
direction、source geometry authority 或更宽 query coverage。

## 5. Retention 与 canonical

Placement 只能因以下原因删除：

- 违反 format、联合 geometry、count、ordinal、lane 或 source authority；
- 被严格 group-support 合同证明为孤立错误相位；
- 删除前后 safety footprint union、全部 legal-window intersection 与 sampling identity 完全
  不变的结构冗余。

Support、residual、tone、background preference 与 expected position只用于 canonical 排序，
不能缩小 retained set。增加有效竞争时，安全包络只能扩大或不变。

Canonical 从 retained placements 中选择一个实际可行的代表状态。固定 direction 和 joint
geometry 下，scalar weighted-Huber 只选择代表 translation；结果不在可行 interval 时使用
interval midpoint，禁止 clamp。

## 6. SafeCropEnvelope 与 budget

每个 output slot 只有一个 geometry owner：`SafeCropEnvelope`。它保存：

```text
placement_source_footprint
required_source_footprint
constrained_source_footprint
saturation_facts
mapped_output_box
```

构建顺序：

```text
outermost(
  union(retained full safety footprints),
  canonical minimum-guard footprint
)
+ exactly one 1 source-px visible interpolation guard
→ source/lane authority intersection
→ direct transform of continuous vertices
→ integer half-open mapped box
```

Full uncertainty 与 minimum guard只取较外侧者，绝不相加。Authority 不得裁掉 retained
placement 或 canonical；只允许裁掉 guard 并记录 saturation。Footprint 不先变成 source AABB，
避免 deskew 时二次膨胀。

Safety 不是“中心点加固定 padding”。每条 transition 的测量 interval、transition width、
fit residual、aperture tolerance、联合 axis scale、数值误差、共享角度 interval 与一次 visible
interpolation allowance 分项保留并向外传播。Robust fit 只选择 canonical 中心；普通协方差不
取得 safety authority。每个 retained placement 的 `full_safety_footprint` 独立消费这些事实，
最终 envelope 取完整 union。

Minimum guard：

| Format | start/end 每边 | top/bottom 每边 |
|---|---:|---:|
| half | 0.15 mm | 0.25 mm |
| 135 / 135-dual | 0.25 mm | 0.25 mm |
| 120-645 | 0.30 mm | 0.25 mm |
| 120-66 | 0.40 mm | 0.25 mm |
| XPan | 0.45 mm | 0.25 mm |
| 120-67 | 0.50 mm | 0.25 mm |

Budget 不从 full interval 或 output 反推。每个 retained physical interpretation 都以设计尺寸
和自己的 joint geometry计算逐边 expansion；实际输出必须位于全部 MaximumLegalWindows 的
intersection。Pixels 转毫米使用可行 scale minimum，不能低估外扩。

## 7. Gate、Finalization 与 Writer

唯一 ordered Gate checks：

```text
scan_canvas_authority
output_slot_count
format_placement
shared_strip_direction
source_frame_geometry
slot_ordinal_assignment
source_lane_authority
placement_set_containment
direct_use_budget
output_transform
```

全部要求 `SUPPORTED`。`CandidateGate` 只冻结 typed facts；`DecisionGate` 导入同一个 check
tuple，并将 typed gap 与 count mode机械映射为 final reason。不存在字符串扫描、第三个 Gate
或 competition reason 推断。

`needs_review` 时 Finalization 不暴露正式 boxes，Writer 不写照片 TIFF。Approved Writer
消费 mapped box、transform 与 lane sampling authority；bilinear 四个 taps逐个检查 authority，
越出 lane 的 tap 使用 photometric background，不能 clip 后采入另一 lane。每个正式 TIFF 只
从原 TIFF 执行一次分块 SciPy inverse-affine sampling。

TIFF 输入只接受单页 `uint16 RGB YXS CONTIG` 与冻结无损压缩。`tifffile + imagecodecs` 独占
decode、encode 与 readback；OpenCV 只提供有界像素测量，SciPy 只提供数值和 sampling。
Orientation 1–8 在 decode boundary 建立 raw↔canonical 可逆映射；正式输出烘焙为正确视觉
方向并写 Orientation=1。每张 TIFF 关闭写句柄后复读验证 dtype、shape、axes、pixels、
photometric、channels、planar、ICC、resolution/unit、受支持 metadata 与压缩。

## 8. Report、manifest 与 Debug

Current-only schema：

```text
report schema id       = x5crop_detection_report_v5
report schema revision = x5crop_v5_current_1
run manifest           = x5crop_run_manifest_v5
output owner            = x5_crop_v5
```

Report 保存 raw observations、profiles、phase groups、direction classes、joint source geometry、
local advances、retained placements、canonical、safe envelope、budget、两级 Gate、transform 与
最终 I/O facts。Transition 至少包含 coordinate interval、peak width、prominence、polarity、
local noise、trace/support 与 provenance。Report 是审计产物，不是 detection cache；不得保存
profiler、候选海洋或开发调用轨迹。

Manifest 只保存 `run_id`、输入 ordinal、便携名称、size、mtime、terminal、依赖/线程、文件系统
等级、best-effort 同意方式、disk reservation 与发布 inventory。它不保存 source-content SHA、
Git、cohort 或 performance receipt；inventory 不包含 manifest 自身。普通文件使用相对路径、
role、type、size、mtime，目录只使用相对路径与 type。

Debug Analysis 只读取 runtime/report facts，将四层事实组织为三联图：第一联合并
source authority 与 pixel evidence，第二联显示全部 retained complete placements 和 canonical
代表，第三联显示 protected output、budget 与 source-atomic decision。它不重新计算 detection、
geometry 或 budget。渲染使用固定 `1653 × 952` 审计网格、一个共享 source preview cache、每联
一个 RGBA overlay 和一次最终 JPEG 编码；竖向片条只旋转展示坐标，不改变 source facts。RAW
transition 提亮但仍低于 observed edge，START/END 从真实 canonical 边界越过照片上缘进入标注区，
状态头始终保留实际 deskew/identity 角度与 Orientation 映射。当前 report 没有可绘制的
`MaximumLegalWindow` polygon，因此图例只陈述冻结的 5%/3% budget limit，不伪造绿色窗口。
Pillow 只在用户显式启用 Debug Analysis 后延迟导入。

## 9. 生产路径与开发验证

默认生产路径只执行 TIFF/Orientation 校验、一次 decode、registered detection、物理求解、
不确定性传播、Gate、一次正式 sampling、TIFF 写出复读、轻量 report/manifest 与安全发布。
它不计算 source-content SHA，不检查 Git/cohort/receipt，不运行 comparator、profiler、tracemalloc、
故障注入或 Debug Analysis。

`tools/verify` 是唯一验证入口。POSIX、GitHub Actions、Windows `.bat` 与 Intel macOS
`.command` 都只作薄转调；入口从 `python3`、`python` 中选择 setup-python 提供且满足
3.12--3.14 合同的解释器。CI 以 Ubuntu 24.04、Windows 2025、Apple Silicon macOS 15 与
Intel macOS 15 乘以 Python 3.12、3.13、3.14 运行同一 `full`。Python 3.13/3.14 额外用
`os.path.isreserved()` 交叉核对项目 portable-name authority，3.12 只消费项目冻结表。

`accuracy`、`diagnostic` 和 `performance` 在生产程序外部先计算 source SHA 并冻结 source
stat，再通过子进程调用同一 `X5_Crop.py`。工具只观察正式 report、manifest 与 outputs；没有
detector bypass、样片参数、验证专用 producer 或较宽 Gate。`non-detection` 对绑定
`90e5e8c4` 的十四项黄金语义作精确 schema 规范化比较；`audit` 还从 `21da1131` 检查逐文件
protected manifest，并固定 freeze anchor 自提交 `35ba1117` 后不得变化。两者只负责防止当前
非检测阶段悄然改动检测、format、Gate、budget、黄金 cohort 或 comparator，不改变 accuracy
verdict。

`platform` 只在干净 tree 上从真实 OS 与架构生成 receipt，运行 `full`、非检测审计、六张平台
样片、真实文件系统 contracts 和关联 performance receipt。`platform-check` 恰好接受同一
expected commit 的一份 Apple Silicon 与一份 Windows x64 receipt，读取并核对关联 performance
文件的真实内容与 SHA；NTFS 结果不能替代 exFAT case。`platform-package intel-macos` 只生成
Git bundle、六张样片的 SHA manifest、薄 `.command` 与校验清单，不包含 TIFF、receipt、RC
或用户包。Receipt 是实机证据；源码相同、CI 或工具存在都不构成平台通过声明。

六张平台样片中 S027、S062、S094、S098 运行完整用户路径；S046、S101 只证明真实
Orientation/ICC/resolution/compression decode 与 report。工具从 S027 canonical pixels 临时
反向派生 Orientation 3/8 raw raster，运行完整正式 CLI，并以普通 S027 输出证明 canonical
像素、ordinal、Orientation=1 与 TIFF 复读一致；临时文件不进 Git，也不形成 accuracy 真值。

生产模块为 NumPy、SciPy、cv2、tifffile、imagecodecs 与 PIL；测试、comparator、fixture、
profiling 和故障注入不进入用户包，开发依赖单独拥有。`tools/install/dependencies.toml` 只冻结
模块能力、模块版本、缺失时的用户级 pip fallback，以及可识别的 Homebrew formula；它不把
平台绑定到 package manager。

依赖安装器先用目标 Python 的 fresh interpreter 检查 import、模块版本、真实 origin、distribution
和 Homebrew Cellar ownership。满足能力合同的模块一律 `reused`；缺失模块才安装最小 user-site
binary wheel；已存在但版本不符时，确认属于 pip 就更新原 distribution，确认属于 Homebrew 且
当前 formula 可提供所需版本才执行 formula update。未知 ownership 在任何写入前失败，禁止用
第二份包遮盖。收据分别记录每项 `reused`、`pip_installed`、`pip_updated` 或
`homebrew_updated`，runtime/report 记录逻辑模块、实际 provider、package、origin、版本和 OpenCV
build fingerprint，不再把缺失 distribution metadata 当作模块缺失。

## 10. 工作量与性能

Producer 的结构上界：

```text
phase_vote_count
  ≤ profile_run_count × ordered_role_count × component_count

template_role_lookup_count
  ≤ template_group_count × ordered_role_count

template_role_match_count
  ≤ phase_vote_count

local_relation_evaluation_count
  ≤ template_group_count × (slot_count - 1)
```

V5 的内存为一维 profiles、有限 runs/votes/groups、typed geometry 与有界像素 buffers；不增加
多份全分辨率梯度、完整 float64 sampling coordinate field、Hough slope family、通用 DP、top-K
或无界 candidate materialization。Direction-bound aggregate 对每条 registered transition 只作
固定次数的 bin 投影，时间与额外 records 均为 `O(Q)`；staged rebind 只消费同一 `Q`，不生成
宽高笛卡尔积。单输入临时内存上限为：

```text
10 × source_pixels + 32 MiB
```

X5 Crop 是唯一并发 owner：`--jobs` 调度 sources，OpenCV、BLAS、OpenMP 与 SciPy 内部线程固定
为 1。性能 receipt 固定 24 sources，并绑定 Git commit、cohort SHA、source SHAs、依赖与线程
身份；当前 commit 未生成有效 receipt 时不得作性能完成声明。

性能验证分两遍。第一遍只计时完全相同的 production CLI，记录逐 source wall、输出数量与大小，
且只有 mean wall 不超过 5 秒参与正式 Gate。第二遍由开发子进程在既有 runtime stage boundary
外部采集 startup/import/unattributed、decode、detection+decision、sampling、encode/write、
readback、publish、I/O total、process peak RSS 与 runtime peak temporary bytes；它只解释耗时，
不进入速度 Gate，也不向默认 CLI 增加 instrumentation。Receipt 同时记录 CPU、物理/逻辑核心、
内存、输入/输出卷与文件系统、可用空间、电源状态和 Windows Defender 实时保护状态。结论只适用
于 receipt 中的命名验证机。

安装器的 missing、update、uninstall 破坏性矩阵只能在一次性系统用户、专用全局 Python 或可恢复
测试机快照执行，仍不使用 `.venv`。日常开发环境与 Homebrew 只作只读 capability/reuse 检查，
不得为了生成 receipt 被自动改写。

## 11. 平面输出事务

正式照片直接位于 target 根部。若 target 为 `MyCrops`，同父目录旁路为
`.MyCrops.lock`、`.MyCrops.transaction.json`、`.MyCrops.new-<uuid>` 与
`.MyCrops.old-<uuid>`。Token 由 target leaf 派生；不同 target 不共享锁。

流程固定为：获取锁并恢复明确状态；创建 staging；处理全部 sources；复读 TIFF；写 report、
summary 和不含自身的 manifest inventory；至少一个 source 非 `runtime_error` 后写 journal；旧
target rename 为 old；new rename 为 target；验证新 ownership；删除 old 与 journal。单 source
失败不取消其它有效结果，全部 source 均为 `runtime_error` 时不发布并保留旧 output。
`runtime_error` 只属于 `RunTerminalOutcome`，不得进入 `DecisionGate.decision.status` 或 final
reasons；`needs_review` 是会随完整 run 发布 report、manifest、summary 与 review material 的
合法终态。

旧 target 只有 current owner、manifest 与完整 inventory 一致时才能替换。遍历使用 lstat
语义并拒绝 symlink、Windows junction 和 reparse point；删除 bottom-up 且永不跟随链接。
进程异常与强制结束支持自动恢复；突然断电后状态明确时恢复，状态歧义时保留 target、new、
old 和 journal，绝不自动删除。发布前的输入、preflight、run-wide ENOSPC 或整体 report/manifest
失败，只有在 staging ownership 明确时才可清理 staging，退出码为 2。事务恢复、rename、发布
或回滚失败一律保留 target、new、old 与 journal 的全部候选，退出码为 3；此时不得声称旧
output 已恢复。

`FilesystemPolicy` 区分 `verified_local` 与 `best_effort_unverified`。未验证文件系统的交互运行
必须明确确认，非交互运行必须显式传入 `--allow-best-effort-output`；同文件系统、锁、rename、
路径安全和磁盘空间仍是不可绕过的硬失败。Scheduler 在 sampling 前对整个 invocation 检查新
结果、报告、可选 debug、事务开销与 32 MiB guard，旧结果在发布前继续占用空间。

## 12. 源码 owner

| 路径 | 唯一职责 |
|---|---|
| `x5crop/formats/` | format 物理尺寸、tolerance 与 gap |
| `x5crop/configuration/` | count request、ScanCanvas catalog、format fit 与 runtime detection configuration |
| `x5crop/io/` | 严格 TIFF、Orientation mapping、metadata policy 与 readback |
| `x5crop/detection/source_core.py` | source/lane authority |
| `photo_geometry/measurement.py` | transitions、SideTransitionRegion 与 raw boundary fit |
| `photo_geometry/template_profiles.py` | profiles、roles、phase votes 与 indexed grouping |
| `photo_geometry/source_geometry.py` | joint axis geometry、SourceFrameGeometry 与 NominalPitch |
| `photo_geometry/template_model.py` | template proposal、local advance、placement 与 work facts |
| `photo_geometry/template_first.py` | producer orchestration 与 exact materialization |
| `photo_geometry/output.py` | SafeCropEnvelope、sampling identity 与 direct-use assessment |
| `x5crop/geometry/convex.py` | 唯一 convex footprint primitives |
| `x5crop/detection/candidate/` | CandidateGate facts |
| `x5crop/detection/decision/` | final status 与 reason mapping |
| `x5crop/detection/final/` | approved geometry exposure |
| `x5crop/export/` | lane-safe TIFF sampling、write 与 readback |
| `x5crop/report/` | current report read model 与 validation |
| `x5crop/runtime/` | invocation、source terminal、run-wide budget 与轻量 manifest |
| `x5crop/output/` | portable name、safe tree、filesystem policy、lock、journal 与 publication |
| `x5crop/debug/` | current facts 的只读可视化 |
| `tools/verify` | 唯一 tracked verifier 入口 |
| `tools/regression/` | 生产程序外部的 SHA-bound accuracy、diagnostic 与 performance |
| `tools/release/` | standalone 与 ZIP manifest |
