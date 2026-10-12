import os, uuid, json, logging, re, time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, model_validator
from redis import Redis
from rq import Queue
from prometheus_client import REGISTRY, generate_latest, CONTENT_TYPE_LATEST
from prometheus_client.core import CounterMetricFamily
from app.core import (
    RUNS,
    VERIFICATION_METRIC_KEY,
    VERIFICATION_METRIC_OUTCOMES,
    run_classification,
    REQUESTS,
    logger,
)
from app.guardrails import inspect_free_text

logging.basicConfig(level=os.getenv('LOG_LEVEL','INFO'), format='%(message)s')
app=FastAPI(title='Export Classification Check Service',version='1.0.0',description='Evidence-first proposed tariff classification; human review remains authoritative.')
redis_conn=Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'),socket_connect_timeout=2,socket_timeout=2)
queue=Queue('classification',connection=redis_conn,default_timeout=int(os.getenv('RUN_TIMEOUT_SECONDS','90')))
QUARANTINE=[]; FEEDBACK=[]; RATE={}


class RedisVerificationCollector:
    """Expose worker verification counters stored in the shared Redis hash."""

    def __init__(self, redis_client):
        self.redis_client = redis_client

    @staticmethod
    def _metric():
        return CounterMetricFamily(
            'export_verification',
            'Outcomes of evidence verification across RQ worker processes.',
            labels=['outcome'],
        )

    def describe(self):
        return [self._metric()]

    def collect(self):
        values = self.redis_client.hgetall(VERIFICATION_METRIC_KEY)
        metric = self._metric()
        decoded_values = {
            key.decode() if isinstance(key, bytes) else str(key):
            int(value)
            for key, value in values.items()
        }
        for outcome in VERIFICATION_METRIC_OUTCOMES:
            metric.add_metric([outcome], decoded_values.get(outcome, 0))
        yield metric


REGISTRY.register(RedisVerificationCollector(redis_conn))


def quarantine(record: dict):
    QUARANTINE.append(record)
    del QUARANTINE[:-500]
    try:
        redis_conn.lpush('quarantine', json.dumps(jsonable_encoder(record)))
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
        limit=max(1,int(os.getenv('RATE_LIMIT_PER_MINUTE','10')))
        if len(times)>=limit:
            retry_after=max(1,int(60-(now-min(times)))) if times else 1
            return Response('Rate limit exceeded',status_code=429,headers={'Retry-After':str(retry_after)})
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

@app.get('/live')
def live():
    return {'status':'ok','timestamp':datetime.now(timezone.utc).isoformat()}

@app.get('/ready')
def ready():
    try:
        redis_conn.ping()
        from rq import Worker
        worker_count = Worker.count(connection=redis_conn)
        q_depth = queue.count if hasattr(queue, 'count') and isinstance(queue.count, int) else 0
        w_count = worker_count if isinstance(worker_count, int) else 0
        return {
            'status': 'ready',
            'redis': 'ok',
            'queue': str(getattr(queue, 'name', 'classification')),
            'queue_depth': q_depth,
            'active_workers': w_count,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    except Exception as exc:
        logger.warning(json.dumps({'event':'readiness_check_failed','error':str(exc)}))
        return Response(
            json.dumps({'status':'not_ready','redis':'unavailable','timestamp':datetime.now(timezone.utc).isoformat()}),
            status_code=503,
            media_type='application/json'
        )

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

    idem_key = request.headers.get('X-Idempotency-Key')
    if idem_key:
        try:
            cached_id = redis_conn.get(f'idempotency:{idem_key}')
            if cached_id:
                cached_rid = cached_id.decode('utf-8') if isinstance(cached_id, bytes) else str(cached_id)
                logger.info(json.dumps({'event':'idempotent_replay','run_id':cached_rid,'idempotency_key':idem_key,'correlation_id':request.state.correlation_id}))
                return {'run_id':cached_rid,'status_url':f'/v1/runs/{cached_rid}','status':'queued','idempotent_replay':True}
        except Exception:
            pass

    rid=str(uuid.uuid4())
    try:
        job=queue.enqueue('app.core.run_classification',payload,rid,job_timeout=int(os.getenv('RUN_TIMEOUT_SECONDS','90')),result_ttl=86400,failure_ttl=86400)
        # Persist the public run ID mapping independently of the RQ job registry.
        # RQ may expire finished jobs from its registry before clients stop polling.
        redis_conn.setex(f'run-job:{rid}', 86400, job.id)
        if idem_key:
            try:
                redis_conn.setex(f'idempotency:{idem_key}', 86400, rid)
            except Exception:
                pass
        job.meta['public_run_id']=rid
        job.save_meta()
        logger.info(json.dumps({'event':'run_submitted','run_id':rid,'correlation_id':request.state.correlation_id,'job_id':job.id}))
        return {'run_id':rid,'status_url':f'/v1/runs/{rid}','queue_job_id':job.id,'status':'queued'}
    except Exception as exc:
        # Graceful local fallback if Redis/worker is unavailable: do not block the submit API with model work.
        raise HTTPException(503,detail='Queue unavailable; no agent run started. Check Redis and worker health.') from exc

@app.get('/v1/runs/{run_id}')
def get_run(run_id: str):
    # In-process cache is useful in tests and single-process deployments.
    if run_id in RUNS:
        return RUNS[run_id]
    try:
        cached=redis_conn.get(f'run-result:{run_id}')
        if cached:
            return json.loads(cached)
    except Exception:
        logger.exception('Could not read cached run result')

    # Public run IDs are intentionally distinct from RQ job IDs. Resolve the
    # durable mapping first; never assume Job.fetch(run_id) is correct.
    try:
        mapped=redis_conn.get(f'run-job:{run_id}')
        if isinstance(mapped, bytes):
            mapped=mapped.decode('utf-8')
        if mapped:
            from rq.job import Job
            job=Job.fetch(str(mapped), connection=redis_conn)
            status=job.get_status(refresh=True)
            status_value=status.value if hasattr(status, 'value') else str(status)
            if status_value == 'finished':
                # The worker stores the complete result under the public run ID.
                cached=redis_conn.get(f'run-result:{run_id}')
                if cached:
                    return json.loads(cached)
                result=job.result
                if isinstance(result, dict):
                    return result
                return {'run_id':run_id,'status':'completed','result':result}
            if status_value == 'failed':
                return {'run_id':run_id,'status':'failed','recommendation':'specialist-classification-review',
                        'proposed_hs_code':None,'verification_passed':False,
                        'rationale':'The background job failed. No classification is asserted.'}
            return {'run_id':run_id,'status':status_value}
    except Exception:
        logger.exception(json.dumps({'event':'run_status_lookup_failed','run_id':run_id}))

    # Compatibility fallback for runs submitted before the mapping was added.
    try:
        for job in queue.get_jobs():
            if len(job.args)>1 and job.args[1]==run_id:
                if job.is_finished:
                    cached=redis_conn.get(f'run-result:{run_id}')
                    if cached:
                        return json.loads(cached)
                    if isinstance(job.result, dict):
                        return job.result
                return {'run_id':run_id,'status':str(job.get_status())}
    except Exception:
        logger.exception('Legacy run lookup failed')

    # A mapping/result can be temporarily unavailable during worker startup.
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
