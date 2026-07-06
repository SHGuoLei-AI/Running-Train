"""经由编辑对话框 — 查看/修剪/延伸/新增/删除经由."""
import os
import sqlite3
import locale
locale.setlocale(locale.LC_COLLATE, 'chs')  # pinyin sort for Chinese
from pypinyin import pinyin, Style as PinyinStyle
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QMessageBox, QDialogButtonBox,
    QListWidget, QListWidgetItem, QAbstractItemView, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
import config

KL_PATH = os.path.join(os.path.dirname(__file__), 'data', 'kl.db')


def _jump_to_letter(line_list, target_letter):
    """Scroll line_list to the first item whose pinyin first letter matches target_letter."""
    for i in range(line_list.count()):
        item = line_list.item(i)
        py = pinyin(item.text(), style=PinyinStyle.FIRST_LETTER, heteronym=False)
        first = py[0][0].upper() if py else ''
        if first == target_letter:
            line_list.scrollToItem(item, QAbstractItemView.ScrollHint.PositionAtTop)
            line_list.setCurrentItem(item)
            return


def create_line_jump_buttons(line_list):
    """Create a row of pinyin-index buttons that jump to first line starting with each letter group."""
    widget = QWidget()
    row = QHBoxLayout(widget)
    row.setContentsMargins(0, 0, 0, 2)
    row.setSpacing(2)

    groups = [
        ("ABCDE", "A"), ("FGH", "F"), ("JK", "J"), ("LMN", "L"),
        ("PQR", "P"), ("ST", "S"), ("WX", "W"), ("YZ", "Y"),
    ]

    for label, target in groups:
        btn = QPushButton(label)
        btn.setFixedWidth(52)
        btn.setMaximumHeight(22)
        btn.setStyleSheet("font-size: 10px; padding: 1px 3px;")
        btn.clicked.connect(lambda checked, t=target, ll=line_list: _jump_to_letter(ll, t))
        row.addWidget(btn)

    row.addStretch()
    return widget


def _get_rg_path():
    return config.get_rg_path()

def _get_rt_path():
    return config.get_rt_path()


class RouteEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("经由编辑")
        self.resize(1000, 600)
        self.setMinimumSize(800, 450)

        self._db = sqlite3.connect(_get_rg_path())
        self._kl = sqlite3.connect(KL_PATH)
        self._routes = []  # list of (id, name, start, end, total_km)
        self._stations = {}  # route_id -> list of (seq, station, line, cum_km, is_junction)

        self._setup_ui()
        self._load_routes()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # --- Top label ---
        layout.addWidget(QLabel("经由列表（来源: rg.db）"))

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # === Left: route list ===
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left_widget = QWidget()
        left_widget.setLayout(left)

        self.route_table = QTableWidget()
        self.route_table.setColumnCount(7)
        self.route_table.setHorizontalHeaderLabels(["ID", "名称", "起点", "终点", "总里程", "禁止高速", "禁止普速"])
        self.route_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.route_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        # Allow editing via double-click / F2 — only name column will be editable per-item
        self.route_table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked |
            QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.route_table.verticalHeader().setVisible(False)
        self.route_table.setColumnWidth(0, 36)
        self.route_table.setColumnWidth(1, 200)
        self.route_table.setColumnWidth(2, 80)
        self.route_table.setColumnWidth(3, 80)
        self.route_table.setColumnWidth(4, 56)
        self.route_table.setColumnWidth(5, 56)
        self.route_table.setColumnWidth(6, 56)
        self.route_table.itemSelectionChanged.connect(self._on_route_selected)
        self.route_table.itemChanged.connect(self._on_route_item_changed)
        self.route_table.cellClicked.connect(self._on_route_cell_clicked)
        left.addWidget(self.route_table)

        # Left button row: add / delete route
        left_btns = QHBoxLayout()
        self.btn_add_route = QPushButton("新增经由...")
        self.btn_add_route.clicked.connect(self._on_add_route)
        self.btn_delete_route = QPushButton("删除经由")
        self.btn_delete_route.clicked.connect(self._on_delete_route)
        left_btns.addWidget(self.btn_add_route)
        left_btns.addWidget(self.btn_delete_route)
        left_btns.addStretch()
        left.addLayout(left_btns)

        splitter.addWidget(left_widget)

        # === Right: station detail ===
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right_widget = QWidget()
        right_widget.setLayout(right)

        self.station_label = QLabel("选择一个经由查看站序")
        self.station_label.setStyleSheet("font-weight: bold;")
        right.addWidget(self.station_label)

        self.station_table = QTableWidget()
        self.station_table.setColumnCount(5)
        self.station_table.setHorizontalHeaderLabels(["序", "站名", "线路", "累计里程", "接续"])
        self.station_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.station_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.station_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.station_table.verticalHeader().setVisible(False)
        self.station_table.setColumnWidth(0, 32)
        self.station_table.setColumnWidth(1, 100)
        self.station_table.setColumnWidth(2, 150)
        self.station_table.setColumnWidth(3, 72)
        self.station_table.setColumnWidth(4, 44)
        right.addWidget(self.station_table, stretch=1)

        # Buttons row
        btn_row = QHBoxLayout()
        self.btn_del_head = QPushButton("删除头部...")
        self.btn_del_head.clicked.connect(self._on_delete_head_section)
        self.btn_del_tail = QPushButton("删除尾部...")
        self.btn_del_tail.clicked.connect(self._on_delete_tail_section)
        self.btn_extend_head = QPushButton("头部延伸...")
        self.btn_extend_head.clicked.connect(self._on_extend_head)
        self.btn_extend_tail = QPushButton("尾部延伸...")
        self.btn_extend_tail.clicked.connect(self._on_extend_tail)

        btn_row.addWidget(self.btn_del_head)
        btn_row.addWidget(self.btn_extend_head)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_extend_tail)
        btn_row.addWidget(self.btn_del_tail)
        right.addLayout(btn_row)

        splitter.addWidget(right_widget)

        # 60:40 ratio
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)

        layout.addWidget(splitter, stretch=1)

        # Bottom row: match button + close
        bottom_row = QHBoxLayout()
        self.btn_match_trains = QPushButton("经由↔️车次匹配")
        self.btn_match_trains.clicked.connect(self._on_match_trains)
        bottom_row.addWidget(self.btn_match_trains)
        bottom_row.addStretch()
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.close)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        # Disable buttons until selection
        self._update_button_state()

    # ── Data loading ─────────────────────────────────────

    def _load_routes(self):
        self._routes = self._db.execute(
            'SELECT id, name, start_station, end_station, total_distance, prohibit_high_speed, prohibit_normal_speed FROM routes ORDER BY id'
        ).fetchall()

        self._stations = {}
        for r in self._routes:
            rid = r[0]
            sts = self._db.execute(
                'SELECT seq, station_name, line_name, cum_distance, is_junction '
                'FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)
            ).fetchall()
            self._stations[rid] = sts

        self._refresh_route_table()

    def _refresh_route_table(self):
        """Rebuild route table from self._routes. Block signals to avoid itemChanged loops."""
        self.route_table.blockSignals(True)
        self.route_table.setRowCount(len(self._routes))
        for i, r in enumerate(self._routes):
            # ID — not editable
            id_item = QTableWidgetItem(str(r[0]))
            id_item.setFlags(id_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.route_table.setItem(i, 0, id_item)

            # Name — editable
            name_item = QTableWidgetItem(r[1])
            self.route_table.setItem(i, 1, name_item)

            # Start — not editable
            start_item = QTableWidgetItem(r[2])
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.route_table.setItem(i, 2, start_item)

            # End — not editable
            end_item = QTableWidgetItem(r[3])
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.route_table.setItem(i, 3, end_item)

            # Total — not editable
            total_item = QTableWidgetItem(f"{r[4]:.0f}")
            total_item.setFlags(total_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.route_table.setItem(i, 4, total_item)

            # 禁止高速 — checkbox
            high_item = QTableWidgetItem()
            high_item.setFlags(high_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # handled by cell click
            high_item.setCheckState(Qt.CheckState.Checked if r[5] else Qt.CheckState.Unchecked)
            self.route_table.setItem(i, 5, high_item)

            # 禁止普速 — checkbox
            normal_item = QTableWidgetItem()
            normal_item.setFlags(normal_item.flags() & ~Qt.ItemFlag.ItemIsEditable)  # handled by cell click
            normal_item.setCheckState(Qt.CheckState.Checked if r[6] else Qt.CheckState.Unchecked)
            self.route_table.setItem(i, 6, normal_item)
        self.route_table.blockSignals(False)

    # ── Route table edit (name only) ────────────────────

    def _on_route_item_changed(self, item):
        """Handle edits to the route table (only name column is editable)."""
        if item.column() != 1:
            return
        row = item.row()
        if row < 0 or row >= len(self._routes):
            return
        rid = self._routes[row][0]
        new_name = item.text().strip()
        if new_name:
            self._db.execute('UPDATE routes SET name=? WHERE id=?', (new_name, rid))
            self._db.commit()
            # Update local cache
            r = list(self._routes[row])
            r[1] = new_name
            self._routes[row] = tuple(r)

    def _on_route_cell_clicked(self, row, col):
        """Handle checkbox toggles for columns 5 (禁止高速) and 6 (禁止普速)."""
        if col not in (5, 6):
            return
        if row < 0 or row >= len(self._routes):
            return
        rid = self._routes[row][0]
        item = self.route_table.item(row, col)
        if item is None:
            return
        new_val = 1 if item.checkState() == Qt.CheckState.Checked else 0
        col_name = 'prohibit_high_speed' if col == 5 else 'prohibit_normal_speed'
        self._db.execute(f'UPDATE routes SET {col_name}=? WHERE id=?', (new_val, rid))
        self._db.commit()
        # Update local cache
        r = list(self._routes[row])
        r[col] = new_val
        self._routes[row] = tuple(r)

    # ── Route selection ─────────────────────────────────

    def _on_route_selected(self):
        rows = self.route_table.selectionModel().selectedRows()
        if not rows:
            self._update_button_state()
            return
        rid = self._routes[rows[0].row()][0]
        self._show_stations(rid)
        self._update_button_state()

    def _show_stations(self, rid):
        sts = self._stations.get(rid, [])
        self.station_table.setRowCount(len(sts))

        # Alternate text color per distinct line segment: black → dark blue → black → ...
        colors = [QColor(0, 0, 0), QColor(0, 0, 139)]
        color_idx = 0
        prev_line = None

        for i, s in enumerate(sts):
            line = s[2]
            if prev_line is not None and line != prev_line:
                color_idx = 1 - color_idx  # toggle 0↔1
            color = colors[color_idx]

            seq_item = QTableWidgetItem(str(s[0]))
            seq_item.setFlags(seq_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            seq_item.setForeground(color)
            self.station_table.setItem(i, 0, seq_item)

            name_item = QTableWidgetItem(s[1])
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setForeground(color)
            self.station_table.setItem(i, 1, name_item)

            line_item = QTableWidgetItem(line)
            line_item.setFlags(line_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            line_item.setForeground(color)
            self.station_table.setItem(i, 2, line_item)

            cum_item = QTableWidgetItem(f"{s[3]:.0f}")
            cum_item.setFlags(cum_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            cum_item.setForeground(color)
            self.station_table.setItem(i, 3, cum_item)

            junc_item = QTableWidgetItem("是" if s[4] else "")
            junc_item.setFlags(junc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            junc_item.setForeground(color)
            self.station_table.setItem(i, 4, junc_item)

            prev_line = line

    def _selected_route_id(self):
        rows = self.route_table.selectionModel().selectedRows()
        if not rows:
            return None
        return self._routes[rows[0].row()][0]

    def _selected_route_row(self):
        rows = self.route_table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    def _update_button_state(self):
        rid = self._selected_route_id()
        has_sel = rid is not None
        sts = self._stations.get(rid, [])
        n = len(sts)
        self.btn_del_head.setEnabled(has_sel and n >= 2)   # need at least 2 to keep 1
        self.btn_del_tail.setEnabled(has_sel and n >= 2)
        self.btn_extend_head.setEnabled(has_sel and n >= 1)
        self.btn_extend_tail.setEnabled(has_sel and n >= 1)
        self.btn_delete_route.setEnabled(has_sel)

    # ── Logical station grouping (merges junction duplicates) ──

    def _get_logical_stations(self, sts):
        """Return list of (display_label, [seq_numbers]) — one item per DB row.
        Display format: 站名（线路）"""
        logical = []
        for s in sts:
            logical.append((f"{s[1]}（{s[2]}）", [s[0]]))
        return logical

    # ── Delete entire route ──────────────────────────────

    def _on_delete_route(self):
        rid = self._selected_route_id()
        if rid is None:
            return
        rname = self._db.execute('SELECT name FROM routes WHERE id=?', (rid,)).fetchone()
        rname = rname[0] if rname else f"ID={rid}"

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除经由 [{rname}] 及其所有站序数据吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._db.execute('DELETE FROM route_stations WHERE route_id=?', (rid,))
        self._db.execute('DELETE FROM routes WHERE id=?', (rid,))
        self._db.commit()
        self._load_routes()
        self.station_table.setRowCount(0)
        self.station_label.setText("选择一个经由查看站序")
        self._update_button_state()

    # ── Match trains against routes ─────────────────────

    def _on_match_trains(self):
        """Run matching with progress dialog and detailed summary."""
        from tools.match_trains import run_matching_with_progress

        cc_path = os.path.join(os.path.dirname(__file__), 'data', 'cc.db')
        run_matching_with_progress(self, self._db, cc_path, _get_rt_path())

    # ── Add new route ────────────────────────────────────

    def _on_add_route(self):
        """Create a new route by picking a kl line segment (start→end)."""
        result = self._pick_kl_route_segment()
        if result is None:
            return

        line_name, start_stn, end_stn = result

        # Query all stations on this line in order
        all_sts = self._kl.execute(
            "SELECT station_name, dist_from_start FROM line_stations "
            "WHERE line_name=? ORDER BY dist_from_start",
            (line_name,)
        ).fetchall()

        # Find indices of start and end stations
        names = [s[0] for s in all_sts]
        try:
            si = names.index(start_stn)
            ei = names.index(end_stn)
        except ValueError:
            return

        if si > ei:
            si, ei = ei, si  # swap so start <= end

        segment = all_sts[si:ei + 1]

        # Create route
        route_name = f"{line_name}({start_stn}→{end_stn})"
        self._db.execute(
            'INSERT INTO routes (name, start_station, end_station, total_distance, junction_count) '
            'VALUES (?, ?, ?, 0, 0)',
            (route_name, start_stn, end_stn)
        )
        rid = self._db.execute('SELECT last_insert_rowid()').fetchone()[0]

        # Build station list for _recalc_distances
        raw = [(sn, line_name, dist, 0) for sn, dist in segment]
        recalc = self._recalc_distances(raw)
        self._save_stations(rid, recalc)
        self._load_routes()

        # Select the new route
        for i, r in enumerate(self._routes):
            if r[0] == rid:
                self.route_table.selectRow(i)
                break
        self._show_stations(rid)
        self._update_button_state()

    def _pick_kl_route_segment(self):
        """Dialog: pick a kl line, then start & end stations on that line.
        Returns (line_name, start_station, end_station) or None."""
        # Load all lines, sort by pinyin
        lines = self._kl.execute(
            "SELECT DISTINCT line_name FROM line_stations"
        ).fetchall()
        lines = sorted(lines, key=lambda x: locale.strxfrm(x[0]))

        dlg = QDialog(self)
        dlg.setWindowTitle("新增经由 — 选择起讫站")
        dlg.resize(520, 520)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel("选择线路:"))

        line_list = QListWidget()
        for (ln,) in lines:
            QListWidgetItem(ln, line_list)
        layout.addWidget(create_line_jump_buttons(line_list))
        layout.addWidget(line_list)

        # Shared state
        state = {'all_sts': [], '_updating': False}

        def update_stations():
            """Refresh both station lists when line changes."""
            state['all_sts'] = []
            start_list.clear()
            end_list.clear()

            if line_list.currentItem() is None:
                return
            ln = line_list.currentItem().text()
            sts = self._kl.execute(
                "SELECT station_name, dist_from_start FROM line_stations "
                "WHERE line_name=? ORDER BY dist_from_start",
                (ln,)
            ).fetchall()
            state['all_sts'] = sts
            for sn, d in sts:
                item_text = f"{sn}  ({d:.0f}km)"
                QListWidgetItem(item_text, start_list)
                QListWidgetItem(item_text, end_list)

        def on_end_changed(current, previous):
            """Preview distance between start and end stations."""
            if state['_updating']:
                return
            si = start_list.currentRow()
            ei = end_list.currentRow()
            sts = state['all_sts']
            if si >= 0 and ei >= 0 and si < len(sts) and ei < len(sts):
                dist = abs(sts[ei][1] - sts[si][1])
                preview_label.setText(
                    f"经由: {sts[si][0]} → {sts[ei][0]}，里程 {dist:.0f}km"
                )
            else:
                preview_label.setText("")

        def on_start_changed(current, previous):
            on_end_changed(current, previous)

        line_list.currentItemChanged.connect(lambda cur, prev: update_stations())

        layout.addWidget(QLabel("选择起点站:"))

        start_list = QListWidget()
        layout.addWidget(start_list)
        start_list.currentItemChanged.connect(on_start_changed)

        layout.addWidget(QLabel("选择终点站:"))

        end_list = QListWidget()
        layout.addWidget(end_list)
        end_list.currentItemChanged.connect(on_end_changed)

        preview_label = QLabel("")
        preview_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        layout.addWidget(preview_label)

        if line_list.count() > 0:
            line_list.setCurrentRow(0)
            update_stations()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        if (line_list.currentItem() is None or
                start_list.currentItem() is None or
                end_list.currentItem() is None):
            return None

        ln = line_list.currentItem().text()
        start_text = start_list.currentItem().text()
        end_text = end_list.currentItem().text()
        start_sn = start_text.split("  (")[0]
        end_sn = end_text.split("  (")[0]

        return (ln, start_sn, end_sn)

    # ── Delete head section ──────────────────────────────

    def _on_delete_head_section(self):
        rid = self._selected_route_id()
        if rid is None:
            return
        sts = self._stations[rid]
        if len(sts) < 2:
            return  # already handled by button state

        logical = self._get_logical_stations(sts)

        # Cannot delete the last station
        if len(logical) <= 1:
            QMessageBox.information(self, "提示", "至少保留一站，无法删除。")
            return

        cut = self._pick_cut_station(logical, is_head=True)
        if cut is None:
            return

        # Collect seq numbers to delete (one per item, 1:1 with DB)
        seqs_to_delete = []
        for i in range(cut + 1):
            seqs_to_delete.extend(logical[i][1])

        # Delete from DB
        placeholders = ','.join('?' for _ in seqs_to_delete)
        self._db.execute(
            f'DELETE FROM route_stations WHERE route_id=? AND seq IN ({placeholders})',
            (rid, *seqs_to_delete)
        )

        # Get remaining and recalc
        remaining = self._db.execute(
            'SELECT station_name, line_name, cum_distance, is_junction '
            'FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)
        ).fetchall()

        if not remaining:
            # Shouldn't happen — we enforced at least 1 remains
            self._load_routes()
            return

        # Ensure first station is not marked as junction
        remaining = list(remaining)
        remaining[0] = (remaining[0][0], remaining[0][1], remaining[0][2], 0)

        new_sts = self._recalc_distances(remaining)
        self._save_stations(rid, new_sts)
        self._reload_route(rid)

    # ── Delete tail section ──────────────────────────────

    def _on_delete_tail_section(self):
        rid = self._selected_route_id()
        if rid is None:
            return
        sts = self._stations[rid]
        if len(sts) < 2:
            return

        logical = self._get_logical_stations(sts)

        if len(logical) <= 1:
            QMessageBox.information(self, "提示", "至少保留一站，无法删除。")
            return

        cut = self._pick_cut_station(logical, is_head=False)
        if cut is None:
            return

        # Collect seq numbers to delete (one per item, 1:1 with DB)
        seqs_to_delete = []
        for i in range(cut, len(logical)):
            seqs_to_delete.extend(logical[i][1])

        placeholders = ','.join('?' for _ in seqs_to_delete)
        self._db.execute(
            f'DELETE FROM route_stations WHERE route_id=? AND seq IN ({placeholders})',
            (rid, *seqs_to_delete)
        )

        remaining = self._db.execute(
            'SELECT station_name, line_name, cum_distance, is_junction '
            'FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)
        ).fetchall()

        if not remaining:
            self._load_routes()
            return

        remaining = list(remaining)
        # Ensure last station is not marked as junction
        remaining[-1] = (remaining[-1][0], remaining[-1][1], remaining[-1][2], 0)

        new_sts = self._recalc_distances(remaining)
        self._save_stations(rid, new_sts)
        self._reload_route(rid)

    def _pick_cut_station(self, logical, is_head):
        """Show dialog to pick the cut station from a logical station list.
        logical: list of (display_name, [seq_numbers])
        is_head: True = delete from head TO this station; False = delete FROM this station to tail
        Returns the index into logical, or None if cancelled."""
        dlg = QDialog(self)
        dlg.setWindowTitle("删除头部站" if is_head else "删除尾部站")
        dlg.resize(420, 380)
        layout = QVBoxLayout(dlg)

        label_text = (
            "选择删除截止站（从头站开始连续删除到该站，至少保留一站）："
            if is_head else
            "选择删除起始站（从该站开始连续删除到尾站，至少保留一站）："
        )
        layout.addWidget(QLabel(label_text))

        station_list = QListWidget()
        # For head: can't pick the last item; for tail: can't pick the first
        selectable = range(len(logical) - 1) if is_head else range(1, len(logical))
        selectable_set = set(selectable)

        for i, (name, _) in enumerate(logical):
            item = QListWidgetItem(name, station_list)
            if i not in selectable_set:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)

        layout.addWidget(station_list)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        if station_list.currentItem() is None:
            return None

        return station_list.currentRow()

    # ── Extend head/tail ────────────────────────────────

    def _on_extend_head(self):
        rid = self._selected_route_id()
        if rid is None:
            return
        sts = self._stations[rid]
        if not sts:
            return

        head_station = sts[0][1]
        head_line = sts[0][2]

        result = self._pick_kl_segment(head_station, head_line, sts, extending_head=True)
        if result is None:
            return

        new_line, segment = result
        # segment = [connection, ..., end]  (connection=head_station, end=chosen end)
        # For head extension, travel order is end→...→connection, so prepend segment[1:] reversed
        new_stns = list(reversed(segment[1:]))

        if not new_stns:
            QMessageBox.information(self, "提示", "没有可延伸的站。")
            return

        is_cross_line = (new_line != head_line)

        to_prepend = []
        for s in new_stns:
            to_prepend.append((s[0], new_line, s[1], 0))

        if is_cross_line:
            # Cross-line: insert connection station on new line as junction
            conn_dist = segment[0][1]
            to_prepend.append((head_station, new_line, conn_dist, 1))
        else:
            # Same-line: last prepended station connects to old head
            if to_prepend:
                to_prepend[-1] = (to_prepend[-1][0], to_prepend[-1][1], to_prepend[-1][2], 1)

        new_seq = []
        seq_num = 1
        for sn, ln, d, is_j in to_prepend:
            new_seq.append((seq_num, sn, ln, d, is_j))
            seq_num += 1
        for s in sts:
            new_seq.append((seq_num, s[1], s[2], s[3], 0))
            seq_num += 1

        raw = [(s[1], s[2], 0, s[4]) for s in new_seq]
        recalc = self._recalc_distances(raw)
        self._save_stations(rid, recalc)
        self._reload_route(rid)

    def _on_extend_tail(self):
        rid = self._selected_route_id()
        if rid is None:
            return
        sts = self._stations[rid]
        if not sts:
            return

        tail_station = sts[-1][1]
        tail_line = sts[-1][2]

        result = self._pick_kl_segment(tail_station, tail_line, sts, extending_head=False)
        if result is None:
            return

        new_line, segment = result
        # segment = [connection, ..., end]  (connection=tail_station, end=chosen end)
        # For tail extension, travel order is connection→...→end, so append segment[1:] as-is
        new_stns = list(segment[1:])

        if not new_stns:
            QMessageBox.information(self, "提示", "没有可延伸的站。")
            return

        is_cross_line = (new_line != tail_line)

        to_append = [(s[0], new_line, s[1], 0) for s in new_stns]

        new_seq = []
        seq_num = 1
        for s in sts:
            new_seq.append((seq_num, s[1], s[2], s[3], 0))
            seq_num += 1

        if is_cross_line:
            # Cross-line: mark last existing as junction, add connection on new line
            if new_seq:
                new_seq[-1] = (new_seq[-1][0], new_seq[-1][1], new_seq[-1][2], new_seq[-1][3], 1)
            conn_dist = segment[0][1]
            new_seq.append((seq_num, tail_station, new_line, conn_dist, 0))
            seq_num += 1
        else:
            # Same-line: last existing becomes junction, new stations follow
            if new_seq and to_append:
                new_seq[-1] = (new_seq[-1][0], new_seq[-1][1], new_seq[-1][2], new_seq[-1][3], 1)

        for sn, ln, d, _ in to_append:
            new_seq.append((seq_num, sn, ln, d, 0))
            seq_num += 1

        raw = [(s[1], s[2], 0, s[4]) for s in new_seq]
        recalc = self._recalc_distances(raw)
        self._save_stations(rid, recalc)
        self._reload_route(rid)

    # ── KL segment picker dialog ─────────────────────────

    def _pick_kl_segment(self, station_name, current_line, route_sts, extending_head=True):
        """Show dialog to pick a kl line segment extending from station_name.

        extending_head: True = prepending to head, False = appending to tail.
        Returns (line_name, segment) or None.
        segment = [(station, dist_on_line), ...] from connection to end (inclusive)."""

        lines = self._kl.execute(
            "SELECT line_name, dist_from_start FROM line_stations WHERE station_name=?",
            (station_name,)
        ).fetchall()
        lines = sorted(lines, key=lambda x: locale.strxfrm(x[0]))

        if not lines:
            QMessageBox.warning(self, "错误", f"kl中未找到站: {station_name}")
            return None

        route_station_names = set(s[1] for s in route_sts)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"从 [{station_name}] {'向前' if extending_head else '向后'}延伸")
        dlg.resize(520, 460)
        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(f"当前站: {station_name}（当前线路: {current_line}）"))
        layout.addWidget(QLabel("选择线路:"))

        line_list = QListWidget()
        for ln, dist in lines:
            marker = " ← 当前线路" if ln == current_line else ""
            QListWidgetItem(f"{ln}  (距起点 {dist:.0f}km){marker}", line_list)
        line_list.setCurrentRow(0)
        layout.addWidget(line_list)

        layout.addWidget(QLabel("选择终点站（点击选中区间）:"))

        station_list = QListWidget()
        layout.addWidget(station_list)

        preview_label = QLabel("")
        preview_label.setStyleSheet("color: #0066cc; font-weight: bold;")
        layout.addWidget(preview_label)

        # Shared mutable state for the dialog
        state = {'all_sts': [], 'cur_idx': None, 'cur_dist': 0, 'is_same_line': False,
                 '_updating': False}

        def update_stations():
            station_list.clear()
            preview_label.setText("")
            if not line_list.currentItem():
                return
            ln = lines[line_list.currentRow()][0]
            cur_dist = lines[line_list.currentRow()][1]
            is_same = (ln == current_line)

            all_sts = self._kl.execute(
                "SELECT station_name, dist_from_start FROM line_stations WHERE line_name=? ORDER BY dist_from_start",
                (ln,)
            ).fetchall()

            state['all_sts'] = all_sts
            state['cur_dist'] = cur_dist
            state['is_same_line'] = is_same

            cur_idx = None
            for i, (sn, d) in enumerate(all_sts):
                if sn == station_name and abs(d - cur_dist) < 0.01:
                    cur_idx = i
                    break
            state['cur_idx'] = cur_idx

            if cur_idx is None:
                return

            # For same-line extension, figure out which direction is already covered by the route
            blocked_left = False   # indices < cur_idx are blocked
            blocked_right = False  # indices > cur_idx are blocked
            if is_same:
                all_names = [s[0] for s in all_sts]
                # Check left neighbor (n-1)
                if cur_idx > 0 and all_names[cur_idx - 1] in route_station_names:
                    blocked_left = True
                # Check right neighbor (n+1)
                if cur_idx < len(all_names) - 1 and all_names[cur_idx + 1] in route_station_names:
                    blocked_right = True

            for i, (sn, d) in enumerate(all_sts):
                text = f"{sn}  ({d:.0f}km)"
                item = QListWidgetItem(text)

                # Connection station — blue bold
                if i == cur_idx:
                    item.setForeground(Qt.GlobalColor.blue)
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                # Same-line blocked direction — gray disabled
                elif is_same and ((blocked_left and i < cur_idx) or (blocked_right and i > cur_idx)):
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setForeground(Qt.GlobalColor.gray)
                # Stations already in route — dimmed but selectable
                elif is_same and sn in route_station_names:
                    item.setForeground(Qt.GlobalColor.darkGray)

                station_list.addItem(item)

        def on_current_changed(current, previous):
            if state['_updating'] or current is None:
                return
            cur_idx = state['cur_idx']
            if cur_idx is None:
                return

            clicked_row = station_list.row(current)
            if clicked_row < 0 or clicked_row == cur_idx:
                preview_label.setText("")
                return

            all_sts = state['all_sts']

            # Highlight range from cur_idx to clicked_row
            state['_updating'] = True
            start = min(cur_idx, clicked_row)
            end = max(cur_idx, clicked_row)
            for i in range(station_list.count()):
                item = station_list.item(i)
                if start <= i <= end:
                    item.setBackground(Qt.GlobalColor.lightGray)
                else:
                    item.setBackground(Qt.GlobalColor.white)
            state['_updating'] = False

            # Build segment for preview
            if clicked_row > cur_idx:
                seg = all_sts[cur_idx:clicked_row + 1]
            else:
                seg = list(reversed(all_sts[clicked_row:cur_idx + 1]))
            # seg = [connection, ..., end]

            new_dist = abs(all_sts[clicked_row][1] - all_sts[cur_idx][1])
            new_names = [s[0] for s in seg[1:]]
            preview_label.setText(f"将接入: {' → '.join(new_names)}，新增 {new_dist:.0f}km")

        station_list.currentItemChanged.connect(on_current_changed)

        def on_line_changed():
            update_stations()

        line_list.currentItemChanged.connect(lambda: on_line_changed())
        if line_list.count() > 0:
            update_stations()

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        cur_idx = state['cur_idx']
        all_sts = state['all_sts']
        clicked_row = station_list.currentRow()

        if cur_idx is None or clicked_row < 0 or clicked_row == cur_idx:
            return None

        # Build segment: [connection, ..., end]
        if clicked_row > cur_idx:
            segment = all_sts[cur_idx:clicked_row + 1]
        else:
            segment = list(reversed(all_sts[clicked_row:cur_idx + 1]))

        ln = lines[line_list.currentRow()][0]
        return (ln, segment)

    # ── Distance recalculation ────────────────────────────

    def _recalc_distances(self, stations):
        """Recalculate cumulative distances from kl data.
        stations: list of (station_name, line_name, cum_distance, is_junction)
        Returns: list of (seq, station_name, line_name, cum_distance, is_junction)"""
        if not stations:
            return []

        result = []
        cum = 0.0
        prev_line = None
        prev_station = None

        for i, (sn, ln, _, is_j) in enumerate(stations):
            if i == 0:
                cum = 0.0
            elif ln != prev_line:
                # Line changed at junction — keep same cum distance
                pass
            else:
                # Same line — get distance from kl
                cur_kl = self._kl.execute(
                    "SELECT dist_from_start FROM line_stations WHERE line_name=? AND station_name=?",
                    (ln, sn)
                ).fetchone()
                prev_kl_val = self._kl.execute(
                    "SELECT dist_from_start FROM line_stations WHERE line_name=? AND station_name=?",
                    (ln, prev_station)
                ).fetchone()
                if cur_kl and prev_kl_val:
                    cum += abs(cur_kl[0] - prev_kl_val[0])

            result.append((i + 1, sn, ln, cum, is_j))
            prev_line = ln
            prev_station = sn

        return result

    def _save_stations(self, rid, stations):
        """Save station list to db. stations: list of (seq, name, line, cum_km, is_junction)."""
        self._db.execute('DELETE FROM route_stations WHERE route_id=?', (rid,))
        for s in stations:
            self._db.execute(
                'INSERT INTO route_stations (route_id,seq,station_name,line_name,cum_distance,is_junction) VALUES (?,?,?,?,?,?)',
                (rid, s[0], s[1], s[2], s[3], s[4])
            )
        # Update route total_distance, start_station, end_station
        total = stations[-1][3] if stations else 0
        first_st = stations[0][1] if stations else ''
        last_st = stations[-1][1] if stations else ''
        self._db.execute(
            'UPDATE routes SET total_distance=?, start_station=?, end_station=? WHERE id=?',
            (total, first_st, last_st, rid)
        )
        self._db.commit()

    def _reload_route(self, rid):
        """Reload a single route's data and refresh UI."""
        r = self._db.execute(
            'SELECT id, name, start_station, end_station, total_distance, prohibit_high_speed, prohibit_normal_speed FROM routes WHERE id=?', (rid,)
        ).fetchone()
        if r is None:
            # Route was deleted
            self._load_routes()
            return
        # Update in self._routes
        for i, route in enumerate(self._routes):
            if route[0] == rid:
                self._routes[i] = r
                break
        # Reload stations
        sts = self._db.execute(
            'SELECT seq, station_name, line_name, cum_distance, is_junction '
            'FROM route_stations WHERE route_id=? ORDER BY seq', (rid,)
        ).fetchall()
        self._stations[rid] = sts

        self._refresh_route_table()
        self._show_stations(rid)
        # Reselect
        for i, route in enumerate(self._routes):
            if route[0] == rid:
                self.route_table.selectRow(i)
                break
        self._update_button_state()

    def closeEvent(self, event):
        self._db.close()
        self._kl.close()
        super().closeEvent(event)
