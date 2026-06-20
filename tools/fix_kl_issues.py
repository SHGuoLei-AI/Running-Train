"""Fix path-track data to match kl.db distances and station structure."""
import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE, 'data', 'rg.db')

# Backup first
import shutil
backup_path = os.path.join(BASE, 'data', 'backup', f'rg_fix_{__import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
os.makedirs(os.path.dirname(backup_path), exist_ok=True)
shutil.copy2(DB_PATH, backup_path)
print(f'Backup: {backup_path}')

db = sqlite3.connect(DB_PATH)
db.execute('BEGIN')

try:
    # 1. 京沪普 (path 2976): fix distances
    db.execute("UPDATE railway_track SET length=64 WHERE id=20089")  # 南京→镇江 63→64
    db.execute("UPDATE railway_track SET length=28 WHERE id=20090")  # 镇江→丹阳 29→28
    print('1. 京沪普: 南京→镇江 64km, 镇江→丹阳 28km')

    # 2. 沪昆普 (path 2980): fix distance + delete 长安镇 tracks + add 海宁→笕桥
    db.execute("UPDATE railway_track SET length=28 WHERE id=20138")  # 嘉兴→海宁 27→28
    print('2. 沪昆普: 嘉兴→海宁 28km')

    # Delete 长安镇 tracks
    db.execute("DELETE FROM railway_track WHERE id=20139")  # 海宁→长安镇
    db.execute("DELETE FROM railway_track WHERE id=20140")  # 长安镇→笕桥
    print('2. 沪昆普: 删除 海宁→长安镇、长安镇→笕桥')

    # Insert new track: 海宁→笕桥 53km at seq=10
    db.execute(
        "INSERT INTO railway_track (path_id, seq, head_station, tail_station, length, deflection, draw_head, draw_tail, label_flip) "
        "VALUES (2980, 10, '海宁', '笕桥', 53, 0, 0, 1, 0)")
    new_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    print(f'2. 沪昆普: 新增 track {new_id} 海宁→笕桥 53km seq=10')

    # Renumber remaining tracks: old seq 12→11, 13→12
    db.execute("UPDATE railway_track SET seq=11 WHERE id=20141")  # 笕桥→杭州东
    db.execute("UPDATE railway_track SET seq=12 WHERE id=20142")  # 杭州东→杭州南
    print('2. 沪昆普: seq renumber 20141→11, 20142→12')

    # 3. 宁安 (path 2984): fix distance
    db.execute("UPDATE railway_track SET length=28 WHERE id=20175")  # 当涂东→芜湖 29→28
    print('3. 宁安: 当涂东→芜湖 28km')

    # 4. 杭深 (path 2990): fix distances
    db.execute("UPDATE railway_track SET length=16 WHERE id=20205")  # 杭州东→杭州南 21→16
    db.execute("UPDATE railway_track SET length=27 WHERE id=20206")  # 杭州南→绍兴北 22→27
    print('4. 杭深: 杭州东→杭州南 16km, 杭州南→绍兴北 27km')

    # 5. 黄南线 (path 2993): fix distance
    db.execute("UPDATE railway_track SET length=16 WHERE id=20223")  # 七宝→上海南 12→16
    print('5. 黄南线: 七宝→上海南 16km')

    db.commit()
    print('\nAll fixes applied successfully.')

except Exception as e:
    db.rollback()
    print(f'ERROR: {e}')
    sys.exit(1)
finally:
    db.close()

# Verify
db = sqlite3.connect(DB_PATH)
print('\n=== Verification ===')
for pid, pname in [(2976, '京沪普'), (2980, '沪昆普'), (2984, '宁安'), (2990, '杭深'), (2993, '黄南线')]:
    tracks = db.execute(
        'SELECT seq, head_station, tail_station, length FROM railway_track WHERE path_id=? ORDER BY seq',
        (pid,)).fetchall()
    print(f'{pname} (path {pid}): {len(tracks)} tracks')
    for t in tracks:
        print(f'  seq={t[0]}: {t[1]} -> {t[2]} ({t[3]}km)')
db.close()
