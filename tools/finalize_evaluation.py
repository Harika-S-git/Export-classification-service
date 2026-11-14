"""Recompute transparent evidence metrics using the actual retrieved context."""
import json,os
from pathlib import Path
import httpx
p=Path('results/evaluation.json');data=json.loads(p.read_text());cases={c['id']:c for c in json.loads(Path('eval/scenarios.json').read_text())}
host=os.getenv('API_URL','http://localhost:8000')
with httpx.Client(timeout=20,trust_env=False) as client:
 for row in data['rows']:
    r=row['actual'];claims=[]
    if r.get('heading'):claims=[('heading','H'+r['heading']),('rule','GRI1'),('policy','P'+r['heading'])]
    trace=client.get(host+'/v1/runs/'+row['run_id']+'/trace').json();retrieved={p['id']:p for e in trace['events'] if e['action']=='tool' for p in e.get('passages',[])}
    ids={c['id'] for c in r.get('citations',[])};supported=sum(ident in ids and ident in retrieved for _,ident in claims)
    score=supported/len(claims) if claims else 1.0
    gold=set(cases[row['case']]['support'])|{'POLICY-GENERAL'}
    relevant=len(gold & retrieved.keys())/len(retrieved) if retrieved else 0
    row['metrics']={'groundedness':score,'context_relevance':relevant,'faithfulness':score,'hallucination_rate':1-score if claims else 0,'claim_count':len(claims),'retrieved_passages':len(retrieved),'safe_abstention':not bool(claims),'proxy_only':True}
    row['verification_rejections']=sum(e['action']=='verification' and not e.get('supported',False) for e in trace['events'])
    row['trace_event_count']=len(trace['events'])
for version in ('v1','v2'):
 rows=[r for r in data['rows'] if r['prompt']==version]
 data['summary'][version]={'scenarios':len(rows),'accuracy':sum(r['correct'] for r in rows)/len(rows),'verification_rejections':sum(r['verification_rejections'] for r in rows),**{m:sum(r['metrics'][m] for r in rows)/len(rows) for m in ('groundedness','context_relevance','faithfulness','hallucination_rate')}}
data['metric_definitions']={'groundedness':'Supported final heading/rule/policy claims divided by emitted claims. A claim requires both a returned citation and matching retrieved passage ID. No claims: 1 (safe abstention), reported separately. Canonical hashes are checked by verifier.','context_relevance':'Distinct retrieved IDs that belong to scenario gold support plus POLICY-GENERAL / all distinct retrieved IDs, averaged over scenarios. Conservative exact-ID relevance proxy.','faithfulness':'Fraction of final structured claims consistent with the retrieved heading, rule and policy evidence. Same deterministic test as groundedness in this bounded schema; not an independent semantic judge.','hallucination_rate':'Unsupported final claims / final claims, zero for no claims. Verifier-rejected draft claims are counted separately and never returned.','accuracy':'Exact expected heading and route, including clarification/escalation. Frozen snapshot acknowledged for evaluation.'}
p.write_text(json.dumps(data,indent=2));print(json.dumps(data['summary'],indent=2))
