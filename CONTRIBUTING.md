# 参与开发

项目仓库：[8mdphgg5yn-eng/photo-move-audit](https://github.com/8mdphgg5yn-eng/photo-move-audit)。问题反馈请使用 [Issues](https://github.com/8mdphgg5yn-eng/photo-move-audit/issues)，代码修改可提交 Pull Request。

## 有价值的反馈

请描述操作系统、Python 版本、来源/目标类型、希望看到的结果、实际结果和最小可复现步骤。若涉及图片解码，同时说明报告中的 `image_decoder`。

优先提供自己制作的色块图片或脱敏后的最小样本。不要提交个人照片、原始完整报告、账号凭据或包含个人信息的本机路径。报告格式和文件名均可能含隐私。

## 修改前后

运行 `python3 -m unittest discover -s tests -v`。影响界面的修改，另做浏览器演示、下载报告和窄屏检查；已有 Playwright 环境可使用 `tests/browser-check.cjs`。

请保持这些语义：

- 按完整内容匹配，不用文件名冒充内容相同。
- 扫描失败、取消、跳过和超限必须有记录，不能静默变成通过。
- 不擅自删除或修复输入文件。
- 检查级别以实际能力记录，不把文件头检查宣传为完整解码。
- 演示结果、合成测试、大图库实际验证和用户反馈分别记载。

新增格式时，需要同时更新实际检查能力、可复现样本和限制说明。仅在扩展名列表中增加一种格式，不能宣称已经支持该格式的完整性验证。
