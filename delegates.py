from PySide6.QtWidgets import QStyledItemDelegate
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPen, QColor


class RadioDelegate(QStyledItemDelegate):
    """将布尔列绘制为单选框样式（实心/空心圆），交互由 cellClicked 处理。"""
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked
        cx = option.rect.center().x()
        cy = option.rect.center().y()
        r = 5
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx - r, cy - r, 2 * r, 2 * r)
        if checked:
            painter.setBrush(QColor(60, 60, 60))
            painter.drawEllipse(cx - 3, cy - 3, 6, 6)
        painter.restore()
