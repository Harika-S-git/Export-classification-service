import json,os
from pathlib import Path
import httpx
host=os.getenv('API_URL','http://localhost:8000');eval=json.loads(Path('results/evaluation.json').read_text());rid=next(r['run_id'] for r in eval['rows'] if r['prompt']=='v2' and r['case']=='02-flask-small')
with httpx.Client(timeout=20,trust_env=False) as c:
 audit=c.get(host+'/v1/runs/'+rid+'/trace').json();Path('results/reference-run-trace.json').write_text(json.dumps(audit,indent=2))
 jaeger=c.get('http://localhost:16686/api/traces',params={'service':'classifier-worker','limit':10}).json();Path('results/jaeger-traces.json').write_text(json.dumps(jaeger,indent=2))
 print('audit events',len(audit['events']),'Jaeger traces',len(jaeger.get('data',[])))
