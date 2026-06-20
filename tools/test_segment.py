import zipfile,struct
def rk(d,o): return d[o]*255+d[o+1]
with zipfile.ZipFile(r'D:\work\running_train\tools\lulutong-3.apk') as z:
    v5=z.read('res/V5.dat'); ct=rk(v5,0); off=2
    sd={}
    for _ in range(ct):
        k=rk(v5,off); nn=v5[off+4]&0xFF; sz=nn*3+3
        payload=v5[off+2:off+2+sz]; ns=payload[2]&0xFF
        m=[(rk(payload,3+j*3),payload[5+j*3]&0xFF) for j in range(ns)]
        if m and m[0][0]==0: sd[k]=m
        off+=5+nn*3
    m=sd.get(29)
    print(f'Markers for ti=29: {m}')
    parts=['4167','4170']
    for dist in [0, 64, 82, 139]:
        seg=0
        for md,mp in m:
            if md>dist: break
            seg=mp
        print(f'  dist={dist}: seg={seg} -> {parts[seg]}')
