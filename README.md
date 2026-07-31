# X5 Crop

[中文用户手册](docs/user-guide.zh-CN.md) ·
[English User Guide](docs/user-guide.en.md) ·
[中文快速启动](docs/quick-start.zh-CN.md) ·
[English Quick Start](docs/quick-start.en.md)

维护文档：[当前架构](docs/ARCHITECTURE.md) ·
[更新日志](docs/CHANGELOG.md)

X5 Crop 用于保守裁切 Hasselblad / Imacon X5 片夹扫描 TIFF：在用户提供 format 后，
full 使用格式默认 slots，partial explicit 严格服从用户 count，partial auto 则输出唯一
匹配片夹对该 format 的全部有效 slots。V4.9 当前开发版直接在原图坐标测量照片四边，
用 format/count 物理约束重建有序照片 polygon，从 observed top/bottom 产生 deskew，再从
原 TIFF 一次 inverse-affine sampling。测量或推断不确定度、1 px 插值 allowance 与固定
毫米 protection 共同形成可重算的安全包络。只有具体且无法吸收的 ordinal、ownership、
containment、geometry 或 transform 风险才进入 `needs_review`。Blank slot 与相邻输出
重叠均可接受；系统不猜真实照片张数。V4.9 发布合同还要求非空照片的保护后输出
足够紧凑、无需人工二次裁切；多余 blank 可直接删除，但过宽照片不得冒充自动完成。
该 direct-use budget 已由用户冻结为片条轴每边 5%、横片条轴每边 3%，各 format 按自身
aperture 换算；独立硬门槛与正交 start/end 模型尚未实现，因此 V4.9 仍是开发版。当前
稳定发布仍为 **v4.2.8**。

X5 Crop conservatively crops TIFF scans from Hasselblad / Imacon X5 holders.
Given a user-supplied format, full mode uses its default slots, partial explicit
obeys the user count, and partial auto writes every valid slot in the uniquely
matched holder. The current V4.9 development build uses a single-capacity
Grid only for slot order and capacity, measures the four photo edges in source
coordinates, reconstructs ordered photo polygons under format/count physical
constraints, derives deskew from observed top/bottom lines, and samples each ROI
once from the original TIFF. Measurement or inference uncertainty, a one-pixel
interpolation allowance, and fixed millimetre protection form a recalculable
safe envelope. Only a concrete, unabsorbed ordinal, ownership, containment,
geometry, or transform risk becomes `needs_review`. Blank slots and overlapping
outputs are allowed; runtime does not infer the true photo count. The V4.9
release contract also requires every nonblank protected crop to be tight enough
for direct use without manual recropping. Extra blank files are cheap to delete;
an oversized photo crop must not be presented as completed automation. That
direct-use budget is now user-frozen at 5% per sequence-axis edge and 3% per
cross-axis edge, converted through each format's own aperture. Its independent
hard gate and the orthogonal start/end model are not yet implemented, so V4.9
remains a development build. The stable release remains **v4.2.8**.

请从 [GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases) 下载
`X5-Crop-vX.X.zip`，不要下载 GitHub 自动生成的 Source code。

Download `X5-Crop-vX.X.zip` from
[GitHub Releases](https://github.com/rrriiicccooo/X5-Crop/releases). Do not use
GitHub's generated Source code archive.

License: MIT — [LICENSE](LICENSE)
