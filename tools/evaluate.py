import argparse,json,time,uuid,os
from pathlib import Path
import httpx
from app.quality import score_evaluation

def run(client,host,payload):
    response=client.post(host+'/v1/runs',json=payload,headers={'X-Client-ID':'evaluation-'+uuid.uuid4().hex});response.raise_for_status();rid=response.json()['run_id']
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        r=client.get(host+'/v1/runs/'+rid);r.raise_for_status();j=r.json()
        if j['status'] in ('completed','escalated'):return rid,j
        time.sleep(.1)
    raise TimeoutError(rid)
def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default=os.environ.get('API_URL','http://api:8000'));p.add_argument('--output',default='results/evaluation.json');a=p.parse_args()
    cases=json.loads(Path('eval/scenarios.json').read_text());rows=[]
    with httpx.Client(timeout=15,trust_env=False) as client:
        for version in ('v1','v2'):
            for case in cases:
                payload={'product':case['product'],'prompt_version':version,'cache':False}
                if case.get('fault'):payload['fault']=case['fault']
                rid,j=run(client,a.host,payload);result=j.get('result',{});trace=client.get(a.host+'/v1/runs/'+rid+'/trace').json();metrics=score_evaluation(result,trace,case['support'])
                expected=case['expected'];correct=result.get('heading')==expected['heading'] and result.get('route')==expected['route']
                rows.append({'case':case['id'],'prompt':version,'run_id':rid,'correct':correct,'expected':expected,'actual':result,'metrics':metrics,'verification_rejections':sum(e['action']=='verification' and not e.get('supported',False) for e in trace['events']),'duration_seconds':j.get('duration_seconds')})
                print(version,case['id'],correct,flush=True)
    summary={}
    for version in ('v1','v2'):
        subset=[r for r in rows if r['prompt']==version]
        summary[version]={'scenarios':len(subset),'accuracy':sum(r['correct'] for r in subset)/len(subset),'verification_rejections':sum(r['verification_rejections'] for r in subset),**{m:sum(r['metrics'][m] for r in subset)/len(subset) for m in ('groundedness','context_relevance','faithfulness','hallucination_rate')}}
    summary['change']='v1 material-first proposal ablation -> v2 article-first proposal. Same retrieval, verifier, scenarios, delayed stub. Measures planner/prompt package, not isolated LLM prompt quality.'
    Path(a.output).parent.mkdir(exist_ok=True,parents=True);Path(a.output).write_text(json.dumps({'summary':summary,'rows':rows},indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
