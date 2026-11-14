"""Classifier LangGraph: decide -> chosen tool -> decide, then independent verifier.
The planner is intentionally deterministic and bounded; the provider proposes only.
"""
import json,time,hashlib,re
from typing import TypedDict
import httpx
from langgraph.graph import StateGraph,END
from .config import settings
from .bounds import tool_deadline
from .corpus import Corpus,TariffRetriever
from .entities import extract
from .provider import Provider,ProviderUnavailable
from .store import event
from .telemetry import step,TOOLS,TASKS

class State(TypedDict,total=False):
    run_id:str; product:dict; entities:dict; evidence:dict; phase:int; action:str
    query:str; tools:int; steps:int; deadline:float; candidates:list; proposed:dict
    result:dict; version:str; fault:str; retry:int; verified:dict

def escalation(s,basis,route='specialist-classification-review'):
    return {'heading':None,'rule':None,'tariff_item':None,'route':route,'basis':basis,'export_policy':'unconfirmed','citations':[],'verified':False,'prompt_version':s['version'],'mode':settings().provider_mode,'entities':s.get('entities',{}),'proposed_only':True}

def candidates_for(entities,evidence):
    articles=set(entities['articles']);materials=set(entities['materials'])
    matches=[]
    for r in evidence.values():
        if r['kind']!='heading':continue
        named=articles & set(r.get('articles',[]))
        if named and (not r['heading'].startswith('73') or materials & {'steel','stainless_steel','iron'}):
            matches.append({'heading':r['heading'],'id':r['id'],'score':len(named)})
    return sorted(matches,key=lambda x:-x['score'])

