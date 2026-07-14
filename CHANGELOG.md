# X5 Crop 更新日志 / Changelog

本文件记录版本级变化、验证记录和发布策略。当前运行流程与源码分层见
`ARCHITECTURE.md`；用户操作见 `README.md`；协作规则见 `AGENTS.md`。

This file records version changes, verification, and release policy. Current
architecture lives in `ARCHITECTURE.md`, user instructions in `README.md`, and
repository rules in `AGENTS.md`.

当前 active 脚本版本 / Active script: **V4.9**
当前稳定发布版本 / Stable release: **v4.2.8**

## 中文更新日志

### V4.9 当前开发线

#### Photo Aperture 联合求解与 Debug 可见性（2026-07-13）

- 首尾 endpoint 搜索不再在全局 solver 前按 nominal frame width 选出唯一边界。符合完整照片宽度的
  endpoint 与由同侧 holder boundary 佐证的 clipped endpoint 会共同进入 assignment consensus；
  dimension residual 现在只决定搜索顺序，片夹压住画面的实测 outer 不会被提前丢弃。
- Internal-boundary content evidence 现在保留逐照片 leading/trailing edge 的短轴空间轨迹。只有同一
  短轴轨迹在相邻照片两侧重合，且 count-independent content run 同时贯穿长轴 boundary interval，
  才能反证未解释切线或佐证 measured-edge overlap；上下错位的独立纹理不再触发自动 overlap bleed。
- Solver 删除 `visible_aperture_coverage_px` 排序目标。所有已测内容被覆盖后，单纯扩大 aperture
  只会多含片基或片夹余量，不再取得物理支配权；不同 outer 继续保持 geometry disagreement。
- Solver 现在显式消费一次缓存的 count-independent content observation，仅用它剔除漏掉已测可见
  内容的 geometry alternatives；content 不能生成、移动或收缩 aperture edge。若全部 alternatives
  都存在 coverage contradiction，solver 保留原始几何并交给 canonical evidence 报告，避免用
  content 反向伪造边界。Solver 与 `PhotoApertureCoverageEvidence` 共享同一 observation 和覆盖算法。
- Boundary observation 破坏性升级为真正的二维 path：每个 local sample 保存 orthogonal interval
  与位置不确定度，top/bottom aperture edge 按每张照片自己的长轴范围解析。Raw channel 仍完整
  报告，solver 只合并几何等价 hypotheses；与内部 separator band 关联的 path 由 band 双边解释
  唯一消费，不再通过 generic measured-path 分支重复扩展候选。
- Separator band 对 measured aperture edge 的归属由 interval 相交且 path midpoint 位于 band 内共同
  决定，不再要求整个 uncertainty interval 被 band 完全包含。Band start/end 与独立 measured edges
  若给出不同照片开口，assignment consensus 保留冲突；geometry-equivalent observation 不重复制造
  `budget_exhausted`。
- Content evidence 删除全局 tonal-position component，只保留 gradient、texture 与 local-contrast
  共识。External aperture preservation 排除相邻边界 uncertainty 和一像素 evidence kernel halo，
  垂直边角活动不再伪装成照片跨越另一条边界。
- Boundary local strongest-change selection 明确归 adaptive measurement，不再被误报为 execution
  budget exhaustion；真实预算只来自 path 数量和 solver search 上限。
- 理想裁切几何收敛为逐张 `PhotoAperture`；可见片基与内部 separator 不进入照片开口。
  `PhotoSequenceSolution` 联合求解照片四边、separator 双边、signed spacing、count 与物理守恒，
  full-canvas containment 和 dimension-only edge 只能保持 provisional。
- Content preservation 拆成逐张 aperture-union coverage、内部 boundary preservation 与外部
  aperture preservation。`PhotoApertureCoverageEvidence` 只按 content-profile 平滑半窗表达位置
  不确定度；未落入任何 aperture 的可见内容不能再由整个 sequence 外包络伪装成已覆盖。
  Content 只反证漏图；单个像素不能改写 aperture，measured edge 与 content 冲突时保留 typed
  conflict 而不删除 measurement。
- Partial auto count 不再把“更大 count 已运行但未求解”误写成“更大 count 已被物理排除”。
  `GeometryResolution.larger_count_hypotheses_resolved` 只有在更大 count ambiguity 确实消失时成立，
  防止空片夹 aperture 替代仍未覆盖的真实照片并获得自动输出权限。
- `SeparatorBandObservation` 只保存 start/end，中点改为派生属性；删除可能与两端漂移的第三状态。
- 新增 canonical `SeparatorWidthConstraint`。一条 band 只有在窄于相邻照片的最小可行长轴宽度时
  才能成为 hard separator；足以容纳完整照片的欠曝或空白区域继续保留为 raw observation，但只能
  形成 dimension-dependent provisional edges，不能增加 separator proof。
- Raw tonal、texture 与 edge-adjacent paths 的 measurement identity 统一为 `BOUNDARY_PATHS`；删除
  assignment 前误称 holder 的 `HOLDER_BOUNDARY_PROFILE` 和 `holder_reference_percentile`，canvas-edge
  adaptive reference 不再偷带片夹身份。
- `PhotoContentObservation` 统一使用 `photo_index` 与 typed `BoundarySide`；删除泛化 `index` 和
  `left/right` 字符串侧名，content crossing、assessment 与 current report 共享同一照片/边界身份。
- Partial auto count 明确区分“较大 count 已被穷尽否定”和“较大 count 仍缺证据”：前者允许继续
  证明较小 count，后者继续阻止自动解决；budget exhaustion 永远保持 unavailable。
- Architecture contract 现在检查 active Enum 成员是否有 runtime 使用者；删除 8 个只属于旧 sequence、
  safety、review-only 与 TIFF identity 模型的孤儿 `MeasurementIdentity`，测试不再保护失效身份。
- `PhotoSequenceSolution` provenance 改为从实际 aperture、separator、dimension 与 holder 输入自动
  派生，root 固定为 `FRAME_GEOMETRY`；measured edge 必须与 raw observation assignment 一一对应。
  Evidence independence 只拒绝 measurement 反向依赖 geometry，不再把正确的
  `measurement -> geometry` 数据流误判为循环。
- Overlap output planning 不再复制 `physically_supported` 或把 provenance 压成字符串；
  `FrameOverlapRequirement` 直接持有 canonical `InterPhotoSpacing`，required bleed、support、boundary
  与 typed provenance 均从该物理事实派生。
- Separator/contact/overlap/unresolved spacing 状态收敛为 `InterPhotoSpacingKind`；删除 runtime、
  content evidence 与 output 中的裸字符串物理身份比较。
- External aperture content preservation 只把边界两侧相邻像素上的连续活动视为 crossing；同一轨迹
  在两侧带状区域内彼此分离的活动不再伪装成可见内容被裁断。
