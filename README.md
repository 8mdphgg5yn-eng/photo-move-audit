# 照片搬家核对器 · Photo Audit

一个本地、只读的照片迁移核对工具。比较两个目录或 ZIP 中媒体文件的完整 SHA-256，列出目标未找到的来源内容、重复副本、目标独有内容和读取/格式异常。文件重命名不影响匹配。

当前稳定版为 **v0.1.2**，源码与安装包见 [GitHub Releases](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases/tag/v0.1.2)。原生选择窗口、本机干净环境安装和公开真实 Takeout 小样本三项约定验证已完成。当前验证范围为 macOS；真实样本含 4 份媒体，大图库、所有导出变体和其他系统仍待扩展验证。具体见 [发布说明](docs/release-0.1.2.md)、[正式版验证记录](docs/release-validation-0.1.2.md) 和 [公开导出包实测](docs/public-export-validation.md)。核心运行只使用 Python 标准库，无账号、云服务、遥测或前端 CDN。采用 [MIT 许可证](LICENSE)。

项目介绍与完整使用说明见 [中文介绍与使用指南](docs/introduction-and-usage.zh-CN.md)，包含下载安装、核对步骤、结果解读及当前检查范围。

## 直接使用

需要 Python 3.10 或更新版本。

macOS 可双击本目录的 `启动照片核对器.command`。它会启动仅绑定 `127.0.0.1` 的服务，并打开浏览器。终端窗口保持开启；按 Ctrl+C 结束。也可在本目录运行：

```sh
python3 -m photo_audit serve
```

使用源码 ZIP 时先完整解压，再双击其中的启动脚本。也可将下载的 wheel 安装到独立虚拟环境；在 wheel 所在目录运行：

下载入口：[完整源码 ZIP](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases/download/v0.1.2/photo-move-audit-0.1.2-source.zip)、[wheel](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases/download/v0.1.2/photo_move_audit-0.1.2-py3-none-any.whl)、[SHA256SUMS](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases/download/v0.1.2/SHA256SUMS)。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps photo_move_audit-0.1.2-py3-none-any.whl
.venv/bin/photo-audit serve
```

上述命令适用于 macOS/Linux，不下载运行依赖。基本安装不包含 Pillow；本次安装实测限于 macOS 上的 Python 3.12.14 和 3.14.8。

点击“用自制样本试一遍”，即可看到已知的漏搬、改名、重复和格式异常。演示图片是程序生成的色块，不读取个人照片。演示文件位于系统临时目录，正常退出后清理。

核对自己的文件时：

1. 填写来源目录或 ZIP 的完整路径，macOS 也可点击“选文件夹”或“选 ZIP”。Google Takeout 的多个 ZIP 可放在同一个目录中，工具会分别读取。
2. 选择或填写目标目录或 ZIP 的完整路径，两端不能相同或互相包含。
3. 点击“开始核对”。扫描期间可停止；停止后的结果明确标为未完成。
4. 查看分类列表，按路径定位文件。ZIP 条目同时显示归属压缩包、内部路径和条目序号。
5. 按需保存 HTML 阅读报告或包含完整记录的 JSON 报告。报告可能含本机路径，分享前请检查。

macOS 选择窗口只在点击按钮后打开，取消会保留原路径。选择路径不会自动开始核对。其他系统保留粘贴路径方式。也可在访达中选中文件/文件夹，按住 Option，右键选择复制路径。

输入框已有有效路径时，选择窗口会从该目录或文件所在目录打开。

保持启动窗口运行时，刷新页面会恢复最近一次结果；正在进行的核对会继续显示进度，不会因刷新重新扫描。填错新路径导致启动失败时，上一份结果和报告仍保留，报告旁会显示其实际对应的来源和目标。

## 命令行

```sh
python3 -m photo_audit check '/path/to/source' '/path/to/destination'
python3 -m photo_audit check '/path/to/source' '/path/to/destination' \
  --json '/path/to/reports/audit.json' --html '/path/to/reports/audit.html'
