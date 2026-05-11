# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'main_window.ui'
##
## Created by: Qt User Interface Compiler version 6.11.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMenu, QMenuBar, QPushButton,
    QSizePolicy, QStatusBar, QTextEdit, QVBoxLayout,
    QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(1517, 1039)
        self.action_exit = QAction(MainWindow)
        self.action_exit.setObjectName(u"action_exit")
        self.action_about = QAction(MainWindow)
        self.action_about.setObjectName(u"action_about")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout = QVBoxLayout(self.centralwidget)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.title_label = QLabel(self.centralwidget)
        self.title_label.setObjectName(u"title_label")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.title_label)

        self.input_field = QLineEdit(self.centralwidget)
        self.input_field.setObjectName(u"input_field")

        self.verticalLayout.addWidget(self.input_field)

        self.control_layout = QHBoxLayout()
        self.control_layout.setObjectName(u"control_layout")
        self.button_layout = QHBoxLayout()
        self.button_layout.setObjectName(u"button_layout")
        self.start_button = QPushButton(self.centralwidget)
        self.start_button.setObjectName(u"start_button")

        self.button_layout.addWidget(self.start_button)

        self.stop_button = QPushButton(self.centralwidget)
        self.stop_button.setObjectName(u"stop_button")

        self.button_layout.addWidget(self.stop_button)

        self.reset_button = QPushButton(self.centralwidget)
        self.reset_button.setObjectName(u"reset_button")

        self.button_layout.addWidget(self.reset_button)


        self.control_layout.addLayout(self.button_layout)

        self.output_text = QTextEdit(self.centralwidget)
        self.output_text.setObjectName(u"output_text")
        self.output_text.setMaximumHeight(30)
        self.output_text.setReadOnly(True)

        self.control_layout.addWidget(self.output_text)


        self.verticalLayout.addLayout(self.control_layout)

        self.canvas_widget = QWidget(self.centralwidget)
        self.canvas_widget.setObjectName(u"canvas_widget")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.canvas_widget.sizePolicy().hasHeightForWidth())
        self.canvas_widget.setSizePolicy(sizePolicy)

        self.verticalLayout.addWidget(self.canvas_widget)

        self.statusbar = QStatusBar(self.centralwidget)
        self.statusbar.setObjectName(u"statusbar")

        self.verticalLayout.addWidget(self.statusbar)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menubar = QMenuBar(MainWindow)
        self.menubar.setObjectName(u"menubar")
        self.menubar.setGeometry(QRect(0, 0, 1517, 33))
        self.menu_file = QMenu(self.menubar)
        self.menu_file.setObjectName(u"menu_file")
        self.menu_help = QMenu(self.menubar)
        self.menu_help.setObjectName(u"menu_help")
        MainWindow.setMenuBar(self.menubar)

        self.menubar.addAction(self.menu_file.menuAction())
        self.menubar.addAction(self.menu_help.menuAction())
        self.menu_file.addAction(self.action_exit)
        self.menu_help.addAction(self.action_about)

        self.retranslateUi(MainWindow)

        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"Running Train Application", None))
        self.action_exit.setText(QCoreApplication.translate("MainWindow", u"\u9000\u51fa", None))
        self.action_about.setText(QCoreApplication.translate("MainWindow", u"\u5173\u4e8e", None))
        self.title_label.setStyleSheet(QCoreApplication.translate("MainWindow", u"font-size: 24px; font-weight: bold;", None))
        self.title_label.setText(QCoreApplication.translate("MainWindow", u"\u6b22\u8fce\u4f7f\u7528\u52a8\u6001\u6a21\u62df\u706b\u8f66\u8fd0\u884c\u56fe", None))
        self.input_field.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u8bf7\u8f93\u5165\u5185\u5bb9...", None))
        self.start_button.setText(QCoreApplication.translate("MainWindow", u"\u5f00\u59cb", None))
        self.stop_button.setText(QCoreApplication.translate("MainWindow", u"\u505c\u6b62", None))
        self.reset_button.setText(QCoreApplication.translate("MainWindow", u"\u91cd\u7f6e", None))
        self.output_text.setPlaceholderText(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u4fe1\u606f\u4f1a\u663e\u793a\u5728\u6b64...", None))
        self.canvas_widget.setStyleSheet(QCoreApplication.translate("MainWindow", u"background-color: white; border: 1px solid black;", None))
        self.menu_file.setTitle(QCoreApplication.translate("MainWindow", u"\u6587\u4ef6(&F)", None))
        self.menu_help.setTitle(QCoreApplication.translate("MainWindow", u"\u5e2e\u52a9(&H)", None))
    # retranslateUi

