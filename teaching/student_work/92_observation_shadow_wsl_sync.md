# 92. Observation shadow WSL 精确同步

## 完成内容

本步把预检固定的五个运行文件同步到 WSL 的 `/home/preface/PGRR-online`。同步前先完成了三项只读检查：目标文件 Git 状态、忽略换行后的差异规模、ROS 节点的逐段差异。结果表明 Windows 节点是在 WSL 版本上增加 observation-shadow 逻辑，两个启动脚本也只有预期的开关增量，没有发现会被删除的 WSL 独有逻辑。

第一次用通用命令转换换行时，检查立即发现转换无效且三个 Python 行尾字符被错误截断，因此没有进行构建或 Arena 运行。随后新增并测试白名单同步器 `sync_observation_shadow_runtime_sources.py`：它只允许五个固定路径、写入前核对预检哈希、逐文件备份、统一为 LF、设置明确权限，并在写入后再次核对哈希。

## 最终验证

- 白名单同步器相关 9 项测试和 Ruff 通过。
- WSL 五个文件的换行归一化 SHA-256 为 5/5 匹配。
- 两个 WSL Bash 文件通过 `bash -n`。
- 三个 Python 文件通过 `py_compile`，缓存写入 `/tmp`。
- 可恢复备份位于 `/tmp/pgrr_observation_shadow_sync_backup_20260913_v2`。

## 边界

本步只同步和验证源码，没有构建 ROS overlay，没有启动容器实验，也没有生成运行效果数据。第一次失败的同步没有越过哈希/语法门禁，随后由白名单同步器覆盖修复。

## 下一步

在 WSL checkout 中执行一次 overlay 构建。构建通过后重新确认预检 ID 尚未存在，再执行唯一一次非冻结 train-only observation-shadow smoke。
