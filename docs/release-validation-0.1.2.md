# v0.1.2 正式版验证记录

验收日期：2026-10-22。本文件记录 v0.1.2 发布前的本机验证。版本号采用 `0.1.2`，发布标签为 `v0.1.2`，不带 rc、alpha 或 beta 后缀；线上发布状态以 [Release 页面](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases/tag/v0.1.2) 为准。

## 改动范围

Python 包版本、`pyproject.toml` 与网页显示统一为 `0.1.2`，页脚改为“本机核对”。增加发布说明、变更记录和发布流程，源码分发清单包含这些材料。核对算法、报告结构、服务接口和原生选择模块没有修改。

候选版证据保留原版本，不将历史结果改写为正式版实测。

## 验收

| 验证项 | 结果和范围 |
| --- | --- |
| 单元测试 | Pillow 环境 48 项通过；基本环境 46 项通过、2 项可选解码测试跳过；Ruff 通过 |
| 构建与安装 | 离线构建 sdist，再由 sdist 构建 wheel；Python 3.12.14、3.14.8 各使用新虚拟环境安装，确认从隔离环境实际导入 |
| 网页与报告 | 已安装 wheel 的桌面及窄屏操作、版本显示与 API 一致、分类及 137 条分页、刷新恢复、报告下载和退出检查通过 |
| 源码 ZIP | 解压后执行权限保留；从源码目录外启动 `.command`，本机服务与报告下载通过 |
| 真实 Takeout | 正式版 wheel 在两个隔离环境各通过 8 个独立预期场景；4 份实际媒体原件未改写 |
| 原生选择窗口 | 沿用候选版真实操作记录；正式版的 `picker.py` 字节指纹与当时验证对象一致。本次没有另开系统弹窗重复操作 |
| 分发文件 | 包元数据、稳定版本号、wheel 内部 RECORD 和包哈希验证；源码及分发包排除本机日志、图库和凭证 |

“两个环境”均在同一台 Mac。真实样本为第三方在社区公开提供的实际 Takeout 复现小样本，含 2 张 JPEG、2 段 MP4；我们没有自行从 Google 账号导出或确认其完整图库。构造的两分卷场景不能证明 Google 原生分卷已经验证。

## 本机证据目录

`artifacts/stable-0.1.2/`：

- `build-final/installation-result.json`：最终正式版构建、隔离安装和源码启动结果；`build/` 保留完善发布说明前的中间包。
- `build-final/installed-browser/`：浏览器操作日志、截图和演示报告。
- `real-basic/result.json`、`real-images/result.json`：正式 wheel 真实样本场景结果和已安装代码指纹。
- `release-gate.json`：正式版三项门禁与分发包 SHA-256，记录原生模块证据沿用关系。
- `package-review.json`：文件清单、版本、元数据、RECORD、内容排除及本地上传预演结果。

原包仍保留在 `artifacts/public-export-validation/originals/`，SHA-256 为 `e1542f664e82147726531fb99113047227227e206e0e2c706f6357fc8cefcc2c`。候选版汇总门禁另存为 `artifacts/stable-validation/release-gate-rc1-final.json`。

## 正式发布材料

`dist/v0.1.2/` 只收录 wheel、sdist、源码 ZIP、`RELEASE_NOTES.md`、`VERIFICATION.md` 与 `SHA256SUMS`，可整体交接。校验和涵盖前三种分发包及两份说明。原始媒体、真实材料报告、虚拟环境、私有构建日志和个人配置不在交接目录。

`VERIFICATION.md` 提供脱敏的执行结果及覆盖边界；完整本机证据仍在 `artifacts/`。若后续修改源码，应重新构建并重做受影响验证，不能沿用旧包的指纹。

## 发布与回执

发布目标为 [8mdphgg5yn-eng/photo-move-audit](https://github.com/8mdphgg5yn-eng/photo-move-audit)。具体操作见 [发布流程](publishing.md)。发布前补齐的仓库、下载及包元数据链接单独重建为 `artifacts/github-publication/build-final/`，重新验证安装与浏览器，应用代码与上述正式版受测对象逐字节一致。线上提交、标签、Release 和附件校验回执在本机另存 `artifacts/github-publication/publication-result.json`。PyPI 不在本次发布渠道内。

仍待扩展验证的范围：大图库、更多导出变体、其他系统、独立实体电脑。云端完整导出、视频全程解码、相册与拍摄日期保留仍不属于本工具当前能力。
