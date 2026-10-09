import os, uuid, json, logging, re, time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, model_validator
from redis import Redis
from rq import Queue
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from app.core import RUNS, run_classification, REQUESTS, logger
from app.guardrails import inspect_free_text

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'), format='%(message)s')
app=FastAPI(title='Export Classification Check Service',version='1.0.0',description='Evidence-first proposed tariff classification; human review remains authoritative.')
redis_conn=Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'),socket_connect_timeout=2,socket_timeout=2)
queue=Queue('classification',connection=redis_conn,default_timeout=int(os.getenv('RUN_TIMEOUT_SECONDS','90')))
QUARANTINE=[]; FEEDBACK=[]; RATE={}

def quarantine(record: dict):
    QUARANTINE.append(record)
    del QUARANTINE[:-500]
    try:
        redis_conn.lpush('quarantine', json.dumps(record))
        redis_conn.ltrim('quarantine', 0, 499)
    except Exception:
        pass

class ProductRequest(BaseModel):
    description: str = Field(min_length=8,max_length=1000)
    materials: list[str] = Field(default_factory=list,max_length=20)
    intended_use: str | None = Field(default=None,max_length=500)
    country_of_export: str = Field(default='India',min_length=2,max_length=80)
    destination_country: str = Field(min_length=2,max_length=80)
    value_usd: float | None = Field(default=None,ge=0,le=1_000_000_000)
    quantity: int | None = Field(default=None,ge=1,le=1_000_000_000)
    client_id: str = Field(default='anonymous',min_length=1,max_length=80)
    @model_validator(mode='after')
    def cross_checks(self):
        if self.country_of_export.strip().lower()==self.destination_country.strip().lower():
            raise ValueError('destination_country must differ from country_of_export for an export request')
        if any(len(m.strip())<2 for m in self.materials): raise ValueError('each material must contain at least 2 characters')
        return self

@app.middleware('http')
async def rate_limit_and_correlation(request: Request, call_next):
    cid=request.headers.get('X-Correlation-ID') or str(uuid.uuid4()); request.state.correlation_id=cid
    if request.url.path.startswith('/v1/runs') and request.method=='POST':
        ip=request.client.host if request.client else 'unknown'; now=time.time(); times=[t for t in RATE.get(ip,[]) if now-t<60]
        if len(times)>=int(os.getenv('RATE_LIMIT_PER_MINUTE','10')): return Response('Rate limit exceeded',status_code=429)
        times.append(now); RATE[ip]=times
    response=await call_next(request); response.headers['X-Correlation-ID']=cid; return response

@app.exception_handler(RequestValidationError)
async def validation_exception(request: Request, exc: RequestValidationError):
    quarantine({'created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':getattr(request.state,'correlation_id','unknown'),'path':request.url.path,'errors':exc.errors()})
    return Response(json.dumps(jsonable_encoder({'detail':exc.errors(),'quarantined':True})),status_code=422,media_type='application/json')

@app.exception_handler(Exception)
async def generic_exception(request, exc):
    logger.exception(json.dumps({'event':'unhandled_exception','correlation_id':getattr(request.state,'correlation_id','unknown')}))
    return Response('Internal service error',status_code=500)

@app.get('/health')
def health():
    try: redis_conn.ping(); redis='ok'
    except Exception: redis='unavailable'
    return {'status':'ok' if redis=='ok' else 'degraded','redis':redis,'timestamp':datetime.now(timezone.utc).isoformat()}

@app.get('/metrics')
def metrics(): return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)

@app.get('/v1/quarantine/summary')
def quarantine_summary():
    try: count=redis_conn.llen('quarantine')
    except Exception: count=len(QUARANTINE)
    return {'count':count,'records':QUARANTINE[-20:]}


@app.post('/v1/runs',status_code=202)
def submit(product: ProductRequest, request: Request):
    payload=product.model_dump()
    flags=[]
    for field in ('description','intended_use'):
        flags.extend({'field':field,'flag':flag} for flag in inspect_free_text(payload.get(field)))
    for index, material in enumerate(payload.get('materials', [])):
        flags.extend({'field':f'materials[{index}]','flag':flag} for flag in inspect_free_text(material))
    if flags:
        quarantine({'created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':request.state.correlation_id,'client_id':payload.get('client_id'),'flags':flags,'decision':'rejected_before_enqueue'})
        raise HTTPException(422,detail={'message':'Request rejected by input guardrails; no agent run started.','flags':flags,'quarantined':True})
    rid=str(uuid.uuid4())
    try:
        job=queue.enqueue('app.core.run_classification',payload,rid,job_timeout=int(os.getenv('RUN_TIMEOUT_SECONDS','90')),result_ttl=86400,failure_ttl=86400)
        logger.info(json.dumps({'event':'run_submitted','run_id':rid,'correlation_id':request.state.correlation_id,'job_id':job.id}))
        return {'run_id':rid,'status_url':f'/v1/runs/{rid}','queue_job_id':job.id,'status':'queued'}
    except Exception as exc:
        # Graceful local fallback if Redis/worker is unavailable: do not block the submit API with model work.
        raise HTTPException(503,detail='Queue unavailable; no agent run started. Check Redis and worker health.') from exc

@app.get('/v1/runs/{run_id}')
def get_run(run_id: str):
    if run_id in RUNS: return RUNS[run_id]
    try:
        cached=redis_conn.get(f'run-result:{run_id}')
        if cached: return json.loads(cached)
    except Exception: pass
    try:
        from rq.job import Job
        job=Job.fetch(run_id,connection=redis_conn) # run_id is not the queue job id; status endpoint below scans by meta if configured
        return {'run_id':run_id,'status':job.get_status()}
    except Exception:
        # Search queue registry by job args so the public run id stays stable.
        try:
            for job in queue.get_jobs():
                if len(job.args)>1 and job.args[1]==run_id:
                    if job.is_finished and job.result: return job.result
                    return {'run_id':run_id,'status':job.get_status()}
        except Exception: pass
        raise HTTPException(404,'Run not found')

@app.post('/v1/feedback')
def feedback(body: dict):
    rid=body.get('run_id'); satisfactory=body.get('satisfactory'); reason=str(body.get('reason',''))[:1000]
    if not isinstance(rid,str) or not isinstance(satisfactory,bool) or not reason.strip(): raise HTTPException(422,'run_id, boolean satisfactory, and non-empty reason are required')
    item={'run_id':rid,'satisfactory':satisfactory,'reason':reason,'created_at':datetime.now(timezone.utc).isoformat()}
    try:
        redis_conn.rpush('feedback',json.dumps(item))
    except Exception: FEEDBACK.append(item)
    return {'saved':True,'feedback_count':len(FEEDBACK),'message':'Feedback recorded.'}

@app.get('/v1/feedback/summary')
def feedback_summary():
    try: items=[json.loads(x) for x in redis_conn.lrange('feedback',0,-1)]
    except Exception: items=FEEDBACK
    return {'count':len(items),'satisfactory':sum(1 for x in items if x['satisfactory']),'unsatisfactory':sum(1 for x in items if not x['satisfactory'])}

@app.get('/',response_class=HTMLResponse)
def home():
    return open(os.path.join(os.path.dirname(__file__),'..','frontend','index.html'),encoding='utf-8').read()
