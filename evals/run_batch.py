"""Batch runner against a live local service; writes raw outputs for review, no fabricated metric claims."""
import json, time, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE='http://localhost:8000'
scenarios=json.loads((ROOT/'scenarios.json').read_text(encoding='utf-8'))
results=[]
for s in scenarios:
    body={'description':s['description'],'destination_country':'United States','country_of_export':'India','client_id':'batch-eval'}
    req=urllib.request.Request(BASE+'/v1/runs',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=10) as r: job=json.loads(r.read())
        start=time.time(); out=None
        while time.time()-start<100:
            with urllib.request.urlopen(BASE+job['status_url'],timeout=10) as r: out=json.loads(r.read())
            if out.get('status') in ('completed','failed'): break
            time.sleep(1)
        results.append({'scenario_id':s['id'],'expected_route':s['expected_route'],'actual_route':out.get('recommendation'),'status':out.get('status'),'verification_passed':out.get('verification_passed'),'latency_seconds':round(time.time()-start,3),'result':out})
    except Exception as e: results.append({'scenario_id':s['id'],'error':str(e)})
outpath=ROOT/'latest_results.json'; outpath.write_text(json.dumps(results,indent=2),encoding='utf-8')
print(f'Wrote {len(results)} results to {outpath}; manually label passage relevance/claim support before computing groundedness, context relevance, faithfulness and hallucination rate.')
