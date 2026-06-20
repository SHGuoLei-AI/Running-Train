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

    SPEEDS = [0.5, 1.0, 2.0, 4.0, 8.0]
    SPEED_LABELS = ["½×", "1×", "2×", "4×", "8×"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(100)
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

        # — 开始 / 暂停 —
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(2)
        self.start_btn = QPushButton("▶")
        self.start_btn.setFixedHeight(20)
        self.start_btn.setStyleSheet("font-size: 9px; padding: 1px;")
        ctrl_row.addWidget(self.start_btn)

        self.pause_btn = QPushButton("⏸")
        self.pause_btn.setFixedHeight(20)
        self.pause_btn.setStyleSheet("font-size: 9px; padding: 1px;")
        ctrl_row.addWidget(self.pause_btn)
        layout.addLayout(ctrl_row)

        # — 速度 —
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(self.SPEED_LABELS)
        self.speed_combo.setCurrentIndex(1)
        self.speed_combo.setStyleSheet("font-size: 8px; padding: 1px;")
        layout.addWidget(self.speed_combo)

        layout.addStretch()

    def _connect_signals(self):
        self.start_btn.clicked.connect(self.start_clicked.emit)
        self.pause_btn.clicked.connect(self.pause_clicked.emit)

        for h in range(24):
            btn = self.__dict__[f'_btn_{h}']
            btn.clicked.connect(lambda checked, h=h: self.hour_clicked.emit(h))

        self.speed_combo.currentIndexChanged.connect(self._on_speed_changed)

    def _on_speed_changed(self, idx: int):
        if 0 <= idx < len(self.SPEEDS):
            self.speed_changed.emit(self.SPEEDS[idx])

    def update_clock(self, minute: float):
        h = int(minute) // 60 % 24
        m = int(minute) % 60
        self.clock_label.setText(f"{h:02d}:{m:02d}")
