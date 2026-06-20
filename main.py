import sys
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from main_window import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # 设默认字体，消 QFont warning
    font = QFont()
    font.setPixelSize(12)
    app.setFont(font)
    window = MainWindow()
    window.showMaximized()
    window.init_splitter_sizes()
    sys.exit(app.exec())
