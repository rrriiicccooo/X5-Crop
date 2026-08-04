# 项目记忆

更新：2026-08-04

这是唯一跨会话检查点。这里只保存当前目标、现场验证、边界、风险与下一步。运行架构见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。源码、Git、
原 TIFF、current report、Debug Analysis 与现场命令输出始终优先。

## 当前目标

把 V4.9 原子切换为 template-first、current-only 架构：吸收 v4.2.8 的一维 profile、理论节距
附近 indexed search、basic 优先和 enhanced 按需，同时保留 V4.9 的物理尺寸、正交边界、
完整竞争、安全包络、逐边 5%/3%、两个 Gate、lane-safe TIFF 和严格性能合同。

本阶段不读取黄金 accuracy geometry，也不追求真实样片批准率。终点是普通源码 commit：
`V4.9 current-architecture baseline`，不是 release-ready，不创建 tag、GitHub Release 或公开
ZIP。下一阶段才在干净架构上重建黄金验证并改进真实识别。

## 工作树检查点

- 分支：`main`
- 当前 HEAD：`0fdb90dc40155cb5cfe2a97bee121453ef27f40a`
- HEAD 只是不改造前的性能基线，不是 checkout 或恢复目标。
- 工作树包含大范围未提交替换；禁止 reset、restore 或历史 checkout，必须保留用户和其它
  session 的修改。
- `tools/regression/cohorts/gold_accuracy.jsonl` 的现有修改必须保留；本阶段不读取它。

当前 producer 已不再是旧 local-line → rank/DP → placement。现有 current path 为 profiles →
完整 template groups → shared direction → joint source geometry/pitch/local delta → retained
placements → safe output。旧 `sequence.py`、`selection.py`、`geometry_build.py`、content subsystem、
active gold runner/comparator 已删除，不保留 compatibility。

## 已冻结事实

- Start/end 每边 direct-use limit 为设计宽度 5%；top/bottom 每边为设计高度 3%。Exact limit
  通过，任意正超量失败。
- Width separation tolerance 为 1.25%，height 为 0.40%；它们不是 padding。
- 同一 source 所有正常 frame 共享真实宽高和两个 axis scale。54/56 component保持独立物理
  interpretation。
- Start/end 无独立 slope，严格正交于唯一 `SharedStripDirection`。多个非等价 transform
  classes直接 typed review，不构建共同 envelope。
- `NominalPitch` 消费联合 width geometry；confirmed local delta只造成一次 phase step。
- 全局 phase support需要空间相距至少一个 frame width 的独立 roles，或通过尺寸合同的完整
  start/end pair。相邻 separator 两侧只能证明 local relation。
- Safety footprint 是 retained full union 与 canonical minimum guard 的 outermost，再加一次
  1 source-pixel visible guard；uncertainty 与 guard不相加。
- Sampling equivalence 不等于 physical-budget equivalence。Budget检查保留全部 retained
  interpretations。
- CandidateGate只记录 typed facts；DecisionGate独占 status/reasons。Review正式输出为零。
- 不允许 top-K、通用 DP、逐帧 scale、样片规则、新全图 field、row index、新依赖或为了通过
  而增加 review。

## 当前验证

最后一次非黄金 `tools/verify full` 在本 dirty implementation 上通过：

```text
81 current contracts
13 configuration format/mode pairs
168-task benchmark workload identity
compileall and X5_Crop.py --version
```

111-source engineering diagnostic 已完成 111/111 terminal records，runtime、authority、
query/template/memory 与 diagnostic official-TIFF failure 均为零；accuracy verdict 明确为
`not_assessed`。当前 111 个 scenario 均为 `needs_review`，不作为本阶段识别状态门槛。

S062 最近一次 dirty-tree diagnostic 形成完整三-slot geometry，并因逐边 budget 主动 review；
query、reuse、template work 与临时内存满足当前结构合同。它不是 accuracy 结论，也不是正式
性能 receipt。

代表性 horizontal/vertical Debug、中文 TIFF 路径、current report、standalone ZIP manifest、
UTF-8 文件名、CRC 复读与 standalone `--version` 已通过 dry-run。TIFF pixel/profile、lane-safe
sampling 与 diagnostics 零正式输出由 current contracts 验证。

冻结性能 authority：

```text
baseline paired SHA-256
097b6c46a12b7f5340a884b0389a2c2a053164b92051636f873eb392fc7e8026

baseline S062 SHA-256
c7779b754fc1189aec3100e94e11472fc420579f4dc52ee53ebdfec7304f0cd3
```

Formal candidate receipts 必须由最终 clean commit 生成；任何 tracked 修改都会使它们失效。

## 验证边界与风险

- 目前只证明 synthetic/current contracts 与非黄金工程行为；尚未完成两轮 cleanup、最终
  commit 后 paired/S062 comparator、pre-push 与 push 后 ZIP 复读。
- 尚未读取黄金 accuracy cohort，因此不能声明继承了 v4.2.8 的真实识别准确率，不能声明
  release-ready。
- `template_first.py` 仍是最大的 producer orchestration 文件。只在发现真实重复 owner 或死
  路径时继续拆分；禁止为了文件尺寸制造 pass-through abstraction。
- 若正确 phase 不在 basic profile 域，或修复需要样片阈值、额外全图扫描、候选 cap、逐帧
  尺寸、丢弃同强度完整 placement或性能放松，停止并请求用户决定。

## 精确下一步

1. 冻结当前 diff并重跑 final non-gold verifier与111-source engineering diagnostic。
2. 对同一冻结 diff连续执行两轮 correctness、性能结构、测试必要性、文档职责和
   `ponytail-review`，要求零 finding。
3. 创建普通源码 commit；在该 HEAD 生成固定路径 paired/S062 receipts并通过 comparator。
4. Tree 不再变化；pre-push通过后推送，从已推送 commit本地构建并复读 ZIP，不发布。
5. 下一阶段重建 current-only 黄金 comparator，验证真实 detection、containment、5%/3%、
   批准率与 deskew，再决定 release-ready 改进。
