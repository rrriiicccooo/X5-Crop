# Codex 协作规则

本文件只保存简短且强制的仓库政策：文档职责、实现边界、验证、发布和交接规则。
架构、历史与当前任务状态由各自唯一文档负责。

## 开始工作

1. 编辑前阅读根 `README.md`。只有用户明确恢复、更新或请求跨会话交接时，才读取
   `docs/PROJECT_MEMORY.md`。
2. 核对当前分支与工作树：

   ```bash
   git branch --show-current
   git status --short
   ```

3. GitHub 是受跟踪源码与文档的权威来源；NAS 和复制目录只用于传输或测试。

仓库：

```text
git@github.com:rrriiicccooo/X5-Crop.git
https://github.com/rrriiicccooo/X5-Crop
```

## 文档职责与语言

| 文件 | 唯一职责 | 语言 |
|---|---|---|
| `README.md` | GitHub 简短入口与语言选择 | 精简中英双语 |
| `docs/user-guide.zh-CN.md` | 中文完整用户手册 | 中文 |
| `docs/user-guide.en.md` | 英文完整用户手册 | English |
| `docs/quick-start.zh-CN.md` | 中文发布版快速启动 | 中文 |
| `docs/quick-start.en.md` | 英文发布版快速启动 | English |
| `docs/ARCHITECTURE.md` | 当前运行流、数值合同与源码分层 | 中文 |
| `docs/CHANGELOG.md` | 版本级行为、验证边界与回滚背景 | 中文 |
| `docs/PROJECT_MEMORY.md` | 按需读取的唯一跨会话检查点 | 中文 |
| `AGENTS.md` | 长期协作政策 | 中文 |

- 内部文档只写中文正文，保留必要的英文标识、类型名、命令与 schema 名。
- 公共中英文文档按语言分开，不在同一文件逐段重复。
- 默认不读取英文公共文档；只有英文文档、发布或对应事实校验任务才读取。
- 用户可见的设置、用法、启动器、输出或发布包变化，必须在同一变更中更新两种公共语言。
- 不复制长篇说明；链接到唯一 owner。文档必须简洁、专业、当前且互不重叠。
- 除根 `README.md`、`AGENTS.md` 与 `LICENSE` 外，实质性文档只放在 `docs/`。
  `docs/ARCHITECTURE.md` 是唯一架构文档，不建立镜像。

## 交接与项目记忆

- `docs/PROJECT_MEMORY.md` 是唯一跨会话交接；不得创建 `SESSION_HANDOFF.md`、
  `NEXT_ACTIONS.md`、`DECISIONS.md` 或同类平行文件。
- 仅在用户明确恢复、请求交接或要求更新项目记忆时读写。
- 只保留当前目标、已验证检查点、验证边界、开放风险和精确下一步。架构与历史留在各自
  owner。
- Git、源码、原 TIFF、current report、Debug Analysis 和现场命令输出始终优先于记忆。
- 人工审阅重新开始时，先定义唯一 current schema；不恢复或迁移旧标签、candidate ID、
  决策或 runtime 白名单。
- 不得让模型查看完整长 TIFF 后代写 reference 边界。Baseline 只能来自绑定 source SHA
  的原图坐标，并由用户直接点击后明确确认，或来自独立校准的外部测量。OpenCV、SciPy、
  X5 Crop、模型视觉、生成 JPG 和算法一致只能产生非权威 proposal；reference 真值歧义
  保持 unresolved。该限制只约束 baseline 权限，不禁止 runtime 使用模型推断产生保守安全
  输出。

## 当前范围

