# 磁力牛顿摆录像与轨迹导出工具

## 安装依赖

```powershell
python -m pip install -r requirements_magnetic_cradle.txt
```

## 运行

```powershell
python magnetic_newton_cradle_recorder.py --camera 0 --num-pendulums 5
```

如果摄像头不是默认设备，可以把 `--camera 0` 改成 `--camera 1` 或 `--camera 2`。

如果想复用某次标定：

```powershell
python magnetic_newton_cradle_recorder.py --config magnetic_cradle_runs\某次实验\calibration.json
```

如果想无预览录制固定时长：

```powershell
python magnetic_newton_cradle_recorder.py --no-preview --duration 20
```

## 操作流程

1. 程序打开摄像头后，会先截取一帧用于标定。
2. 按照从左到右的顺序，依次点击每个摆的悬点。
3. 逐个框选每个摆球或贴在摆球上的高对比度标记。
4. 进入预览界面后，按 `r` 开始录像，再按 `r` 停止录像。
5. 按 `q` 退出并保存全部结果。

## 输出文件

每次实验会保存在 `magnetic_cradle_runs/日期_时间/` 目录下：

- `raw_video.mp4`：原始摄像头录像。
- `annotated_tracking.mp4`：带悬线、摆球中心和轨迹的标注视频。
- `pendulum_tracking_long.csv`：长表数据，每行是某一帧中某一个摆的数据。
- `pendulum_tracking_wide.csv`：宽表数据，每行是一帧，适合做时间序列分析。
- `angle_timeseries.png`：各摆角度随时间变化图。
- `calibration.json`：本次标定参数，可复用。

## 数据字段

- `x_px`, `y_px`：摆球中心的像素坐标。
- `angle_deg`, `angle_rad`：相对竖直向下方向的摆角。
- `omega_rad_s`：角速度，按相邻帧差分估计。
- `speed_px_s`：像素速度。
- `confidence`：颜色跟踪置信度，数值低时说明跟踪可能丢失。

## 建议

为了让 OpenCV 更稳定地识别每个摆球，建议在摆球正面贴上颜色明显的小圆点，背景尽量单一，摄像头固定并与摆动平面正对。做混沌分析时，优先使用 `angle_deg` 或 `angle_rad` 时间序列，再计算相空间、庞加莱截面、相关维数或 Lyapunov 指数。
