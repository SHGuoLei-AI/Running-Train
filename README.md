# Running Train PySide6 App

这是一个基于 PySide6 的动态模拟火车运行图应用。主窗口加载 Qt Designer 设计的界面，并在自定义画布中绘制轨道和火车运行点。

## 功能概览

- 绘制铁路轨道
- 绘制并移动火车点
- 支持开始、停止、重置动画
- 显示全局模拟时钟
- 通过 `TrainPath` 组织一条或多条首尾相接的轨道

## 核心模型

### RailwayTrack

`RailwayTrack` 表示一段轨道，包含：

- `id`: 轨道 ID
- `name`: 轨道名称
- `length`: 轨道长度
- `angle`: 轨道角度，单位为度
- `start_point`: 轨道起点坐标
- `end_point()`: 根据起点、长度和角度计算终点坐标

### TrainPath

`TrainPath` 表示列车路径，由一条或多条轨道组成：

- 创建时传入路径起始点坐标
- 使用 `add_track(track)` 逐条添加轨道
- 第一条轨道起点会设为路径起始点
- 后续轨道起点会自动设为上一条轨道的终点

示例：

```python
path = TrainPath((100, 100))
track_a = path.add_track(RailwayTrack("T001", "A段", 500, 45))
track_b = path.add_track(RailwayTrack("T002", "B段", 300, 90))
```

## 安装

1. 确保已安装 Python。
2. 安装依赖：

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## Qt Designer 工作流

界面文件位于 `ui/main_window.ui`。如果修改了 UI，需要重新生成 Python 文件：

```bash
pyside6-uic ui/main_window.ui -o ui/main_window.py
```

业务逻辑建议写在 `main.py` 中，避免直接修改自动生成的 `ui/main_window.py`。

## 项目结构

```text
running_train/
├── main.py
├── requirements.txt
├── README.md
├── QT_DESIGNER_GUIDE.md
└── ui/
    ├── __init__.py
    ├── main_window.ui
    └── main_window.py
```
