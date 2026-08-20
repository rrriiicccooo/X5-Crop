# 项目记忆

更新：2026-08-20

这是唯一跨会话检查点。长期政策见 [AGENTS.md](../AGENTS.md)，运行合同见
[ARCHITECTURE.md](ARCHITECTURE.md)，版本变化见 [CHANGELOG.md](CHANGELOG.md)。现场 Git、源码、
原 TIFF、current report、Debug Analysis 和最新命令输出优先。

## 当前目标

V5 保持一条 current-only fixed-template-first production path，尚未发布。本轮已把性能、RSS、核心
helper owner、测试工具、平台 receipt 与全部文档做有限收束：不改变几何、Gate 或黄金真值合同，
5 秒 mean 继续作为正式性能 Gate，3 秒 mean 只作为 non-blocking challenge。后续能力改进只按
真实未闭物理事实推进，不从 111 张无真值样片反向调特殊规则。

## 当前证据

- Fresh `tools/verify full`：386 tests 通过、skip 2；compile、configuration、cohort、shell、release
  standalone smoke 与 version contract 全部通过。
- Fresh `tools/verify accuracy`：九张 user-confirmed gold 全部为 nominal，9/9 `approved_auto`；S055、
  S098 已纳入正常能力，不再属于 challenge。
- Fresh `tools/verify diagnostic`：111/111 terminal、工程合同失败 0，49 张 `approved_auto`、62 张
  `needs_review`，recognition accuracy 为 `not_assessed`。Review 根因是 placement unresolved 22、
  transform sampling 11、content veto 9、direct-use budget 8、no legal placement 7、local advance 5。
  Phase 为 resolved 99、ambiguous 5、unresolved 7；cross 为 resolved 94、unresolved 17；
  `phase_template_mismatch` 仍只有 S053、S107。
- 改动前 clean commit `90192291` 的 24-source baseline mean 为 4.071 秒/张。首个代码提交
  `286cf91c` 的 v5_4 clean-path measurement 为 3.688 秒/张，5 秒 Gate 通过，3 秒 challenge 未达到；
  这次首次把未插桩 production peak RSS 与 cProfile 分开，production RSS mean 约 879 MB、max 约
  1.269 GB，cProfile RSS mean 约 887 MB、max 约 1.276 GB，detector 临时缓冲 mean 约 0.92 MB、
  max 约 1.49 MB。后续 receipt 必须重新绑定实际 release commit；不同测量方式之间不作虚假趋势
  对照。
- Affine sampling 已用跨 256 行 chunk 的随机 uint16 fixture 逐像素对照旧实现；合成基准约减少
  5.7% sampling 时间。坐标/值缓冲只分配一次，不预清零必定覆盖的输出，不创建额外 uint16 chunk。
- `interval_math.py` 是 template interval 算术 owner；direct cross direction closure 属于
  `template_cross_geometry.py`。模板测试 fixture 已迁到独立 support owner，测试不再互相导入私有
  helper。v4/V5 对照只接受正式九张黄金；release test 会真实构建 ZIP 并启动 standalone。

## 开放风险与下一步

1. 3 秒 challenge 仍未达到，但不阻断。每个候选 release commit 都须重建 24-source performance
   receipt；只有 5 秒 mean 是阻断条件。若没有明确且可复现的高收益，不再为追 3 秒扩大内存、
   改变像素值、放宽几何或引入持久 runtime。
2. 62 张 review 不是准确率失败。S053 缺 phase/pitch closure，S107 缺 cross authority，其它样片也
   必须先区分真实多解与错误候选；保持 review，不能用 coarse 距离、强度分数或 holder 长轴中心
   替 placement 选答案。
3. Release 前须在同一最终 commit 上取得 Apple Silicon macOS、Intel macOS 与 Windows x64 三份
   实机 receipt。APFS/HFS+、NTFS 分别验证；没有独立卷时 exFAT 保持
   `best_effort_unverified`，不得伪装成实机已验证。在此以前不创建 RC、tag、Release 或公开 ZIP。
