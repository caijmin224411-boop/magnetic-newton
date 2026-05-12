# 磁力牛顿摆记录器

这是一个基于 OpenCV 的磁力牛顿摆实验工具。它支持实时摄像头记录，也支持对手机或相机拍好的视频做离线逐帧识别。正式实验数据更推荐使用离线模式：手机先录高帧率视频，电脑再逐帧分析。

## 安装

```powershell
python -m pip install -r requirements.txt
```

## 离线视频逐帧分析

把视频放到 `videos` 文件夹，例如：

```text
videos\test.mp4
```

运行：

```powershell
python analyze_video.py --video videos\test.mp4 --num-pendulums 5
```

程序会打开视频第一帧：

1. 从左到右点击每个摆的悬点。
2. 逐个框住黑色摆锤上的黄色标识点。
3. 程序自动逐帧分析完整视频。

输出保存在 `video_runs\日期_时间\`：

- `raw_video.mp4`：原始片段
- `annotated_tracking.mp4`：带轨迹的标注视频
- `pendulum_tracking_long.csv`：长表数据
- `pendulum_tracking_wide.csv`：宽表数据
- `angle_timeseries.png`：角度曲线
- `calibration.json`：标定参数
- `result.json`：本次分析摘要

复用某次标定：

```powershell
python analyze_video.py --video videos\test.mp4 --config video_runs\某次分析\calibration.json
```

只分析其中一段：

```powershell
python analyze_video.py --video videos\test.mp4 --start 3.5 --end 12.0
```

如果视频分辨率太大，标定窗口超出屏幕，可以缩放交互画面：

```powershell
python analyze_video.py --video videos\test.mp4 --display-scale 0.5
```

如果手机慢动作视频的帧率元数据不准，可以手动指定：

```powershell
python analyze_video.py --video videos\test.mp4 --fps 120
```

## 网页实时界面

这个网页界面需要在连接摄像头的电脑上本地运行。直接打开 GitHub 页面或仓库文件不能控制本机摄像头，因为真正调用摄像头的是本机 Python/OpenCV 后端。

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
- 显示当前实际 FPS
- 点击每个摆的悬点
- 框选每个摆锤上的黄色标识点
- 开始和停止录像
- 自动保存视频、CSV 数据和角度曲线

## 摄像头检测

```powershell
python camera_test.py
```

DroidCam 帧率低时优先尝试：

- 设备编号选 `1`
- 分辨率先用 `640 x 480`
- 帧率填 `60`
- 预览质量填 `60-70`
- 使用 USB 连接
- 手机端和电脑端关闭省电模式

## 命令行实时录像

```powershell
python magnetic_newton_cradle_recorder.py --camera 0 --num-pendulums 5
```

复用某次标定：

```powershell
python magnetic_newton_cradle_recorder.py --config magnetic_cradle_runs\某次实验\calibration.json
```

## 数据字段

- `x_px`, `y_px`：标识点中心的像素坐标
- `angle_deg`, `angle_rad`：相对竖直向下方向的摆角
- `omega_rad_s`：角速度，按相邻帧差分估计
- `speed_px_s`：像素速度
- `confidence`：跟踪置信度；`0` 表示该帧没有找到黄色点，位置沿用上一帧

## 实验建议

正式实验建议用手机原生相机录制 `720p 120fps` 或 `1080p 60fps`，然后用 `analyze_video.py` 离线分析。优先高帧率，不优先高分辨率。

黑色摆锤上的黄色标识点要尽量亮、尽量圆，直径最好在画面里达到 `10-20` 像素。背景避免出现黄色物体，摄像头固定并正对摆动平面。