- Sequence conservation 收敛为 `PhotoSequenceSolution` 的构造不变量。相邻 spacing 已由 aperture
  edge 差值唯一决定，不再把同一几何恒等式重复包装成 evidence、CandidateGate check、final reason
  或 report 字段，避免 geometry 自证。
- 删除 physical geometry 与 evidence 中重复的 `automatic_processing_supported`。Standard/dual-lane
  candidate 由 CandidateGate 表达自动处理资格，review-only assessment 明确没有 CandidateGate；
  DecisionGate 不再读取低层权限开关。
- Report identity 破坏性更新为
  `detection_report / photo_aperture_sequence_resolution`，旧 schema 只会 cache miss。
- Debug Analysis 仍为三联图，图例由 diagnostics configuration 唯一生成。绿色表示理想
  `PhotoAperture`，蓝色虚线表示 `FrameCropEnvelope` 或 protected output；holder、raw observation、
  measured edge、dimension hypothesis 与 corroborated overlap 各有固定标记。横纵 boundary renderer
  现在遵守同一轴向不变量，Debug 不再从 output envelope 伪造 aperture。
- `ARCHITECTURE.md` 已按当前物理数据流重写；`README.md` 与 `AGENTS.md` 同步 current schema、
  Debug 图例和 handoff。当前 397 项测试、14 组 format/mode configuration、compile、launcher 与一张
  `half/full` 真实三联图验证通过。

#### 全量实测完整性根因修复（2026-07-13）

- Preprocess 现在产出带 canonical `WorkspaceExtent` 的 `PreparedWorkspace`；deskew 扩张 canvas 后，
  finalization、report identity 与 cache restoration 不再回退到原始 TIFF shape。
- Sequence solver 将 boundary uncertainty 与可见 sequence interval 规范求交；无正宽、非单调或非法
  geometry 返回 typed unavailable，不再形成非法 `SequenceSolution` 或图片级 runtime exception。
- PhotoInterval identity validation 统一复用 canonical interval factory；删除用未求交 boundary path
  重复推导 identity 的平行校验，`X5_00017` 与 `X5_00026` 不再发生自相矛盾的 geometry exception。
- `InternalBoundaryPreservationEvidence` 逐条验证内部切线。Frame union coverage 不再替代切线安全；
  连续内容跨越没有 independent separator、measured contact 或 corroborated overlap 的切线会明确
  contradict candidate content preservation。
- `FrameBleedPlan` 与 optional `FinalizationPlan` 已拆开：GeometryResolution 未解决时 report 明确保存
  `finalization_plan=null`、`final_geometry=null` 和不可导出状态；`--export-review` 不能写出 provisional
  frames，三联 Debug 仍可用诊断样式展示它们。
- Partial auto count matrix 保持物理 trait 驱动；holder slack 和已确认 edge occlusion 都不会进入首尾
  frame dimensions 或 px/mm consensus。Full 模式的双 canvas endpoint 只为完整 independent separator
  sequence 提供范围，不自行形成 proof；mixed measured/canvas endpoint 仍保持 placement unresolved。
- Current report identity 为 `detection_report / gray_sequence_integrity`，旧 schema 直接 cache miss。
- Selection report 将候选裁切明确命名为 `provisional_geometry`；只有 output section 可以保存 final
  geometry。Runtime 以 typed completed/failed outcome 汇总每个输入，并由父进程唯一写入
  `x5_crop_run_manifest.jsonl`。Manifest 精确记录 terminal outcome、失败阶段、report/debug 与实际
  output；report validation 失败会保留并重绘 `RUNTIME ERROR` Debug，更早失败不伪造分析图。
- Manifest 新增只读运行指标：input processing / detection 时间、assessed candidates、assignment
  evaluations 与 exact measurement-cache hits/misses。Dual-lane 的 lane cache 共用同一统计 owner；
  指标不参与 detection、Gate、early-stop 或输出决策。
- 修复后以 113 张 TIFF 重跑默认 diagnostics：113/113 完成、113/113 写入 terminal manifest、合法
  `gray_sequence_integrity` report 与三联 Debug Analysis，0 runtime exception，0 unresolved frame
  export。全部候选目前仍为 unresolved REVIEW，留待独立 calibration；本轮不通过放宽 Gate 获得
  PASS。累计记录 818 个 assessed candidates、896,652 次 assignment evaluations 和
  3,334/1,458 次 exact measurement-cache hit/miss；`half/full` 的 sequence search 是后续明确性能热点。
- 另验证 unresolved `--export-review` 禁止 provisional frame、current-schema cache reuse、真实双进程
  metrics 回传和 Debug `NOT EXPORTABLE` 标记。完整 Architecture Audit A/B 仍留待独立任务。

#### 灰度外观语义与 separator sequence 收敛（2026-07-13）

- 删除 `FilmBaseReference`、`FilmStructureEvidence`、`ApertureContactEvidence` 及材料一致性证明；
  严重欠曝画面与片基可能具有相同灰度外观，appearance 不再授予材料身份或 Gate 权限。
- `GrayAppearanceObservation` 统一保存 boundary outer/inner 与 separator 的灰度测量；
  `CandidateEvidence` 直接持有 `SeparatorSequenceEvidence`，物理 proof path 改为
  `separator_sequence_led`。
- 短轴 scale 只在 top/bottom 内侧均有明确内容纹理时产生 px/mm 下限；低纹理内侧保持 unresolved，
  不再产生片基假设对应的 scale 上限。
- Current report identity 更新为 `detection_report / gray_sequence_resolution`；旧 schema 直接 cache
  miss，不保留类型、字段、reason、alias、shim 或 reducer。
- 验证通过 459 项测试和 14 组 format/mode configuration；真实 smoke 覆盖 `005`、`X5_00044`、
  `X5_00021`、`X5_00006`、`X5_00001`、`120-67/full` 与 `120-66/partial auto`。七份 report 均通过
  current-schema validation，并完成 cache reuse、review export、TIFF metadata 与三联 Debug Analysis
  检查。完整 Architecture Audit A/B 留待独立任务。

#### 灰度材料、Outer 与扫描比例物理化（2026-07-13）

- Detection 固定只消费 canonical gray workspace；RGB/chroma/holder color 与 135 片孔不进入
  runtime、cache、proof path 或 report schema，原始通道与 ICC 继续由 TIFF I/O/export 保存。
- `GrayMaterialObservation` 成为 boundary outer/inner material 与 separator material 的唯一灰度材料
  类型，并以 typed low/high/midrange tail 取代布尔材料标签。Boundary path 使用多截面、极性无关的
  纹理/change-point 观测；proposal family 名不再授予 holder 身份，渐变、灰尘和混合明暗片夹可
  保持同一数据流。