- 当前源码检查点是 `X5_Crop.py` V4.9 template-first 架构实验，不再作为发布目标。
- 下一生产版本是 V5，以 current-only 方式替换 V4.9，不恢复旧兼容路径。
- 当前稳定 GitHub Release：`v4.2.8`。
- 开发源码位于 `x5crop/`；Release 可嵌入为单文件 `X5_Crop.py`。
- 除非用户明确恢复 app 或 native packaging，只处理 standalone X5 Crop workflow。
- V5 的目标输入是用户提供受支持 format、mode 与必要 count 的 Hasselblad / Imacon X5
  片夹扫描。每个 lane 是顺序明确的一条片条；支持水平、垂直、TIFF Orientation、相邻照片
  接触和局部重叠，不处理两段胶片物理压叠。当前真实验证域以单页 16-bit RGB contiguous
  TIFF 为主；其它 TIFF 结构只有建立明确 I/O 与复读合同后才能进入生产域，不能静默猜测。
- 当前任务和人工审阅状态只保存在 `docs/PROJECT_MEMORY.md`。

## 产品宗旨与批准语义

- X5 Crop 的目标是在用户已经提供 format 后，自动生成**足够安全且不切掉真实照片内容**
  的裁切；full count 固定，partial 同时支持 authoritative `explicit` count 与保守
  `auto`。项目不是唯一还原或测量真实物理边界，也不追求手术刀式精度。
- 用户提供的 format 始终是 runtime authority。显式 count 是 authority；partial `auto`
  不推断真实照片张数，而是在唯一匹配 scan-canvas 后使用该片夹对该 format 的有效最大
  容量作为 `output_slot_count`。不得自动猜 format、读取 filename count，或恢复旧版无界
  count heuristic。
- Separator、outer、expected position、格式尺寸与其它模型线索可以参与 proposal、
  assessment 和 canonical selection。必须在 report/debug 中区分 observed 与 inferred；
  score 无权删除会改变安全 union 或 physical legal-window intersection 的摆放。
- 产品人工成本顺序固定为：切掉真实内容最严重；非空照片输出过宽、需要逐张重新裁切
  次之；多输出一张可直接删除的 blank TIFF 成本最低。不得为了减少 blank，把每张真实
  照片变成需要人工二次裁切的半成品。
- `approved_auto` 同时表示最终保护后输出内容安全，且非空照片的外扩保持在已冻结的
  direct-use budget 内，用户无需再次裁切。它不表示每条照片边、separator 或 Grid phase 都被
  唯一证明，也不保证每张输出只含本 slot 的像素。固定 protection 与 bounded
  contact/overlap 可以带入少量邻片像素并让相邻输出重叠，但不得大到使非空输出失去
  直接使用价值。
- 自动批准的安全 authority 是所有仍符合正式像素 evidence、固定 format template、
  source-wide joint geometry、count/order、NominalPitch/local advance、共同 direction 与
  source/lane authority 的完整 retained placements。最终输出必须包含每个 retained full
  footprint，并位于每个 retained physical interpretation 的 MaximumLegalWindow 内。
  Canonical 只用于代表 geometry、deskew、minimum guard、排序与报告，不独占安全真相。
- Runtime 对 template-group pixel evidence 作经过黄金验证的检测假设，不声称覆盖完全漏检的
  纯物理位置。只有空间充分分离的独立 roles 或完整 opposite-edge pair 才能取得整组 phase
  authority；相邻 separator 两侧只能证明 local advance。
- `needs_review` 只用于具体且无法由 protection 吸收的输出风险，例如请求的显式 count
  无法成立、完整 placement 不足、direction 或 source geometry 不唯一、ordinal 无法成立、
  retained placement 越出 authority、安全包络无法 containment、任一边超过 direct-use
  budget，或 transform 无法建立。不得只因 separator 缺失、画面为空或多个摆放在采样上
  等价而送审。
- Partial `auto` 保留片夹全部有效 slots；前后及中间 blank 均可输出。当前没有 authoritative
  blank producer，因此所有 capacity slots 都按可能含照片处理并接受同一 5%/3% 检查。
  Contact/overlap 优先允许输出框重叠以保全内容。
- Decision 以整个 source 为原子：任一 slot 存在无法吸收的风险时，整张 source
  `needs_review` 且不写任何正式照片 TIFF。V5 不建立 partial output、slot salvage、混合状态或
  对应兼容路径。
