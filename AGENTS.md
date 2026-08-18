# Codex 协作规则

本文件只保存长期协作政策。当前架构见
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)，版本变化见
[docs/CHANGELOG.md](docs/CHANGELOG.md)，当前任务见按需读取的
[docs/PROJECT_MEMORY.md](docs/PROJECT_MEMORY.md)。

## 开始工作

1. 编辑前阅读 `README.md`。只有用户明确要求恢复、更新或交接时才读取
   `docs/PROJECT_MEMORY.md`。
2. 检查当前分支和工作树：

   ```bash
   git branch --show-current
   git status --short
   ```

3. 以现场 Git、源码、原 TIFF、current report、Debug Analysis 和最新命令输出为准；历史计划、
   记忆与旧 receipt 只作线索。

GitHub 是 tracked 源码与文档的权威来源。NAS 和复制目录只用于传输或测试。
首次 clone 运行 `tools/git/install_hooks.sh`，启用仓库中的 `.githooks`。

## 子代理调度

以下原则适用于 `luna_worker` 及其他自定义 subagent；主 Agent 负责拆解任务、保持主任务目标
不变，并验收 worker 的结果：

- 体量较大且相互独立的子任务，优先派发给多个 `luna_worker` 并行处理；几分钟内能够完成的
  轻量任务直接留在主线程。
- 每个 worker 的任务描述必须上下文完整，明确文件范围、任务边界、预期输出和可核验的验收
  标准；worker 不得修改主任务目标或自行扩大范围。
- 只读任务可以并行。涉及文件写入的 worker 必须使用独立 worktree；无法隔离时改为串行，
  避免多个任务同时修改同一工作树。
- worker 完成后，主线程必须按预先给出的验收标准检查结果；未达标时，补全上下文和失败证据后
  重新派发，不直接把未验收结果视为完成。
- 如果多个 worker 无法并行，检查 `~/.codex/config.toml` 中的
  `agents.max_concurrent_threads_per_session` 是否被设置为 `1`。

## 长时间异步工作

- 对长时间运行的异步任务，使用空输入轮询 `write_stdin` 时，`yield_time_ms` 必须至少为
  `180000`；不需要中间输出时优先使用 `300000`。
- 调用 `functions.wait` 时，`yield_time_ms` 必须至少为 `180000`。
- 调用 `functions.exec` 包裹含等待操作的工具时，外层 `@exec yield_time_ms` 必须比内部最长的
  工具等待时间至少多 `30000` 毫秒，避免外层代码单元先行 yield。
- 通过非空 `write_stdin` 发送交互式输入时，不应用上述长等待要求。
- 这些工具会在进程或代码单元完成时提前返回；不要仅为报告任务仍在运行而唤醒主模型。

## 文档职责

| 文件 | 唯一职责 | 语言 |
|---|---|---|
| `README.md` | GitHub 简短入口与语言选择 | 精简中英双语 |
| `docs/user-guide.zh-CN.md` | V5 中文完整手册（发布前为开发预览） | 中文 |
| `docs/user-guide.en.md` | V5 English user guide (development preview before release) | English |
| `docs/quick-start.zh-CN.md` | V5 中文快速启动（发布前为开发预览） | 中文 |
| `docs/quick-start.en.md` | V5 English quick start (development preview before release) | English |
| `docs/ARCHITECTURE.md` | 已确认的 V5 合同、运行流、数值合同与源码 owner | 中文 |
| `docs/CHANGELOG.md` | 版本级行为与验证边界 | 中文 |
| `docs/PROJECT_MEMORY.md` | 当前目标、证据边界、风险与下一步 | 中文 |
| `AGENTS.md` | 长期协作政策 | 中文 |

- 内部文档只写中文正文，保留必要的英文标识、命令和 schema 名。
- 用户可见行为变化必须同步更新中英文公共文档。
- 不复制架构、版本历史或当前任务状态；链接到唯一 owner。
- 除 `README.md`、`AGENTS.md` 与 `LICENSE` 外，实质性文档只放在 `docs/`。
- 文档保持当前、简洁、专业；不写执行流水账、聊天记录或过期计划。

## 项目记忆与 reference 权限

