# Assignment 7：论文结果图

实现 `scripts/paper/make_figures.py::outcome_density_figure`。从锁定 final results 中选择
共同 episode 的 Base 与 PGRR，对每个场景显示成功率 `k/n`，对每个密度显示
GOAL/COLLISION/OTHER 的比例。

验收：

```bash
make figures
pdffonts paper/figures/final_outcomes_by_density.pdf
```

不得读 pilot CSV 或手工填值。缺失组合应显式缺失。PDF 使用嵌入的 TrueType/Type 42
字体、色盲可区分颜色和可读字号。附生成命令和源文件 hash。失败案例选择一个“聚合
后看似改善、按场景却相反”的例子，讨论 Simpson's paradox 风险。