python3 -m photo_audit demo
```

将示例路径替换成实际路径，输出报告的父目录须已存在。CLI 不覆盖已有报告，也不允许将报告写进两个输入目录。浏览器的下载位置由浏览器控制，请另存到专用报告目录。

退出码：

| 退出码 | 含义 |
| --- | --- |
| 0 | 来源存在可核对媒体、本次扫描完成、未发现缺失或记录的异常。只限本工具检查范围，不代表所有媒体都能完整播放 |
| 1 | 扫描完成，但有目标未找到的内容或格式检查异常 |
| 2 | 输入/输出错误、扫描不完整、取消或未读取到来源媒体 |

演示包含故意设置的异常，因此 `demo` 正常情况下退出 1。

## 怎样解释结果

- **来源文件数**是成功计算完整指纹的媒体记录数。ZIP 中的副本分别计数。
- **来源不同内容**按完整字节指纹去重。一份来源内容只需要在目标找到一份相同内容；不会要求保留所有重复副本。
- **目标未找到**指本次目标扫描中没有同一指纹；如果目标扫描未完成，这只是部分结果。
- **重复内容组**分别统计来源和目标，不把两端正常的对应副本当成重复清理对象。
- **目标多出**不是错误，可能是新拍摄、编辑、压缩或元数据改写后的文件。
- **异常与未完成项**区分已发现的格式问题和无法完成的读取。文件头不符也可能只是扩展名错误，需要人工判断。

报告保存每份媒体的位置、大小、完整指纹、实际格式检查级别，以及 ZIP CRC 是否完成。`scan_complete` 只说明声明范围内的扫描流程完成。

## 完整性检查的实际范围

默认不安装任何第三方包：识别部分常见文件头、空文件、读取长度/错误，以及 ZIP 中已读取媒体条目的 CRC。

如果运行环境已有 Pillow，自动增加 JPEG、PNG、GIF、WebP、BMP、TIFF 的 `verify()` 与首帧解码。其他格式仍按实际能力标注。超过像素保护阈值的图片不强行解码。可在自己的虚拟环境中另装可选依赖：

```sh
python3 -m pip install '.[images]'
```

这是可选安装步骤，会从包源下载依赖；基本运行不需要执行。每次报告会记录 Pillow 是否可用。

| validation | 实际含义 |
| --- | --- |
| first_frame_decoded | 支持格式经过校验及首帧解码，不保证所有帧或所有页面 |
| header_only | 仅文件头层面的检查，未确认完整解码 |
| unchecked | 已核对字节内容，但没有该格式的解码/文件头检查 |
| failed | 文件为空、签名不符或图片解码检查未通过 |

## 已知边界

1. 无法仅凭导出包证明云端已经全部导出。不要单凭报告删除来源或云端照片。
2. 不做视频全程解码，不确认所有动画帧、多页图像或动态照片的配对情况。
3. 不核对相册、拍摄日期和 EXIF/JSON 保留情况；元数据 JSON 与其他非媒体文件按忽略项计数。
4. 不比较视觉相似度。编辑、压缩或元数据改写会改变指纹。
5. 支持媒体扩展名列表见 `photo_audit/core.py` 的 `MEDIA`。未知扩展名不进入媒体分母，即使内部实际是照片。
6. 不递归打开 ZIP 内的嵌套 ZIP，不支持加密 ZIP；无法读取项会阻止完整扫描结论。
7. 不跟随被识别的符号链接，不解压到磁盘，不自动删除、移动、重命名或修复任何输入文件。
8. 每端默认最多 25 万个文件/ZIP 条目、单媒体 32 GiB、媒体读取总量 4 TiB；高压缩比条目受保护限制。超限报告未完成。这不是针对所有恶意压缩包的安全审计。
9. 扫描不是文件系统快照。对观察到的本地文件和 ZIP 改动会报错；扫描结束后的变化不在报告覆盖内。建议暂停正在写入两端的同步任务后核对。
10. 当前逐文件读取和计算指纹，尚无断点续扫和持久索引。大图库耗时、内存和不同文件系统兼容性尚未实测。
11. 一次本机服务只保留最近一次核对结果；刷新可恢复该结果，新核对成功启动后替换旧记录。关闭服务后内存结果消失，需另存报告。浏览器仅在当前标签页的 sessionStorage 中保存会话令牌，不保存路径或报告。
12. 服务提供本机网页界面，不提供局域网/公网部署模式。随机会话令牌和同源检查不构成对本机恶意程序的隔离。

## 测试与复现

无需安装测试依赖：

```sh
python3 -m unittest discover -s tests -v
```

覆盖改名匹配、同名不同内容、多分卷 ZIP、重复计数、CRC 失败、空来源、读取失败、符号链接、读取/条目上限、取消、HTML 转义、CLI 输出保护、本机 API 与报告下载。Pillow 解码测试在未安装 Pillow 时明确跳过。

浏览器集成检查需要已经安装的 Playwright 和 Chromium/Chrome，可选环境变量 `PHOTO_AUDIT_PLAYWRIGHT_MODULE` 和 `PHOTO_AUDIT_BROWSER` 分别指定现有模块和浏览器路径。先启动本机服务，再传入终端显示的完整会话 URL：

```sh
node tests/browser-check.cjs 'http://127.0.0.1:PORT/#SESSION'
```

该测试生成自制样本的截图和报告至 `artifacts/`，不应使用个人图库作为公开测试素材。可用 `PHOTO_AUDIT_TEST_OUTPUT` 指定独立证据目录。具体本机验证见 [验证记录](docs/verification.md) 和 [2026-10-22 扩展测试](docs/test-2026-10-22.md)。

另有独立的合成迁移及完整字节读取检查：

```sh
PYTHONPATH=. python3 tests/scenario_check.py --output artifacts/scenarios.json
```

该检查创建两端共 6090 条媒体记录及每端 64 MiB 的合成字节文件，使用临时目录并在结束后清理。它不读取个人照片，不代表真实大图库或视频解码已经验证。

发行包构建和安装检查见 [正式版验证记录](docs/release-validation-0.1.2.md)。`scripts/release_check.py` 只生成本地分发包和验证记录，不执行上传或发布。发布操作与文件清单见 [发布流程](docs/publishing.md)。

## 与现有工具的关系

本工具用于在本机比较迁移前后的媒体内容，配合既有下载器或相册系统使用。立项调研参考了 [immich-go](https://github.com/simulot/immich-go)、[takeout-to-immich](https://github.com/tomerh2001/takeout-to-immich) 和 [GoogleTakeoutFixer](https://github.com/feloex/GoogleTakeoutFixer) 的公开文档。本次没有安装这些工具做对照，也未复制其实现。

下一步应先用志愿者提供的非敏感测试材料检验误报、操作负担和大图库表现，再决定增加元数据配对、断点续扫或特定相册服务适配。尚未进行社区招募或对外发送。