- V5 只处理同一有序片条内相邻照片的接触或局部重叠。Ordinal 不变，start/end 继续是不同
  物理边界，local advance 可以缩短，相邻输出可以重复采样同一 source pixels；不建立二维
  layer、遮挡恢复或多胶片 ownership graph。
- 回归验收关注 format、count authority、slot count、顺序、retained placement survival、
  真实内容 containment、逐边 direct-use budget 与 TIFF 保真；不要求复刻历史 box，也不把
  canonical 贴近人工边界本身当作批准条件。
- Accuracy completion 只使用 source-SHA-bound、用户确认 geometry 的黄金样片。未确认
  样片、filename `pass/unknown`、auto-count 观察率与 calibration 结果不能冒充真实
  accuracy holdout；它们只用于 calibration、coverage、性能与非阻断诊断。
- Runtime 应继续识别真实照片边，因为它可以收窄 retained placement intervals、提高安全
  批准率、减少外扩并改善 deskew；但“真实边已被唯一识别”不是 Gate。黄金真实边只用于
  离线评价 observation、placement survival、containment、逐边预算与 deskew，不得反馈为
  样片规则、whitelist 或 runtime 边界。

## 长期实现规则

- 除非用户明确改变要求，保持 TIFF 位深、通道结构、ICC/色彩空间、resolution、
  metadata 与已知无损压缩行为。
- TIFF Orientation 是 decode boundary authority。V5 必须保存 raw raster 到 canonical visual
  coordinates 的可逆映射，在 canonical coordinates 中完成检测、ordinal 与输出，并把正式
  输出像素烘焙为正确视觉方向后写 `Orientation=1`；report 保留原 tag 与完整映射。
- V5 可使用 `NumPy`、OpenCV `cv2`、`SciPy`、`tifffile`、`imagecodecs` 与
  `Pillow`。`tifffile + imagecodecs` 独占原 TIFF I/O，OpenCV 只提供有界像素测量，SciPy
  只提供数值原语，Pillow 只服务 Debug Analysis；库不得取得物理解释、Gate 或输出政策权限。
- V5 安装器先检查所有受支持全局 Python 与实际可导入模块；满足冻结模块能力的现有依赖不论
  provider 都直接复用。缺失项才以最小 binary wheel 安装到所选 Python 的用户级 site；已有
  版本不符时，只能沿可确认的原 pip distribution 或 Homebrew formula 更新，未知 ownership
  必须在写入前停止，不得用第二份包遮盖。不创建私有 `.venv`，不得无约束升级；runtime report
  记录实际 provider、package、origin、版本与必要的数值 build/thread identity。
- V5 首版不引入通用视觉大模型、训练模型、ONNX Runtime 或 PyTorch runtime。未来 learned
  boundary evidence 只能作为像素 evidence，并继续经过同一物理求解器、安全 Gate 与黄金验证；
  它属于后续版本的独立决策。
- 结构清理不需要保持历史 PASS/REVIEW、geometry、confidence、reason、schema、debug
  或 cache parity；优先当前安全输出合同。
- V5 从首个可运行的端到端 vertical slice 起使用黄金样片检查 detection、边界、批准与 deskew；
  不得为单个文件放宽规则，且必须复查已知正常格式，尤其是 `135`。
- Named-TIFF 与端到端回归必须运行完整 detection flow，包括 scan-canvas matching、
  registered measurement、template grouping、safe containment 与 transform assessment。纯
  solver 单测可显式构造
  typed `DetectionWorkspace` fixture；production runtime 不得 bypass。
- Direct-use budget 必须在 source coordinates 中按输出 slot、按边计算，并使用物理单位或明确
  scale 映射。它必须由用户确认的可用性标准冻结，不得从 V4.2.8 历史 box、当前算法分布、
  总面积 clamp 或某个单独样片反推。只有未来存在 authoritative blank producer 时，blank
  才能获得豁免；当前 capacity slot 不因视觉空白绕过预算。
