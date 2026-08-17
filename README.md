# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

X5 Crop 用于裁切 Hasselblad / Imacon X5 片夹扫描 TIFF。用户提供胶片格式和照片格数；程序先按
已知格式放置固定模板，再从整条片带到局部边界逐步对准。只有照片内容、输出范围和 TIFF 写出都
安全时才输出整组照片，否则保留原扫描件供人工检查。本仓库中的 V5 尚未发布，当前公开稳定版
仍为 **v4.2.8**。

X5 Crop crops Hasselblad / Imacon X5 holder-scan TIFFs. You provide the film
format and exposure-slot count. The program aligns a fixed format template from
the whole strip down to local boundaries, then writes the complete photo set
only when content, output bounds, and TIFF fidelity are safe. Otherwise it
keeps the source scan for review. V5 in this repository is unreleased; the
latest public stable release remains **v4.2.8**.

发布包 / Release package: download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases), not the
generated Source code archive.

维护文档：[当前架构](docs/ARCHITECTURE.md) · [更新日志](docs/CHANGELOG.md)

License: MIT — [LICENSE](LICENSE)
