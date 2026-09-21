# 91. Observation shadow 运行源码哈希门禁

## 完成内容

预检工件现在固定真实运行所需五个文件的换行归一化 SHA-256：观测构建器、shadow 比较器、ROS 恢复管理器、外层启动器和内层启动器。新增只读核验器 `verify_observation_shadow_runtime_sources.py`，可在运行前比较 WSL/Arena checkout 与预检工件，同时避免把 Windows CRLF 与 WSL LF 误判为代码差异。

核验器不会复制或修改文件，只报告每个文件是否存在、实际哈希、预期哈希和是否一致。任意文件缺失或过期都会以非零退出码阻止继续。

## 验证结果

- 15 个预检、哈希核验、运行证据及 ROS 静态集成测试通过。
- Ruff 通过。
- 当前 Windows 权威工作区的五个文件自检为 5/5 匹配。
- 更新后的预检与自检分别保存在：
  - `outputs/student/refactor_baseline/observation_shadow_smoke_preflight.json`
  - `outputs/student/refactor_baseline/observation_shadow_source_selfcheck.json`

## 结论边界

5/5 自检只证明预检工件正确绑定了当前工作区，尚不证明 WSL 的 `~/PGRR-online` 或容器 overlay 已同步。核验器明确记录 `copy_performed=false`，且每项记录 `line_endings_normalized=true`。

## 下一步

先对 WSL checkout 做只读哈希比较。只有发现不一致时才同步这五个明确文件，并在同步前检查目标工作树，避免覆盖未知修改；随后重新核验 5/5 并构建 overlay。
