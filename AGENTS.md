# Codex Agent Rules / Codex 协作规则

This file contains short, binding repository rules. It owns standing policy,
document roles, release policy, and verification priorities—not architecture,
history, or task status.

本文件只保存简短且强制的仓库规则：长期政策、文档职责、发布政策和验证优先级。
架构、历史和当前任务状态不属于这里。

## First Moves / 开始工作

1. Read `README.md` before editing. Read `PROJECT_MEMORY.md` only when the user
   explicitly resumes, updates, or requests the cross-session handoff.
2. Check the current branch and working tree:

   ```bash
   git branch --show-current
   git status --short
   ```

3. Treat GitHub as authoritative for tracked source and docs. NAS and copied
   folders are transport or testing surfaces only.

开始编辑前阅读 `README.md`。只有在用户明确恢复、更新或请求跨会话交接时才读取
`PROJECT_MEMORY.md`。始终先核对分支和工作树；GitHub 是受跟踪源码与文档的权威来源。

Repository / 仓库：

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## Document Ownership / 文档职责

| File / 文件 | Canonical responsibility / 唯一职责 |
|---|---|
| `快速启动_Quick_Start.md` | Release quick-start / 发布版快速启动 |
| `README.md` | Complete user manual / 完整用户手册 |
| `ARCHITECTURE.md` | Current runtime flow and source layering / 当前运行流与源码分层 |
| `CHANGELOG.md` | Version-level behavior, validation, and rollback context / 版本级行为、验证与回滚信息 |
| `PROJECT_MEMORY.md` | On-demand rolling checkpoint for cross-session continuation / 按需读取的跨会话滚动检查点 |
| `AGENTS.md` | Standing coordination policy only / 仅长期协作政策 |

Do not duplicate long explanations. Link to the canonical owner. User-readable
durable docs must remain concise, professional, current, non-overlapping, and
Chinese-English paired where practical.

不要复制长篇解释；应链接到唯一所有者。面向用户的长期文档必须简洁、专业、当前、
互不重叠，并在适合时保持中英文对应。

## Handoff And Project Memory / 交接与项目记忆

- `PROJECT_MEMORY.md` is the sole cross-session handoff. Do not create parallel
  `SESSION_HANDOFF.md`, `NEXT_ACTIONS.md`, `DECISIONS.md`, or equivalent files.
- Read or update it only when the user explicitly resumes, requests a handoff,
  or asks to change project memory.
- Keep only the current objective, verified checkpoint, validation boundary,
  open risks, and exact next action. Architecture and history stay with their
  canonical documents.
- Git, source, original TIFFs, current reports, Debug Analysis, and live command
  output always outrank memory.
- When manual review restarts, define one current schema before recording labels.
  Never restore or migrate retired labels, candidate IDs, decisions, or runtime
  whitelists.

`PROJECT_MEMORY.md` 是唯一跨会话交接文件；不得建立平行 handoff。只有用户明确要求恢复、
交接或更新项目记忆时才读写它。项目记忆只保存当前目标、已验证检查点、验证边界、开放风险与
精确下一步；现场 Git、源码、原 TIFF、current report、Debug 与命令输出始终优先。人工审阅
重新开始时先定义唯一 current schema，不恢复或迁移旧标签、ID、结论或运行时白名单。

## Current Scope / 当前范围

- Active entry point / 当前入口：`X5_Crop.py` V4.9.
- Stable GitHub Release / 当前稳定发布：`v4.2.8`.
- Development source lives under `x5crop/`; releases may embed it into one
  standalone `X5_Crop.py`.
- Keep work on the standalone X5 Crop workflow unless the user explicitly
  resumes app or native packaging.
- Root `ARCHITECTURE.md` is the only architecture document; there is no `docs/`
  mirror.
- Current task and manual-review status live only in `PROJECT_MEMORY.md`.

## Standing Implementation Rules / 长期实现规则

- Preserve TIFF bit depth, channel structure, ICC/color space, resolution,
  metadata, and known lossless compression behavior unless explicitly changed.
- Structural cleanup need not preserve historical PASS/REVIEW, geometry,
  confidence, reason, schema, debug, or cache parity. Prefer the cleaner and
  more physically truthful current model.
- Calibrate detection behavior from real samples after structural closure. Do
  not broadly loosen rules to make one file pass; recheck known-good formats,
  especially `135`.
- Named-TIFF and end-to-end regressions must run the complete detection flow,
  including scan-canvas matching, source photo-edge observation, and transform
  assessment. Pure solver unit tests may construct an explicit typed
  `DetectionWorkspace` fixture, but production runtime must have no bypass.
- Keep photo dimensions in `FramePhysicalSpec` and holder-scan dimensions in the
  sole `ScanCanvasPhysicalSpec` catalog. TIFF resolution tags are preserved I/O
  metadata, never detection scale, evidence, or decision input.
- Horizontal-strip wording is the baseline for directional requests; implement
  the rotated vertical behavior too.
- Update user docs for changes to setup, usage, launchers, outputs, or release
  packaging; update `ARCHITECTURE.md` for runtime flow or source-layer changes;
  update `CHANGELOG.md` for version-level behavior, packaging, validation, or
  rollback changes.

除非用户明确改变要求，否则必须保持 TIFF 位深、通道、ICC/色彩空间、分辨率、元数据和
已知无损压缩行为。结构重构以当前物理真实性为准，不以历史输出一致性为目标；检测校准必须
回到真实样片，不能为单个文件普遍放宽规则。照片规格与片夹扫描画布必须由不同 typed owner
保存；TIFF resolution 标签只作 I/O metadata，不得成为检测尺度或决策输入。

## Extreme Cleanliness Contract / 极致干净合同

