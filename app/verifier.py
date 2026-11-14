"""Independent verification agent service and graph; never trusts supplied citations."""
import hashlib,time
from typing import TypedDict
class VerifyState(TypedDict, total=False):
    request: dict
    valid: bool
    reason: str
    canonical: dict
    entities: dict
    heading: str|None
    output: dict
from fastapi import FastAPI
from fastapi.responses import Response
from langgraph.graph import StateGraph, END
from .config import settings
from .contracts import VerifyRequest,safe_text
from .corpus import Corpus
from .entities import extract
from .provider import Provider,ProviderUnavailable
from .store import event,db
from .telemetry import setup,step,TASKS,generate_latest,CONTENT_TYPE_LATEST,TOOLS

app=FastAPI(title='Evidence verification agent',version='1.0.0');setup('verification-agent')

def check(s):
    request=s['request'];rid=request['run_id'];corpus=Corpus();supplied={r['id']:r for r in request['evidence']};canonical={}
    with step('verifier','resolve_citations',rid):
        for ident,r in supplied.items():
            TOOLS.labels('verifier','clause_lookup').inc();p=corpus.lookup(ident)
            if not p or p['text']!=r['text'] or p['sha256']!=r.get('sha256'):
                return {'valid':False,'reason':'Citation text or digest differs from canonical corpus','canonical':{}}
            canonical[ident]=p
        event(rid,'verifier','tool',tool='canonical_clause_lookup',query=list(supplied),passages=list(canonical.values()))
    heading=request['proposed'].get('heading');ent=extract(request['product']);reason='';supported=True
    if not heading:
        return {'valid':True,'canonical':canonical,'entities':ent,'heading':None}
    h=canonical.get('H'+heading)
    if not h or h.get('kind')!='heading':supported=False;reason='Proposed heading was not retrieved'
    elif not set(ent['articles']) & set(h.get('articles',[])):supported=False;reason='Heading does not name the identified article'
    elif heading.startswith('73') and not set(ent['materials']) & {'steel','stainless_steel','iron'}:supported=False;reason='Material premise unsupported'
    if not {'GRI1','N15','N73','N96','POLICY-GENERAL'} <=canonical.keys():supported=False;reason='Missing rule or applicable note evidence'
    if heading and 'P'+heading not in canonical:supported=False;reason='Export policy evidence missing'
    # Refuse excluded articles rather than let a matching surface noun win.
    d=(request['product']['description']+' '+request['product'].get('intended_use','')).lower()
    if any(w in d for w in ['cosmetic','medical','dental','toy','electrical','electric','motorised','furniture','ivory','tortoise','bone','horn','animal by-product']):
        heading=None;ent['outside_or_excluded']=True
    return {'valid':supported,'reason':reason,'canonical':canonical,'entities':ent,'heading':heading}

def deliberate(s):
    req=s['request'];rid=req['run_id']
    if not s['valid']:return {}
    with step('verifier','adversarial_check',rid):
        try:
            review=Provider().call(rid,'verifier',{'prompt_version':req['prompt_version'],'product':req['product'],'candidates':[{'heading':s['heading']}] if s['heading'] else [],'passages':list(s['canonical'].values()),'fault':req['fault']})
            if review.get('heading')!=s['heading']:return {'valid':False,'reason':'Independent provider review disagrees with proposal'}
        except ProviderUnavailable as ex:return {'valid':False,'reason':'Verifier provider unavailable: '+str(ex)}
    return {}

def verdict(s):
    req=s['request'];rid=req['run_id']
    if not s['valid']:
        TASKS.labels('verifier','rejected').inc();out={'supported':False,'reason':s.get('reason','Unsupported evidence')};event(rid,'verifier','verification',**out);return {'output':out}
    ent=s['entities'];heading=s['heading'];route='clear-for-filing';basis=('GRI 1: heading '+str(heading)+' names the identified article; the heading terms and applicable notes control classification.');policy='unconfirmed';item=None
    ids=['GRI1','N15','N73','N96']
    if ent['ambiguous'] and ent['articles']:
        heading=None;route='specialist-classification-review';basis='GRI 1 does not settle the composite article. GRI 2 then GRI 3(a)/(b) do not establish specificity or essential character from the supplied facts. Remaining support is unresolved; a specialist must assess GRI 3, including 3(c).';ids+=['GRI2','GRI3']
    elif not heading:
        route='specialist-classification-review' if ent['articles'] or ent.get('outside_or_excluded') else 'seek-product-clarification'
        basis='Article is excluded, outside chapters 73/96, or not identified in the supported lexicon. Supply function, construction and material details; specialist must review out-of-scope articles.';ids+=['SCOPE']
    else:
        if heading.startswith('96'):basis+=' Section XV Note 1(m) excludes articles of Chapter 96, so base-metal content does not override the article heading.'
        ids+=['H'+heading,'P'+heading,'POLICY-GENERAL'];p=s['canonical']['P'+heading];policy=p.get('policy','unconfirmed')+' (frozen corpus snapshot; conditions and destination restrictions require broker review)'
        if heading=='9617':
            if not req['product']['complete']:
                route='seek-product-clarification';basis+=' Confirm which part and that it is not a glass inner.'
            elif ent.get('capacity_l') is None:
                route='seek-product-clarification';basis+=' Heading 9617 is established; capacity is required to choose the eight-digit flask tariff item.'
            else:item='96170011' if ent['capacity_l']<=.75 else '96170012'
        if not settings().policy_snapshot_confirmed and route=='clear-for-filing':
            route='specialist-classification-review';basis+=' The bundled historical policy snapshot has not been confirmed for the intended shipment date.'
    citations=[{k:s['canonical'][i][k] for k in ('id','text','source','page','sha256')} for i in dict.fromkeys(ids) if i in s['canonical']]
    for c in citations:safe_text(c['text'])
    result={'heading':heading,'tariff_item':item,'rule':'GRI 1' if heading else None,'route':route,'basis':basis,'export_policy':policy,'citations':citations,'verified':True,'proposed_only':True,'prompt_version':req['prompt_version'],'mode':settings().provider_mode,'entities':ent}
    TASKS.labels('verifier','success').inc();out={'supported':True,'reason':'Canonical citation, article, rule, note and policy checks passed','result':result}
    event(rid,'verifier','verification',**out);return {'output':out}

g=StateGraph(VerifyState);g.add_node('check',check);g.add_node('deliberate',deliberate);g.add_node('verdict',verdict);g.set_entry_point('check');g.add_edge('check','deliberate');g.add_edge('deliberate','verdict');g.add_edge('verdict',END);graph=g.compile()
@app.post('/verify')
def verify(req: VerifyRequest):return graph.invoke({'request':req.model_dump()})['output']
@app.get('/health')
def health():db().ping();Corpus();return {'status':'ok','agent':'verifier'}
@app.get('/metrics')
def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
