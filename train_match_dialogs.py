"""Dialogs for train-route matching inspection."""
import os
import re
import locale
import sqlite3

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QDialogButtonBox,
    QHeaderView, QAbstractItemView, QWidget, QTextEdit,
)
from PySide6.QtCore import Qt
import config

try:
    locale.setlocale(locale.LC_COLLATE, 'chs')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CC_PATH = os.path.join(BASE_DIR, 'data', 'cc.db')


def _get_rg_path():
    return config.get_rg_path()

def _get_rt_path():
    return config.get_rt_path()




# ═══════════════════════════════════════════════════════════════════
# TrainDetailPopup — shared train detail dialog
# ═══════════════════════════════════════════════════════════════════
class TrainDetailPopup(QDialog):
    """Show train stops and matched route segments for one train."""

    def __init__(self, train_name, parent=None):
        super().__init__(parent)
        self._train_name = train_name
        self.setWindowTitle(f"车次详情 - {train_name}")
        self.resize(700, 550)
        self.setMinimumSize(550, 400)

        self._db = sqlite3.connect(_get_rt_path())
        self._llt = sqlite3.connect(CC_PATH)

        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        self.header_label = QLabel(self._train_name)
        self.header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.header_label)

        # Stops table
        layout.addWidget(QLabel("停站表"))
        self.stops_table = QTableWidget()
        self.stops_table.setColumnCount(6)
        self.stops_table.setHorizontalHeaderLabels(["序号", "站名", "当前车次", "到达", "出发", "里程km"])
        self.stops_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stops_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.stops_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stops_table.verticalHeader().setVisible(False)
        self.stops_table.horizontalHeader().setStretchLastSection(True)
        self.stops_table.setColumnWidth(0, 40)
        self.stops_table.setColumnWidth(1, 100)
        self.stops_table.setColumnWidth(2, 80)
        self.stops_table.setColumnWidth(3, 60)
        self.stops_table.setColumnWidth(4, 60)
        layout.addWidget(self.stops_table, 1)

        # Matches table
        layout.addWidget(QLabel("经由匹配"))
        self.matches_table = QTableWidget()
        self.matches_table.setColumnCount(5)
        self.matches_table.setHorizontalHeaderLabels(
            ["起点站", "终点站", "距离km", "经由", "方向"])
        self.matches_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.matches_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.matches_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.matches_table.verticalHeader().setVisible(False)
        self.matches_table.horizontalHeader().setStretchLastSection(True)
        self.matches_table.setColumnWidth(0, 100)
        self.matches_table.setColumnWidth(1, 100)
        self.matches_table.setColumnWidth(2, 60)
        self.matches_table.setColumnWidth(3, 160)
        layout.addWidget(self.matches_table, 1)

        # Close button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)

    def _load_data(self):
        name = self._train_name

        # Header from region_trains
        rt_info = self._db.execute(
            'SELECT from_station, to_station FROM region_trains WHERE train_name=?',
            (name,)).fetchone()
        if rt_info:
            self.header_label.setText(f"{name}  ({rt_info[0]} — {rt_info[1]})")
        else:
            self.header_label.setText(name)

        # Stops from llt_schedule
        ti_row = self._llt.execute(
            'SELECT train_index FROM trains WHERE train_name=?', (name,)).fetchone()
        if ti_row:
            ti = ti_row[0]
            stops = self._llt.execute(
                'SELECT stop_seq, station_name, segment_train_no, arrive_time, depart_time, distance_km '
                'FROM train_stops WHERE train_index=? ORDER BY stop_seq', (ti,)).fetchall()
        else:
            stops = []

        self.stops_table.setRowCount(len(stops))
        for row, s in enumerate(stops):
            for col, val in enumerate(s):
                item = QTableWidgetItem(str(val) if val is not None else '')
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if col in (0, 2, 5)
                                      else Qt.AlignmentFlag.AlignLeft)
                self.stops_table.setItem(row, col, item)

        # Matches from train_route_matches
        segs = self._db.execute(
            'SELECT seg_start_station, seg_end_station, seg_distance_km, '
            '       route_name, match_type, is_reverse '
            'FROM train_route_matches WHERE train_name=? '
            'ORDER BY seg_start_seq', (name,)).fetchall()

        self.matches_table.setRowCount(len(segs))
        for row, s in enumerate(segs):
            # start station
            self.matches_table.setItem(row, 0,
                QTableWidgetItem(s[0] if s[0] else ''))
            # end station
            self.matches_table.setItem(row, 1,
                QTableWidgetItem(s[1] if s[1] else ''))
            # distance
            dist_item = QTableWidgetItem(f"{s[2]:.0f}" if s[2] is not None else '')
            dist_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.matches_table.setItem(row, 2, dist_item)
            # route name
            route_item = QTableWidgetItem(s[3] if s[3] else '')
            self.matches_table.setItem(row, 3, route_item)
            # direction
            dir_text = '↩' if s[5] else ''
            if s[4] == 'unmatched':
                dir_text = '未匹配'
            dir_item = QTableWidgetItem(dir_text)
            dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.matches_table.setItem(row, 4, dir_item)

            # Grey out unmatched rows
            if s[4] == 'unmatched':
                for col in range(5):
                    item = self.matches_table.item(row, col)
                    if item:
                        item.setForeground(Qt.GlobalColor.gray)

    def closeEvent(self, event):
        self._db.close()
        self._llt.close()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════
