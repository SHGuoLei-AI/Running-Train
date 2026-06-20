import zipfile,struct
def rk(d,o): return d[o]*255+d[o+1]
with zipfile.ZipFile(r'D:\work\running_train\tools\lulutong-2.apk') as z:
    data=z.read('res/V5.dat')
    print(f'V5.dat: {len(data)} bytes')
    ct=rk(data,0); print(f'ct={ct}')
    split_data={}
    off=2
    for i in range(ct):
        if off+5>len(data): break
        key=rk(data,off); nn=data[off+4]&0xFF; sz=nn*3+3
        if off+2+sz<=len(data):
            payload=data[off+2:off+2+sz]; ns=payload[2]&0xFF
            markers=[(rk(payload,3+j*3),payload[5+j*3]&0xFF) for j in range(ns) if 5+j*3<len(payload)]
            if markers and markers[0][0]==0: split_data[key]=markers
        off+=5+nn*3
    print(f'split_data entries: {len(split_data)}')
    print(f'7579 in split_data: {split_data.get(7579)}')
