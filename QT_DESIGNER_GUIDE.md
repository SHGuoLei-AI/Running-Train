# Qt Designer 使用指南

## 项目结构

```
running_train/
├── main.py                 # 主程序入口
├── requirements.txt        # 依赖包
├── README.md              # 项目说明
└── ui/
    ├── __init__.py        # UI包
    ├── main_window.ui     # Qt Designer设计文件
    └── main_window.py     # 由pyside6-uic生成的Python代码
```

## 工作流程

### 1. 打开Qt Designer编辑UI

在Windows上打开Qt Designer设计工具编辑 `ui/main_window.ui`：

```bash
pyside6-designer ui/main_window.ui
```

或者在Qt Creator中打开该文件。

### 2. 修改UI后重新生成Python文件

如果在Qt Designer中修改了UI设计，运行以下命令将`.ui`文件转换为Python代码：

```bash
pyside6-uic ui/main_window.ui -o ui/main_window.py
```

### 3. 运行应用

```bash
python main.py
```

## 文件说明

### main_window.ui
- **格式**: XML格式的Qt设计文件
- **用途**: 用Qt Designer图形工具编辑UI布局
- **包含**: 窗口布局、控件、菜单栏等

### main_window.py
- **格式**: 自动生成的Python文件
- **用途**: 定义UI元素的类
- **注意**: 直接编辑此文件可能被覆盖，建议只编辑main.py中的逻辑

### main.py
- **格式**: Python主程序
- **用途**: 
  - 加载UI
  - 实现业务逻辑
  - 连接信号和槽（按钮点击、菜单选择等）

## 当前功能

主窗口包含：

- **菜单栏**: 文件（退出）、帮助（关于）
- **输入框**: 用户输入内容
- **按钮**: 开始、停止、重置
- **输出区**: 显示操作日志
- **状态栏**: 显示当前状态

## 修改UI的步骤

1. 打开Qt Designer:
   ```bash
   pyside6-designer ui/main_window.ui
   ```

2. 在Qt Designer中修改UI（拖放控件、调整布局等）

3. 保存UI文件

4. 重新生成Python代码:
   ```bash
   pyside6-uic ui/main_window.ui -o ui/main_window.py
   ```

5. 在`main.py`中编写事件处理逻辑

## 常见任务

### 添加新按钮

1. 在Qt Designer中添加QPushButton控件
2. 设置其objectName（如"new_button"）
3. 运行pyside6-uic重新生成Python代码
4. 在main.py中连接信号:
   ```python
   self.ui.new_button.clicked.connect(self.on_new_button_clicked)
   ```
5. 实现处理函数

### 修改样式

1. 在Qt Designer中选择控件
2. 在右侧属性面板修改styleSheet
3. 或在Python代码中设置:
   ```python
   self.ui.button.setStyleSheet("background-color: blue; color: white;")
   ```

## 依赖

确保已安装PySide6：

```bash
pip install -r requirements.txt
```
