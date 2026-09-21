# 第 7、8 类编译回执

实际执行 scripts/student/compile_remaining_family_smokes.py，使用 eight_family_common.write_smoke。
两个训练原型已生成 JSON、顶视预览、SHA-256，并写入 outputs/student/families_7_8_smoke/families_7_8_manifest.json。

- 第 7 类：medium/train，seed 91610，两名循环横穿行人及局部瓶颈。
- 第 8 类：low/train，seed 91700，目标前 3 m 的循环横穿行人。

完成 schema、静态 A* 连通性和预览检查；新测试与第 3–6 类、公共层回归共 6 项通过。
Arena 尚未执行，不能记录运行成功或比较结果。

第 8 类为持续横穿的空间原型；精确时机的一次横穿及遮挡尚未实现。
第 7 类瓶颈宽度使用占据栅格货架半宽计算，实际 Gazebo 净宽仍需核验。
公共层写出 JSON/预览并返回记录；本入口负责将两条记录保存为 manifest。