- 照片尺寸只属于 `FramePhysicalSpec`；片夹扫描画布只属于
  `ScanCanvasPhysicalSpec` catalog。片夹与 format 的适用关系及最大容纳张数也由该
  catalog 的 typed fit 拥有；count 只能排除装不下的 profile，不能缩短 validation
  domain。TIFF resolution 只作 I/O metadata，不得进入检测尺度、证据或决策。
- Deskew 只负责把照片的共同 top/bottom 长边校正为水平。每个 lane 使用一个共享方向并执行
  一次 inverse-affine sampling；不要求短边垂直，也不做 projective 或非线性矫正。S098 的
  非规则短边只进入 containment 压力验收，不得污染 normal deskew tolerance。
- V5 不实现 blank TIFF suppression，也不预建 blank producer、occupancy Gate、输出省略
  schema 或隐藏阈值。它是未来版本独立重新定义的优化方向。
- 方向性需求以水平片条措辞为基准，同时实现旋转等价的垂直行为。
- Runtime flow 或 source layering 变化更新 `docs/ARCHITECTURE.md`；版本行为、打包、
  验证或回滚变化更新 `docs/CHANGELOG.md`。

## 极致干净合同

- 每个 active concept 只有一个 canonical name、type、owner 和真相来源。
- 权限只沿 proposal、build、evidence、assessment、selection、decision、
  finalization、output、report、debug 单向流动。
- `CandidateGate` 和 `DecisionGate` 是仅有的两个 Gate；只有 `DecisionGate` 创建 final
  status 与 final reasons。
- Format spec、adaptive measurement、runtime configuration 和 report description
  保持分离。配置只在 runtime boundary 解析；lower layer 接收显式 typed input，不查询
  registry 或发明默认值。
- Foundation code 只知道 geometry、pixels、TIFF I/O、cache mechanics 与 units，不知道
  format identity、decision state 或 report schema。
- Runtime、tests、tools、report 与 debug 只消费 current schema。Report 是审计产物，
  不是 detection cache；只缓存精确且与 count/offset 无关的 measurement。
- 被替代的 API、字段、alias、import、reducer、shim、test 和兼容分支必须同批删除。
- 不保留 dead file、unreachable helper、pass-through wrapper、重复 model、隐藏 decision
  constant，或只搬运复杂度的 abstraction。
- 只有消除真实重复或职责歧义时才增加 abstraction；名称必须表达物理事实或生命周期职责。
- 代码、contract tests、`docs/ARCHITECTURE.md`、current reports 与 Debug Analysis
  必须描述同一系统。
- 每发现一类残留，先增加能失败的 contract，再删除整类残留并保留 contract。
- 架构清理只有在 full verifier 通过，且同一冻结 checklist 连续两次只读审计无已知问题后
  才闭合。只有明确 contract violation、无法表达的物理事实或真正不兼容能力才能重新打开。

## 检测与性能

- Search hint、blank appearance、重复宽度与 expected position 不是物理真值，但可以作为
  bounded query/canonical input。它们不能建立首个 placement anchor、source direction 或
  source geometry authority。
- Search corridor 始终只是 query proposal；不得把 query object、片夹边或胶片边提升为
  observed photo edge，也不为它们增加专门 fallback。
- Producer 必须 template-first：先由 format/count 和基础 profiles 形成完整 template groups，
  再让绑定像素证据确认或收紧。禁止恢复 local-line 排名、通用 DP、width×height 笛卡尔积、
  top-K、逐帧尺寸或 selected-placement 临时 query。
- 同一 source 的 width/height factor 与 axis scale必须作为联合状态传播。NominalPitch 与 budget
  直接消费联合状态；不得拆区间后自由组合。
- Early-stop 只来自 resolved output-safety assessment，而不是精确边界证明。预算耗尽表示
  safety assessment unavailable，不能成为 reliability evidence；candidate 与 final
  decision 权限分离。
