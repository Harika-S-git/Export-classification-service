import asyncio,os
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST,Counter
from .config import settings
from .contracts import StubRequest,StubResponse
from .telemetry import setup,step
app=FastAPI(title='Delayed model stub',version='1.0.0');setup('provider-stub')
CALLS=Counter('stub_requests','Stub requests')
@app.get('/health')
def health():return {'status':'ok','mode':'stub'}
@app.get('/metrics')
def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
@app.post('/generate',response_model=StubResponse)
async def generate(request: StubRequest):
    body=request.model_dump();CALLS.inc();s=settings();fault=body.get('fault','none') if s.enable_faults else s.stub_fault
    await asyncio.sleep(s.stub_delay)
    if fault=='provider_down':raise HTTPException(503,'injected provider outage')
    if fault=='timeout':await asyncio.sleep(s.call_timeout+1)
    candidates=body.get('candidates',[]);answer={'heading':candidates[0]['heading'] if candidates else None}
    if fault=='unsupported':answer={'heading':'9999'}
    return {'answer':answer,'usage':{'prompt_tokens':len(str(body))//4,'completion_tokens':12},'provider':'delayed-stub'}

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
FastAPIInstrumentor.instrument_app(app)