class ClassifierAgent:
    def __init__(self):
        self.corpus=Corpus();self.retriever=TariffRetriever(corpus=self.corpus)
        g=StateGraph(State)
        for name,fn in [('decide',self.decide),('tool',self.tool),('propose',self.propose),('handoff',self.handoff),('finish',self.finish)]:g.add_node(name,fn)
        g.set_entry_point('decide')
        g.add_conditional_edges('decide',lambda s:s['action'],{'tool':'tool','propose':'propose','finish':'finish'})
        g.add_edge('tool','decide');g.add_edge('propose','handoff')
        g.add_conditional_edges('handoff',lambda s:'decide' if s.get('retry')==1 and not s.get('result') else 'finish',{'decide':'decide','finish':'finish'})
        g.add_edge('finish',END);self.graph=g.compile()
    def decide(self,s):
        s['steps']=s.get('steps',0)+1
        if time.monotonic()>s['deadline'] or s['steps']>=settings().max_steps or s.get('tools',0)>=settings().max_tool_calls:
            return {'action':'finish','result':escalation(s,'Execution budget exhausted; no verified determination.')}
        phase=s.get('phase',0)
        if phase==0:return {'action':'tool','query':'request_fields'}
        if phase==1:
            # Initial search is material-oriented on purpose; it cannot be the final search.
            return {'action':'tool','query':' '.join(s['entities']['materials'])+' household articles'}
        if phase==2:
            # Derived from retrieved notes: section XV explicitly excludes chapter 96.
            notes=' '.join(r['text'] for r in s['evidence'].values() if r['kind']=='note')
            # Parse a modifying provision we actually read, rather than add a
            # guessed chapter to every query. Missing notes trigger exact lookup.
            modifiers=sorted(set(re.findall(r'articles of Chapter\s+(\d+)',notes)))
            in_scope=[chapter for chapter in modifiers if chapter in ('73','96')]
            derived=' '.join('chapter '+chapter for chapter in in_scope)
            note_ids=[r['id'] for r in s['evidence'].values() if r['kind']=='note']
            if not notes:return {'action':'tool','query':'missing_notes'}
            event(s['run_id'],'classifier','modifier_decision',basis='Read exclusion references; check article-naming headings before material classification',read_note_ids=note_ids,modifier_chapters=modifiers,derived_query=derived)
            return {'action':'tool','query':' '.join(s['entities']['articles'])+' named article '+derived}
        if phase==3:return {'action':'tool','query':'applicable_clauses'}
        if phase==4 and s.get('retry',0):return {'action':'tool','query':'exact_heading_retry'}
        return {'action':'propose'}
    def tool(self,s):
        q=s['query'];rid=s['run_id'];e=dict(s.get('evidence',{}));entities=s.get('entities',{})
        name='request_fields' if q=='request_fields' else 'clause_lookup' if q in ('applicable_clauses','exact_heading_retry','missing_notes') else 'corpus_search'
        with step('classifier',name,rid),tool_deadline(settings().call_timeout):
            TOOLS.labels('classifier',name).inc()
            if name=='request_fields':
                entities=extract(s['product']);passages=[]
            elif name=='corpus_search':
                docs=self.retriever.invoke(q);passages=[d.metadata for d in docs]
                # Material search reads the section and chapter notes, including exclusions.
                if s.get('phase')==1:
                    passages += [self.corpus.lookup(x) for x in ('N15','N73','N96')]
            else:
                c=candidates_for(entities,{**e,**{r['id']:r for r in self.corpus.search(' '.join(entities['articles']),16,'heading')}})
                ids=['GRI1','GRI2','GRI3','N15','N73','N96','POLICY-GENERAL']
                for x in c: ids += [x['id'],'P'+x['heading']]
                if not c or entities['ambiguous']:ids += ['SCOPE']
                passages=[self.corpus.lookup(i) for i in ids]
            for p in passages:
                if p:e[p['id']]=p
            event(rid,'classifier','tool',tool=name,query=q,passages=[p for p in passages if p],entities=entities,latency_budget_seconds=settings().call_timeout)
        return {'entities':entities,'evidence':e,'phase':s.get('phase',0)+1,'tools':s.get('tools',0)+1}
    def propose(self,s):
        with step('classifier','propose',s['run_id']):
            c=candidates_for(s['entities'],s['evidence'])
            # v1 is a controlled ablation: uses material candidate ahead of article candidate.
            if s['version']=='v1' and 'vacuum flask' in s['entities']['articles'] and any('steel' in m for m in s['entities']['materials']):
                c=[{'heading':'7323','id':'H7323','score':1}]+c
            try:
                answer=Provider().call(s['run_id'],'classifier',{'prompt_version':s['version'],'product':s['product'],'candidates':c,'passages':list(s['evidence'].values()),'fault':s['fault']})
                return {'proposed':answer,'candidates':c}
            except ProviderUnavailable as ex:return {'result':escalation(s,'Provider unavailable: '+str(ex)), 'proposed':{}}
    def handoff(self,s):
        if s.get('result'):return {}
        with step('classifier','verifier_handoff',s['run_id']):
            try:
                if s['fault']=='verifier_down':raise httpx.ConnectError('injected verifier outage')
                from opentelemetry.propagate import inject
                carrier={'X-Correlation-ID':s['run_id']};inject(carrier)
                with httpx.Client(timeout=settings().call_timeout*3,trust_env=False) as client:
                    r=client.post(settings().verifier_url.rstrip('/')+'/verify',json={'run_id':s['run_id'],'product':s['product'],'proposed':s['proposed'],'evidence':list(s['evidence'].values()),'prompt_version':s['version'],'fault':s['fault']},headers=carrier);r.raise_for_status();v=r.json()
                event(s['run_id'],'classifier','handoff_result',verification=v)
                if not v['supported']:
                    if not s.get('retry'):
                        return {'retry':1,'phase':4,'verified':v}
                    return {'result':escalation(s,'Independent verification failed after alternate exact-clause retrieval: '+v['reason']),'verified':v,'retry':2}
                return {'verified':v,'result':v['result'],'retry':2}
            except httpx.HTTPError as ex:return {'result':escalation(s,'Verification agent unavailable: '+type(ex).__name__),'retry':2}
    def finish(self,s):
        r=s.get('result') or escalation(s,'No supported answer within bounded graph.')
        TASKS.labels('classifier','success' if r.get('verified') else 'escalated').inc()
        return {'result':r}
    def run(self,rid,submission):
        s={'run_id':rid,'product':submission['product'],'version':submission['prompt_version'],'fault':submission['fault'],'deadline':time.monotonic()+settings().run_timeout,'phase':0,'tools':0,'steps':0,'evidence':{},'retry':0}
        return self.graph.invoke(s,{'recursion_limit':60})['result']
