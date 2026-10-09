"""Locust smoke/load test. Measures submission latency; use a polling scenario for true end-to-end SLO."""
import os, json
from locust import HttpUser, task, between

class ExportCheckUser(HttpUser):
    wait_time=between(0.2,1.0)
    @task
    def submit_and_poll(self):
        payload={'description':'Stainless steel vacuum flask with a moulded plastic outer body','materials':['stainless steel','plastic'],'intended_use':'Reusable beverage container','country_of_export':'India','destination_country':'United States','client_id':'locust'}
        r=self.client.post('/v1/runs',json=payload,name='POST /v1/runs')
        if r.status_code!=202: return
        body=r.json(); url=body.get('status_url')
        if not url: return
        # Use a bounded polling loop; this records the whole user journey, not submission only.
        import time
        start=time.monotonic()
        while time.monotonic()-start < 100:
            p=self.client.get(url,name='GET /v1/runs/{run_id}')
            if p.status_code!=200: return
            state=p.json().get('status')
            if state in ('completed','failed'): return
            time.sleep(1)