- `FilmBaseReference + FilmStructureEvidence` 取代 separator-only proof identity；只有完整 hard
  sequence 与 distinct typed locations 上的同尾部、低纹理材料共识才能形成 `film_structure_led`；
  单个区域、重复位置或高纹理 track/separator 不能伪装成片基材料。
- TIFF resolution 改为未经物理确认的 `ResolutionMetadataObservation`。逐候选
  `PhysicalScaleObservation` 使用 typed provenance 表达 photo-edge 有界比例、holder-to-image 下限或
  holder-to-film-base 上限；long-axis dimension consensus 至少需要两张独立照片，逐轴 supported 状态
  可独立消费。冲突 metadata 只保留 diagnostic，calibration unavailable 不阻断 normalized detection。
- Current report identity 更新为
  `detection_report / gray_material_sequence_resolution`；input 只保存 resolution metadata，候选
  evidence 保存解析后的逐轴 calibration，configuration 完整保存 boundary-path measurement 参数。
  旧 schema 或不完整 configuration 直接 cache miss，不保留投影或 alias。
- Boundary path groups 按完整参数对象 exact cache 并跨 auto-count hypotheses 复用；候选、Gate、
  GeometryResolution、DecisionGate 与 final reasons 仍不缓存。
- Cross-axis separator path 允许显式参数控制的小范围局部中断，但不能跨到远处内容边缘；该参数
  属于全局 adaptive measurement，不是 format profile。
- `FilmBaseReference` 在 typed model 内强制 adaptive texture limit、来源/位置类型和最小共识数量，
  `AssessedCandidate` 还把 holder material、film-base、film structure 与 aperture contact 精确绑定回
  同一 geometry；report restoration 无法再用伪造 source、boundary 或材料构造 supported reference。
- `DecisionGateAssessment` 强制 canonical check order 与唯一 reason ownership；current report validator
  精确验证 selection/output/transform 对应的 DecisionGate，以及 selected geometry 到
  `FinalizationPlan` 和 final geometry 的完整身份链。
- Boundary-side 几何逻辑统一使用 `BoundarySide`，不再依赖其 `str` 子类兼容；candidate 之前的 root
  scale 删除不可达的 film-base 上限分支，只有 candidate-local aperture evidence 可产生该上限。
- `PhotoInterval`、frame dimensions、coverage、conservation、occupancy、partial-edge、independence、
  film material 与 candidate-local scale observations 全部绑定到同一 candidate geometry；合法的独立
  photo-edge uncertainty 可以变化，但陈旧或伪造的 evidence projection 会在 typed model 边界被拒绝。
- Physical scale 使用 typed root/candidate scope；`provenance.source` 只作说明，不能改变 observation
  所属阶段或绕过 candidate geometry identity。
- Dual-lane composition 直接消费每条 lane 的 canonical `SelectionResult`，保留 child
  `GeometryResolution`；没有实测 divider 的 full dual-lane 使用 `ReviewOnlyGeometry`，不再生成伪造的
  standard sequence。

#### 封口参数与几何解析契约（2026-07-12）

- `62e47cd2` 已通过同一冻结清单下的 Audit A 与全新上下文 Audit B，作为
  `architecture closure candidate`；正式关闭仍等待新的 Codex 任务完整重跑双轮审核。
- 最终验证覆盖 413 项测试、142 个可达 active modules、201 个已分类参数 contract、14 个
  format/mode configuration，以及五类真实 TIFF smoke、current report validation、cache reuse、
  review export、双进程、TIFF metadata 和三联 Debug Analysis。
- DecisionGate 现在直接消费完整 `GeometryResolution.state`，assignment consensus 与 search-budget
  exhaustion 不再因下游只重算部分字段而漏过最终 Gate；实质 selection disagreement 继续独占其
  具体 final reason，不重复产生 aggregate geometry reason。
- Focused separator measurement 现在使用独立的 typed measurement identity，并由 provenance
  直接派生 geometry dependency；sequence solver 不再覆盖 assignment 的派生 state/reason，真实
  runtime 与 synthetic contract 共享同一条非独立证据路径。
- Current-schema validation 现在通过正式 dataclass 构造器执行全部跨字段物理不变量，并核对
  input/signature、configuration/candidate、count 与 finalization geometry 的共同 identity；损坏记录
  或 restoration 失败只会导致重新检测。Configuration fingerprint 也不再静默字符串化未知类型。
- Inter-frame spacing 与 holder occlusion 收敛为 CandidateGeometry 的唯一事实源；CandidateEvidence
  直接拥有 sequence conservation，删除无不变量的 evidence 包装层，output bleed、Debug 和 report
  不再读取事实副本。
- Decision 与 output ownership 再收口：删除只转发 DecisionGate 的 `DecisionResult`，`DecisionGateAssessment`
  直接拥有 checks、status 和 final reasons；layout、图像尺寸、
  decision geometry 和 bleed 统一进入 typed `FinalizationPlan`。`FinalDetection` 只能由一个
  finalization factory 按 plan 精确生成。
- Current report 将 transform geometry 移到 input/preprocess，output 仅保存 canonical finalization plan
  与 final geometry，删除会反向驱动 cache replay 的 diagnostics section。Restoration 现在重用
  正式 finalization 并拒绝任何与重算结果不一致的持久化 geometry。
- Holder occlusion 拆成搜索约束与求解后证据；white-holder 可能性不再被当作零
  遮挡拒绝正确 separator，也不能在 boundaries 解出前伪装成 supported evidence。
- `SequenceSolution` 与 `SeparatorAssignment` 现在交叉验证 frame partition、photo indexes、
  boundary/constraint identity 和 spacing references。超过照片宽度的推导 overlap 保持 hypothesis。
- Sequence observation/hypothesis budgets 不再被 count 静默扩大；候选组合生成受同一硬
  预算限制。Holder occupancy 改由实际 holder slack 派生，不再由 full/partial 请求模式声明。
- Partial edge safety 的 state、reason 与 boundary support 现在只由适用模式、hard separator、
  frame coverage 和 frame dimension evidence 派生；删除复制的 holder occupancy 状态，无法再构造
  与底层物理事实矛盾的 supported evidence。
- Holder occupancy 现在从 normalized horizontal work-space 的 spans 计算 slack/fill ratio，并按原始
  layout 选择 source X/Y calibration；completeness 与 occupancy projection 全部改为构造时派生，
  删除永远 supported 的伪 evidence state，partial occupancy proof 也必须确实观测到 underfilled geometry。
- Frame coverage 现在只保存 canonical holder/sequence、frame union、content runs 与 candidate count；
  uncovered content、region diagnostic、state 和 reason 全部确定性派生，无法与 interval facts 漂移。
