import json,time,uuid,os,statistics
from pathlib import Path
import httpx
from .evaluate import run
host=os.getenv('API_URL','http://api:8000');rows=[]
p={'product':{'description':'Stainless steel vacuum flask with plastic body','capacity_l':1},'nonce':'cache-benchmark-'+uuid.uuid4().hex}
with httpx.Client(timeout=15,trust_env=False) as c:
    for cache in (False,True):
        for i in range(12):
            started=time.perf_counter();rid,j=run(c,host,{**p,'cache':cache});r=j['result']
            rows.append({'cache_enabled':cache,'iteration':i,'run_id':rid,'latency_seconds':time.perf_counter()-started,'cost_usd':r['cost_usd'],'cache_hit':r['cache_hit'],'prompt_tokens':r['prompt_tokens'],'completion_tokens':r['completion_tokens']})
summary={}
for name,data in [('uncached',[r for r in rows if not r['cache_enabled']]),('warm_cached',[r for r in rows if r['cache_hit']])]:
    lat=sorted(r['latency_seconds'] for r in data)
    summary[name]={'n':len(lat),'p50_seconds':statistics.median(lat),'p95_seconds':lat[max(0,int(.95*len(lat)+.999)-1)],'mean_cost_usd':statistics.mean(r['cost_usd'] for r in data),'mean_prompt_tokens':statistics.mean(r['prompt_tokens'] for r in data)}
Path('/tmp/cache-benchmark.json').write_text(json.dumps({'summary':summary,'rows':rows},indent=2));print(json.dumps(summary,indent=2))
