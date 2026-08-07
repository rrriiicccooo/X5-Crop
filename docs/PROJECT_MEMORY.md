# 项目记忆

更新：2026-08-07

这是唯一跨会话检查点，只保存当前目标、已验证检查点、开放风险与精确下一步。长期产品与
实现政策见 [AGENTS.md](../AGENTS.md)，当前运行架构见 [ARCHITECTURE.md](ARCHITECTURE.md)，
版本变化见 [CHANGELOG.md](CHANGELOG.md)。源码、Git、原 TIFF、current report、Debug Analysis
与现场命令输出始终优先。

## 当前目标

V4.9 已完成 template-first 架构实验使命，不再作为发布目标。下一生产版本是 V5，直接在
`main` 上 current-only 实现，不创建 V5 分支，也不先把 V4.9 修到黄金样片全部通过。

产品优先级依次是：不切掉真实内容；提高识别覆盖与边界准确率；提高安全自动批准率；保持
整体速度；改善 deskew；最后才是减少 blank TIFF。V5 不实现 blank TIFF suppression。

## 已验证检查点

- `8c8040b0` 是 V5 开工前的 V4.9 实验架构 checkpoint；旧 producer 与兼容路径已删除。
- `192a8318` 已建立六项固定生产依赖、Python 3.12-3.14 用户级安装器、依赖收据、保守卸载器、
  macOS/Windows 启动器接线和 Release manifest。`561a9af5` 修复 CI workflow 解析，GitHub
  Verify 已通过。
- 安装器不会静默改变已有 Python 环境：其它 OpenCV distribution 或任一冻结依赖的不同版本
  都会在 package 变更前安全停止。
- 当前非黄金验证为 94 个 tests、13 个配置 format/mode pairs、168-task 固定 workload、
  compileall 与 standalone version；固定依赖下的 V4.9 性能 receipts 已重建。
- 111-source 工程诊断已有 111/111 terminal records，runtime、authority、query/template、内存
  与正式 TIFF failure 均为零；accuracy 明确为 `not_assessed`。
- 九张 source-SHA-bound 黄金展开为 14 个场景；原 TIFF 与人工确认资产已有 Git 外备份。

## 验证边界与开放风险

- 当前源码和 [ARCHITECTURE.md](ARCHITECTURE.md) 仍是 V4.9 实验实现。V5 runtime、唯一 schema、
  黄金 comparator、完整用户路径性能 receipt、accuracy 与发布验证都尚未建立。
- 当前 `gold_accuracy.jsonl` 仍使用 V4.9 角色字段：S055 为 `nominal`，S098 为
  `stress_excluded`。V5 已冻结二者均为 challenge，其余七张为 nominal；必须随 V5 schema 与
  comparator 原子迁移，不能让旧字段成为 V5 truth。
- V5 首版只使用已冻结的六项生产依赖，不引入通用视觉大模型、训练模型、ONNX Runtime 或
  PyTorch runtime。
- 5%/3% 是逐边 direct-use 硬上限，不是理想边界准确率。第一条端到端 slice 后，需要用黄金
  结果冻结边界质量、完整用户路径速度/内存与 deskew 最大垂直漂移门槛。
- 弱边、接触/重叠、空槽与 Orientation challenge 样片以后按 source-SHA-bound 人工确认流程
  增加，不阻断当前实现。XPan 与 120-645 样片以后加入；135-dual 不增加真实样片。
- macOS Apple Silicon、Intel Mac 与 64 位 Windows 都是正式平台，但仍需分别完成 Release
  Candidate 安装、启动、依赖版本、代表性黄金、TIFF I/O 与性能验证。

## 精确下一步

1. 在新任务中制定 V5 vertical-slice 实现计划；固定依赖与安装体系视为已完成前置条件。
2. 第一批 runtime 同时建立 V5 唯一 schema、黄金 comparator、cohort 角色迁移和完整用户路径
   performance receipt，并删除同批被替代的 V4.9 路径。
3. 完成 TIFF decode/Orientation → registered bounded measurement → template placement → source-
   atomic safe output → TIFF readback 的端到端 slice。
4. 从第一条 slice 起运行全部黄金，检查 observation、placement survival、真实内容
   containment、逐边 5%/3%、批准与 deskew；只修通用算法，不增加样片规则。
5. 输出边界误差、完整用户路径性能/内存、deskew 最大垂直漂移与视觉对比，由用户一次冻结门槛；
   随后扩展 format/mode、困难 challenge 和双平台 Release Candidate 验证。
