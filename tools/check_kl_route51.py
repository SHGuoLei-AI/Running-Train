"""Query kl for沪苏通 related line distances."""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

kl = sqlite3.connect(r'D:\work\running_train\data\kl_new.db')

lines_to_check = ['沪苏通线', '虹封线', '黄南线', '宁启线(南京)']

for line_name in lines_to_check:
    print(f'=== {line_name} ===')
    # Check exact name first
    matches = kl.execute("SELECT DISTINCT line_name FROM line_stations WHERE line_name LIKE ?", (f'%{line_name.split("(")[0]}%',)).fetchall()
    exact = [m for m in matches if m[0] == line_name]
    if not exact:
        print(f'  Available: {matches}')
        continue

    rows = kl.execute(
        "SELECT station_name, dist_from_start, dist_from_prev, is_junction FROM line_stations WHERE line_name=? ORDER BY dist_from_start",
        (line_name,)
    ).fetchall()
    for r in rows:
        j = ' [J]' if r[3] else ''
        print(f'  {r[0]:12s}  from_start={r[1]:6.1f}  prev={r[2]:6.1f}{j}')
    print()

# Now compute what Route 51 SHOULD be
print('=== Route 51 corrected distance calculation ===')
# Step 1: 虹封线 上海虹桥(0)→封浜(14)
hf = kl.execute("SELECT station_name, dist_from_start FROM line_stations WHERE line_name='虹封线' ORDER BY dist_from_start").fetchall()
print(f'虹封线: {hf[0][0]}({hf[0][1]:.0f}) → {hf[1][0]}({hf[1][1]:.0f}) = {hf[1][1] - hf[0][1]:.0f}km')

# Step 2: 黄南线 封浜→黄渡
hn = kl.execute("SELECT station_name, dist_from_start FROM line_stations WHERE line_name='黄南线' ORDER BY dist_from_start").fetchall()
print(f'黄南线: {hn}')
# Find 封浜 and 黄渡
for s in hn:
    print(f'  {s[0]} at {s[1]}')

# Step 3: 沪苏通线 黄渡→赵甸
hst = kl.execute("SELECT station_name, dist_from_start, dist_from_prev, is_junction FROM line_stations WHERE line_name='沪苏通线' ORDER BY dist_from_start").fetchall()
print(f'\n沪苏通线 ({len(hst)} stations):')
for s in hst:
    j = ' [J]' if s[3] else ''
    print(f'  {s[0]:12s}  from_start={s[1]:6.1f}  prev={s[2]:6.1f}{j}')
print(f'  全线={hst[-1][1]:.0f}km (from {hst[0][0]} to {hst[-1][0]})')

# Step 4: 宁启线 赵甸→启东
nq = kl.execute("SELECT station_name, dist_from_start, dist_from_prev, is_junction FROM line_stations WHERE line_name='宁启线(南京)' ORDER BY dist_from_start").fetchall()
zd_idx = next(i for i, s in enumerate(nq) if s[0] == '赵甸')
print(f'\n宁启线(南京) from 赵甸(index={zd_idx}):')
for s in nq[zd_idx:]:
    j = ' [J]' if s[3] else ''
    print(f'  {s[0]:12s}  from_start={s[1]:6.1f}  prev={s[2]:6.1f}{j}')

kl.close()
