# 第 8 讲：从结果文件到可审计论文

## 证据链

论文中的每个数值必须能追溯到 episode JSONL、`results.parquet`、`summary.csv` 或
`statistics.json`。表格和图由脚本生成，正文可使用自动生成的 LaTeX macro。维护
claim-evidence matrix：声明、实验、图表、原始文件、统计状态和反例逐项对应。

## Assignment 7

实现 `outcome_density_figure`：

- 只使用 `_valid_rows` 接受的算法 episode；
- 用 `_select_central_methods` 选共同 manifest 上的主对比；
- 一部分按场景显示成功率与 `k/n`；
- 一部分按 low/medium/high 显示 goal/collision/other failure；
- 缺失组合显示缺失，不补零、不复制其他密度；
- 输出矢量 PDF，字体嵌入且可读。

图注必须说明结果来自哪一个固定 manifest。运行过程“截图”应优先由 telemetry 重建，
标出机器人、行人、路径、恢复状态和动作；它不是相机图像，不能写成真实视觉输入。

## 写结果而不是写愿望

先写实验设置和指标定义，最终结果完成后才写摘要。只有置信区间和统计支持时才使用
“显著改善”。如果 PPO、学习 detector 或 Gazebo 未完成，就从题目和贡献中删掉相应
增益表述。

Related Work 需要阅读方法、实验和限制，不能凭搜索摘要写。引用优先 DOI 或正式会议，
无 DOI 时再用 arXiv；作者、年份和编号逐项核验。

## 最小自检

```bash
make figures
make tables
make paper
pdffonts paper/main.pdf
```

检查未解析引用、表格与 CSV 一致、无 Type 3 字体、图中文字可读、匿名作者信息和页数。

## 结论边界

PGRR 可讨论失败触发介入、规划专家标注、离散子目标、DAgger 分布覆盖和 action mask。
不得声称形式化无碰撞保证、解决通用社会导航，或“首次结合规划/IL/RL”。限制部分应
明确二维 LiDAR、已知静态地图、仿真人群差异、有限离散动作和缺少实机验证。
