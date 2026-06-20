"""Migrate data from old/ DBs to the new 4-DB architecture.

kl.db  — 客里表 (from kl_new.db)
cc.db  — 时刻表 (from llt_schedule.db)
rg.db  — 几何结构 (from running_train.db: graph + routes)
rt.db  — 图上车次 (from running_train.db: region_trains + matches, + train stops from llt_schedule.db)
"""
import sqlite3, os, sys
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASE, 'data')
OLD = os.path.join(DATA, 'old')

# ── Schema definitions ──────────────────────────────────────────────

KL_SCHEMA = '''
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE line_list (
    id INTEGER PRIMARY KEY, line_name TEXT UNIQUE NOT NULL,
    start_station TEXT, end_station TEXT, mileage TEXT
);
CREATE TABLE line_stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    line_name TEXT NOT NULL, station_name TEXT NOT NULL,
    dist_from_start REAL DEFAULT 0, dist_from_prev REAL DEFAULT 0,
    is_junction INTEGER DEFAULT 0
);
'''

CC_SCHEMA = '''
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE stations (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE trains (
    id INTEGER PRIMARY KEY, train_index INTEGER NOT NULL UNIQUE,
    train_name TEXT NOT NULL, from_station TEXT, to_station TEXT,
    start_date INTEGER, end_date INTEGER, out_of_date INTEGER DEFAULT 0,
    is_compound INTEGER DEFAULT 0, version TEXT
);
CREATE TABLE train_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    train_index INTEGER NOT NULL, stop_seq INTEGER NOT NULL,
    station_name TEXT NOT NULL, segment_train_no TEXT,
    arrive_time TEXT, depart_time TEXT,
    dwell_minutes INTEGER DEFAULT 0, distance_km INTEGER DEFAULT 0
);
CREATE INDEX idx_ts_train ON train_stops(train_index);
CREATE INDEX idx_ts_name ON train_stops(station_name);
'''

RG_SCHEMA = '''
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE train_graph (
    name TEXT PRIMARY KEY, length REAL, width REAL, scale REAL DEFAULT 1
);
CREATE TABLE railway_path (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    graph_name TEXT REFERENCES train_graph(name),
    code TEXT, name TEXT NOT NULL, kl_line_name TEXT,
    start_x REAL, start_y REAL, angle REAL DEFAULT 0, hidden INTEGER DEFAULT 0
);
CREATE INDEX idx_rp_graph ON railway_path(graph_name);
CREATE TABLE railway_track (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path_id INTEGER REFERENCES railway_path(id),
    seq INTEGER NOT NULL,
    head_station TEXT, tail_station TEXT,
    length REAL, deflection REAL DEFAULT 0,
    draw_head INTEGER DEFAULT 1, draw_tail INTEGER DEFAULT 0
);
CREATE INDEX idx_rt_path ON railway_track(path_id);
CREATE TABLE routes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL, start_station TEXT NOT NULL, end_station TEXT NOT NULL,
    total_distance REAL, junction_count INTEGER DEFAULT 0,
    prohibit_high_speed INTEGER DEFAULT 0, prohibit_normal_speed INTEGER DEFAULT 0
);
CREATE TABLE route_stations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id INTEGER REFERENCES routes(id),
    seq INTEGER NOT NULL, station_name TEXT NOT NULL,
    line_name TEXT NOT NULL, cum_distance REAL DEFAULT 0,
    is_junction INTEGER DEFAULT 0
);
CREATE INDEX idx_rs_route ON route_stations(route_id);
'''

RT_SCHEMA = '''
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE region_trains (
    train_name TEXT PRIMARY KEY, from_station TEXT, to_station TEXT
);
CREATE TABLE train_stops (
    train_name TEXT NOT NULL, stop_seq INTEGER NOT NULL,
    station_name TEXT NOT NULL, arrive_time TEXT, depart_time TEXT,
    distance_km REAL DEFAULT 0,
    PRIMARY KEY (train_name, stop_seq)
);
CREATE INDEX idx_rts_name ON train_stops(train_name);
CREATE TABLE train_route_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    train_name TEXT NOT NULL,
    seg_start_seq INTEGER, seg_end_seq INTEGER,
    seg_start_station TEXT, seg_end_station TEXT,
    seg_distance_km REAL,
    route_id INTEGER, route_name TEXT,
    is_reverse INTEGER DEFAULT 0, match_type TEXT, is_matched INTEGER DEFAULT 1,
    FOREIGN KEY (train_name) REFERENCES region_trains(train_name)
);
CREATE INDEX idx_trm_train ON train_route_matches(train_name);
'''


def create_db(path, schema):
    if os.path.exists(path):
        os.remove(path)
    db = sqlite3.connect(path)
    db.executescript(schema)
    db.commit()
    return db