- Frame topology 收敛为 `SequenceSolution` / `DualLaneSolution` 的构造不变量；删除重复 evidence、
  CandidateGate check 和不可达 final reason。CandidateGate checks 也必须与 canonical evidence 及完整
  proof-path set 精确一致。
- 删除只复制 coverage、alignment、partial edge 与 frame contacts 的 ContentPreservationEvidence；
  CandidateGate 现在直接从 canonical evidence 投影唯一 content-preservation check。
- Sequence/content alignment 删除 caller-supplied state、reason、outside side 和 slack；这些结论现在
  只由 canonical sequence span 与 content span 派生。
- Frame content 删除 caller-supplied state、reason 和 median summary；这些 read model 现在只由
  adaptive threshold、逐 frame observations 与明确的 unavailable cause 派生。
- Holder texture 删除 caller-supplied state、reason 与 contrast summary；这些结论现在只由 holder
  slack regions、frame-content reference 与明确的 measurement failure 派生。
- Evidence independence 删除 caller-supplied state/reason；sequence/supporting root identities、
  dependency cycles 与 automatic-processing applicability 现在是唯一事实源。
- GeometryResolution 补齐 assignment-resolution 与 search-budget facts，并删除 caller-supplied
  state/reasons；唯一 early-stop result 现在从完整解析事实确定性派生。
- CountResolution 将自由 reason 字符串替换为 typed outcome，并校验 physically-resolved outcome
  必须对应真实 early-stop。
- Selection consensus 从自由字符串改为 typed outcome；report validation 与 DecisionGate 共享同一个
  geometry-agreement identity。
- GateCheck stage 改为 typed lifecycle identity，candidate/decision 的 final-reason 权限不再由自由
  字符串控制。
- Boundary observation side/kind 与 holder-occlusion side 改为共享 typed physical identities；
  white-holder 与 edge-side 语义不再由字符串授予。
- Sequence conservation 删除 caller-supplied extent/state/reason，改由 visible/occlusion/frame/spacing
  intervals 与 typed spacing basis 确定性派生。
- Observed/corroborated/hypothesized spacing 删除自由 reason 字段；read-model reason 现在由 concrete
  spacing type 与 signed kind 派生。
- Spacing kind 同样删除 caller-supplied 字段，separator/contact/overlap/unresolved 只由 signed
  interval 唯一派生。
- Review-only evidence 删除唯一固定值的 reason 字段，收敛成无字段 marker；最终原因仍只由
  DecisionGate 生成。
- 同步修正文档中的 review-only assessment 描述，并用 current-schema contract 防止 marker payload
  说明回潮。
- 删除协调规则中 execution-budget reliability 可触发 early-stop 的旧授权；只有
  `GeometryResolution` 可以提前停止候选搜索。
- Deskew measurement 与 transform evidence 删除自由 reason 字符串，统一使用 foundation-owned typed
  measurement outcome。
- Deskew measurement outcome 现在同时校验 angle 与 line-fit 形状，current report/cache 不能恢复
  不可能的测量组合。
- Boundary assignment consensus 删除 caller-supplied state/reason，改为 typed solver outcome；
  disagreement、budget exhaustion 与 dual-lane component unresolved 不再共用自由文本状态。
- Holder occlusion side 删除 caller-supplied state/reason，改为 typed measurement outcome；普通 combined
  width 由两侧自动求和，只有单 frame 双边分配未解决时保留 unallocated total。
- FrameBleedPlan 删除 caller-supplied feasible/reason；output protection conclusion 现在只由 unresolved
  boundaries 与实际 per-boundary protection 派生。
- Separator assignment 删除 caller-supplied state/reason/geometry-dependency；assignment classification
  现在只由 observation、position/width constraints 与 cross-axis measurement 派生。
- Cross-axis separator measurement 删除 caller-supplied state/reason，改为 typed measurement outcome；
  availability 与 continuity classification 不能再和测量值漂移。
- Transform geometry 删除 caller-supplied state/applied/reason 组合，改由 typed deskew outcome 与
  canonical angle/span measurements 派生；report 同时删除手写 transform schema projection，统一使用
  current typed read model。
- Standard proof paths 改由 typed candidate model 从 geometry/evidence 重算校验；确认 undercrop 不再
  同时制造派生的 boundary failure，测试 fixture 也不再手工伪造 Gate。
- Dual-lane evidence 现在保留各 lane 的 typed CandidateGate 与 geometry resolution；父 candidate
  会核对 exact component geometry，并从 lane facts 重算唯一 mode-composition proof。
- Format physical sizes 与 runtime configuration bundle 各自收敛为一个 canonical tuple；删除
  重复 nominal size 输入、重复 initial configuration 存储和 configuration registry 隐藏缓存。
- Separator measurement region 现在先 canonicalize 再同时用于 cache key 与 pixels，无交集
  region 明确失败，不再静默测量整图。Export array/frame 和 TIFF compression mode 也保持
  canonical typed boundary，未知 compression mode 不再默认为 source mode。
- Global sequence solver 现在按物理数据流先解出单调 boundaries，再测量首尾
  holder occlusion，最后构建 signed spacing；这使单个缺失 separator 的可验证叠片
  保护路径在真实 runtime 可达，同时禁止候选层预先注入遮挡结论。
- Holder occlusion 的未分配状态改由 typed width interval 关系表达，不再依赖 reason
  文本驱动物理逻辑。Dual-lane divider 测量严格遵守 proposal execution budget。
- Dual-lane holder gutter 现在是 typed `LaneDividerEvidence`；只有相对两侧内容证据支持的 divider
  才能自动处理，lane 分区连续覆盖整个 canvas，lane-local frame index 会转换为全局 identity。
- Separator profile 参数与像素测量已统一归 `image` owner；源码层级依赖图新增无环契约，旧
  `geometry` profile 路径直接删除。
- Decision 与 finalization 生命周期拆为 `DecisionGateAssessment -> FinalDetection`；DecisionGate 不再提前
  创建带有占位 output geometry 的“最终”对象。
- Current report 删除永远为空的 `schema_validation` section，并统一使用唯一 typed read-model
  projection；旧通用 `_plain` / `json_safe` 二次序列化路径已删除。
- Debug Analysis 固定为一个三联图输出；删除不可达的 frame-overlay 开关、重复 panel identity/title
  registry 和伪多文件 list 返回值。
- Architecture contracts 现同时审核 tools/tests 的孤儿 helper、原参数 pass-through 与 unused import；
  已删除三个死/转发接口及七个失效 import。
- Current schema 唯一身份更新为 `detection_report / physical_sequence_resolution`；旧 revision
  不再被 report、cache、tests 或 tools 接受。
- Dimension-constrained cut 保留完整位置区间，不再把未观测边界伪装成精确中点。
- Separator band 必须整体落入 boundary position constraint 才能成为独立实测证据；仅中心点
  落入约束的宽 tonal region 保持 geometry-dependent，不能定义 hard separator。
