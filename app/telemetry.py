import json, logging, os, time
from contextlib import contextmanager
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logging.basicConfig(level=logging.INFO, format='%(message)s')
TASKS = Counter('agent_tasks', 'Agent tasks', ['agent', 'outcome'])
STEPS = Counter('agent_steps', 'Steps', ['agent'])
TOOLS = Counter('agent_tool_calls', 'Tool calls', ['agent','tool'])
LATENCY = Histogram('agent_step_seconds', 'Step latency', ['agent','step'])
RUN = Histogram('run_seconds', 'Submission to terminal duration', buckets=(1,2,3,5,10,15,20,30,45,60,120))
RETRIES = Counter('provider_retries', 'Retried provider requests', ['agent'])
TOKENS = Counter('llm_tokens', 'Provider-reported tokens', ['agent','kind'])
COST = Counter('llm_cost_usd', 'Actual configured cost', ['agent'])
CACHE = Counter('cache_access', 'Cache hits/misses', ['result'])
REJECTS = Counter('ingestion_rejects', 'Quarantined input')
START = time.time()
UPTIME = Gauge('service_uptime_seconds', 'Process uptime')
UPTIME.set_function(lambda: time.time()-START)
FRESH = Gauge('corpus_built_timestamp_seconds', 'Index build timestamp')
CHUNKS = Gauge('corpus_chunks', 'Index chunks')
PIPELINE = Gauge('corpus_chunks_per_second', 'Last pipeline throughput')
CIRCUIT = Gauge('provider_circuit_open', 'Provider breaker open')
tracer = trace.get_tracer('export-check')

def setup(service):
    from .config import settings
    endpoint=settings().otel_exporter_otlp_endpoint
    if endpoint:
        p=TracerProvider(resource=Resource.create({'service.name':service, 'service.instance.id':os.getenv('HOSTNAME','local')}))
        p.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint.rstrip('/')+'/v1/traces',timeout=3)))
        trace.set_tracer_provider(p)
    global tracer
    tracer=trace.get_tracer(service)

def log(event, **fields):
    logging.info(json.dumps({'event':event,'timestamp':time.time(),**fields},default=str))

@contextmanager
def step(agent, name, run_id):
    started=time.monotonic()
    with tracer.start_as_current_span(name) as span:
        span.set_attribute('run.id',run_id); span.set_attribute('agent.name',agent)
        try: yield span
        finally:
            elapsed=time.monotonic()-started
            STEPS.labels(agent).inc(); LATENCY.labels(agent,name).observe(elapsed)
            from .store import event
            event(run_id,agent,'step',step=name,latency=elapsed)
