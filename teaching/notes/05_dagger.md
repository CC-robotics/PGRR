# 第 5 讲：DAgger 与策略诱导分布

## BC 的协变量偏移

BC 只见过专家访问的状态。部署时一次小错误会把机器人带到训练分布外，随后误差继续
累积。导航恢复尤其容易出现这种问题，因为触发状态本来就少且接近失败边界。

## DAgger 循环

1. 当前策略只在 train split 运行；
2. 收集它实际访问的恢复状态；
3. 特权专家离线重标注这些状态；
4. 与已有数据按 episode 合并；
5. 重新训练；
6. 在固定 validation 场景评价；
7. 重复第二轮。

专家给标签时可以看真值，策略输入仍不能看真值。测试场景绝不能进入聚合数据。

## 数据审计

每轮记录 episode ID、scenario、map、seed、split、source policy、Arena commit、project
commit 和数据 hash。检查 NaN/Inf、mask 至少一个合法动作、expert action 合法、重复
episode 和 split 泄漏。

比较：

- 新旧状态的目标距离、failure score、LiDAR clearance 分布；
- 专家动作分布和动作切换；
- validation cost regret；
- 真实闭环 recovery success，而非只看分类 accuracy。

## 两轮不等于一定提升

第二轮可能引入大量相似 WAIT 状态或标签噪声，使性能退化。应报告每轮结果和数据量，
不能只保留最有利的迭代。模型选择只看 validation；test 在配置锁定后运行一次。

## 练习

从两个迭代 manifest 计算场景分布和动作 Jensen-Shannon divergence，生成一张图并解释
偏移来源。然后选一个策略失败 episode，判断是 observation coverage、专家标签还是
闭环执行误差。

```bash
make train-dagger DAGGER_ITERATION=1
make train-dagger DAGGER_ITERATION=2
```

大型采集不是作业硬门槛；可以用已保存的小 shard 验证完整聚合与训练数据流。
