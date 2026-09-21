# DAgger manifest 固定数据的本地与 Git 历史检索

## 检索目标

上一项标签/mask 审计发现本地 iteration-3 与 validation HDF5 哈希不符合 manifest。
本步新增只读工具 `scripts/student/audit_dagger_manifest_artifacts.py`，在以下范围按内容
SHA-256 查找四个 manifest 引用：

1. 当前 `data/**/*.h5`；
2. 当前仓库所有 Git 历史中曾提交的 `data/**/*.h5` blob。

输出保存在 `outputs/student/dagger_diagnostic/manifest_artifact_search.json`。脚本不恢复、
覆盖或下载文件，也不访问远程仓库。

## 结果

两个 manifest 形成四条引用（shared validation 被两个 manifest 分别引用）：

| 引用 | 期望哈希前缀 | 本地/Git 历史状态 |
|---|---|---|
| selected iteration-3 train | `d529efb4` | 未找到 |
| selected shared validation | `5d446cd0` | 未找到 |
| later iteration-5 train | `2a46403f` | 当前本地匹配 |
| later shared validation | `5d446cd0` | 未找到 |

聚合为 1 条 `local_match`、3 条 `not_found_local_or_git_history`。单元测试与 Ruff 均
通过。

## 结论和边界

这排除了“canonical 文件只是换了本地文件名”以及“可以直接从当前 Git 历史恢复”两种
简单情况。iteration-3/validation 的严格分布复核需要项目外的可信备份或原始制作者
提供文件；在此之前不能改 manifest 来迁就现有副本，也不能把现有副本的分布数字写成
canonical 对照。

这不阻塞继续做纯代码重构、场景静态预检和使用已经核验的 iteration-5 文件进行描述性
诊断，但它是未来声称“第二轮是否过拟合”时必须披露的 provenance 限制。