- Every active concept has one canonical name, type, owner, and source of truth.
- Data and authority flow one way through proposal, build, evidence, assessment,
  selection, decision, finalization, output, report, and debug.
- `CandidateGate` and `DecisionGate` are the only gates. Only `DecisionGate`
  creates final status and final reasons.
- Format specs, adaptive measurements, runtime configuration, and report
  descriptions remain separate. Resolve configuration at the runtime boundary;
  lower layers receive explicit typed inputs and never query registries or invent
  defaults.
- Foundation code knows geometry, pixels, TIFF I/O, cache mechanics, and units—not
  format identity, decision state, or report schema.
- Runtime, tests, tools, report, and debug consume the current schema only. Reports
  are audit artifacts, never a detection cache; only exact count/offset-independent
  measurements may be cached. Delete superseded APIs, fields, aliases, imports,
  reducers, shims, tests, and compatibility branches in the same change.
- Keep no dead files, unreachable helpers, pass-through wrappers, duplicate
  models, hidden decision constants, or abstractions that merely move complexity.
- Add an abstraction only when it removes real duplication or ownership
  ambiguity. Names must state physical facts or lifecycle responsibility.
- Code, contract tests, `ARCHITECTURE.md`, current reports, and Debug Analysis must
  describe the same system.
- For each newly discovered residue, add a contract that fails on that class,
  remove the whole class, and retain the contract. Tests and fixtures obey the
  same current-only and physical-truth rules as runtime code.
- Architecture cleanup closes only after the full verifier passes and two
  consecutive read-only audits using the same frozen checklist find no known
  violations. Reopen it only for a demonstrated contract violation, an
  unrepresentable physical fact, or a genuinely incompatible capability.

每个概念只能有一个名称、类型、所有者和真相来源；权限单向流动。删除而不是兼容，复用现有
typed object 而不是重复翻译，只有消除真实重复或职责歧义时才增加抽象。代码、测试、架构、
当前报告和 Debug 必须描述同一个系统。

## Detection And Performance / 检测与性能

- Search hints, blank appearance, repeated-width patterns, and execution budgets
  are not physical proof. Unresolved geometry remains typed unresolved.
- Early-stop comes only from resolved geometry. Budget exhaustion is unavailable
  geometry, never reliability evidence; candidate and final decisions remain
  separate authorities.
- Profile one fixed real sample before optimizing. Record wall/detection time,
  candidate builds, repeated measurements, and the actual call-stack hotspot.
- Cache only exact count/offset-independent measurements with typed keys—never
  candidates, gates, decisions, final reasons, or approximate geometry.
- Re-profile the same sample after each optimization wave, then run contracts,
  representative format/mode samples, current-schema validation, and visual Debug
  Analysis inspection. Output diffs are calibration evidence, not parity gates.

## Verification / 验证

`tools/verify` is the canonical executable verifier. Hooks and CI are thin
adapters and must call it rather than duplicate its commands.

`tools/verify` 是唯一可执行验证入口；Hook 和 CI 只能作为薄适配器调用它，不能复制命令。

```bash
tools/verify full
```

For detection changes, compare current-schema reports with:

```bash
python3 -m tools.regression.compare <baseline> <candidate>
```

Inspect at least transform outcome/source and mapped shared short axes, lane
divider mapping, status/reasons, selected rank, geometry resolution, crop
envelopes, and final boxes. Report diffs are audit evidence, not historical-parity
requirements.

Local `Test/` fixtures are untracked and their layout is not a source contract.
Discover available TIFFs at verification time:

```bash
find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
```

When available, cover representative `135/full`, `120-66/partial`, `half/full`,
and `120-67/full` inputs. Unit-test success alone never proves named TIFF geometry;
inspect current reports and Debug Analysis before a physical-completion claim.

## Completion And Sync / 完成与同步

- Enable the versioned hooks once per clone with `tools/git/install_hooks.sh` and
  never use `--no-verify`.
- After Codex changes tracked source, docs, configuration, launchers, or release
  metadata, verify, commit, and push the current branch unless the user explicitly
  says not to. This is standing authorization for a verified push.
- Before committing, confirm staged and unstaged changes are intentional. If a
  commit or push fails, report the blocker and leave the safest possible state.

每次修改受跟踪内容后，除非用户明确禁止，都应完成验证、提交并推送当前分支；不得绕过 Hook。

## Git And Local Files / Git 与本地文件

- Preserve user and other-session changes; never reset or restore them without
  explicit permission.
- Keep `.gitignore`, `.github/`, and `tools/` visible. `install/` is also kept
  visible so release inputs participate in routine validation.
- Intended sparse checkout / 预期稀疏检出：

  ```text
  /*
  !/archive/
  !/release/
  !/LICENSE
  ```

- Never commit `.venv/`, `.venv-build/`, `build/`, `dist/`, `release/`, caches,
  `.DS_Store`, `downloaded_apps/`, `Test/`, generated `x5_crop_output/`, or large
  TIFF samples unless explicitly approved as Git LFS fixtures.

## Release Packages / 发布包

- `tools/release/manifest.py` is the exact package-content owner.
- Build a user zip with
  `python3 -m tools.release.build --version <version>`.
- The builder must generate the standalone script, package only manifest entries,
  preserve executable launchers, and use Python `zipfile` so Chinese names carry
  UTF-8 metadata.
- User packages exclude modular source, tests, internal docs, diagnostics
  launchers, local samples, and generated outputs.
- On macOS, prepare only the current release folder: mark the main launcher and
  installer executable and remove quarantine attributes when available. Never
  establish permanent system-wide trust.

`tools/release/manifest.py` 是发布内容的唯一清单；发布构建器只能打包清单条目，并正确保存中文
文件名和启动器权限。发布包不得包含模块化源码、测试、内部文档、诊断启动器、样片或生成输出。
