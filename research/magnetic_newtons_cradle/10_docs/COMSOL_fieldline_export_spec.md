# COMSOL 磁场线实时显示导出格式

真正实时重新求解 COMSOL 不适合本项目，因为五个摆每一帧位置都变，有限元重算会非常慢。推荐方式是：

1. 在 COMSOL 中先求单个圆柱磁体的二维截面磁场。
2. 导出规则网格上的 `Bx, By`。
3. 实时模拟时根据磁体位置平移、叠加、插值。
4. 在 Python 动画里画 streamlines。

## 推荐导出 CSV 格式

文件名建议：

```text
comsol_single_magnet_Bfield_70mT.csv
```

列名：

```text
x_m,y_m,Bx_T,By_T
```

含义：

- `x_m`：相对磁体中心的横向坐标，单位 m
- `y_m`：相对磁体中心的竖向坐标，单位 m
- `Bx_T`：磁感应强度 x 分量，单位 T
- `By_T`：磁感应强度 y 分量，单位 T

网格范围建议：

```text
x: -0.12 m 到 0.12 m
y: -0.10 m 到 0.10 m
```

网格密度建议：

```text
121 x 101 或更高
```

## COMSOL 中需要导出的变量

一般磁场模块里可导出：

```text
mf.Bx
mf.By
```

如果模型坐标不是 x-y 平面，需要对应修改为实际截面的两个方向。

## COMSOL 手动导出步骤

0. 目前已经为你新建了一个几何模型：

```text
06_sources/comsol_field_grid/single_magnet_Bfield_70mT_model.mph
```

它包含：

- 空气域：`x = -120 mm 到 120 mm`，`y = -100 mm 到 100 mm`
- 磁体截面：厚度 `15 mm`，直径 `30 mm`
- 参数：`Rmag, Tmag, Bface, Br_eff, xmax, ymax`
- 网格

1. 打开这个 `.mph`。
2. 添加 `AC/DC -> Magnetic Fields` 物理场。
3. 将内侧小矩形域设置为永磁体，磁化方向沿 `+x`。
4. 永磁体强度可先用：

```text
Br_eff = 0.19799 T
```

这个值来自 70 mT 极面磁场的等效估计。

5. 外侧空气域相对磁导率设为 1。
6. 外边界使用 Magnetic Insulation 或默认开放边界近似。若有 Infinite Element Domain 更好，但当前展示用普通空气框也够用。
7. 求解 Stationary 磁场。
8. 进入 `Results -> Datasets`，确认使用的是求解结果数据集。
9. 进入 `Results -> Export -> Data`。
10. Dataset 选择当前磁场解。
11. Expression 填：

```text
x
y
mf.Bx
mf.By
```

如果 COMSOL 变量名不同，就用实际磁场接口对应的 `Bx, By`。

12. Unit 建议：

```text
m
m
T
T
```

13. Grid 选择规则网格，建议：

```text
x: range(-0.12,0.002,0.12)
y: range(-0.10,0.002,0.10)
```

这样大约是 `121 x 101 = 12221` 个点。

14. 导出为 CSV 后，把列名改成：

```text
x_m,y_m,Bx_T,By_T
```

15. 保存到：

```text
06_sources/comsol_field_grid/comsol_single_magnet_Bfield_70mT.csv
```

后续实时场线程序会优先读取这个 COMSOL 真网格；如果没有这个文件，就使用当前的有限圆柱近似网格。

## 为什么只导出单个磁体

磁场近似满足叠加原理。实时模拟中第 `i` 个磁体的位置为：

```math
(x_i(t), y_i(t))
```

总磁场可以近似写成：

```math
B_x(x,y,t)=\sum_i B_x^{single}(x-x_i(t),y-y_i(t))
```

```math
B_y(x,y,t)=\sum_i B_y^{single}(x-x_i(t),y-y_i(t))
```

这样就不需要每一帧重新跑 COMSOL。

## 注意

当前项目的 GIF 预览 `motion_with_fieldlines_preview_5cm.gif` 使用的是快速偶极近似，只适合展示“磁场线随摆运动变化”的视觉效果。若要作为严格理论图，应使用上述 COMSOL 导出的 `Bx, By` 网格替换偶极场。

目前已经生成一个同格式测试网格：

```text
06_sources/comsol_field_grid/single_magnet_Bfield_grid_70mT_finite_cylinder.csv
```

它不是 COMSOL 真结果，但列名和单位已经按 COMSOL 实时场线程序需要的格式准备好了。