- `docs/PROJECT_MEMORY.md` 是唯一跨会话检查点；不建立 `SESSION_HANDOFF.md`、
  `NEXT_ACTIONS.md`、`DECISIONS.md` 或同类文件。
- 只在用户明确要求时读写，并只保留当前目标、已验证事实、开放风险和精确下一步。
- Baseline 必须绑定 source SHA，并由用户在原图坐标中直接确认，或来自独立校准的外部测量。
  OpenCV、SciPy、X5 Crop、模型视觉、生成 JPG 和算法一致只能产生非权威 proposal。
- 不让模型查看完整长 TIFF 后代写 reference 边界；真值歧义保持 unresolved。

## 当前产品边界

- 仓库只有一条 V5 current-only production path；公开稳定版仍是 `v4.2.8`，V5 尚未发布。
- V5 直接在 `main` 开发，不创建 V5 分支。历史实现只保存在 Git history 与 tags。
- 只处理 standalone X5 Crop workflow；除非用户明确恢复，不开发旧 app 或 native packaging。
- 输入是用户已提供 format 和可选 count 的 Hasselblad / Imacon X5 片夹扫描。正式 TIFF
  域、物理模型、Gate、输出事务和源码 owner 以 `docs/ARCHITECTURE.md` 为唯一说明。

以下产品语义不可被便利性优化绕过：

- 用户 format 始终是 authority。省略 count 表示用户确认匹配片夹的默认完整格数；明确 count 表示
  用户确认实际 slot 数，并包含中间空白曝光格。片夹容量不得猜 format、真实照片数或 filename
  count。Runtime 不保留 full/partial mode，也不使用长轴居中；是否铺满只在 selection 后按 outer
  外侧能否再容纳一个 W 判断。`135-dual` 只有 12=6+6 可自动处理，其它 count 直接 review。
- Detector 先从整条片带建立 coarse support 和共同方向，再把 format、count 与片夹 authority 编译成
  有界固定模板，只在理论 outer、separator 和 top/bottom 附近精修。独立像素观察负责对准、解释
  最多一次直接 local advance 并否决非法 placement；不得用模板投影创造自己的 phase authority。
- 安全层只处理唯一胜出 placement 的联合可行状态，不合并落选位置、不分别相加不能同时发生的
  最大误差、不静默裁掉越界 footprint。具体 bleed 和预算只由 `docs/ARCHITECTURE.md` 定义。
- Contact 与 overlap 在获得用户确认黄金以前一律 review，不建立第二套 detector 或特殊自动 bleed。
- `CandidateGate` 只记录 typed assessment；只有 `DecisionGate` 创建 final status 与 reasons。
- 任一 slot 不安全时，整个 source `needs_review` 且不写正式照片；不做 slot salvage。
- 不为减少 blank TIFF 牺牲内容保护或 direct-use 质量。V5 不实现 blank suppression。
- TIFF 位深、通道、ICC、resolution、支持的 metadata、无损压缩和 Orientation 必须按当前
  I/O 合同保真；正式输出写 `Orientation=1`。

## 实现边界

- 每个概念只有一个 canonical name、type、owner 和真相来源。权限只沿 input、evidence、
  assessment、selection、decision、finalization、output、report、debug 单向流动。
- 被替代的 API、schema、flag、alias、wrapper、test 和 import 同批删除；不保留 fallback、shim、
  feature flag、dead code 或平行 runtime。
- Producer 必须 fixed-template-first 且工作量有界；不恢复完整链 materialization/cache、通用 DP、
  top-K、候选笛卡尔积、逐帧尺寸、selected-placement 临时 query 或无界全图 evidence。
- 新增自由度必须说明它减少的物理未知量、唯一 owner、启用与禁止条件、工作上界、反例、Debug、
  Gate 失败表达，并证明普通黄金不变；不能完成这些合同的能力不进入 production。
- 连续几何保留到最终 sampling；不得逐格取整并累计坐标误差。不同 placement 保持竞争，同一
  placement 的连续误差才进入联合安全范围。
- 性能优化只能复用 candidate-independent 计算或完全相同的状态。除非用户明确批准行为变化，优化
  前后 registered observations、合法 placements、winner/runner 与 provenance 必须相同。