- 优化前固定一个真实样片，记录 wall/detection time、profiles、template groups、geometry
  materialization、measurement reuse 与真实 call-stack hotspot。
- 只缓存带 typed key 的精确 count/offset-independent measurement；不缓存 candidate、
  Gate、decision、final reason 或近似 geometry。
- 多尺度像素证据只在预登记的 corridors、traces 或分块 ROI 中计算并复用缓冲区；禁止同时
  长期保存多份全分辨率梯度、方差、候选 evidence 或完整 float64 sampling coordinate fields。
- X5 Crop 是唯一并发 owner。默认由 `--jobs` 调度 source；OpenCV、BLAS、OpenMP 与 SciPy
  内部线程固定为 1，只有 macOS、Windows 各自的冻结基准证明更快且内存仍有界时才可改变。
- V5 性能 Gate 使用真实端到端路径：启动/import、一次 decode、检测、决策、全分辨率
  sampling、压缩、写出与复读；同时记录 detection-only、I/O、p50、p95、最慢样片和峰值临时
  内存。标准化小块 I/O 只作底层诊断，不能代表用户整体等待时间。
- 每轮优化后复测同一样片，再运行 contracts、代表性 format/mode、current-schema
  validation，并人工检查 Debug Analysis。输出差异是校准证据，不是历史 parity gate。

## 验证

`tools/verify` 是唯一可执行验证入口；Hook 与 CI 只能薄调用，不能复制命令。

- `.githooks/pre-commit` 通过 `tools/verify staged` 负责 staged hygiene。
- `.githooks/pre-push` 把实际 refs 交给 `tools/verify pre-push`：纯 Markdown push 只检查文档
  diff；其它非 runtime 变化运行 full contracts；`x5crop/`、`X5_Crop.py`、依赖或固定性能输入
  变化才增加 performance receipts 比较。
- 正常 commit-and-push 流程中，同一棵 tree、同一 scope 只验证一次。不要在 `git push` 前手工
  重复验证；成功的 pre-push Hook 是唯一最终验证。
- 只有不准备 push，或需要 full 输出排障时才手工运行：

  ```bash
  tools/verify full
  ```

- 验证后 tree 变化，旧结果立即失效。
- Detection 变化应比较 current-schema report：

  ```bash
  python3 -m tools.regression.compare <baseline> <candidate>
  ```

- 至少检查 transform outcome/source、lane divider mapping、status/reasons、joint source
  geometry、retained placements、canonical、crop envelopes、budget 与 final boxes。
- `Test/` fixture 未受跟踪，其目录布局不是源码合同。验证时动态发现 TIFF：

  ```bash
  find Test -type f \( -iname '*.tif' -o -iname '*.tiff' \) | sort
  ```

- 验证角色只有 `gold_accuracy_blocking` 与 `diagnostic_unreviewed`。V5 accuracy blocker 使用
  九张 source-SHA-bound、用户确认 geometry 的现有黄金起步；S055、S098 为 challenge，其余
  七张为 nominal。Nominal 必须安全自动批准；challenge 以安全批准为目标，但
  `needs_review` 可接受，任何不安全批准都失败。全部黄金都可用于开发和回归，不建立独立
  holdout role，也不得把结果表述为未知总体上的独立泛化率。S098 不参与 normal threshold
  或 aperture tolerance 校准；任一样片失败只能修通用算法并重跑全部黄金，不得增加样片规则。
- `diagnostic_unreviewed.jsonl` 的 111 条记录不产生 accuracy expectation 或 verdict。
  Filename `pass/unknown` 与 filename count 不得进入 detector、runtime whitelist、状态
  映射或 verifier expectation。111-source 只阻断 crash、hang、静默漏项、非法
  report/manifest/schema、消费未完成 query、无界 query/template/memory、正式 TIFF 损坏和
  source/lane authority 逃逸；单输入临时内存上界为
  `10 × source_pixels + 32 MiB`。识别 status、reason、geometry 与 count 只作诊断。
