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

# Step 3: Find all tN.dat files (DataMgr format, ~66-69KB)
t_files = []
for name, data in res_files.items():
    if 30000 < len(data) < 80000 and is_tdata_file(data):
        t_files.append(data)
print(f"Found {len(t_files)} train data files")

# Step 4: Parse all train info records
all_trains = {}
for data in t_files:
    o = 0
    while o < len(data) - 17:
        k = rk(data, o); n = rk(data, o+15); sz = 17 + n*7
        if o + sz <= len(data):
            all_trains[k] = data[o+2:o+sz]
        o += sz

print(f"Parsed {len(all_trains)} train info records")

# Step 5: Decode and export
def decode_train(info):
    n = rk(info, 13)
    stops = []
    for i in range(n):
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
            'station': name, 'arrive': arrive,
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

# CSV
csv_path = os.path.join(os.path.dirname(os.path.abspath(APK)), f'train_schedule_{ver}.csv')
with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.writer(f)
    w.writerow(['车次','站序','站名','到点','开点','停时(分)','里程(km)'])
    rows = 0
    for ti_idx in range(len(ti_n)):
        if ti_idx not in all_trains: continue
        info = all_trains[ti_idx]; stops = decode_train(info)
        for i, s in enumerate(stops):
            w.writerow([ti_n[ti_idx], i+1, s['station'], s['arrive'], s['depart'], s['dwell'], s['distance']])
            rows += 1

print(f"\nDone! CSV: {csv_path}")
print(f"File size: {os.path.getsize(csv_path):,} bytes, {rows} rows")
print(f"Sample:")
with open(csv_path, 'r', encoding='utf-8-sig') as f:
    for _ in range(8): print(f.readline().strip())
