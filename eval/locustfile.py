"""Locust measures complete run, not POST latency. Each user polls one in-flight run."""
import time,uuid,os
from locust import HttpUser,task,between,events
class Analyst(HttpUser):
    wait_time=between(.05,.15)
    @task
    def classify(self):
        start=time.perf_counter();error=None
        try:
            r=self.client.post('/v1/runs',json={'product':{'description':'Stainless steel vacuum flask with a plastic body','capacity_l':1},'cache':False,'nonce':uuid.uuid4().hex},headers={'X-Client-ID':str(id(self))},name='submission')
            r.raise_for_status();rid=r.json()['run_id']
            while time.perf_counter()-start<180:
                j=self.client.get('/v1/runs/'+rid,name='poll').json()
                if j.get('status') in ('completed','escalated'):
                    if j['status']=='escalated':error=RuntimeError('Run escalated')
                    break
                time.sleep(.2)
            else:error=TimeoutError('No terminal run within 180s')
        except Exception as exc:error=exc
        events.request.fire(request_type='RUN',name='complete_run',response_time=(time.perf_counter()-start)*1000,response_length=0,exception=error)
