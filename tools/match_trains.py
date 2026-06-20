"""Match region trains to routes and output CSV."""
import sqlite3, csv, sys, os
sys.stdout.reconfigure(encoding='utf-8')

def train_type_allowed(train_name, prohibit_high, prohibit_normal):
    """Check if train type is compatible with route speed restrictions.
    G/D/C = high-speed, K/T/Z/Y/pure-numeric = normal-speed.
    """
    if not prohibit_high and not prohibit_normal:
        return True
    first = train_name[0]
    is_high = first in 'GDC'
    if prohibit_high and is_high:
        return False
    if prohibit_normal and not is_high:
        return False
    return True


def match_trains(llt_db, rt_db, rg_db=None, progress=None):
    """Run matching engine. Returns (rows, all_db_records, stats).

    rows: list of [train_name, origin, segs_str]
    all_db_records: list of tuples for INSERT into train_route_matches
    stats: (full, partial, none)
    progress: optional callback(name, idx, total) called per train

    llt_db: schedule DB (cc.db) — trains, train_stops
    rt_db: region trains DB (rt.db) — region_trains, train_route_matches
    rg_db: geometry DB (rg.db) — routes, route_stations (defaults to rt_db for backward compat)
    """
    if rg_db is None:
        rg_db = rt_db  # backward compat: when routes were in same DB
    routes = rg_db.execute(
        'SELECT id,name,start_station,end_station,total_distance,prohibit_high_speed,prohibit_normal_speed '
        'FROM routes').fetchall()

    # Load route station sequences for partial matching
    route_stations = {}
    for r in routes:
        rid = r[0]
        sts = rg_db.execute(
            'SELECT station_name, cum_distance FROM route_stations WHERE route_id=? ORDER BY seq',
            (rid,)).fetchall()
        route_stations[rid] = sts
        rev_sts = [(s[0], r[4] - s[1]) for s in reversed(sts)]
        route_stations[-rid] = rev_sts

    region_names = [r[0] for r in rt_db.execute(
        'SELECT train_name FROM region_trains ORDER BY train_name').fetchall()]
    name_to_ti = {}
    for (ti, name) in llt_db.execute(
            'SELECT train_index, train_name FROM trains').fetchall():
        name_to_ti[name] = ti

    route_map = {r[0]: r[1] for r in routes}

    rows = []
    all_db_records = []
    total_names = len(region_names)
    for idx, name in enumerate(region_names):
        if progress:
            progress(name, idx, total_names)
        ti = name_to_ti.get(name)
        if ti is None: continue
        stops = llt_db.execute(
            'SELECT stop_seq,station_name,distance_km FROM train_stops '
            'WHERE train_index=? ORDER BY stop_seq', (ti,)).fetchall()
        if not stops: continue
        origin = f'{stops[0][1]}-{stops[-1][1]}'

        # Find all matches (forward + reverse + partial)
        matches = []
        for r in routes:
            rid, rname, rst, ren, rdist, prohibit_high, prohibit_normal = r
            if not train_type_allowed(name, prohibit_high, prohibit_normal):
                continue
            for i, si in enumerate(stops):
                for j in range(i + 1, len(stops)):
                    sd = stops[j][2] - si[2]
                    if abs(sd - rdist) == 0:  # exact distance match only
                        if si[1] == rst and stops[j][1] == ren:
                            matches.append((i, j, rid, rname, sd, False, si[1], stops[j][1]))
                        elif si[1] == ren and stops[j][1] == rst:
                            matches.append((i, j, rid, rname, sd, True, si[1], stops[j][1]))
                    # Partial match: train end is on the route
                    rsts = route_stations.get(rid, [])
                    r_dists = {s[0]: s[1] for s in rsts}
                    if si[1] == rst and stops[j][1] in r_dists:
                        r_d = r_dists[stops[j][1]]
                        if abs(sd - r_d) == 0:
                            matches.append((i, j, rid, rname, sd, False, si[1], stops[j][1]))
                    # Partial match: train start is on the route
                    if stops[j][1] == ren and si[1] in r_dists:
                        r_d = rdist - r_dists[si[1]]
                        if abs(sd - r_d) == 0:
                            matches.append((i, j, rid, rname, sd, False, si[1], stops[j][1]))
                    # Reverse partial
                    rev_sts = route_stations.get(-rid, [])
                    rev_dists = {s[0]: s[1] for s in rev_sts}
                    if si[1] == ren and stops[j][1] in rev_dists:
                        r_d = rev_dists[stops[j][1]]
                        if abs(sd - r_d) == 0:
                            matches.append((i, j, rid, rname, sd, True, si[1], stops[j][1]))
                    if stops[j][1] == rst and si[1] in rev_dists:
                        r_d = rdist - rev_dists[si[1]]
                        if abs(sd - r_d) == 0:
                            matches.append((i, j, rid, rname, sd, True, si[1], stops[j][1]))
                    # Middle segment: both endpoints on route (neither at endpoints)
                    if si[1] in r_dists and stops[j][1] in r_dists:
                        r_d = r_dists[stops[j][1]] - r_dists[si[1]]
                        if abs(sd - r_d) == 0 and r_d > 0:
                            matches.append((i, j, rid, rname, sd, False, si[1], stops[j][1]))
                    if si[1] in rev_dists and stops[j][1] in rev_dists:
                        r_d = rev_dists[stops[j][1]] - rev_dists[si[1]]
                        if abs(sd - r_d) == 0 and r_d > 0:
                            matches.append((i, j, rid, rname, sd, True, si[1], stops[j][1]))

        # Fallback for 0km trains: match by station name sequence only
        if not matches and all(s[2] == 0 for s in stops):
            train_names = [s[1] for s in stops]
            for i in range(len(train_names)):
                for j in range(len(train_names) - 1, i, -1):
                    sub = train_names[i:j+1]
                    best_rid, best_rname, best_rev = None, None, False
                    for r in routes:
                        rid, rname, rst, ren, rdist, _ph, _pn = r
                        rsts = route_stations.get(rid, [])
                        r_names = [s[0] for s in rsts]
                        for k in range(len(r_names) - len(sub) + 1):
                            if r_names[k:k+len(sub)] == sub:
                                best_rid, best_rname, best_rev = rid, rname, False
                                break
                        if best_rid: break
                        rev_names = list(reversed(r_names))
                        for k in range(len(rev_names) - len(sub) + 1):
                            if rev_names[k:k+len(sub)] == sub:
                                best_rid, best_rname, best_rev = rid, rname, True
                                break
                        if best_rid: break
                    if best_rid:
                        matches.append((i, j, best_rid, best_rname, 0, best_rev, sub[0], sub[-1]))
                        break

        # Dedup: for same start-end pair, keep best distance match
        matches.sort(key=lambda m: (m[0], -(m[1] - m[0])))
        seen_pairs = set()
        unique = []
        for m in matches:
            key = (m[0], m[1])
            if key not in seen_pairs:
                seen_pairs.add(key)
                unique.append(m)
        unique.sort(key=lambda m: (m[0], -(m[1] - m[0])))

        # Build segment string and DB records
        segments = []
        db_records = []
        cur = 0
        for m in unique:
            if m[0] >= cur:
                if m[0] > cur:
                    d = stops[m[0]][2] - stops[cur][2]
                    segments.append(f'[{stops[cur][1]}-{stops[m[0]][1]} {d:.0f}km未匹配]')
                    db_records.append((name, cur, m[0],
                        stops[cur][1], stops[m[0]][1], d, None, None, 0, 'unmatched', 0))
                rev = '↩' if m[5] else ''
                segments.append(f'[{m[6]}-{m[7]} {m[4]:.0f}km R{m[2]}{rev}]')
                db_records.append((name, m[0], m[1],
                    m[6], m[7], m[4], m[2], f'R{m[2]} {route_map[m[2]]}', m[5], 'matched', 1))
                cur = m[1]
        if cur < len(stops) - 1:
            d = stops[-1][2] - stops[cur][2]
            segments.append(f'[{stops[cur][1]}-{stops[-1][1]} {d:.0f}km未匹配]')
            db_records.append((name, cur, len(stops) - 1,
                stops[cur][1], stops[-1][1], d, None, None, 0, 'unmatched', 0))

        rows.append([name, origin, ' '.join(segments)])
        all_db_records.extend(db_records)

    # Stats
    matched_all = sum(1 for r in rows if '未匹配' not in r[2])
    matched_partial = sum(1 for r in rows if '未匹配' in r[2] and 'R' in r[2])
    unmatched_all = sum(1 for r in rows if 'R' not in r[2])
    return rows, all_db_records, (matched_all, matched_partial, unmatched_all)


