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

#### 封口参数与几何解析契约（2026-07-12）

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
- Dual-lane 坐标迁移使用命名 typed aggregate，不再用五元 tuple 下标传递物理 stage data。
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
- Diagnostics 参数不再使 detection analysis fingerprint 失效；无法测得的 content threshold 也只
  计算一次。Malformed current-schema record 现在返回 validation error，不再从 validator 抛异常。
- 290 项测试、14 个 format/mode configuration、package/regression compile、launcher syntax、
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
  `BoundaryObservation -> SequenceHypothesis -> CandidateGeometry -> CandidateEvidence -> CandidateGate -> GeometryResolution -> DecisionGate`
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
- Candidate comparison now uses `EvidenceQuality` and deterministic physical ordering.
  Scalar confidence, weighted scores, format-family profiles, and fixed-percentage
  geometry clustering are removed.
- Directly built `DetectionConfiguration` replaces the policy/parameter/assembly
  translation chain. The superseded `x5crop.policies` source tree is deleted without
  a compatibility shim.
- Per-boundary `FrameBleedPlan` replaces global overlap capacity. Only adjacent frame
  sides receive independently observed or independent-constraint corroborated overlap protection.
- Current reports use `detection_report / physical_sequence_resolution` with canonical
  `input / configuration / selection / decision / output` sections. Old records are
  redetected.
- Candidate geometry now uses distinct `SequenceSolution`, `DualLaneSolution`, and
  `ReviewOnlyGeometry` types instead of optional lane fields or empty sequence geometry.
- All behavioral and schema diffs are accepted for this structural project; numerical
  measurement calibration remains separate.

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
