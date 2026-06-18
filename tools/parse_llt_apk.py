"""Parse train schedule directly from APK - no emulator needed!"""
import sys, struct, json, csv, zipfile, os, re
sys.stdout.reconfigure(encoding='utf-8')

APK = sys.argv[1] if len(sys.argv) > 1 else r'D:\work\running_train\tools\llt\lulutong0617.apk'
def rk(d,o): return d[o]*255+d[o+1] if o+2<=len(d) else 0

# Step 1: Extract all res/* files from APK (include non-.dat)
with zipfile.ZipFile(APK) as z:
    res_files = {}
    for name in z.namelist():
        if name.startswith('res/') and not name.endswith('.xml') and not name.endswith('.png'):
            if not name.endswith('/'):  # skip directories
                res_files[name] = z.read(name)
print(f"Found {len(res_files)} data files in APK res/")

# Step 2: Identify key files by size/structure
# s.i and t.i use DataInputStream format (2B count + UTF strings)
def is_index_file(data):
    try:
        ct = struct.unpack('>H', data[:2])[0]
        return 100 < ct < 50000 and len(data) > ct * 3
    except: return False

def is_tdata_file(data):
    """Check if file uses DataMgr OooO0oO format (t0-t19/s0-s9)"""
    try:
        o = 0
        while o < min(len(data) - 17, 200):
            k = rk(data, o); n = rk(data, o+15); sz = 17+n*7
            if 0 < n < 100 and o+sz <= len(data): return True
            o += 1
        return False
    except: return False

# Find s.i and t.i by IndexMgr structure (2B count + UTF strings)
si_data = ti_data = None
for name, data in res_files.items():
    if not is_index_file(data): continue
    ct = struct.unpack('>H', data[:2])[0]
    # s.i: station index, 3000-4000 entries
    # t.i: train index, 10000-20000 entries
    if 3000 <= ct <= 4000 and si_data is None:
        si_data = data
        print(f"s.i: {name} ({len(data)}B, {ct} entries)")
    elif 10000 <= ct <= 20000 and ti_data is None:
        ti_data = data
        print(f"t.i: {name} ({len(data)}B, {ct} entries)")

if not si_data or not ti_data:
    print("ERROR: Cannot find s.i or t.i!")
    sys.exit(1)

# Parse s.i
si_ct = struct.unpack('>H', si_data[:2])[0]
si_n = []; off = 2
for _ in range(si_ct):
    l = struct.unpack('>H', si_data[off:off+2])[0]; off += 2
    si_n.append(si_data[off:off+l].decode('utf-8')); off += l

# Parse t.i
ti_ct = struct.unpack('>H', ti_data[:2])[0]
ti_n = []; off = 2
for _ in range(ti_ct):
    l = struct.unpack('>H', ti_data[off:off+2])[0]; off += 2
    ti_n.append(ti_data[off:off+l].decode('utf-8')); off += l

print(f"Stations: {len(si_n)}, Trains: {len(ti_n)}")

# Step 2.5: Parse xw.dat (compound train split markers by distance, ~116KB)
split_data = {}
for name, data in res_files.items():
    if 80000 < len(data) < 150000:
        try:
            ct = rk(data, 0)
            off = 2
            for _ in range(ct):
                if off+5 > len(data): break
                key = rk(data, off)
                n = data[off+4] & 0xFF
                sz = n*3+3
                if off+2+sz <= len(data):
                    payload = data[off+2:off+2+sz]
                    ns = payload[2] & 0xFF
                    markers = [(rk(payload, 3+j*3), payload[5+j*3] & 0xFF) for j in range(ns) if 5+j*3 < len(payload)]
                    # ns should be 0-5 (reasonable); first marker dist=0
                    if 0 <= ns <= 5 and markers and markers[0][0] == 0:
                        split_data[key] = markers
                off += 5 + n*3
        except: pass
    if len(split_data) > 1000:
        print(f"Split markers: {name} ({len(split_data)} entries)")
        break
    split_data = {}

