import json,time
import httpx
from .config import settings
from .store import db,event
from .telemetry import RETRIES,TOKENS,COST,CIRCUIT

class ProviderUnavailable(Exception):pass
class Provider:
    """Shared Redis breaker; half-open probe is single-flight across replicas."""
    def call(self,run_id,agent,request):
        s=settings();r=db();now=time.time();opened=float(r.get('breaker:until') or 0)
        if opened>now:CIRCUIT.set(1);raise ProviderUnavailable('circuit_open')
        probe=False
        if opened:
            probe=bool(r.set('breaker:probe','1',nx=True,ex=10))
            if not probe:raise ProviderUnavailable('half_open_probe_busy')
        try:
            for attempt in range(s.max_retries+1):
                started=time.monotonic()
                try:
                    if s.provider_mode=='stub':
                        payload=request;path='/generate';headers={}
                    else:
                        if not s.provider_model: raise ProviderUnavailable('model_not_configured')
                        prompt=open('prompts/'+request['prompt_version']+'.txt').read()
                        payload={'model':s.provider_model,'messages':[{'role':'system','content':prompt},{'role':'user','content':json.dumps(request)}],'temperature':0,'max_tokens':150,'response_format':{'type':'json_object'}}
                        path='/chat/completions';headers={'Authorization':'Bearer '+s.provider_api_key}
                    from opentelemetry.propagate import inject
                    carrier={**headers,'X-Correlation-ID':run_id};inject(carrier)
                    with httpx.Client(timeout=s.call_timeout,trust_env=False) as c:
                        response=c.post(s.provider_url.rstrip('/')+path,json=payload,headers=carrier);response.raise_for_status();data=response.json()
                    if s.provider_mode!='stub':
                        data={'answer':json.loads(data['choices'][0]['message']['content']),'usage':data.get('usage',{}),'provider':s.provider_mode}
                    usage=data.get('usage',{});pt=int(usage.get('prompt_tokens',0));ct=int(usage.get('completion_tokens',0))
                    price=(pt*s.token_input_price+ct*s.token_output_price)/1000000 if s.provider_mode!='stub' else 0
                    TOKENS.labels(agent,'prompt').inc(pt);TOKENS.labels(agent,'completion').inc(ct);COST.labels(agent).inc(price)
                    event(run_id,agent,'model',attempt=attempt,prompt_version=request['prompt_version'],prompt_artifact='prompts/'+request['prompt_version']+'.txt',request=request,answer=data['answer'],prompt_tokens=pt,completion_tokens=ct,cost_usd=price,latency=time.monotonic()-started,usage_kind='reported' if s.provider_mode!='stub' else 'stub_estimate',usage_complete=('prompt_tokens' in usage and 'completion_tokens' in usage),provider_mode=s.provider_mode,model=s.provider_model if s.provider_mode!='stub' else 'deterministic-stub',pricing_per_million={'input':s.token_input_price,'output':s.token_output_price})
                    r.delete('breaker:failures','breaker:until');CIRCUIT.set(0)
                    return data['answer']
                except (httpx.HTTPError,ValueError,KeyError) as e:
                    failures=r.incr('breaker:failures');r.expire('breaker:failures',60)
                    event(run_id,agent,'provider_failure',attempt=attempt,error=type(e).__name__,latency=time.monotonic()-started)
                    if failures>=3:r.set('breaker:until',time.time()+15,ex=30);CIRCUIT.set(1)
                    if attempt>=s.max_retries or failures>=3:raise ProviderUnavailable(type(e).__name__) from e
                    RETRIES.labels(agent).inc();time.sleep(.15*2**attempt)
        finally:
            if probe:r.delete('breaker:probe')
