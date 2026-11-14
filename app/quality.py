"""Transparent deterministic equivalent evaluator; no LLM-as-judge fiction."""
def score_live(result):
    citations=result.get('citations',[]);heading=result.get('heading');ids={c['id'] for c in citations}
    claims=([('heading','H'+heading),('rule','GRI1'),('policy','P'+heading)] if heading else [])
    supported=sum(i in ids for _,i in claims)
    groundedness=supported/len(claims) if claims else 1.0
    # Context relevance is scored on final evidence, with scope/rules/notes all relevant.
    relevant=sum(c['id'].startswith(('GRI','N','POLICY','SCOPE')) or c['id'] in {'H'+str(heading),'P'+str(heading)} for c in citations)
    return {'groundedness':groundedness,'context_relevance':relevant/len(citations) if citations else 0,'faithfulness':groundedness,'hallucination_rate':1-groundedness if claims else 0,'claim_count':len(claims),'proxy_only':True}

def score_evaluation(result,trace,support):
    retrieved={p['id']:p for e in trace['events'] if e['action']=='tool' for p in e.get('passages',[])}
    ids={c['id'] for c in result.get('citations',[])};heading=result.get('heading')
    claims=['H'+heading,'GRI1','P'+heading] if heading else []
    grounded=sum(i in ids and i in retrieved for i in claims)/len(claims) if claims else 1.0
    return {'groundedness':grounded,'context_relevance':len((set(support)|{'POLICY-GENERAL'}) & retrieved.keys())/len(retrieved) if retrieved else 0,'faithfulness':grounded,'hallucination_rate':1-grounded if claims else 0,'claim_count':len(claims),'retrieved_passages':len(retrieved),'safe_abstention':not bool(claims),'proxy_only':True}