# Step 3: Find all tN.dat files (DataMgr format, ~66-69KB)
t_files = []
for name, data in res_files.items():
    if 30000 < len(data) < 80000 and is_tdata_file(data):
        t_files.append(data)
print(f"Found {len(t_files)} train data files")

# Step 4: Parse all train info records
# Sort by record count: t-data files first (~858 records), s-data last (0-2 records)
# This prevents s-data key collisions from overwriting t-data records
def count_records(data):
    c = 0; o = 0
    while o < len(data) - 17:
        n = rk(data, o+15); sz = 17 + n*7
        if o+sz <= len(data): c += 1; o += sz
        else: o += 1
    return c
t_files.sort(key=count_records, reverse=True)

all_trains = {}
for data in t_files:
    o = 0
    while o < len(data) - 17:
        k = rk(data, o); n = rk(data, o+15); sz = 17 + n*7
        if o + sz <= len(data):
            if k not in all_trains: all_trains[k] = data[o+2:o+sz]
        o += sz

print(f"Parsed {len(all_trains)} train info records")

# Filter out invalid records (from s-data files etc.)
valid_trains = {}
for k, info in all_trains.items():
    n = rk(info, 13)
    if n < 2 or n > 80: continue
    ok = True
    for i in range(min(n, 3)):
        p = 15 + i*7
        if p+7 > len(info): ok = False; break
        si2 = rk(info, p)
        if si2 >= len(si_n): ok = False; break
        if info[p+2] > 99 or info[p+3] > 59: ok = False; break
    if ok: valid_trains[k] = info
removed = len(all_trains) - len(valid_trains)
if removed: print(f"Filtered out {removed} invalid records")
all_trains = valid_trains

# Step 5: Decode and export
def decode_train(info, compound_parts, split_markers=None):
    """split_markers: list of (distance_km, part_idx) from xw.dat"""
    n = rk(info, 13)
    stops = []
    segment = 0
    for i in range(n):
        # Determine segment from distance-based split markers
        if split_markers:
            pos = 15 + i*7
            if pos+7 <= len(info):
                dist = rk(info, pos+5)
                segment = 0
                for marker_dist, marker_part in split_markers:
                    if marker_dist > dist: break
                    segment = marker_part

        if compound_parts and segment < len(compound_parts):
            train_no = compound_parts[segment]
        elif compound_parts:
            train_no = compound_parts[0]
        else:
            train_no = ""

        pos = 15 + i*7
        if pos+7 > len(info): break
        st = rk(info, pos)
        arr_h, arr_m = info[pos+2], info[pos+3]
        dwell = info[pos+4]; dist = rk(info, pos+5)
        name = si_n[st] if 0 <= st < len(si_n) else f"?{st}"
        dep_h, dep_m = arr_h, arr_m + dwell
        while dep_m >= 60: dep_h += 1; dep_m -= 60
        arrive = f"{dep_h:02d}:{dep_m:02d}" if i == 0 else f"{arr_h:02d}:{arr_m:02d}"
        stops.append({
            'station': name, 'train_no': train_no,
            'arrive': arrive,
            'depart': f"{dep_h:02d}:{dep_m:02d}", 'dwell': dwell, 'distance': dist
        })
    return stops

# Find version from APK's ver.txt resource (tiny file with date like "20260618")
ver = None
for name, data in res_files.items():
    if len(data) < 20:
        try:
            text = data.decode('ascii').strip()
            if text.isdigit() and len(text) == 8:
                ver = text
                print(f"Version: {ver} (from {name})")
                break
        except: pass
if not ver:
    m = re.search(r'lulutong[_]?(\d+)\.apk', APK)
    ver = m.group(1) if m else 'unknown'

