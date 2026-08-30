# 项目记忆

更新：2026-08-30。现场 `main`、tracked cohort、原 TIFF、source SHA、本地 source record 与最新命令
输出高于历史记录。长期合同见 [ARCHITECTURE.md](ARCHITECTURE.md)，标注规则见
[MANUAL_ANNOTATION.md](MANUAL_ANNOTATION.md)，协作与验证规则见 [AGENTS.md](../AGENTS.md)。

## 当前目标

按基础 nominal、较难 nominal、challenge 三阶段改进 V5 的通用检测。发布底线是 development nominal
与未来 sealed nominal 全部安全 `approved_auto`，全部角色 `unsafe_approved_auto = 0`；不得把失败
nominal 改成 challenge、隐藏竞争 placement、放宽黄金合同或牺牲正式 mean `<= 5s` 的性能来达标。
Challenge 的安全 auto 是能力发现，安全 review 仍合格。

当前优先补足直接 START/END、separator local advance、phase/cross observation 与 selected-only 安全
状态。Production 尚无 score；未来只允许在硬合法候选之后加入独立校准、带 OOD 与 abstention 的概率
选择，具体准入合同见架构第 9.2 节。

## 已验证检查点

- 黄金 reference 含 106 个唯一 source SHA、110 个显式 count task：96 个 nominal、14 个 challenge，
  优化分层为 66 / 30 / 14。全部 task 已人工确认；同源 count 变体共享物理边界但独立验证。
- 当前 detector source manifest `499db30bea59e746` 的完整黄金结果为 110/110 完成、分析错误 0、
  危险自动批准 0；11 个安全
  `approved_auto`、99 个 `needs_review`。基础 nominal 为 10/66，较难 nominal 为 1/30，challenge
  14 个均 review。Candidate 为 65 个不可用、25 个安全、20 个不安全；Review candidate 偏差只作机制
  诊断，不是正式危险输出。
- 直接绑定的 start/end 已保留 native coordinate；Grid 只补未观察角色。Phase anchor 与 post-phase local
  refinement 已分离，后者不能反向取得 phase/pitch 权限。每个唯一 separator 可约束自己的 local
  advance，关系总数不超过 `count - 1`，只作一次 O(count) 传播。Cross 的 fit direction 负责物理成员
  资格，完整方向区间只进入 selected frame span 的输出保护。
- 对 96 个 nominal 的 v4.2.8 同源机制对照中，旧版 80 个自动批准只有 10 个安全、70 个危险；旧候选
  总计只有 11 个安全。V5 同批有 25 个安全 candidate，11 个安全自动批准且无危险批准。旧版更高的
  表面通过率主要来自未经校准的 confidence/best-score 与 fallback，不能作为迁移目标。
- v4.2.8 有安全候选而 V5 尚未形成安全自动结果的 9 个任务为 S007、S010、S011、S022、S025、S026、
  S032、S033、S038；它们只提供机制调查入口，不证明旧 geometry owner 或 decision rule 正确。
- 按 SHA 去重的物理先验诊断覆盖 106 个 source：scan-canvas/profile 全部匹配；395 个直接可见 pitch
  中 391 个落在 runtime interval。`135`/`half` 的 347 个直接可见 separator gap 只有 20 个落入窄
  gap 先验，说明稳定量是 pitch，separator 宽度只应拥有局部权限。黄金 Frame 的较小 W/H 不能反向
  校准 catalog，因为人工线是最内侧可接受裁切，不是片门真值。
- 格式覆盖仍只有 `135` 57、`120-66` 32、`120-67` 3、`half` 14 个 unique source；尚无 `xpan`、
  `120-645`、`135-dual`。当前全部为可查看的 development gold，没有 calibration pool 或 sealed
  acceptance，不能宣称未见 X5 扫描泛化、概率校准或 release readiness。

## 验证边界与开放风险

- 0 危险自动批准只是首要安全底线，不等于 nominal 能力完成。当前仍有 56 个基础 nominal review；
  phase ambiguity/discontinuity、cross authority、candidate 几何、direct-use budget 与 source authority
  必须分开处理。
- `+ / -` 的 source-wide 亮带不能仅凭极性和跨度取得 separator material 权限；照片内部能形成相同
  结构，S034 是危险反例。Polarity-complete outer/cross observation 继续成立，亮 separator 必须等待
  新的独立物理区分事实，不能按宽度分数或样片规则补丁放行。
- 当前 106 source 只能用于 feature/model development、训练与反例发现，不能事后充当独立概率校准。未来 scorer 需要新增、预先
  冻结的 calibration source 和完全未参与拟合的 sealed source；任一 feature/model/threshold/候选生成
  改动都会使旧 receipt 失效。
- 黄金 diagnostic 时间不是正式性能证据。性能只接受 clean committed tree 上的 24-source 完整用户路径
  receipt；5 秒均值阻断，3 秒均值为持续优化目标。

## 精确下一步

1. 按 typed root failure 拆解 56 个基础 nominal review；一次只修改一个通用机制，并对完整黄金保持
   `unsafe_approved_auto = 0`。
2. 先调查上述 9 个 v4.2.8 安全候选，区分可吸收的局部 START/END、separator pair、cross observation
   与必须拒绝的 Grid/fallback/旧 score；任何迁移都重新检查全部黄金，而非只看目标样片。
3. 基础 nominal 全部稳定安全自动通过后，再处理弱边缘、片距变化和 width estimate，最后处理
   contact/overlap 等 challenge；缺失 format 只由新真实来源补齐。
4. 概率选择层保持设计状态，直到 observation 与安全状态成熟、calibration/sealed 数据到位并冻结
   schema、风险阈值、OOD、typed failures 和 `O(K × F)` 性能上界；当前不创建 scorer 占位代码。