def migrate_kl(old_kl, new_kl):
    """Copy kl_new.db → kl.db"""
    print('Migrating kl.db...')
    # Copy tables
    for table in ['line_list', 'line_stations']:
        rows = old_kl.execute(f'SELECT * FROM {table}').fetchall()
        col_count = len(rows[0]) if rows else 0
        placeholders = ','.join(['?'] * col_count)
        new_kl.executemany(f'INSERT INTO {table} VALUES ({placeholders})', rows)
    # Set version from jprailfan (latest data update date from website)
    # For now, use the existing data — user can update via meta table
    new_kl.execute("INSERT INTO meta VALUES ('version', ?)",
                   (old_kl.execute("SELECT value FROM meta").fetchone() or ('unknown',))[0] if _has_meta(old_kl) else ('unknown',))
    new_kl.commit()
    kt = new_kl.execute('SELECT COUNT(*) FROM line_list').fetchone()[0]
    ks = new_kl.execute('SELECT COUNT(*) FROM line_stations').fetchone()[0]
    print(f'  kl.db: {kt} lines, {ks} stations')


def migrate_cc(old_cc, new_cc):
    """Copy llt_schedule.db → cc.db"""
    print('Migrating cc.db...')
    for table in ['stations', 'trains', 'train_stops']:
        rows = old_cc.execute(f'SELECT * FROM {table}').fetchall()
        if not rows:
            continue
        col_count = len(rows[0])
        placeholders = ','.join(['?'] * col_count)
        new_cc.executemany(f'INSERT INTO {table} VALUES ({placeholders})', rows)
    # Extract version from trains table
    ver = old_cc.execute('SELECT DISTINCT version FROM trains LIMIT 1').fetchone()
    new_cc.execute("INSERT INTO meta VALUES ('version', ?)", (ver[0] if ver else 'unknown',))
    # Create indexes
    new_cc.execute('CREATE INDEX IF NOT EXISTS idx_ts_train ON train_stops(train_index)')
    new_cc.execute('CREATE INDEX IF NOT EXISTS idx_ts_name ON train_stops(station_name)')
    new_cc.commit()
    st = new_cc.execute('SELECT COUNT(*) FROM stations').fetchone()[0]
    tr = new_cc.execute('SELECT COUNT(*) FROM trains').fetchone()[0]
    ts = new_cc.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]
    print(f'  cc.db: {st} stations, {tr} trains, {ts} stops, version={ver[0] if ver else "?"}')


def migrate_rg(old_rt, new_rg):
    """Extract geometry + routes from running_train.db → rg.db"""
    print('Migrating rg.db...')
    # train_graph — same columns
    rows = old_rt.execute('SELECT * FROM train_graph').fetchall()
    if rows:
        new_rg.executemany('INSERT INTO train_graph VALUES (?,?,?,?)', rows)

    # railway_path — may have 8 or 9 columns (code added later)
    rp_cols = [c[1] for c in old_rt.execute('PRAGMA table_info(railway_path)').fetchall()]
    rp_select = ', '.join(rp_cols)
    rp_insert_cols = [c for c in rp_cols if c in ('id', 'graph_name', 'name', 'kl_line_name', 'start_x', 'start_y', 'angle', 'hidden', 'code')]
    rp_placeholders = ','.join(['?'] * len(rp_insert_cols))
    rows = old_rt.execute(f'SELECT {rp_select} FROM railway_path').fetchall()
    if rows:
        new_rg.executemany(
            f'INSERT INTO railway_path ({",".join(rp_insert_cols)}) VALUES ({rp_placeholders})', rows)

    # railway_track — 9 columns
    rows = old_rt.execute('SELECT * FROM railway_track').fetchall()
    if rows:
        new_rg.executemany(
            'INSERT INTO railway_track VALUES (?,?,?,?,?,?,?,?,?)', rows)

    # routes — old has created_at, new doesn't
    rows = old_rt.execute(
        'SELECT id, name, start_station, end_station, total_distance, '
        'junction_count, prohibit_high_speed, prohibit_normal_speed '
        'FROM routes').fetchall()
    if rows:
        new_rg.executemany(
            'INSERT INTO routes (id, name, start_station, end_station, '
            'total_distance, junction_count, prohibit_high_speed, prohibit_normal_speed) '
            'VALUES (?,?,?,?,?,?,?,?)', rows)

    # route_stations — 7 columns
    rows = old_rt.execute('SELECT * FROM route_stations').fetchall()
    if rows:
        new_rg.executemany(
            'INSERT INTO route_stations VALUES (?,?,?,?,?,?,?)', rows)
    # Set meta
    new_rg.execute("INSERT INTO meta VALUES ('author', '')")
    new_rg.execute("INSERT INTO meta VALUES ('version', '1')")
    new_rg.execute("INSERT INTO meta VALUES ('kl_version', '')")
    new_rg.execute("INSERT INTO meta VALUES ('cc_version', '')")
    new_rg.commit()
    pg = new_rg.execute('SELECT COUNT(*) FROM railway_path').fetchone()[0]
    tk = new_rg.execute('SELECT COUNT(*) FROM railway_track').fetchone()[0]
    rt = new_rg.execute('SELECT COUNT(*) FROM routes').fetchone()[0]
    rs = new_rg.execute('SELECT COUNT(*) FROM route_stations').fetchone()[0]
    print(f'  rg.db: 1 graph, {pg} paths, {tk} tracks, {rt} routes, {rs} route_stations')