# Export
use_db = '--db' in sys.argv
if use_db:
    import sqlite3
    db_path = os.path.join(os.path.dirname(os.path.abspath(APK)), '..', 'data', 'llt_schedule.db')
    print(f"Writing SQLite to {db_path}...")
    if os.path.exists(db_path): os.remove(db_path)
    db = sqlite3.connect(db_path)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=OFF")
    db.executescript("""
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
        CREATE INDEX idx_stops_train ON train_stops(train_index);
        CREATE INDEX idx_stops_station ON train_stops(station_name);
        CREATE INDEX idx_trains_name ON trains(train_name);
    """)
    db.executemany("INSERT INTO stations VALUES (?,?)", [(i,n) for i,n in enumerate(si_n)])
    train_rows=[]; stop_rows=[]
    for ti_idx in range(len(ti_n)):
        if ti_idx not in all_trains: continue
        info=all_trains[ti_idx]
        name=ti_n[ti_idx]; parts=name.split('/')
        markers=split_data.get(ti_idx); n_stops=rk(info,13)
        sd=info[3]+info[4]*128+info[5]*16384+info[6]*16384
        ed=info[7]+info[8]*128+info[9]*16384+info[10]*16384
        od=info[11]&0xFF; fs=ts=""
        if n_stops>0:
            fi=rk(info,15); ti2=rk(info,len(info)-7)
            fs=si_n[fi] if 0<=fi<len(si_n) else ""; ts=si_n[ti2] if 0<=ti2<len(si_n) else ""
        train_rows.append((ti_idx,name,fs,ts,sd,ed,od,int(len(parts)>1),ver))
        segment=0
        for i in range(n_stops):
            pos=15+i*7
            if pos+7>len(info): break
            st=rk(info,pos); ah,am=info[pos+2],info[pos+3]; dw=info[pos+4]; dist=rk(info,pos+5)
            sn=si_n[st] if 0<=st<len(si_n) else ""; dh,dm=ah,am+dw
            while dm>=60: dh+=1; dm-=60
            ar=f"{dh:02d}:{dm:02d}" if i==0 else f"{ah:02d}:{am:02d}"
            dp=f"{dh:02d}:{dm:02d}"
            if markers:
                segment=0
                for md,mp in markers:
                    if md>dist: break
                    segment=mp
            sname=parts[segment] if segment<len(parts) else (parts[0] if parts else name)
            stop_rows.append((ti_idx,i+1,sn,sname,ar,dp,dw,dist))
    db.executemany("INSERT INTO trains (train_index,train_name,from_station,to_station,start_date,end_date,out_of_date,is_compound,version) VALUES (?,?,?,?,?,?,?,?,?)", train_rows)
    db.executemany("INSERT INTO train_stops (train_index,stop_seq,station_name,segment_train_no,arrive_time,depart_time,dwell_minutes,distance_km) VALUES (?,?,?,?,?,?,?,?)", stop_rows)
    db.commit()
    tc=db.execute("SELECT COUNT(*) FROM trains").fetchone()[0]
    sc=db.execute("SELECT COUNT(*) FROM train_stops").fetchone()[0]
    print(f"Done: {tc} trains, {sc} stops, {os.path.getsize(db_path):,} bytes")
    db.close()
else:
    csv_path = os.path.join(os.path.dirname(os.path.abspath(APK)), f'train_schedule_{ver}.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['全车次','本站车次','站序','站名','到点','开点','停时(分)','里程(km)'])
        rows = 0
        for ti_idx in range(len(ti_n)):
            if ti_idx not in all_trains: continue
            info = all_trains[ti_idx]
            parts = ti_n[ti_idx].split('/')
            markers = split_data.get(ti_idx)
            stops = decode_train(info, parts, markers)
            for i, s in enumerate(stops):
                w.writerow([ti_n[ti_idx], s['train_no'], i+1, s['station'], s['arrive'], s['depart'], s['dwell'], s['distance']])
                rows += 1
    print(f"\nDone! CSV: {csv_path}")
    print(f"File size: {os.path.getsize(csv_path):,} bytes, {rows} rows")
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        for _ in range(5): print(f.readline().strip())
