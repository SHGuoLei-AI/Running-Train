"""列车模拟控制面板 — 左侧窄面板"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                                QLabel, QPushButton, QComboBox)
from PySide6.QtCore import Qt, Signal


class SimulationControlPanel(QWidget):
    """控制面板：100px 宽，左侧面板"""

    start_clicked = Signal()
    pause_clicked = Signal()
    hour_clicked = Signal(int)     # 0-23
    speed_changed = Signal(float)
    step_minute = Signal(int)      # -10, -1, +1, +10

    SPEEDS = [0.5, 1.0, 2.0, 4.0, 8.0]
    SPEED_LABELS = ["½×", "1×", "2×", "4×", "8×"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(100)
        self._running = False
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 4, 2, 4)
        layout.setSpacing(4)

        # — 上半：3 行 × 4 列（0-11）—
        top_grid = QGridLayout()
        top_grid.setSpacing(1)
        for h in range(12):
            btn = QPushButton(f"{h:02d}")
            btn.setFixedSize(23, 18)
            btn.setStyleSheet("font-size: 8px; padding: 0px;")
            row = h // 4
            col = h % 4
            top_grid.addWidget(btn, row, col)
            self.__dict__[f'_btn_{h}'] = btn
        layout.addLayout(top_grid)

        # — 时钟 —
        self.clock_label = QLabel("00:00")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self.clock_label)

        # — 下半：3 行 × 4 列（12-23）—
        bot_grid = QGridLayout()
        bot_grid.setSpacing(1)
        for h in range(12, 24):
            btn = QPushButton(f"{h:02d}")
            btn.setFixedSize(23, 18)
            btn.setStyleSheet("font-size: 8px; padding: 0px;")
            row = (h - 12) // 4
            col = (h - 12) % 4
            bot_grid.addWidget(btn, row, col)
            self.__dict__[f'_btn_{h}'] = btn
        layout.addLayout(bot_grid)

        # — 步进按钮：快退10 / 后退1 / 前进1 / 快进10 —
        step_row = QHBoxLayout()
        step_row.setSpacing(2)

        self.step_back_10_btn = QPushButton("⏪10")
        self.step_back_10_btn.setFixedHeight(20)
        self.step_back_10_btn.setStyleSheet("font-size: 8px; padding: 1px;")
        step_row.addWidget(self.step_back_10_btn)

        self.step_back_1_btn = QPushButton("◀1")
        self.step_back_1_btn.setFixedHeight(20)
        self.step_back_1_btn.setStyleSheet("font-size: 8px; padding: 1px;")
        step_row.addWidget(self.step_back_1_btn)

        self.step_fwd_1_btn = QPushButton("1▶")
        self.step_fwd_1_btn.setFixedHeight(20)
        self.step_fwd_1_btn.setStyleSheet("font-size: 8px; padding: 1px;")
        step_row.addWidget(self.step_fwd_1_btn)

        self.step_fwd_10_btn = QPushButton("10⏩")
        self.step_fwd_10_btn.setFixedHeight(20)
        self.step_fwd_10_btn.setStyleSheet("font-size: 8px; padding: 1px;")
        step_row.addWidget(self.step_fwd_10_btn)

        layout.addLayout(step_row)

        # — 开始/暂停 + 速度（同一行，各半宽）—
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(2)

        self.toggle_btn = QPushButton("▶")
        self.toggle_btn.setFixedHeight(22)
        self._update_toggle_style()
        ctrl_row.addWidget(self.toggle_btn, stretch=1)

        self.speed_combo = QComboBox()
        self.speed_combo.setEditable(True)
        self.speed_combo.lineEdit().setReadOnly(True)
        self.speed_combo.lineEdit().setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_combo.addItems(self.SPEED_LABELS)
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setFixedHeight(22)
        self.speed_combo.setStyleSheet(
            "QComboBox { font-size: 9px; padding: 0px 2px; color: black; background: white; }"
            "QComboBox QAbstractItemView { font-size: 9px; }"
            "QComboBox::drop-down { width: 12px; }")
        ctrl_row.addWidget(self.speed_combo, stretch=1)
        layout.addLayout(ctrl_row)
        layout.addStretch()

    def _update_toggle_style(self):
        if self._running:
            self.toggle_btn.setText("⏸")
            self.toggle_btn.setStyleSheet(
                "font-size: 11px; padding: 1px; color: #1565C0; font-weight: bold;")
        else:
            self.toggle_btn.setText("▶")
            self.toggle_btn.setStyleSheet(
                "font-size: 14px; padding: 1px; color: #C62828; font-weight: bold;")

    def _connect_signals(self):
        self.toggle_btn.clicked.connect(self._on_toggle)

        for h in range(24):
            btn = self.__dict__[f'_btn_{h}']
            btn.clicked.connect(lambda checked, h=h: self.hour_clicked.emit(h))

        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)

        self.step_back_10_btn.clicked.connect(lambda: self.step_minute.emit(-10))
        self.step_back_1_btn.clicked.connect(lambda: self.step_minute.emit(-1))
        self.step_fwd_1_btn.clicked.connect(lambda: self.step_minute.emit(1))
        self.step_fwd_10_btn.clicked.connect(lambda: self.step_minute.emit(10))

    def _on_toggle(self):
        if self._running:
            self.pause_clicked.emit()
        else:
            self.start_clicked.emit()

    def set_running(self, running: bool):
        """更新按钮状态（由外部时钟状态驱动）"""
        self._running = running
        self._update_toggle_style()

    def _on_speed_changed(self, idx: int):
        if 0 <= idx < len(self.SPEEDS):
            self.speed_changed.emit(self.SPEEDS[idx])

    def update_clock(self, minute: float):
        h = int(minute) // 60 % 24
        m = int(minute) % 60
        self.clock_label.setText(f"{h:02d}:{m:02d}")
