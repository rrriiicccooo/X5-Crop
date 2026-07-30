# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

维护文档：[当前架构](docs/ARCHITECTURE.md) ·
[更新日志](docs/CHANGELOG.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF：在用户提供 format 后，
full 使用固定张数，partial 同时支持显式与 bounded auto count。V4.9 当前开发版通过
有界 Grid、向外安全包络和固定毫米 protection 自动导出通过安全合同的 frame TIFF；
只有具体且无法吸收的 count、ordinal、ownership、containment 或 authority 风险才进入
`needs_review`。系统优先不切掉真实照片内容，允许相邻输出重叠和适量向外多保留，
不要求唯一还原真实边界。当前稳定发布仍为 **v4.2.8**。

X5 Crop conservatively crops TIFF scans from Hasselblad / Imacon X5 holders.
Given a user-supplied format, full mode uses its fixed count while partial mode
supports either an explicit count or bounded automatic count. The current V4.9
development build uses a bounded Grid, outward safe envelopes, and fixed
millimetre protection to export frame TIFFs that satisfy the safety contract.
Only a concrete, unabsorbed count, ordinal, ownership, containment, or authority
risk becomes `needs_review`. Adjacent outputs may overlap and retain extra
pixels; unique physical-boundary reconstruction is not required. The stable
release remains **v4.2.8**.

请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

License: MIT — [LICENSE](LICENSE)