- Cross-axis pixel-path measurement 已前移到 separator observation；assignment、photo edges、
  partial safety 和 evidence independence 不再把 continuity 未成立的 tonal band 当成独立边界。
- Global solver 保留同一 span/count 下所有最大 independent-anchor assignment 解，并输出
  `BoundaryAssignmentConsensus`。不同物理解的切线区间不相交时，`GeometryResolution` 保持
  unavailable，tonal strength 或先验位置只能选择 REVIEW representative，不能消除歧义。
- Boundary observation 改为逐边独立 edge reference 和 scan direction；相对两端及四边不再
  共享 white-holder 身份，左白右黑、上白下黑等真实 mixed boundary 可同时表达。
- Holder occlusion 的 state、side、white-holder provenance 与 hidden-width interval 现在由 typed
  invariant 约束；完全不相交的 boundary constraints 直接无解，不再伪造 midpoint。
- 已由 white-holder measurement 确认遮挡的首尾 frame 不再进入普通 photo-width contradiction；
  dimension evidence 只使用未遮挡且独立测得的 frame。
- 单张照片双侧白片夹遮挡使用 canonical `combined_hidden_width_px`；两侧分配未知时保持
  unavailable，sequence conservation 不再重复累加同一段缺失宽度。
- Partial auto count 找到最高 resolved count 后，最终 selection pool 只保留该 count；此前评估过的
  unresolved 较大 count 不再被普通排序重新选回。
- Content unavailable 不再否决 fixed/requested count 的完整 separator/geometry proof；明确 content
  contradiction 仍阻断，partial auto count 仍要求正向 coverage 才能 resolved。
- DecisionGate 将 mode eligibility、CandidateGate physical failure、count、geometry 与 selection
  disagreement 分区；下游派生检查使用 `not_applicable`，同一根因只生成一个 final reason。
- `GeometryResolution.coverage_resolved` 已由物理语义准确的
  `content_preservation_compatible` 取代；current schema validator 精确拒绝旧字段形状。
- Deskew line fit、angle 和 reason 已改为 immutable typed measurements；`image` 层只测量和计算
  quality，base/fallback mode 与择优迁到 runtime。旧 `dict[str, Any]` detail 总线及 write-only
  candidate detail 已删除。
- Observed、corroborated 与 hypothetical spacing 的 `kind` 现在必须与 signed interval 完全一致；
  非法 separator/overlap 身份在 typed model 边界直接拒绝，不再保留不可达的 contradicted 分支。
- 单个 separator 宽度上限由边界两侧照片的物理占位决定，不再被其他 boundary 的 overlap
  抵消。可信 calibration、两端实测边界与其余独立 spacing 唯一共同确定的负 residual 可形成
  `CorroboratedSpacingEvidence`，只保护相邻输出，不反向证明 conservation。
- 固定的 format/full count 与用户显式 count 已和 partial auto inference 分离；固定 count
  不再因 placement 未解决而伪装成 count 未解决。
- Geometry clustering 要求同簇区间具有共同共识；非支配的不同几何仍保持 disagreement。
- `FrameDimensionPrior` 不再充当独立 measurement evidence。没有独立 separator observation
  时，evidence independence 保持 unavailable。
- 参数契约现在动态发现参数 dataclass、模块级数值常量和隐藏 percentile；每项都具有唯一
  role、unit、stage、rationale 和 calibration status。
- 函数内数值检查现在只豁免 AST 可证明的下标、维度和数学恒等式；content evidence 的
  component consensus、Debug 样式、RGB/uint8 编码和通用物理系数均有显式 owner。
- `DualLaneSolution` 只保存 canonical lane solutions 与全局输出 geometry，不再复制展平后的
  observations、assignments、boundaries、spacings 或 photo intervals。Aggregate geometry 必须由
  lane solutions 精确投影，residuals 与 assignment consensus 也只能由 lane results 聚合。
- Separator evidence、signed spacing、Debug overlay 与逐 frame overlap protection 共享 typed
  `FrameBoundaryReference`；相同局部 boundary index 在不同 lane 中保持不同物理身份。
- `GeometryResolution`、`GeometryCluster`、`CountResolution` 与 `SelectionResult` 现在拒绝
  supported/reason 漂移、空 cluster、重复 candidate、未评估 count 和 selected/ranked 不一致。
- `GateCheck` 删除从未使用的 consequence 维度，并在类型边界锁定 candidate/decision stage
  与 final reason ownership；CandidateGate、DecisionGate 和 FinalDetection 拒绝不完整或跨层状态。
- `CandidateAssessment` 只保存 canonical evidence 与 CandidateGate；`EvidenceQuality` 从 evidence、
  proof paths 和 geometry residuals 确定性派生。Count hypothesis 从 plan、build、assessment 到
  selection 全程保持同一 identity，不再保存可手写的 physical-eligibility 布尔副本。
- Review-only assessment 不再构造零值 physical evidence 或 CandidateGate；dual-lane assessment
  保留各 lane 的 canonical evidence，并由父级 CandidateGate 单独判断 composition。
- Count、frame boundary、dimension prior、scan calibration 与 measurement dependency 的权限判别
  改为 typed identities；自由字符串不再控制 auto count、hard separator、overlap corroboration 或
  evidence independence。
- TIFF I/O 新增 canonical `TiffMetadata`，裁片写出与写后验证现在保留 description、datetime、
  software、artist、XMP 及其它明确可安全迁移的 metadata tag。
- Debug separator overlay 直接使用 FinalizationPlan 的原图尺寸，不再从缩放 preview 反推并产生
  off-by-one 坐标；随之删除无调用者的 scale floor 参数。
- Sequence hypothesis identity 只保留 measurement provenance；geometry 删除重复 name/strategy，
  frame-content evidence 删除只供 generic report reflection 使用的固定 composite 字段。
- Regression compare 使用 source page 与完整 request configuration 构成 typed identity；重复 identity
  直接失败，不再让同名 TIFF 的不同 page 或运行配置静默覆盖。
- Debug overlay 与 current report projection 直接接收 canonical separator、GateCheck、calibration 和
  bleed-plan 类型；项目内已知对象不再以 `Any` 掩盖边界。
- Deskew base/fallback 选择删除无单位的加权 quality score、固定 pass threshold 和 gain；有效性、
  独立上下边拟合、inlier 数与残差按确定性次序比较，参数台账也只使用单一真实单位。
- `FrameBoundary` 现在必须与其 canonical separator assignment 或 dimension constraint 的 position
  与 provenance 完全一致；证据身份和实际切线不能在 typed model 内漂移。
- Deskew line-fit 与 angle measurement 在构造时拒绝非有限值、无支持拟合、负 residual 及
  “成功但没有 edge fit”等不可能状态。
