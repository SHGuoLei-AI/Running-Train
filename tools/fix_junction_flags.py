"""Set is_junction=1 on BOTH entries of every junction station pair."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
rt = sqlite3.connect(r'D:\work\running_train\data\running_train.db')

routes = rt.execute('SELECT id, name FROM routes ORDER BY id').fetchall()
fixed = 0
pairs = 0

for rid, rname in routes:
    sts = rt.execute(
        'SELECT seq, station_name, line_name, is_junction FROM route_stations WHERE route_id=? ORDER BY seq',
        (rid,)
    ).fetchall()
    if len(sts) < 2:
        continue
    for i in range(len(sts) - 1):
        s1 = sts[i]
        s2 = sts[i + 1]
        if s1[1] == s2[1] and s1[2] != s2[2]:
            pairs += 1
            if s1[3] != 1:
                rt.execute('UPDATE route_stations SET is_junction=1 WHERE route_id=? AND seq=?', (rid, s1[0]))
                fixed += 1
            if s2[3] != 1:
                rt.execute('UPDATE route_stations SET is_junction=1 WHERE route_id=? AND seq=?', (rid, s2[0]))
                fixed += 1

rt.commit()

# Verify
issues = 0
for rid, rname in routes:
    sts = rt.execute(
        'SELECT seq, station_name, line_name, is_junction FROM route_stations WHERE route_id=? ORDER BY seq',
        (rid,)
    ).fetchall()
    for i in range(len(sts) - 1):
        s1 = sts[i]
        s2 = sts[i + 1]
        if s1[1] == s2[1] and s1[2] != s2[2]:
            if s1[3] != 1 or s2[3] != 1:
                print(f'  BUG Route {rid}: seq {s1[0]}/{s2[0]} j={s1[3]}/{s2[3]}')
                issues += 1

print(f'Junction pairs: {pairs}, fixed: {fixed} flags, verify issues: {issues}')
rt.close()