- 非黄金记录只有经过 source SHA 绑定的人工审核和用户明确确认，才能提升为
  `gold_accuracy_blocking`；不得根据当前算法输出自动晋升。
- 弱边、接触/重叠、空槽、Orientation 等困难样片可在 source SHA 绑定、人工确认后加入
  challenge；不得建立真实 `must_review` 样片类别。Runtime `needs_review` 是证据不足时的
  安全结果，不是任何目标图片的永久归类。
- 现有真实样片可以校准 search prior 与 measurement，但样片覆盖不完整。经验分布不得变成
  “未见过即失败”的硬边界；coverage gap 只限制验证或发布声明，不得单独制造
  `needs_review`。135-dual 不增加真实 fixture；XPan 与 120-645 样片以后按同一黄金流程加入。
  三者均不得成为 V5 实现 blocker，也不得建立格式级 denylist。
- 样片可用时覆盖代表性 `135/full`、`120-66/partial`、`half/full` 与 `120-67/full`。
  Unit tests 通过不证明 named-TIFF 安全裁切；完成声明前必须检查 current reports、Debug
  Analysis 与输出是否存在真实内容 inward loss，以及非空 approved 输出是否宽到需要人工
  二次裁切。

## 完成与同步

- 每个 clone 运行一次 `tools/git/install_hooks.sh`，不得使用 `--no-verify`。
- Codex 修改 tracked source、docs、configuration、launcher 或 release metadata 后，
  除非用户明确禁止，应提交并推送当前分支；依赖已启用 Hook，不重复手工验证。
- Commit 前确认 staged 与 unstaged 变化均为预期。失败时报告 blocker 并保留最安全状态。

## Git 与本地文件

- V5 直接在 `main` 开发；除非用户以后明确改变决定，不创建或切换到 V5 分支。
- 保留用户和其它 session 的修改；没有明确许可不得 reset 或 restore。
- `.gitignore`、`.github/`、`tools/` 与 `tools/install/` 必须可见。
- Sparse checkout 必须关闭；包括 `LICENSE` 在内的全部 tracked tree 都保存在本地。
  历史源码只保存在 Git history 与 tags，不维护 `archive/`。

- 用户明确要求干净交接时，在最终 Hook push 后再次删除 ignored cache、compiled bytecode、
  Finder metadata 与 generated output。
- 不提交 `.venv/`、`.venv-build/`、`build/`、`dist/`、`release/`、cache、`.DS_Store`、
  `downloaded_apps/`、`Test/`、生成的 `x5_crop_output/` 或大 TIFF；除非用户明确批准其
  作为 Git LFS fixture。

## 发布包

- `tools/release/manifest.py` 是 package content 的唯一 owner。
- 使用 `python3 -m tools.release.build --version <version>` 构建用户 ZIP。
- Builder 必须生成 standalone script，只打包 manifest entries，保持 launcher executable，
  并使用 Python `zipfile` 保存中文文件名的 UTF-8 metadata。
- 发布包分别提供中文与英文用户手册、快速启动，不使用逐段中英混排文档。
- 用户包不包含 modular source、tests、内部文档、本地样片或 generated output。
- macOS 与 Windows 都是正式平台。核心 Python、gold comparator 与代表性 TIFF I/O 在两个
  平台使用同一合同；Release Candidate 分别验证依赖安装、数值版本、启动器、中文路径、
  TIFF 复读与性能下限，不能以源码相同代替平台验证。
- 两个平台的安装器都优先复用已经满足模块能力合同的全局 Python；只有缺失项及明确属于 pip
  的版本更新进入该 Python 的用户级 site。启动器选择满足版本合同的同一全局 Python，使
  `X5_Crop.py` 可在任意文件夹独立运行；不得创建 Release-local `.venv`，也不得把 Homebrew
  或其它 package manager 设为运行前置条件。
- macOS 只准备当前 Release folder：标记主 launcher 与 installer executable，并在可用时
  移除 quarantine attribute；不得建立永久 system-wide trust。
