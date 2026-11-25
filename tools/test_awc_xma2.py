#!/usr/bin/env python3
"""Build XMA2 WAVE wrappers from AWC 0x55 data chunks and decode with ffmpeg."""
import argparse, csv, mmap, struct, subprocess, wave
from pathlib import Path
import numpy as np

KNOWN={0x55,0x36,0x76,0xA3,0xFA,0x48,0x5C,0x68,0x2B,0x5A,0xD9,0xBD}

def parse_awc(path):
    with open(path,'rb') as f:
        mm=mmap.mmap(f.fileno(),0,access=mmap.ACCESS_READ)
        count,dataoff=struct.unpack_from('<II',mm,8)
        idx=struct.unpack_from(f'<{count}H',mm,16)
        table=None
        for n in range(1,min(40000,dataoff//8)+1):
            start=dataoff-8*n; cs=[]; ok=True
            for pos in range(start,dataoff,8):
                raw=struct.unpack_from('<Q',mm,pos)[0]
                typ,size,off=raw>>56,(raw>>28)&0x0fffffff,raw&0x0fffffff
                if typ not in KNOWN or not size or off+size>len(mm): ok=False; break
                cs.append((typ,size,off))
            if ok and any(t==0x55 for t,_,_ in cs): table=cs; break
        if not table: mm.close(); return []
        streams=[]
        for s in range(count):
            start=idx[s]; end=idx[s+1] if s+1<count else len(table)
            data=next((mm[o:o+z] for t,z,o in table[start:end] if t==0x55),None)
            fmt=next((mm[o:o+z] for t,z,o in table[start:end] if t==0x76),None)
            if data and fmt:
                num=struct.unpack_from('<I',fmt,0)[0]; rate=struct.unpack_from('<H',fmt,8)[0]
                streams.append((data,num,rate))
        mm.close()
        return streams

def wav_xma2(data,num,rate,channels=1,block=2048,encver=0):
    blockcount=(len(data)+block-1)//block
    avg=len(data)*rate//max(num,1)
    # WAVEFORMATEX
    wfx=struct.pack('<HHIIHH',0x0166,channels,rate,avg,block,16)
    # XMA2WAVEFORMATEX tail: cbSize, NumStreams, ChannelMask, SamplesEncoded, BytesPerBlock,
    # PlayBegin, PlayLength, LoopBegin, LoopLength, LoopCount, EncoderVersion, BlockCount
    channel_mask = 0x3 if channels == 2 else 0x4
    tail=struct.pack('<H H I I I I I I I B B H',34,channels,channel_mask,num,block,0,num,0,0,0,encver,blockcount%65536)
    fmt=wfx+tail
    fact=struct.pack('<I',num)
    chunks=b'fmt '+struct.pack('<I',len(fmt))+fmt
    chunks+=b'fact'+struct.pack('<I',len(fact))+fact
    chunks+=b'data'+struct.pack('<I',len(data))+data
    return b'RIFF'+struct.pack('<I',4+len(chunks))+b'WAVE'+chunks

def score(path):
    with wave.open(str(path),'rb') as w:
        r=w.getframerate(); raw=w.readframes(min(w.getnframes(),r*3))
    x=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
    if not len(x): return None
    rms=float(np.sqrt(np.mean(x*x)))
    p=np.abs(np.fft.rfft(x*np.hanning(len(x))))**2+1e-20
    f=np.fft.rfftfreq(len(x),1/r); p=p[(f>=20)&(f<=20000)]
    flat=float(np.exp(np.mean(np.log(p)))/np.mean(p))
    ac=np.correlate(x,x,'full')[len(x)-1:]; ac/=ac[0]+1e-20
    harm=float(np.max(ac[r//2000:r//50])) if len(ac)>r//50 else 0
    return rms,flat,harm,len(x)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--limit',type=int,default=20); ap.add_argument('--out',type=Path,default=Path('output/audio-tests/xma2'))
    a=ap.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
    rows=list(csv.DictReader(open('output/extracted/audio-awc/manifest.tsv'),delimiter='\t'))[:a.limit]
    results=[]
    for ri,row in enumerate(rows):
        for si,(data,num,rate) in enumerate(parse_awc(row['path'])):
            for ch in (1,2):
                for ver in (0,2,3):
                    tag=f'r{ri}-s{si}-ch{ch}-v{ver}'
                    src=a.out/f'{tag}.wav'; dst=a.out/f'{tag}.pcm.wav'
                    src.write_bytes(wav_xma2(data,num,rate,channels=ch,encver=ver))
                    r=subprocess.run(['ffmpeg','-hide_banner','-v','error','-y','-i',str(src),'-c:a','pcm_s16le',str(dst)],capture_output=True,text=True)
                    m=score(dst) if dst.exists() else None
                    if m:
                        rms,flat,harm,n=m; results.append((flat,-harm,rms,ri,si,ch,ver,n,str(src),r.stderr.strip()[:100]))
                        if rms>0.001 and (flat<0.35 or harm>0.15):
                            keep=a.out/'hits'; keep.mkdir(exist_ok=True); dst.replace(keep/f'{tag}.wav'); src.replace(keep/f'{tag}.xma2.wav')
                        else: dst.unlink(missing_ok=True); src.unlink(missing_ok=True)
                    else: src.unlink(missing_ok=True)
        print('done',ri,row['path'],'results',len(results))
    results.sort()
    with (a.out/'results.tsv').open('w',newline='') as f:
        w=csv.writer(f,delimiter='\t',lineterminator='\n'); w.writerow(['flat','negharm','rms','row','stream','ch','ver','samples','src','err']); w.writerows(results[:200])
    for r in results[:20]: print(r)

if __name__=='__main__': main()
