"""RQ worker with parent metrics endpoint. Steps are reconstructed from Redis events.
Forked task Prometheus counters are not scraped as parent counters: aggregate audit
records instead, so scaling and RQ child exits do not silently drop measurements.
"""
import os,time,json,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from rq import Worker
from prometheus_client import generate_latest,CollectorRegistry,Gauge,Histogram
from .config import settings
from .store import db
# Preload graph modules before fork to avoid per-job Python import overhead.
from .jobs import execute

def audit_metrics():
    r=db();registry=CollectorRegistry();ridkeys=list(r.scan_iter('run:*'))[-2000:]
    latency=Histogram('worker_run_seconds','End to end run latency',registry=registry,buckets=(1,2,3,5,10,20,30,45,60,120))
    tasks=Gauge('worker_agent_tasks','Agent outcomes',['agent','outcome'],registry=registry)
    tools=Gauge('worker_agent_tool_calls','Tools',['agent'],registry=registry)
    steps=Gauge('worker_agent_steps','Steps',['agent'],registry=registry)
    retries=Gauge('worker_agent_retries','Retries',['agent'],registry=registry)
    cost=Gauge('worker_agent_cost_usd','Cost',['agent'],registry=registry)
    step_latency=Histogram('worker_step_seconds','Step duration',['agent','step'],registry=registry)
    counts={};tc={};sc={};rc={};cc={}
    for key in ridkeys:
        row=r.hgetall(key);d=json.loads(row.get('duration_seconds','null'))
        if d is not None:latency.observe(d)
        for raw in r.lrange('events:'+key[4:],0,-1):
            e=json.loads(raw);a=e['agent']
            if e['action']=='step':
                sc[a]=sc.get(a,0)+1;step_latency.labels(a,e['step']).observe(e['latency'])
            if e['action']=='tool':tc[a]=tc.get(a,0)+1
            if e['action']=='provider_failure':rc[a]=rc.get(a,0)+1
            if e['action']=='model':cc[a]=cc.get(a,0)+e['cost_usd']
            if e['action']=='verification':
                k=(a,'success' if e['supported'] else 'rejected');counts[k]=counts.get(k,0)+1
            if e['action']=='terminal':
                k=(a,e['status']);counts[k]=counts.get(k,0)+1
    for (a,o),v in counts.items():tasks.labels(a,o).set(v)
    for metric,data in [(tools,tc),(steps,sc),(retries,rc),(cost,cc)]:
        for a,v in data.items():metric.labels(a).set(v)
    Gauge('worker_queue_depth','Queued requests',registry=registry).set(r.llen('rq:queue:classification'))
    Gauge('worker_container_uptime_seconds','Worker uptime',registry=registry).set(time.time()-START)
    return generate_latest(registry)
START=time.time()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body=audit_metrics() if self.path=='/metrics' else b'ok' if db().ping() else b'error'
            self.send_response(200);self.end_headers();self.wfile.write(body)
        except Exception:self.send_response(503);self.end_headers()
    def log_message(self,*args):pass
if __name__=='__main__':
    threading.Thread(target=HTTPServer(('0.0.0.0',9100),Handler).serve_forever,daemon=True).start()
    from redis import Redis
    Worker(['classification'],connection=Redis.from_url(settings().redis_url),name=os.getenv('HOSTNAME','worker')).work()