# RouteMatchTrainsDialog — "经由匹配的车次"
# ═══════════════════════════════════════════════════════════════════
class RouteMatchTrainsDialog(QDialog):
    """Left: route list. Right: matched trains for selected route."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("经由匹配的车次")
        self.resize(1000, 600)
        self.setMinimumSize(800, 450)

        self._rg = sqlite3.connect(_get_rg_path())
        self._rt = sqlite3.connect(_get_rt_path())

        self._setup_ui()
        self._load_routes()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── Left: route list ──────────────────────────────────
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.route_table = QTableWidget()
        self.route_table.setColumnCount(6)
        self.route_table.setHorizontalHeaderLabels(
            ["ID", "名称", "起点", "终点", "距离", "车次数"])
        self.route_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.route_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.route_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.route_table.verticalHeader().setVisible(False)
        self.route_table.setColumnWidth(0, 36)
        self.route_table.setColumnWidth(1, 180)
        self.route_table.setColumnWidth(2, 80)
        self.route_table.setColumnWidth(3, 80)
        self.route_table.setColumnWidth(4, 50)
        self.route_table.setColumnWidth(5, 60)
        self.route_table.horizontalHeader().setStretchLastSection(False)
        self.route_table.itemSelectionChanged.connect(self._on_route_selected)
        left_layout.addWidget(self.route_table)

        # ── Right: matched trains ─────────────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.train_table = QTableWidget()
        self.train_table.setColumnCount(3)
        self.train_table.setHorizontalHeaderLabels(
            ["车次", "区段", "匹配区段"])
        self.train_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.train_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.train_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.train_table.verticalHeader().setVisible(False)
        self.train_table.setColumnWidth(0, 120)
        self.train_table.setColumnWidth(1, 180)
        self.train_table.horizontalHeader().setStretchLastSection(True)
        self.train_table.cellDoubleClicked.connect(self._on_train_double_clicked)
        right_layout.addWidget(self.train_table)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 5)
        layout.addWidget(splitter)

        # Close button
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        layout.addWidget(btn_box)

    def _load_routes(self):
        # Routes from rg.db, match counts from rt.db
        routes = self._rg.execute(
            'SELECT id, name, start_station, end_station, total_distance '
            'FROM routes ORDER BY id').fetchall()
        match_counts = {}
        for row in self._rt.execute(
            'SELECT route_id, COUNT(DISTINCT train_name) '
            'FROM train_route_matches WHERE is_matched=1 GROUP BY route_id').fetchall():
            match_counts[row[0]] = row[1]

        self._routes = [(r[0], r[1], r[2], r[3], r[4], match_counts.get(r[0], 0)) for r in routes]
        self.route_table.setRowCount(len(self._routes))
        for row, r in enumerate(self._routes):
            rid, name, ss, es, dist, cnt = r
            for col, val in enumerate([
                str(rid), name, ss, es, f"{dist:.0f}" if dist else '', str(cnt)
            ]):
                item = QTableWidgetItem(val)
                if col in (0, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.route_table.setItem(row, col, item)

    def _on_route_selected(self):
        rows = self.route_table.selectionModel().selectedRows()
        if not rows:
            self.train_table.setRowCount(0)
            return
        route_id = self._routes[rows[0].row()][0]

        trains = self._rt.execute(
            '''SELECT trm.train_name,
                      rt.from_station || '-' || rt.to_station,
                      GROUP_CONCAT(
                          CASE WHEN trm.is_matched
                          THEN trm.seg_start_station || '-' || trm.seg_end_station
                              || ' ' || CAST(ROUND(trm.seg_distance_km) AS INT) || 'km R' || trm.route_id
                          ELSE trm.seg_start_station || '-' || trm.seg_end_station
                              || ' ' || CAST(ROUND(trm.seg_distance_km) AS INT) || 'km未匹配'
                          END, '; ')
               FROM train_route_matches trm
               LEFT JOIN region_trains rt ON trm.train_name = rt.train_name
               WHERE trm.route_id = ?
               GROUP BY trm.train_name
               ORDER BY trm.train_name''', (route_id,)).fetchall()

        self.train_table.setRowCount(len(trains))
        for row, t in enumerate(trains):
            self.train_table.setItem(row, 0, QTableWidgetItem(t[0]))
            self.train_table.setItem(row, 1, QTableWidgetItem(t[1] or ''))
            self.train_table.setItem(row, 2, QTableWidgetItem(t[2] or ''))

    def _on_train_double_clicked(self, row, col):
        item = self.train_table.item(row, 0)
        if not item:
            return
        train_name = item.text().strip()
        if train_name:
            dlg = TrainDetailPopup(train_name, self)
            dlg.exec()

    def closeEvent(self, event):
        self._rg.close()
        self._rt.close()
        super().closeEvent(event)


# ═══════════════════════════════════════════════════════════════════
# TrainMatchRoutesDialog — "车次匹配的经由"
# ═══════════════════════════════════════════════════════════════════
class TrainMatchRoutesDialog(QDialog):
    """车次列表：查看匹配结果、清洗非数字结尾车次。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("车次列表")
        self.resize(950, 550)
        self.setMinimumSize(600, 400)

        self._rg = sqlite3.connect(_get_rg_path())
        self._rt = sqlite3.connect(_get_rt_path())

        self._setup_ui()
        self._load_from_db()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Title
        title = QLabel("经由匹配结果")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["车次", "区段", "经由匹配"])
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 180)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.cellDoubleClicked.connect(self._on_train_double_clicked)
        layout.addWidget(self.table, 1)

        # Status bar
        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        # Bottom row: toggle + clean + close
        bottom_row = QHBoxLayout()
        self.btn_toggle_zero = QPushButton("只显示0匹配")
        self.btn_toggle_zero.setCheckable(True)
        self.btn_toggle_zero.clicked.connect(self._on_toggle_zero_match)
        bottom_row.addWidget(self.btn_toggle_zero)
        self.btn_in_graph = QPushButton("图内未匹配区段")
        self.btn_in_graph.clicked.connect(self._on_show_in_graph_unmatched)
        bottom_row.addWidget(self.btn_in_graph)
        self.btn_clean_trains = QPushButton("清洗车次")
        self.btn_clean_trains.setToolTip("删除所有不以数字结尾的车次")
        self.btn_clean_trains.clicked.connect(self._on_clean_trains)
        bottom_row.addWidget(self.btn_clean_trains)
        bottom_row.addStretch()
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.close)
        bottom_row.addWidget(btn_box)
        layout.addLayout(bottom_row)

    def _on_clean_trains(self):
        """删除所有不以数字结尾的车次。"""
        from PySide6.QtWidgets import QMessageBox

        all_trains = self._rt.execute(
            'SELECT train_name FROM region_trains').fetchall()
        to_delete = [t[0] for t in all_trains if not re.search(r'\d$', t[0])]

        if not to_delete:
            QMessageBox.information(self, "清洗车次", "没有需要清洗的车次。")
            return

        reply = QMessageBox.question(
            self, "确认清洗",
            f"将删除 {len(to_delete)} 个非数字结尾的车次：\n\n"
            + '、'.join(to_delete[:20])
            + (f'\n... 等共 {len(to_delete)} 个' if len(to_delete) > 20 else ''),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_stops = 0
        deleted_matches = 0
        for name in to_delete:
            c = self._rt.execute(
                'SELECT COUNT(*) FROM train_stops WHERE train_name=?',
                (name,)).fetchone()
            deleted_stops += c[0] if c else 0
            m = self._rt.execute(
                'SELECT COUNT(*) FROM train_route_matches WHERE train_name=?',
                (name,)).fetchone()
            deleted_matches += m[0] if m else 0

            self._rt.execute(
                'DELETE FROM train_route_matches WHERE train_name=?', (name,))
            self._rt.execute(
                'DELETE FROM train_stops WHERE train_name=?', (name,))
            self._rt.execute(
                'DELETE FROM region_trains WHERE train_name=?', (name,))

        self._rt.commit()

        QMessageBox.information(
            self, "清洗完成",
            f"已删除 {len(to_delete)} 个车次\n"
            f"（含 {deleted_stops} 条停站记录，{deleted_matches} 条匹配记录）。")

        self._load_from_db()

    def _load_from_db(self):
        """Read match results from train_route_matches table."""
        records = self._rt.execute(
            '''SELECT trm.train_name,
                      rt.from_station || '-' || rt.to_station,
                      trm.seg_start_station, trm.seg_end_station,
                      ROUND(trm.seg_distance_km), trm.route_id,
                      trm.route_name, trm.is_reverse, trm.is_matched
               FROM train_route_matches trm
               LEFT JOIN region_trains rt ON trm.train_name = rt.train_name
               ORDER BY trm.train_name, trm.seg_start_seq''').fetchall()

        if not records:
            self.status_label.setText("匹配表为空，请先在经由编辑器中执行“经由↔️车次匹配”。")
            return

        # Group by train_name
        from collections import OrderedDict
        groups = OrderedDict()
        for r in records:
            name = r[0]
            if name not in groups:
                groups[name] = {'origin': r[1] or '', 'segs': []}
            seg_start, seg_end = r[2], r[3]
            dist, rid, rname, is_rev, is_matched = r[4], r[5], r[6], r[7], r[8]
            if is_matched:
                rev = '↩' if is_rev else ''
                if rname:
                    # 拼接路由（如R11+R9）直接显示route_name
                    seg = f'[{seg_start}-{seg_end} {dist:.0f}km {rname}{rev}]'
                else:
                    seg = f'[{seg_start}-{seg_end} {dist:.0f}km R{rid}{rev}]'
            else:
                seg = f'[{seg_start}-{seg_end} {dist:.0f}km未匹配]'
            groups[name]['segs'].append(seg)

        rows = []
        for name, data in groups.items():
            rows.append([name, data['origin'], ' '.join(data['segs'])])

        self._all_rows = rows

        # Stats
        matched_all = sum(1 for r in rows if '未匹配' not in r[2])
        matched_partial = sum(1 for r in rows if '未匹配' in r[2] and 'R' in r[2])
        unmatched_all = sum(1 for r in rows if 'R' not in r[2])

        self._stats = (matched_all, matched_partial, unmatched_all)
        self._show_rows(rows)

    def _show_rows(self, rows):
        """Populate table with given rows."""
        matched_all = sum(1 for r in rows if '未匹配' not in r[2])
        matched_partial = sum(1 for r in rows if '未匹配' in r[2] and 'R' in r[2])
        unmatched_all = sum(1 for r in rows if 'R' not in r[2])

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            for col, val in enumerate(r):
                self.table.setItem(row_idx, col, QTableWidgetItem(str(val)))
        self.table.setSortingEnabled(True)

        self.status_label.setText(
            f"共 {len(rows)} 条记录  |  "
            f"全匹配: {matched_all}  /  部分: {matched_partial}  /  零匹配: {unmatched_all}"
        )

    def _on_toggle_zero_match(self, checked):
        """Toggle between all rows and zero-match only."""
        if checked:
            self.btn_toggle_zero.setText("显示全部")
            rows = [r for r in self._all_rows if 'R' not in r[2]]
        else:
            self.btn_toggle_zero.setText("只显示0匹配")
            rows = self._all_rows
        self._show_rows(rows)

    def _on_show_in_graph_unmatched(self):
        """Show popup with unmatched segments whose both ends are in graph."""
        graph_stations = set()
        for row in self._rg.execute(
            'SELECT head_station, tail_station FROM railway_track').fetchall():
            graph_stations.add(row[0])
            graph_stations.add(row[1])

        segs = self._rt.execute(
            '''SELECT trm.train_name,
                      rt.from_station || '-' || rt.to_station,
                      trm.seg_start_station, trm.seg_end_station,
                      ROUND(trm.seg_distance_km)
               FROM train_route_matches trm
               LEFT JOIN region_trains rt ON trm.train_name = rt.train_name
               WHERE trm.is_matched = 0
               ORDER BY trm.train_name, trm.seg_start_seq''').fetchall()

        in_graph = [(name, od, ss, es, dist) for name, od, ss, es, dist in segs
                    if ss in graph_stations and es in graph_stations]

        dlg = QDialog(self)
        dlg.setWindowTitle("图内未匹配区段")
        dlg.resize(500, 420)
        layout = QVBoxLayout(dlg)
        text = QTextEdit()
        text.setReadOnly(True)
        layout.addWidget(text)

        if in_graph:
            text.append(f"共 {len(in_graph)} 个区段（两端都在图内但未匹配）：\n")
            for name, od, ss, es, dist in in_graph:
                text.append(f"  {name} ({od}): [{ss}-{es} {dist:.0f}km未匹配]")
        else:
            text.append("✅ 无图内未匹配区段！")

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(dlg.close)
        layout.addWidget(btn_box)
        dlg.exec()

    def _on_train_double_clicked(self, row, col):
        item = self.table.item(row, 0)
        if not item:
            return
        train_name = item.text().strip()
        if train_name:
            dlg = TrainDetailPopup(train_name, self)
            dlg.exec()

    def closeEvent(self, event):
        self._rg.close()
        self._rt.close()
        super().closeEvent(event)
