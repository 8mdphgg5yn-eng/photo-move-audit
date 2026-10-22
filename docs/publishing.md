# v0.1.2 发布流程

稳定版本号为 `0.1.2`，Git 标签为 `v0.1.2`。发布仓库为 [8mdphgg5yn-eng/photo-move-audit](https://github.com/8mdphgg5yn-eng/photo-move-audit)，发布记录见 [GitHub Releases](https://github.com/8mdphgg5yn-eng/photo-move-audit/releases)。本文件记录维护流程，不会自动上传任何文件。

## 已准备的材料

交接目录为 `dist/v0.1.2/`。GitHub Releases 附件为三个分发包、`RELEASE_NOTES.md`、`VERIFICATION.md` 和 `SHA256SUMS`；`RELEASE_NOTES.md` 同时用作发布正文。将两份说明都作为附件提供，可直接运行完整校验和检查。

在交接目录核对文件：

```sh
shasum -a 256 -c SHA256SUMS
```

源码 ZIP 包含的顶层目录可以单独成为本项目的仓库根目录。只从这个明确准备的源码目录上传，避免将父目录中的其他项目、测试原件、日志或个人材料加入公开仓库。README、许可证、变更记录和贡献说明均随源码提供。

## GitHub Releases

确定目标账号或组织、仓库地址及源代码提交后，将本次源码纳入该仓库，并让标签 `v0.1.2` 指向对应提交。随后创建 Release 草稿、上传附件、填写发布正文，核对后发布；正式版不勾选 pre-release。

以下命令从交接目录执行，要求远端已有正确标签，防止自动在错误提交上创建标签。后续版本发布时同步调整版本号和文件名；已发布版本不重复创建或替换附件。

```sh
gh release create v0.1.2 \
  photo-move-audit-0.1.2-source.zip \
  photo_move_audit-0.1.2-py3-none-any.whl \
  photo_move_audit-0.1.2.tar.gz RELEASE_NOTES.md VERIFICATION.md SHA256SUMS \
  --repo 8mdphgg5yn-eng/photo-move-audit --verify-tag --draft \
  --title '照片搬家核对器 v0.1.2' --notes-file RELEASE_NOTES.md
```

该命令会创建线上草稿并上传文件，应在目标和发布动作获确认后执行。核对草稿及所有附件后发布，标记为最新稳定 Release，并保存线上回执及下载文件的指纹。

## 可选 PyPI 渠道

wheel 与 sdist 已按 Python 分发格式构建，但没有声称 `photo-move-audit` 名称已在 PyPI 注册、可用或归本项目所有。选择 PyPI 时，先核实包名和账户权限；凭证由本机安全配置或平台的可信发布流程提供，不写入源码或发布说明。

可对两个文件做不上传的本地格式预演，不指定 `--index` 或 `--check-url`：

```sh
uv publish --dry-run --no-config \
  photo_move_audit-0.1.2-py3-none-any.whl photo_move_audit-0.1.2.tar.gz
```

实际上传时只选择这两个 Python 分发文件。源码 ZIP、校验和、说明及 `artifacts/` 不作为 PyPI 分发包上传。本地格式预演不证明名称可注册、账户有权限或 PyPI 已接收文件。

本机 uv 0.11.7 拒绝 `publish --offline` 的组合，故未把该次调用记为通过。`--dry-run` 的本地检查另外执行；配置实际目标和凭证留待正式发布阶段。

流程依据：[GitHub 发布管理文档](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)、[uv 构建与发布文档](https://docs.astral.sh/uv/guides/package/)。