- Runtime 不再复制一个仅把 `report` 设为 false 的伪 worker configuration；串行、并行与 workflow
  全部接收同一个 canonical `RunConfig`，selection 也不再拥有误导性的 configuration alias。
- Boundary proof 的 measurement authority 只比较 typed `MeasurementIdentity`；自由字符串不能再
  决定 canvas、safety 或 review-only provenance 是否具有物理证明权限。
- Shared domain 不再混放 report、TIFF 或 output 类型：current-schema `ReportResult` 归 report 并在
  构造时验证，`ImageProfile` 与 TIFF tag value 归 I/O，`AxisBleedParameters` 归 output；units 只
  接收 resolution 与 unit，不再依赖完整 TIFF profile。
- Candidate geometry 删除重复的 source string；typed geometry、automatic eligibility、sequence
  strategy 与 provenance 是唯一身份。Candidate-source constants 与跨层 `constants.py` 删除，
  final reason vocabulary 由 DecisionGate 子层独占。
- Detection request/context 现在锁定 mode、layout、configuration、lane configuration 与 measurement
  cache identity；统一 work-layout validator 删除所有“未知即 vertical”的静默 fallback。
- Transform geometry 与 per-frame bleed plan 增加完整 typed invariants；applied angle、span pair、用户
  bleed、overlap protection、unresolved boundaries、feasible 和 reason 不能表达互相矛盾的状态。
- `CropEnvelope` 不再兼任 output clamp。`FrameBleedPlan` 显式保存 holder/lane
  `frame_output_bounds`，用户与叠片 bleed 可在基础物理包络外扩张，但不能越过实际输出边界；
  final frame 必须包含对应 decision frame。
- `FormatPhysicalSpec` 删除未参与检测的 family 描述，`FrameSizeMm` 删除由 option 顺序已唯一表达的
  nominal/variant label；configuration report 只输出检测实际消费的物理事实。
- CandidateGate 直接消费的 topology、content preservation、frame dimensions、sequence
  conservation 与 evidence independence 现在由 typed invariants 锁定 state/measurement 一致性。
  Dual-lane topology 使用 composition scope，measurement provenance 保留 lane identity。
- DecisionGateAssessment 在自身边界验证 final reason vocabulary；未知 reason 不再延迟到 report
  validator 才失败。
- `EvidenceQuality` 现在是 `AssessedCandidate` 的 canonical derived property；selection 与 report
  只读该结果，旧的 assessment quality 计算入口已删除。
- Active detection/cache 接口统一使用 `Configuration` 与 `Parameters` 词汇；旧的局部
  `*_policy` / `profile_config` 命名已删除。
- Deskew 固定灰度身份阈值已由 per-image robust statistics 取代；percentile sampling budget、
  edge quantiles 和 numerical floors 均由显式参数拥有。
- Physical fact、adaptive measurement、numerical safety、execution budget 与 diagnostics 参数
  在 canonical owner 构造时验证；低层 helper 不再静默修正无效参数。
- Separator observation 现在要求真实横跨短轴的 8 邻域像素路径。Content span 与 frame coverage
  冲突保持 unavailable，旧的 write-only undercrop confirmation 字段已删除。
- Observation、hypothesis、solver 与 dual-lane proposal 的预算耗尽状态全程传播；截断搜索不能
  形成 resolved geometry。Dual-lane composition 同时要求每条 lane 的 gate 与 geometry resolution。
- Cache reuse 不再从 report candidate 反向选择 configuration；output bleed layout 必须显式传入。
- Analysis reuse source identity 现在包含文件内容 SHA-256；同一次运行只计算一次，并由 cache
  lookup 与 current report 共同使用。相同文件名、大小和时间戳不再足以复用检测。
- TIFF `ImageProfile` 已成为 immutable typed input contract；rational、enum 和 NumPy scalar 在
  I/O 边界归一化，calibration/cache/report 不再兼容解析底层 tag 对象或旧 rational shape。
- Current report validator 现在递归要求 canonical typed model 与 report projection 的精确字段集合；
  顶层或任意嵌套层级出现旧 alias、额外字段或不一致 derived gate 字段都会拒绝 cache reuse。
- `detector_kind` 不再作为重复 configuration 字段存储，而由 physical layout 与 strip mode 唯一
  推导；DetectionContext 同时删除无消费方的 TIFF `ImageProfile`，I/O metadata 不再下沉 detection。
- Measurement cache 的参数、精确区域与 threshold key 已改为 named immutable types；旧
  `tuple[Any, ...]` 位置 key 删除，cache 仍只保存 count/offset-independent root measurements。
- `FinalDetection` 已删除 optional selection、sequence span、separator assignments 与 frame
  boundaries 等候选阶段副本。Report/debug 显式接收 `SelectionResult` 或 selected candidate；
  cache restoration 只恢复 final decision/output，不再维护半有效 FinalDetection 或物理反序列化。
- Analysis reuse 在任何 Debug Preview/Analysis 请求下都会重新检测；cached crop export 只重放
  必要的 array transform，不再重建 base gray，也不再接收未消费的 configuration bundle。
- Analysis reuse fingerprint 现在覆盖完整的已解析 configuration bundle；dual-lane 子配置变化会
  使旧分析失效。Bundle 同时拒绝空集合、initial identity 漂移和重复 configuration identity。
- Diagnostics 参数不再使 detection analysis fingerprint 失效；无法测得的 content threshold 也只
  计算一次。Malformed current-schema record 现在返回 validation error，不再从 validator 抛异常。
- 318 项测试、14 个 format/mode configuration、package/regression compile、launcher syntax、
  version 和 whitespace 检查通过。

#### 物理序列求解与经验参数退场（2026-07-12）

- 逐边贪心 assignment 已替换为全局单调 `SequenceSolution` solver；零宽、负宽和倒序 frame
  不再能形成候选。
- `FrameDimensionPrior`、`PhotoInterval`、position/width constraints、
  `ObservedSpacingEvidence` 和 `SpacingHypothesis` 成为不同 canonical types。Geometry
  hypothesis 不能自证 overlap 或触发自动 bleed。
- 候选比较改为 `EvidenceQuality` 与确定性物理排序；scalar confidence、weighted score、
  format-family profile 和固定 geometry clustering percentage 已删除。
- `DetectionPolicy` / `FormatParameters` / assembly wrappers 已由直接构建的
  `DetectionConfiguration` 取代；旧 `x5crop.policies` 源码树已删除且无 compatibility shim。
- Global overlap capacity 已替换为逐 boundary `FrameBleedPlan`。只有 independently observed 或
  independent-constraint corroborated overlap 扩张相邻两张 frame 的对应侧，无关 frame 不再共享最大 bleed。
- Current report schema 更新为 `detection_report / physical_sequence_resolution`，canonical
  sections 为 `input / configuration / selection / decision / output`。旧 record 直接重新检测。