def run_matching_with_progress(parent, rg_db, cc_path, rt_path):
    """Run matching engine with progress dialog + summary. Writes to rt.db.

    Returns (rows, all_db_records, stats).
    rg_db: sqlite3.Connection to rg.db (routes + railway_track)
    cc_path: path to cc.db (schedule data)
    rt_path: path to rt.db (region_trains, output matches)
    """
    from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTextEdit,
                                   QDialogButtonBox, QApplication)

    dlg = QDialog(parent)
    dlg.setWindowTitle("经由匹配进度")
    dlg.resize(520, 480)
    dlg_layout = QVBoxLayout(dlg)

    text_edit = QTextEdit()
    text_edit.setReadOnly(True)
    dlg_layout.addWidget(text_edit)

    close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    close_btn.rejected.connect(dlg.close)
    close_btn.button(QDialogButtonBox.StandardButton.Close).setEnabled(False)
    dlg_layout.addWidget(close_btn)

    dlg.show()
    QApplication.processEvents()

    def log(msg):
        text_edit.append(msg)
        QApplication.processEvents()

    log("开始匹配...")

    llt_db = sqlite3.connect(cc_path)
    rt_db = sqlite3.connect(rt_path)

    try:
        def progress(name, idx, total):
            if idx % 30 == 0:
                log(f"  处理中: {idx}/{total} — {name}")

        rows, all_db_records, stats = match_trains(llt_db, rt_db, rg_db, progress=progress)
        matched_all, matched_partial, unmatched_all = stats

        log(f"\n匹配完成，正在写入数据库...")

        rt_db.execute('DELETE FROM train_route_matches')
        for rec in all_db_records:
            rt_db.execute(
                'INSERT INTO train_route_matches '
                '(train_name, seg_start_seq, seg_end_seq, '
                ' seg_start_station, seg_end_station, seg_distance_km, '
                ' route_id, route_name, is_reverse, match_type, is_matched) '
                'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                rec)
        rt_db.commit()

        log("数据库已更新。")

        # ── Collect graph stations ──
        graph_stations = set()
        for row in rg_db.execute(
            'SELECT head_station, tail_station FROM railway_track').fetchall():
            graph_stations.add(row[0])
            graph_stations.add(row[1])

        # ── Classify zero-match trains ──
        zero_match = [r for r in rows if 'R' not in r[2]]

        name_to_ti = dict(llt_db.execute(
            'SELECT train_name, train_index FROM trains').fetchall())

        outside = []
        zero_km = []
        inside_unmatched = []

        for r in zero_match:
            name = r[0]
            ti = name_to_ti.get(name)
            stops = llt_db.execute(
                'SELECT station_name, distance_km FROM train_stops '
                'WHERE train_index=? ORDER BY stop_seq',
                (ti,)).fetchall()

            if not stops:
                continue

            if all(s[1] == 0 for s in stops):
                zero_km.append(name)
                continue

            train_stations = set(s[0] for s in stops)
            in_graph = train_stations & graph_stations

            if len(in_graph) >= 2:
                inside_unmatched.append((name, r[1]))
            else:
                outside.append((name, r[1]))

        log(f"\n══════ 匹配完成 ══════")
        log(f"总车次数: {len(rows)}")
        log(f"全匹配:   {matched_all}")
        log(f"部分匹配: {matched_partial}")
        log(f"零匹配:   {unmatched_all}")

        log(f"\n── 零匹配分类 ──")
        log(f"图外车次:           {len(outside)} 趟")
        log(f"0公里特例(Y字头等): {len(zero_km)} 趟")
        log(f"图内未匹配:         {len(inside_unmatched)} 趟")

        if zero_km:
            log(f"\n0公里特例车次: {', '.join(zero_km)}")

        if inside_unmatched:
            log(f"\n── 图内未匹配车次明细 ──")
            for name, od in inside_unmatched:
                log(f"  {name}  ({od})")
        else:
            log(f"\n✅ 图内≥2站的车次全部匹配！")

        # ── Unmatched segments inside graph ──
        in_graph_unmatched = []
        for rec in all_db_records:
            if rec[10] == 0:  # is_matched == 0
                if rec[3] in graph_stations and rec[4] in graph_stations:
                    in_graph_unmatched.append((rec[0], rec[3], rec[4], rec[5]))

        log(f"\n── 图内未匹配区段（两端都在图内）──")
        if in_graph_unmatched:
            name_to_od = {r[0]: r[1] for r in rows}
            log(f"共 {len(in_graph_unmatched)} 个区段：")
            for name, ss, es, dist in in_graph_unmatched:
                od = name_to_od.get(name, '?-?')
                log(f"  {name} ({od}): [{ss}-{es} {dist:.0f}km未匹配]")
        else:
            log(f"✅ 无！")

        close_btn.button(QDialogButtonBox.StandardButton.Close).setEnabled(True)

        return rows, all_db_records, stats

    finally:
        llt_db.close()
        rt_db.close()


if __name__ == '__main__':
    BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db = sqlite3.connect(os.path.join(BASE, 'data', 'cc.db'))
    rg = sqlite3.connect(os.path.join(BASE, 'data', 'rg.db'))
    rt = sqlite3.connect(os.path.join(BASE, 'data', 'rt.db'))

    print(f'Matching...')
    rows, all_db_records, stats = match_trains(db, rt, rg)
    matched_all, matched_partial, unmatched_all = stats

    # Write CSV
    csv_path = os.path.join(BASE, 'tools', 'train_route_match.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['车次', '区段', '经由匹配'])
        w.writerows(rows)

    # Insert into DB (rt.db)
    rt.execute('DELETE FROM train_route_matches')
    for rec in all_db_records:
        rt.execute(
            'INSERT INTO train_route_matches '
            '(train_name, seg_start_seq, seg_end_seq, seg_start_station, seg_end_station, '
            'seg_distance_km, route_id, route_name, is_reverse, match_type, is_matched) '
            'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            rec)
    rt.commit()

    print(f'Done: {len(rows)} trains matched, {len(all_db_records)} segments')
    print(f'CSV: {csv_path}')
    print(f'Full match: {matched_all}, Partial: {matched_partial}, No match: {unmatched_all}')
    db.close()
    rg.close()
    rt.close()
