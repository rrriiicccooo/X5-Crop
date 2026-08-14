# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户提供胶片格式、片条模式和
partial 曝光格数；程序只在照片内容、裁切范围和 TIFF 写出都安全时输出照片，否则保留原扫描件
供人工检查。仓库中的 V5 尚未发布，当前公开稳定版本仍为 **v4.2.8**。

X5 Crop conservatively crops Hasselblad / Imacon X5 holder-scan TIFFs. You
provide the film format, strip mode, and partial-strip exposure count. Photos
are written only when content, crop bounds, and TIFF output are safe; otherwise
the source scan is retained for review. V5 in this repository is unreleased;
the latest public stable version remains **v4.2.8**.

发布包：[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 中的
`X5-Crop-vX.X.zip`，不要使用自动生成的 Source code 压缩包。

Release package: download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases), not the
generated Source code archive.

维护文档：[当前架构](docs/ARCHITECTURE.md) · [更新日志](docs/CHANGELOG.md)

License: MIT — [LICENSE](LICENSE)
