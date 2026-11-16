import os,uuid
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('VERIFIER_URL','http://localhost:8001')
os.environ.setdefault('PROVIDER_URL','http://localhost:8002')
os.environ.setdefault('DATA_DIR','.local-data')
from app.verifier import check
from app.corpus import build,Corpus
from unittest.mock import patch

def request():
 build();corpus=Corpus()
 return {'request':{'run_id':str(uuid.uuid4()),'product':{'description':'Stainless steel vacuum flask with plastic body','capacity_l':1},'proposed':{'heading':'9617'},'evidence':list(corpus.records),'prompt_version':'v2','fault':'none'}}
def test_citation_tamper_rejected():
 s=request();s['request']['evidence'][0]={**s['request']['evidence'][0],'text':'forged'}
 assert check(s)['valid'] is False
def test_unretrieved_heading_rejected():
 s=request();s['request']['proposed']['heading']='9999'
 with patch('app.verifier.event'):assert check(s)['valid'] is False
def test_named_heading_passes():
 s=request()
 with patch('app.verifier.event'):assert check(s)['valid'] is True
def test_medical_intended_use_escalates():
 s=request();s['request']['product']['intended_use']='For medical use'
 with patch('app.verifier.event'):assert check(s)['heading'] is None
def test_animal_origin_condition_escalates():
 s=request();s['request']['product']['description']='Bone buttons for garments';s['request']['proposed']['heading']='9606'
 with patch('app.verifier.event'):assert check(s)['heading'] is None
def test_unproposed_heading_escalates():
 s=request();s['request']['proposed']['heading']=None
 with patch('app.verifier.event'):
     r=check(s)
     assert r['valid'] is True
     assert r['heading'] is None
