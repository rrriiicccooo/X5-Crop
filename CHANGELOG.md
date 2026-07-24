# X5 Crop 更新日志 / Changelog

本文件只记录版本级行为、验证边界和回滚背景。当前架构见 `ARCHITECTURE.md`，用户操作见
`README.md`。 / This file records version behavior, validation boundaries, and
rollback context. See `ARCHITECTURE.md` for design and `README.md` for usage.

- 当前开发版本 / Active development: **V4.9**
- 当前稳定发布 / Stable release: **v4.2.8**

## V4.9 — 当前开发线 / Current Development

V4.9 是 current-only 的物理模型与源码重构。历史 PASS/REVIEW、报告 schema、人工标签和
裁切几何不是兼容目标。 / V4.9 is a current-only physical-model and source rewrite.
Historical decisions, schemas, human labels, and crop geometry are not compatibility
targets.

### 2026-07-24 — Tools、文档与人工审阅归零

- `tools/` 只保留四类当前职责：`verify`、`release/`、`regression/compare.py` 和
  `tests/`。Release builder、manifest 与 standalone builder 归入 `tools/release/`；
  Git Hook 安装器归入 `tools/git/`；共享测试 fixture 与静态合同归入
  `tools/tests/support/`。 / Tooling now has four current roles: verification,
  release construction, report comparison, and contracts. Files are grouped by owner.
- 删除旧 `frame_slot_reference`、`sample_expectations`、`sample_validation`、
  `sample_identity` 及其专用测试。这些模块只服务已撤销的人工基线，不再有当前输入。
  / Removed the legacy manual-reference regression chain and its dedicated tests.
- 清空本地旧人工审阅：manual crop、deskew、photo-edge 标签、清单、审阅图、survey 和
  comparison 全部退出工作区；不迁移任何旧结论。原始 TIFF 样片保留。 /
  Reset all local manual-review labels and generated review artifacts without
  migrating conclusions; source TIFF samples remain.
- 当前没有人工基线或 human-confirmed photo-edge authority。Runtime、tests 和 tools
  均不读取人工白名单；下一轮人工审阅必须以新 schema 从零建立。 /
  No human baseline is current. A future review cycle must start from a new schema.
- README 与 Quick Start 改为中英文共用结构；CHANGELOG 只保留当前版本事实；
  ARCHITECTURE 继续独占运行流与数值合同。 / User docs now share one concise bilingual
  structure, while architecture remains the sole design owner.

### V4.9 当前累计行为 / Current Cumulative Behavior

- `FramePhysicalSpec` 只保存照片尺寸；`ScanCanvasPhysicalSpec` 只保存片夹扫描画布。
  TIFF DPI/PPI 仅作 I/O metadata。 / Photo and scan-canvas facts have separate owners;
  TIFF resolution is metadata only.
- 已知单条画布由 source pixel aspect 唯一匹配并生成 `CanvasPixelScale`；无匹配或竞争
  profile 保持 typed unresolved。`135-dual` 不虚构固定画布。 /
  Known canvases resolve one physical pixel scale; unmatched, competing, and
  dual-lane cases preserve their typed state.
- 分帧前从任意清晰区域形成材料与极性无关的 photo-edge observations。连续 ridge 成为
  不可拆 fragment；法向联合区域同时约束 top、bottom、照片高度、中心、containment 和
  完整 `FrameSizeMm`。 / Cross-region observations feed one joint normal geometry
  model with complete physical labels.
- `PhotoEdgePairEvidence` 是唯一边缘身份真相。Deskew、mapped pair、
  `SharedShortAxisPlan` 和 frame sequence 只消费同一 selected pair；旋转后不重新测量
  短轴。 / All downstream consumers reuse one source pair.
- Pair identity、transform precision 与全 workspace shared-axis safety 独立判断。
  `CandidateGate` 判断候选，`DecisionGate` 独占最终 PASS/REVIEW。 /
  Identity, transform, and crop safety are separate consumers; only `DecisionGate`
  creates final status.
- 当前 report revision 为 `cross_region_photo_edge_geometry`。Report 与 Debug
  只读 typed evidence，不保存 dense responses，不重算几何，也不作为 detection cache。
  / Report and Debug are read-only audit surfaces for the current schema.

## 验证边界 / Validation Boundary

- `tools/verify` 是唯一机械验证入口；Hook 与 CI 只调用它。 /
  `tools/verify` is the sole mechanical verifier used by hooks and CI.
- Unit/contract、compile、configuration 和 release-package 检查证明结构一致性，不证明
  真实照片边缘已经达到生产准确性。 / Mechanical checks prove structural consistency,
  not production photo-edge accuracy.
- 当前人工审阅已归零，因此不存在 human-confirmed PASS、pair 或 crop baseline。
  恢复人工审阅前，只能声明机器证据与结构验证。 /
  With manual review reset, no human-confirmed PASS, pair, or crop baseline exists.

## v4.2.8 — 当前稳定发布 / Stable Release

v4.2.8 仍是面向普通用户的稳定 GitHub Release。V4.9 尚未替代稳定发布。 /
v4.2.8 remains the stable GitHub Release; V4.9 has not replaced it.

## 发布与回滚 / Release And Rollback

- 发布包由 `tools/release/manifest.py` 独占内容清单，由
  `python3 -m tools.release.build --version <version>` 构建。 /
  `tools/release/manifest.py` owns package contents; `tools.release.build` creates
  the archive.
- V4.9 为破坏性 current-only 迁移。回滚必须整体恢复物理模型、配置、workspace、
  report schema、contracts 与文档；不得混用旧人工基线、旧 deskew 或旧 schema。 /
  Rollback must restore the model, configuration, workspace, schema, contracts,
  and docs as one unit.