def migrate_rt(old_rt, old_cc, new_rt):
    """Extract region_trains + matches from running_train.db, stops from llt_schedule.db → rt.db"""
    print('Migrating rt.db...')
    # Copy region_trains
    rows = old_rt.execute('SELECT * FROM region_trains').fetchall()
    if rows:
        new_rt.executemany('INSERT INTO region_trains VALUES (?,?,?)', rows)
    rt_count = len(rows)
    print(f'  region_trains: {rt_count}')

    # Copy train_route_matches
    rows = old_rt.execute('SELECT * FROM train_route_matches').fetchall()
    if rows:
        col_count = len(rows[0])
        placeholders = ','.join(['?'] * col_count)
        new_rt.executemany(f'INSERT INTO train_route_matches VALUES ({placeholders})', rows)
    trm_count = len(rows)
    print(f'  train_route_matches: {trm_count}')

    # Copy train stops for region trains only
    region_names = {r[0] for r in old_rt.execute('SELECT train_name FROM region_trains').fetchall()}
    # Build train_index -> train_name mapping from cc.db
    idx_to_name = {}
    for ti, name in old_cc.execute('SELECT train_index, train_name FROM trains').fetchall():
        idx_to_name[ti] = name

    # Get stops for region trains
    stop_count = 0
    batch = []
    for ti, name in idx_to_name.items():
        if name not in region_names:
            continue
        stops = old_cc.execute(
            'SELECT stop_seq, station_name, arrive_time, depart_time, distance_km '
            'FROM train_stops WHERE train_index=? ORDER BY stop_seq', (ti,)).fetchall()
        for seq, stn, arr, dep, dist in stops:
            batch.append((name, seq, stn, arr, dep, dist or 0))
        stop_count += len(stops)
        # Commit in batches to avoid memory issues
        if len(batch) >= 10000:
            new_rt.executemany(
                'INSERT INTO train_stops (train_name, stop_seq, station_name, arrive_time, depart_time, distance_km) '
                'VALUES (?,?,?,?,?,?)', batch)
            batch = []
    if batch:
        new_rt.executemany(
            'INSERT INTO train_stops (train_name, stop_seq, station_name, arrive_time, depart_time, distance_km) '
            'VALUES (?,?,?,?,?,?)', batch)

    # Set meta
    cc_ver = old_cc.execute('SELECT DISTINCT version FROM trains LIMIT 1').fetchone()
    new_rt.execute("INSERT INTO meta VALUES ('cc_version', ?)", (cc_ver[0] if cc_ver else '',))
    new_rt.execute("INSERT INTO meta VALUES ('rg_version', '1')")
    new_rt.commit()
    ts_count = new_rt.execute('SELECT COUNT(*) FROM train_stops').fetchone()[0]
    print(f'  train_stops (region only): {ts_count} (filtered from {old_cc.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]} total)')
    print(f'  rt.db: {rt_count} trains, {ts_count} stops, {trm_count} match records')


def _has_meta(db):
    try:
        db.execute('SELECT 1 FROM meta LIMIT 1')
        return True
    except sqlite3.OperationalError:
        return False


def main():
    # Open old DBs
    old_cc = sqlite3.connect(os.path.join(OLD, 'llt_schedule.db'))
    old_kl = sqlite3.connect(os.path.join(OLD, 'kl_new.db'))
    old_rt = sqlite3.connect(os.path.join(OLD, 'running_train.db'))

    # Create new DBs
    new_kl = create_db(os.path.join(DATA, 'kl.db'), KL_SCHEMA)
    new_cc = create_db(os.path.join(DATA, 'cc.db'), CC_SCHEMA)
    new_rg = create_db(os.path.join(DATA, 'rg.db'), RG_SCHEMA)
    new_rt = create_db(os.path.join(DATA, 'rt.db'), RT_SCHEMA)

    # Migrate
    migrate_kl(old_kl, new_kl)
    migrate_cc(old_cc, new_cc)
    migrate_rg(old_rt, new_rg)
    migrate_rt(old_rt, old_cc, new_rt)

    # Close
    for db in [old_cc, old_kl, old_rt, new_kl, new_cc, new_rg, new_rt]:
        db.close()

    print('\n=== Migration complete ===')
    print('New DBs in data/:')
    for name in ['kl.db', 'cc.db', 'rg.db', 'rt.db']:
        path = os.path.join(DATA, name)
        size_kb = os.path.getsize(path) / 1024
        print(f'  {name}: {size_kb:.0f} KB')


if __name__ == '__main__':
    main()
