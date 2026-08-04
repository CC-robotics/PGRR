# Assignment 2：恢复动作与坐标变换

实现 `RecoveryAction.target_pose` 和 `build_action_space`。动作顺序、ID、半径和角度是
公开接口，不得修改。非子目标返回 `None`；子目标从机器人坐标转换到世界坐标。

验收：

```bash
pytest tests/unit/test_action_space.py \
  tests/student/test_student_tasks.py::test_student_action_space_and_world_transform -q
```

完成后把 `ACTIONS` 改为由 `build_action_space()` 生成，并可删除 starter 的 compatibility
registry。增加 yaw 为 `0`、`pi/2`、`-pi/2` 的参数化测试。画出 21 个点，注明四个特殊
动作。失败案例分析单位（度/弧度）或坐标系方向写错导致的轨迹。
