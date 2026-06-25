"""Check railway_path tracks against kl.db — v3 with skip detection."""
import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)
import config
RG = sqlite3.connect(config.get_rg_path())
KL = sqlite3.connect(os.path.join(BASE, 'data', 'kl.db'))

# 1. Load kl data
kl_lines = {}
for line_name, stn, dfs, dfp, is_jct in KL.execute(
    'SELECT line_name, station_name, dist_from_start, dist_from_prev, is_junction '
    'FROM line_stations ORDER BY line_name, dist_from_start'
):
    kl_lines.setdefault(line_name, []).append((stn, dfs, dfp, bool(is_jct)))

# 2. Load all paths
paths = RG.execute('SELECT id, name, kl_line_name FROM railway_path ORDER BY id').fetchall()

results = []

for pid, pname, kl_line in paths:
    if not kl_line:
        continue

    if kl_line not in kl_lines:
        results.append((pid, pname, kl_line, 'KL_LINE_NOT_FOUND',
                        f'"{kl_line}" not in kl.db'))
        continue

    stations = kl_lines[kl_line]
    station_names = [s[0] for s in stations]
    station_set = set(station_names)

    tracks = RG.execute(
        'SELECT id, head_station, tail_station, length, seq '
        'FROM railway_track WHERE path_id=? ORDER BY seq', (pid,)
    ).fetchall()

    if not tracks:
        results.append((pid, pname, kl_line, 'NO_TRACKS', ''))
        continue

    # Detect direction
    fwd = rev = 0
    for tid, head, tail, tlen, seq in tracks:
        if head in station_set and tail in station_set:
            hi = station_names.index(head)
            ti = station_names.index(tail)
            if hi < ti:
                fwd += 1
            elif hi > ti:
                rev += 1
    direction = 'REVERSE' if rev > fwd else 'FORWARD'

    for tid, head, tail, tlen, seq in tracks:
        if head not in station_set:
            results.append((pid, pname, kl_line, 'STATION_NOT_ON_KL',
                            f'track {tid}: HEAD "{head}" not on kl line'))
            continue
        if tail not in station_set:
            results.append((pid, pname, kl_line, 'STATION_NOT_ON_KL',
                            f'track {tid}: TAIL "{tail}" not on kl line'))
            continue

        hi = station_names.index(head)
        ti = station_names.index(tail)

        if direction == 'FORWARD':
            if hi >= ti:
                results.append((pid, pname, kl_line, 'ORDER',
                                f'track {tid}: {head}->{tail} wrong dir (kl idx: {hi}->{ti})'))
                continue
            expected = sum(stations[i][2] for i in range(hi + 1, ti + 1))
            skipped = station_names[hi+1:ti]
        else:
            if hi <= ti:
                results.append((pid, pname, kl_line, 'ORDER',
                                f'track {tid}: {head}->{tail} wrong dir (kl idx: {hi}->{ti})'))
                continue
            expected = sum(stations[i][2] for i in range(ti + 1, hi + 1))
            skipped = station_names[ti+1:hi]

        # Check for skipped stations (even if distance matches)
        if skipped:
            msg = f'track {tid}: {head}->{tail} skips {len(skipped)} station(s): {"->".join(skipped)}'
            msg += f' | track={tlen}km kl_sum={expected}km'
            if tlen != expected:
                msg += f' DIFF={tlen-expected}km'
            results.append((pid, pname, kl_line, 'SKIP' if tlen == expected else 'SKIP_AND_DIST',
                            msg))
        elif tlen != expected:
            results.append((pid, pname, kl_line, 'DIST_MISMATCH',
                            f'track {tid}: {head}->{tail} track={tlen}km kl={expected}km diff={tlen-expected}km'))

RG.close()
KL.close()

# 3. Write output
out_path = os.path.join(BASE, 'tools', 'path_kl_check_result.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    if not results:
        f.write('OK: All paths align with kl data.\n')
    else:
        from collections import Counter
        cats = Counter(r[3] for r in results)
        f.write(f'Total: {len(results)} issues\n')
        f.write(f'Categories: {dict(cats)}\n')
        f.write('='*80 + '\n')

        cur_path = None
        for pid, pname, kl_line, cat, detail in sorted(results):
            if (pid, pname, kl_line) != cur_path:
                cur_path = (pid, pname, kl_line)
                f.write(f'\n-- path {pid} "{pname}" (kl: {kl_line}) --\n')
            f.write(f'  [{cat}] {detail}\n')

print(f'Done. {len(results)} issues. See tools/path_kl_check_result.txt')