- Candidate geometry 拆成 `SequenceSolution / DualLaneSolution / ReviewOnlyGeometry`；
  dual-lane 与 review-only 不再用空字段或可选 lane 字段伪装成标准 sequence。
- 所有结构、PASS/REVIEW、count、crop 和 schema diff 均按批准方案接受；measurement 数值校准
  仍是后续独立项目。

#### Frame Sequence 物理模型重构（2026-07-11）

- Detection 采用
  `BoundaryPathObservation -> SequenceHypothesis -> CandidateGeometry -> CandidateEvidence -> CandidateGate -> GeometryResolution -> DecisionGate`
  的 immutable typed data flow。
- 普通物理候选的 canonical source 统一为 `frame_sequence`；boundary、separator 和 dimensions
  只作为 observation/proof provenance。
- `HolderSpan`、`VisibleSequenceSpan` 和 `CropEnvelope` 成为不同 canonical identities；
  generic outer、film-span、gap family、equal grid 和 detection correction surfaces 已删除。
- Separator 是 count-independent raw band。只有完全落入物理允许区间、通过横跨短轴连续性且
  provenance 独立的 assignment 才是 hard separator。
- 缺失 separator 使用 `DimensionConstrainedBoundary`；focused pixel measurement 保持
  geometry-dependent，不能增加 hard separator 数量。
- 每个 raw band 都保留 candidate-specific assignment；未落入任何允许区间的宽 band 明确记录为
  contradicted，只有 `used_for_boundary` 的独立 assignment 能定义实测切线。
- Frame sequence 使用 signed spacing 守恒：正值为 separator、零为接触、负值为叠片。
  Separator 宽度和片距允许变化，photo-size 使用真实 band edges 与物理 frame dimensions。
- Holder occlusion 只允许发生在首张 leading edge 和末张 trailing edge；没有真实 white-holder
  transition 时不能声称 occlusion。不可见遮挡不算脚本 undercrop，可见内容未被 frame union
  覆盖仍然阻断。
- Partial auto count 按允许 count 从大到小评估。`GeometryResolution` 是唯一 early-stop 输入；
  CandidateGate 和 confidence 都不能停止候选搜索。
- Content 只向外扩张 `CropEnvelope`，并提供遗漏内容反证和 preservation evidence；它不创建或
  修改 `VisibleSequenceSpan`、frame dimensions 或内部 cut。Content-region measurement 使用
  物理 frame-width reference，不读取 nominal/candidate count。
- `CropEnvelope` 只覆盖 boundary uncertainty。额外 margin 由用户 bleed 唯一控制；signed overlap
  只能增加长轴 bleed，不能改变 candidate、Gate 或 status。
- Finalization 不再读取 gray 或重新检测几何，只应用 `OutputBleedPlan` 和 canvas clamp。
- Dual-lane composition 保留每条 lane 的独立 `CropEnvelope` 和 signed spacing；基础输出 frame
  不再跨越两排胶片，任一 lane 的叠片仍可进入统一 `OutputBleedPlan`。

#### 架构与 schema 清理

- `CandidateGate` 与 `DecisionGate` 是唯一 gates；只有 DecisionGate 创建 status 和
  `final_review_reasons`。
- Runtime 是 format/mode/policy 唯一解析边界。Foundation 不知道 format identity、decision 或
  report schema，也不静默创建参数。
- 删除旧字段、alias、shim、reducer、compatibility schema、重复 overlap model、单字段 trace
  wrapper 和孤儿 count preflight。
- Current report identity 更新为：

```text
schema_id: detection_report
schema_revision: frame_sequence_geometry
```

- Report/debug/cache reuse 只接受 current schema。Debug Analysis 保持三联图，只读 typed final
  model。
- 历史 reference diff 只用于定位变化，不作为 parity gate；PASS/REVIEW、crop、confidence、reason
  和 schema diff 全部允许，参数与阈值留待真实样片校准。

#### 本轮验证

- 212 项 current contract/behavior tests 与 14 个 format/mode policy consistency checks 通过；
  package/regression compile、launcher syntax、version 和 whitespace 检查通过。
- 代表样片覆盖 `135/full`、`135/partial auto`、`135/partial -n 3`、
  `120-66/partial auto`、`half/full`、`120-67/full|partial`；另验证 dual-lane、cache reuse、
  review export、双 worker、TIFF metadata 和三联 Debug Analysis。
- 结构验收不以样片当前 PASS/REVIEW 数量为阻塞条件；检测参数校准是后续独立项目。

### 版本摘要

| Version | 状态 | 摘要 |
|---|---|---|
| V4.9 | 当前 active development | Typed physical frame-sequence model；历史输出不作为 oracle。 |
| V4.7 | 上一个 development | 源码分层重构，薄入口与模块化 `x5crop/`。 |
| V4.6 | development | Policy-driven detection 结构。 |
| V4.3-V4.5 | historical development | Full/partial、120、half、diagnostics 与 candidate experiments。 |
| V4.2.8 | 当前 stable release | Partial 模式才询问 count；Return/`auto` 自动判断。 |
| V3-V4.2 | historical | 早期主流程、格式参数与几何实验。 |

### 发布策略

- GitHub Releases 是用户下载入口；`main` 可以领先稳定发布版。
- Release zip 只包含 standalone script、launchers、TXT user docs 和 install/uninstall launchers。
- 用户包不包含 `x5crop/`、tests、development docs、diagnostics launcher 或生成文件。

## English Changelog

### V4.9 Current Development Line

#### Physical Sequence Resolution And Empirical-Profile Removal (2026-07-12)

- The sole current schema identity is now
  `detection_report / physical_sequence_resolution`; reports, cache, tests, and
  tools do not accept the superseded revision.
- Dimension-constrained cuts retain their position intervals instead of turning
  unobserved boundaries into exact midpoints. A separator's width allowance is
  independent of overlap at another boundary.
- Trusted calibration, measured sequence edges, and all remaining observed
  spacings may uniquely corroborate one negative spacing. This evidence protects
  only the adjacent output sides and cannot prove its own conservation equation.
- Function-local numeric checks now exempt only AST-identifiable indexes,
  dimensions, and mathematical identities. Content-evidence consensus, debug
  styling, RGB/uint8 encoding, and universal physical coefficients have explicit
  owners. Dual-lane translation now uses a named typed aggregate instead of a
  positional five-tuple.
- A global monotonic `SequenceSolution` solver replaces greedy boundary assignment;
  zero-width, negative-width, and reversed frames cannot become candidates.
- Frame priors, photo intervals, position/width constraints, observed spacing, and
  geometry spacing hypotheses are separate canonical types. A geometry hypothesis
  cannot prove overlap or trigger automatic bleed.
