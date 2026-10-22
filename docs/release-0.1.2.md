# 照片搬家核对器 v0.1.2

本地、只读的照片迁移核对工具。比较迁移前后的目录或 ZIP，按完整 SHA-256 找到缺失、重复和目标独有内容；改过文件名仍能匹配。支持本机网页、命令行及 HTML/JSON 报告，采用 MIT 许可证。

本次为首个正式稳定版本，验证范围以 macOS 为主。稳定版表示当前声明功能已经通过约定验收，具体覆盖范围和已知限制如下。

## 获取和启动

| 文件 | 用途 |
| --- | --- |
| `photo-move-audit-0.1.2-source.zip` | 完整源码、文档、测试及 macOS 启动脚本 |
| `photo_move_audit-0.1.2-py3-none-any.whl` | 安装到 Python 虚拟环境 |
| `photo_move_audit-0.1.2.tar.gz` | Python 源码分发包 |
| `SHA256SUMS` | 核对下载文件是否与准备的版本一致 |

需要已经安装 Python 3.10 或更新版本；本次安装实测为 macOS 上的 Python 3.12.14 和 3.14.8。分发包不捆绑 Python，也不是签名的 macOS `.app` 或安装器。

macOS 用户可完整解压源码 ZIP，双击其中的 `启动照片核对器.command`。终端保持开启，按 Ctrl+C 结束服务。

使用 wheel 时，在文件所在目录执行：

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps photo_move_audit-0.1.2-py3-none-any.whl
.venv/bin/photo-audit serve
```

核心运行使用 Python 标准库，无需账号、云服务或网络下载。Pillow 是可选图片校验能力；不含 Pillow 的环境会在报告中标明仅做文件头检查。完整使用方法见源码包中的 `README.md`。

## 本次版本

- 本机网页支持演示、原生路径选择、结果分类、分页、刷新恢复和报告下载。
- 读取失败、停止、超限或扫描期间观察到文件变化时，明确报告异常或未完成。
- 与候选版相比，同步稳定版版本号、界面文字和发布资料；内容比较与校验逻辑保持一致。

## 验证

48 项单元测试在 Pillow 环境全部通过；基本环境 46 项通过、2 项可选解码测试跳过。原生窗口完成文件夹选择、ZIP 选择和取消。正式分发包通过两个干净虚拟环境安装、源码 ZIP 解压启动及浏览器操作验证。

公开 Takeout 小样本含 2 张 JPEG、2 段 MP4，两个隔离环境各 8 个场景通过，原始 ZIP 指纹未变。场景覆盖改名、缺失、重复、文件中部字节改写和截断压缩包。来源为 [Immich 社区公开复现样本](https://github.com/immich-app/immich/discussions/11500)；详细范围及正式版证据见源码包中的 `docs/public-export-validation.md`、`docs/release-validation-0.1.2.md`。

## 当前边界

1. 不证明云端已经完整导出，不核对相册及拍摄日期元数据；不要仅凭报告删除来源照片。
2. 不进行视频全程解码；支持图片的可选解码只覆盖首帧。
3. 大图库、Google 原生多分卷、更多导出变体、其他系统和独立实体电脑尚未实测。
4. 测试用的第三方真实照片和视频不随本软件分发。

反馈时请提供系统、Python 版本、输入类型和可复现步骤，优先使用自制或脱敏最小样本。报告可能包含本机路径，请检查后再分享。
