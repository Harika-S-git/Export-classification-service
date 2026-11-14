import json,time,uuid
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,Response,HTMLResponse
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from rq import Queue
from rq.job import Job
from redis import Redis
from .config import settings
from .contracts import Submission,Feedback,Accepted,RunStatus,TraceResponse,FeedbackReceipt,AnalyticsResponse,HealthResponse,CorpusResponse
from .store import db,get_run,put_run,event,events,quarantine
from .jobs import cache_key
from .telemetry import setup,REJECTS,CACHE,FRESH,CHUNKS,PIPELINE,generate_latest,CONTENT_TYPE_LATEST,RUN
from .corpus import Corpus

app=FastAPI(title='Export Classification Check Service',version='1.0.0',description='Asynchronous proposed classifications for chapters 73/96. A broker decides. Polling avoids callback SSRF and client availability dependencies.');setup('submission-api');FastAPIInstrumentor.instrument_app(app)
@app.middleware('http')
async def correlation(request,call_next):
    request.state.correlation=str(uuid.uuid4())
    if int(request.headers.get('content-length','0'))>16000:return JSONResponse({'detail':'payload too large'},status_code=413)
    response=await call_next(request);response.headers['X-Correlation-ID']=request.state.correlation;return response
@app.exception_handler(RequestValidationError)
async def invalid(request,exc):
    errors=json.loads(json.dumps(exc.errors(),default=str));item=quarantine(errors,await request.body(),request.state.correlation);REJECTS.inc()
    return JSONResponse(status_code=422,content={'detail':errors,'quarantine_id':item['id'],'agent_started':False})
@app.get('/',response_class=HTMLResponse,include_in_schema=False)
def client():return Path('web/index.html').read_text()
@app.get('/health',response_model=HealthResponse)
def health():
    db().ping();c=Corpus();return {'status':'ok','corpus':c.manifest['digest'],'mode':settings().provider_mode}
@app.get('/metrics',include_in_schema=False)
def metrics():
    m=Corpus().manifest;FRESH.set(m['built_at']);CHUNKS.set(m['chunks']);PIPELINE.set(m['chunks_per_second'])
    return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.post('/v1/runs',status_code=202,response_model=Accepted)
def submit(body:Submission,request:Request):
    s=settings();r=db()
    if body.fault!='none' and not s.enable_faults:raise HTTPException(403,'Fault injection disabled')
    # X-Client-ID is a demo tenant label; deploy behind authenticated gateway for real tenants.
    label=request.headers.get('X-Client-ID',request.client.host)[:128]
    import hashlib
    key='rate:'+hashlib.sha256(label.encode()).hexdigest()+':'+str(int(time.time())//s.rate_window)
    count=r.incr(key)
    if count==1:r.expire(key,s.rate_window)
    if count>s.rate_limit:raise HTTPException(429,'Client rate limit reached',headers={'Retry-After':str(s.rate_window)})
    payload=body.model_dump();rid=str(uuid.uuid4());now=time.time()
    from opentelemetry.propagate import inject
    carrier={};inject(carrier)
    put_run(rid,run_id=rid,status='queued',submitted_at=now,request=payload,correlation_id=rid,trace_context=carrier)
    hit=r.get('cache:'+cache_key(payload)) if body.cache and s.cache_enabled and body.fault=='none' else None
    if hit:
        result=json.loads(hit);result.update(cache_hit=True,cost_usd=0,prompt_tokens=0,completion_tokens=0)
        put_run(rid,status='completed',result=result,finished_at=time.time(),duration_seconds=time.time()-now);CACHE.labels('hit').inc();event(rid,'api','cache_hit',citation_ids=[c['id'] for c in result['citations']]);RUN.observe(time.time()-now)
    else:
        CACHE.labels('miss').inc()
        try:
            conn=Redis.from_url(s.redis_url,socket_timeout=3)
            job=Queue('classification',connection=conn).enqueue('app.jobs.execute',rid,payload,job_id=rid,job_timeout=s.run_timeout,result_ttl=86400,failure_ttl=86400)
            event(rid,'api','submitted',queue='classification',prompt_version=body.prompt_version)
        except Exception:
            put_run(rid,status='escalated',error='Queue unavailable');raise HTTPException(503,'Queue unavailable')
    return {'run_id':rid,'status_url':'/v1/runs/'+rid,'trace_url':'/v1/runs/'+rid+'/trace'}
@app.get('/v1/runs/{rid}',response_model=RunStatus)
def status(rid:str):
    run=get_run(rid)
    if not run:raise HTTPException(404,'Unknown run')
    if run['status'] in ('running','queued'):
        try:
            j=Job.fetch(rid,connection=Redis.from_url(settings().redis_url));js=j.get_status().value
            if js in ('failed','stopped','canceled'):
                put_run(rid,status='escalated',error='Worker failed or timed out; no recommendation available');run=get_run(rid)
        except Exception:pass
        if time.time()-run['submitted_at']>300:
            put_run(rid,status='escalated',error='Queue/run deadline exceeded');run=get_run(rid)
    return run
@app.get('/v1/runs/{rid}/trace',response_model=TraceResponse)
def audit(rid:str):
    if not get_run(rid):raise HTTPException(404,'Unknown run')
    return {'run_id':rid,'events':events(rid)}
@app.post('/v1/runs/{rid}/feedback',status_code=201,response_model=FeedbackReceipt)
def feedback(rid:str,body:Feedback):
    run=get_run(rid)
    if not run or run['status'] not in ('completed','escalated'):raise HTTPException(409,'Feedback requires terminal run')
    db().rpush('feedback',json.dumps({'run_id':rid,'timestamp':time.time(),**body.model_dump()}));return {'persisted':True}
@app.get('/v1/analytics',response_model=AnalyticsResponse)
def analytics():
    r=db();items=[json.loads(x) for x in r.lrange('feedback',0,-1)]
    return {'feedback_count':len(items),'satisfactory_rate':sum(i['satisfactory'] for i in items)/len(items) if items else None,'quality':[json.loads(x) for x in r.lrange('quality',-50,-1)],'quarantine_count':r.llen('quarantine'),'breaker_open_until':r.get('breaker:until')}
@app.get('/v1/corpus',response_model=CorpusResponse)
def corpus():return Corpus().manifest
