# 磁力牛顿摆记录器

这是一个基于 OpenCV 的磁力牛顿摆实验记录工具。它可以调用摄像头录像，追踪多个摆球的运动，并导出可用于混沌状态研究的时间序列数据。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 网页界面

这个网页界面需要在连接摄像头的电脑上本地运行。直接打开 GitHub 页面或仓库文件不能控制你电脑的摄像头，因为真正调用摄像头的是本机 Python/OpenCV 后端。

```powershell
python web_app.py
```

也可以双击：

```text
start_web.bat
```

启动后在浏览器打开：

```text
http://127.0.0.1:7860
```

网页界面支持：

- 打开和关闭摄像头
- 检测可用摄像头编号
- 在实时画面上点击每个摆的悬点
- 拖框选择每个摆锤上的黄色标识点
- 开始和停止录像
- 自动保存原始视频、标注视频、CSV 数据和角度曲线

## 命令行模式

先检测摄像头编号：

```powershell
python camera_test.py
```

```powershell
python magnetic_newton_cradle_recorder.py --camera 0 --num-pendulums 5
```

如果摄像头不是默认设备，可以把 `--camera 0` 改成 `--camera 1` 或 `--camera 2`。

复用某次标定：

```powershell
python magnetic_newton_cradle_recorder.py --config magnetic_cradle_runs\某次实验\calibration.json
```

无预览录制固定时长：

```powershell
python magnetic_newton_cradle_recorder.py --no-preview --duration 20
```

## 输出文件

每次实验会保存在 `magnetic_cradle_runs/日期_时间/` 目录下：

- `raw_video.mp4`：原始摄像头录像
- `annotated_tracking.mp4`：带悬线、摆球中心和轨迹的标注视频
- `pendulum_tracking_long.csv`：长表数据，每行是某一帧中某一个摆的数据
- `pendulum_tracking_wide.csv`：宽表数据，每行是一帧，适合时间序列分析
- `angle_timeseries.png`：各摆角度随时间变化图
- `calibration.json`：本次标定参数

## 数据字段

- `x_px`, `y_px`：摆球中心的像素坐标
- `angle_deg`, `angle_rad`：相对竖直向下方向的摆角
- `omega_rad_s`：角速度，按相邻帧差分估计
- `speed_px_s`：像素速度
- `confidence`：颜色跟踪置信度，数值低时说明跟踪可能丢失

## 实验建议

建议在黑色摆锤正面画或贴亮黄色标识点，标定时只框住黄色点。程序会优先使用黄色 HSV 阈值，并结合悬点位置、摆长约束和最大跳变限制来减少串扰；如果某一帧没有找到黄色点，会保持上一帧位置并把 `confidence` 记为 0，而不是跳去追背景。背景尽量单一，摄像头固定并与摆动平面正对。做混沌分析时，优先使用 `confidence > 0` 的 `angle_deg` 或 `angle_rad` 时间序列，再计算相空间、庞加莱截面、相关维数或 Lyapunov 指数。
