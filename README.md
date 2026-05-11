# Running Train

基于 PySide6 的铁路运行图编辑工具。从 JSON 文件加载线路数据，在左侧画布绘制轨道，在右侧表格编辑数据，两边实时同步。

## 功能

- 线路图绘制：每条区间渲染三条线段（黑色中线、红色上行线、绿色下行线）及站名标注
- 数据绑定：表格编辑实时反映到画布，支持增删线路和区间、上下移动线路
- 文件读写：打开/保存 JSON 格式的运行图数据
- 单选框样式：布尔列以空心/实心圆展示，点击切换
- 画布缩放：+/- 按钮调整显示比例（1–10），# 恢复默认

## 项目结构

```text
running_train/
├── main.py              # 入口
├── main_window.py       # 主窗口（UI + 交互逻辑）
├── models.py            # 数据模型 + JSON 序列化
├── canvas.py            # 自定义画布（轨道绘制）
├── delegates.py         # 单选框委托（空心/实心圆）
├── requirements.txt
├── README.md
└── data/
    └── 上海周边.json      # 示例数据
```

## 数据模型

```text
TrainGraph
├── name, length, width, scale
└── RailwayPath[]
    ├── id, name, start_point, angle, hidden
    └── RailwayTrack[]
        ├── head_station, tail_station
        ├── length, deflection
        └── draw_head, draw_tail
```

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```
