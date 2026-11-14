import hashlib,json,time
from .config import settings
from .store import db,get_run,put_run,event,events
from .contracts import Recommendation,safe_text
from .telemetry import setup,RUN,step
from .agents import ClassifierAgent,escalation

_INITIALIZED=False
def execute(rid,submission):
    global _INITIALIZED
    if not _INITIALIZED:setup('classifier-worker');_INITIALIZED=True
    from opentelemetry.context import attach,detach
    from opentelemetry.propagate import extract
    context_token=attach(extract(get_run(rid).get('trace_context',{})))
    start=time.time();put_run(rid,status='running',started_at=start)
    try:
        with step('classifier','run',rid):
            result=ClassifierAgent().run(rid,submission)
        for field in ('basis','export_policy'):safe_text(result[field])
        # Only structured templates reach the public output; no arbitrary model prose.
        audit=events(rid);calls=[e for e in audit if e['action']=='model']
        result.update(cost_usd=sum(e['cost_usd'] for e in calls),prompt_tokens=sum(e['prompt_tokens'] for e in calls),completion_tokens=sum(e['completion_tokens'] for e in calls))
        result=Recommendation.model_validate(result).model_dump()
        key=cache_key(submission)
        if result['verified'] and submission['cache'] and settings().cache_enabled and submission['fault']=='none':db().set('cache:'+key,json.dumps(result),ex=settings().cache_ttl)
        terminal='completed' if result['verified'] else 'escalated'
    except Exception as exc:
        event(rid,'classifier','failure',error=type(exc).__name__,message=str(exc)[:300])
        result=Recommendation.model_validate(escalation({'version':submission['prompt_version']},'Run failed safely: '+type(exc).__name__)).model_dump();terminal='escalated'
    done=time.time();submitted=get_run(rid)['submitted_at'];RUN.observe(done-submitted)
    put_run(rid,status=terminal,result=result,finished_at=done,duration_seconds=done-submitted)
    event(rid,'classifier','terminal',status=terminal,latency=done-submitted)
    if int(rid.replace('-','')[:8],16)%settings().quality_sample_every==0:
        # Evidence quality proxy, not a claim of legal correctness.
        from .quality import score_live
        db().rpush('quality',json.dumps({'run_id':rid,'timestamp':done,**score_live(result)}))
    from opentelemetry import trace
    provider=trace.get_tracer_provider()
    if hasattr(provider,'force_flush'):provider.force_flush(timeout_millis=2000)
    detach(context_token)
    return terminal

def cache_key(submission):
    from .corpus import Corpus
    key={'product':submission['product'],'version':submission['prompt_version'],'corpus':Corpus().manifest['digest'],'mode':settings().provider_mode,'provider_configuration':hashlib.sha256((settings().provider_url+settings().provider_model).encode()).hexdigest(),'policy_confirmed':settings().policy_snapshot_confirmed,'nonce':submission['nonce']}
    return hashlib.sha256(json.dumps(key,sort_keys=True).encode()).hexdigest()