- Measurement replay 仅是绑定 source SHA、configuration、measurement revision 和 plan identity 的
  开发工具；不得携带真值、进入 production、充当 fallback 或提供更容易通过的 detector path。
- `tifffile + imagecodecs` 独占正式 TIFF I/O；OpenCV 只作有界像素测量；SciPy 只作数值与
  sampling；Pillow 只在显式 Debug Analysis 时延迟导入。
- V5 首版不加入视觉大模型、训练模型、ONNX Runtime 或 PyTorch runtime。未来 learned evidence
  仍须经过同一物理求解、安全 Gate 与黄金验证。
- X5 Crop 是唯一并发 owner。生产默认 `--jobs 1`、上限 3；OpenCV、BLAS、OpenMP 与 SciPy
  内部线程固定为 1，除非双平台冻结基准证明改变更快且内存有界。
- 安装器按模块能力复用现有全局 Python 环境。缺失项才最小安装；版本不符只沿已确认的原
  pip distribution 或 Homebrew formula 更新；未知 ownership 在写入前停止。不创建 `.venv`，
  不叠加第二个 provider，不把 Homebrew 设为前置条件。

## 验证

`tools/verify` 是唯一验证入口：

```text
staged | full | accuracy | diagnostic | performance |
platform | platform-check | platform-package | pre-push
```

- Hook、CI、Windows `.bat` 与 Intel `.command` 只能薄调用该入口，不复制验证逻辑。
- `.githooks/pre-commit` 运行 staged hygiene；`.githooks/pre-push` 根据实际 commit range 选择
  documentation 或 full。纯 Markdown 使用 documentation；其余改动和无法识别的范围使用 full。
  不得使用 `--no-verify`。
- Performance 不属于日常 commit 或 push Gate。只在准备发布时运行，并绑定最终 release commit；
  tree 变化后旧 receipt 立即失效。
- `Test/` 不受 Git 跟踪，目录布局不是源码合同；工具以 cohort 中的相对路径和 source SHA 绑定
  样片。不得把 TIFF、生成输出或 receipt 提交到 Git。
- Accuracy 只有 `gold_accuracy_blocking` 与 `diagnostic_unreviewed` 两种角色。九张黄金各运行一项，
  共九项，并逐项携带用户确认 count；不保留 auto 重复任务。
  Nominal 必须安全自动批准，challenge 允许安全 `needs_review`。不得新增样片规则、whitelist、
  格式 denylist 或根据当前输出自动晋升黄金。
- Accuracy、diagnostic、performance 与 platform cohort 的每条记录都必须携带明确 count；工具不得
  从片夹容量、文件名、目录中的历史 full/partial 标签或像素推导。
- 111-source diagnostic 只判断 crash、hang、terminal/schema 完整性、authority、query/template、
  内存和 TIFF 工程合同，不产生 accuracy verdict。
- 性能 Gate 使用 24-source 完整用户路径，正式 mean 上限为 5 秒；SHA、profiling 和 Debug
  Analysis 在计时外。Receipt 只证明其中记录的 commit、依赖、工作量和命名机器。
- Named-TIFF 与端到端验证必须调用正式 CLI 和完整 detection flow；测试工具不得提供更容易
  通过的 detector path。

## Git、完成与发布

- 保留用户和其它任务的修改；没有明确许可不得 reset、restore 或删除未知文件。
- 使用 `rg` 搜索；不可用时再用下一种工具。文件编辑使用 `apply_patch`。
- Commit 前核对 staged 与 unstaged diff。除非用户明确禁止，tracked 变更应提交并由正常 Hook
  推送当前 `main`。
- 不提交 `.venv/`、`build/`、`dist/`、`release/`、cache、`.DS_Store`、`Test/`、
  `x5_crop_output/` 或大 TIFF；除非用户明确批准 Git LFS fixture。
- `tools/release/manifest.py` 是发布内容唯一 owner。用户包不包含 modular source、tests、tools、
  fixtures、内部文档、开发依赖或生成输出。
- 构建命令为 `python3 -m tools.release.build --version <version>`。只有 accuracy、性能、依赖、
  TIFF、中文路径、文件系统恢复和目标平台实机 receipt 全部绑定同一 release commit 后，才可
  创建 RC、tag、GitHub Release 或公开 ZIP。