- Edge frames with supported white-holder occlusion are excluded from ordinary
  photo-width contradiction; dimension evidence uses only unoccluded independent frames.
- Two-sided single-frame holder occlusion keeps one canonical combined hidden-width
  interval while per-side allocation remains unavailable, preventing double counting.
- Candidate comparison now uses `EvidenceQuality` and deterministic physical ordering.
  Scalar confidence, weighted scores, format-family profiles, and fixed-percentage
  geometry clustering are removed.
- Active detection and cache interfaces now use only `Configuration` and `Parameters`
  vocabulary; stale local policy/config aliases are removed.
- Directly built `DetectionConfiguration` replaces the policy/parameter/assembly
  translation chain. The superseded `x5crop.policies` source tree is deleted without
  a compatibility shim.
- Per-boundary `FrameBleedPlan` replaces global overlap capacity. Only adjacent frame
  sides receive independently observed or independent-constraint corroborated overlap protection.
- `CropEnvelope` no longer doubles as the output clamp. Each frame has an explicit
  holder/lane `frame_output_bounds`; user and overlap bleed may expand beyond the
  physical envelope without shrinking or moving the decision frame.
- Current reports use `detection_report / physical_sequence_resolution` with canonical
  `input / configuration / selection / decision / output` sections. Old records are
  redetected.
- Candidate geometry now uses distinct `SequenceSolution`, `DualLaneSolution`, and
  `ReviewOnlyGeometry` types instead of optional lane fields or empty sequence geometry.
- All behavioral and schema diffs are accepted for this structural project; numerical
  measurement calibration remains separate.
- Debug overlays and current-report projections now accept canonical separator,
  GateCheck, calibration, and bleed-plan types instead of hiding known boundaries
  behind `Any`.
- Deskew base/fallback selection no longer uses a unitless weighted score, fixed
  pass threshold, or gain. It compares validity, independent edge fits, inliers,
  and residuals deterministically, and every parameter contract has one concrete unit.
- `FrameBoundary` must now exactly match the position and provenance of its canonical
  separator assignment or dimension constraint, preventing evidence identity from
  drifting away from the cut actually used.
- Deskew line-fit and angle measurements now reject non-finite values, unsupported
  fits, negative residuals, and impossible successful-without-an-edge states at
  construction time.
- Runtime no longer copies a report-disabled pseudo worker configuration. Sequential,
  parallel, and workflow paths receive the same canonical `RunConfig`, and selection
  no longer appears to own a separate configuration alias.
- Boundary-proof authority now compares typed `MeasurementIdentity` values only;
  free-text literals cannot decide whether canvas, safety, or review-only provenance
  has physical proof authority.

#### Physical Frame-Sequence Model (2026-07-11)

- Detection now follows immutable typed stages from boundary observations through
  CandidateGate, GeometryResolution, and DecisionGate.
- Ordinary physical candidates now use the canonical `frame_sequence` source;
  boundary, separator, and dimensions remain observation/proof provenance only.
- `HolderSpan`, `VisibleSequenceSpan`, and `CropEnvelope` are distinct canonical
  identities. Generic outer/film-span, gap families, equal grids, and detection
  correction surfaces are removed.
- Separator bands are count-independent raw observations. Only fully contained,
  cross-axis-continuous, provenance-independent assignments become hard evidence.
- Missing separators use `DimensionConstrainedBoundary`; focused measurements remain
  geometry-dependent and never increase hard-separator count.
- Every raw band keeps a candidate-specific assignment. Bands outside every physical
  interval remain explicit contradictions; only independent assignments marked
  `used_for_boundary` define measured cuts.
- Signed spacing represents separator, contact, or overlap and participates in one
  sequence-conservation equation. Variable separator width/spacing is allowed;
  photo-size evidence uses physical frame dimensions and measured band edges.
- Holder occlusion is limited to the leading edge of the first frame and trailing
  edge of the last. Occlusion requires a real white-holder transition and shortened
  visible edge frame.
- Partial auto count evaluates larger allowed counts first. GeometryResolution alone
  controls early-stop; CandidateGate and confidence cannot stop candidate search.
- Content only expands `CropEnvelope` outward and supplies missing-content
  counterevidence and preservation evidence. It never creates or changes the
  visible sequence, frame dimensions, or internal cuts.
- CropEnvelope covers boundary uncertainty only. User bleed is the only extra margin;
  signed overlap can increase long-axis bleed but cannot change candidate geometry,
  Gate outcomes, or status.
- Finalization only applies `OutputBleedPlan` and canvas clamp. It does not read pixels
  or redetect geometry.
- Dual-lane composition retains one `CropEnvelope` and lane-indexed signed spacing per
  lane. Base output frames no longer span both rows, and overlap in either lane still
  reaches the shared `OutputBleedPlan`.

#### Architecture And Schema Cleanup

- CandidateGate and DecisionGate are the only gates; only DecisionGate creates status
  and `final_review_reasons`.
- Runtime is the sole format/mode/policy resolution boundary. Foundation layers know
  no format identity, decision state, or report schema.
- Superseded fields, aliases, shims, reducers, schemas, duplicate overlap models,
  single-field trace wrappers, and orphan count preflight are deleted without
  compatibility surfaces.
- Current report identity is `detection_report / frame_sequence_geometry`.
- Report, debug, and cache reuse accept current schema only. Debug Analysis remains a
  passive three-panel readout.
- Historical reference diffs are audit material, not parity gates. Detection
  calibration remains a separate real-sample project.

#### Verification

- All 212 current contract/behavior tests and 14 format/mode policy consistency checks
  passed, together with package/regression compile, launcher syntax, version, and
  whitespace validation.
- Representative smokes cover standard full/partial, partial auto/explicit count,
  120-66, half, 120-67, dual lane, cache reuse, review export, multiprocessing, TIFF
  metadata, and three-panel Debug Analysis.
- Current PASS/REVIEW counts do not block structural acceptance; numerical calibration
  follows separately.

### Version Summary

| Version | Status | Summary |
|---|---|---|
| V4.9 | Active development | Typed physical frame-sequence model; historical output is not an oracle. |
| V4.7 | Previous development | Layered source rewrite with a thin entry and modular `x5crop/`. |
| V4.6 | Development | Policy-driven detection structure. |
| V4.3-V4.5 | Historical development | Full/partial, 120, half, diagnostics, and candidate experiments. |
| V4.2.8 | Stable release | Count is requested only in partial mode; Return/`auto` selects automatic count. |
| V3-V4.2 | Historical | Early workflow, format parameters, and geometry experiments. |

### Release Policy

- GitHub Releases are the user download channel; `main` may lead the stable release.
- Release zips contain only the standalone script, launchers, TXT user docs, and
  install/uninstall launchers.
- User packages exclude `x5crop/`, tests, development docs, diagnostics launchers,
  and generated files.
