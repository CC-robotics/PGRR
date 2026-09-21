# 第 7 类 PGRR 功能回合：推理环境阻塞记录

日期：2026-09-09。

## 已执行检查

- WSL `checkpoints/final/best.onnx` 是指向 `../dagger/coverage_safety_aligned/best.onnx` 的有效符号链接。
- 两条路径 SHA-256 均为正式配置值 `78807ce56f575943ca3f965be9b71c0d83c0ca3f2a23f267fe04fd6a00c119d2`。
- `student_v78_bottleneck_cross_flow_merge_medium_train_r00_s91610_pgrr_function01` 在进入 episode 前退出，原因是 `/workspace/.venv-inference/bin/python` 缺失。
- function01 留下 runtime/status 启动日志，但没有 JSONL、metadata 或 outcome；不得记为一个完成 episode，也不是 PGRR 性能结果。

## 标准恢复配方

Git 历史中的原项目配方为在项目根目录创建 `--system-site-packages` 的 `.venv-inference`，并固定安装：

- `coloredlogs==15.0.1`
- `flatbuffers==25.12.19`
- `humanfriendly==10.0`
- `numpy==2.2.6`
- `onnxruntime==1.23.2`

联网安装属于持久环境修改，自动审批因先前“不安装环境”的约束而拒绝，未绕过。需要用户明确授权后才能执行。

## 后续保护

`scripts/student/run_family7_pgrr_function_smoke.sh` 已将默认新 ID 改为 `function02`，并在启动 Arena 前依次检查 Docker、场景、checkpoint 哈希、推理 Python 和所有目标输出冲突。function01 日志完整保留。

## 2026-09-09 解除情况

用户明确授权后，已按上述固定版本创建 `.venv-inference`。CPUExecutionProvider 成功加载正式 ONNX；随后 function02 已完成。具体功能证据见 `47_family7_pgrr_function_smoke_result.md`。本文件保留为 function01 未完成尝试及环境恢复的审计记录。
