import json,re,datetime,time
from pathlib import Path
from app.store import db
starts=[]
for p in Path('results/load').glob('*-console.txt'):
    m=re.search(r'\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+)\]',p.read_text())
    if m:starts.append((datetime.datetime.strptime(m[1],'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=datetime.timezone.utc).timestamp(),p.stem.replace('-console','')))
starts.sort();profiles={}
def percentile(x,q):
 x=sorted(x);return x[min(len(x)-1,int(q*(len(x)-1)))] if x else None
for i,(start,name) in enumerate(starts):
 end=starts[i+1][0] if i+1<len(starts) else time.time();q=[];execute=[];total=[]
 for key in db().scan_iter('run:*'):
    row={k:json.loads(v) for k,v in db().hgetall(key).items()}
    if start<=row.get('submitted_at',0)<end and row.get('finished_at') and len(row.get('request',{}).get('nonce',''))==32:
       q.append(row['started_at']-row['submitted_at']);execute.append(row['finished_at']-row['started_at']);total.append(row['finished_at']-row['submitted_at'])
 profiles[name]={'n':len(total),'queue_p50_seconds':percentile(q,.5),'queue_p95_seconds':percentile(q,.95),'execution_p50_seconds':percentile(execute,.5),'execution_p95_seconds':percentile(execute,.95),'server_total_p95_seconds':percentile(total,.95)}
Path('/tmp/load-profile.json').write_text(json.dumps(profiles,indent=2));print(json.dumps(profiles,indent=2))
