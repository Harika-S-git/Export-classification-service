import hashlib,json
from pathlib import Path
from app.entities import extract
from app.corpus import LocalEmbeddings

def test_immutable_corpus():
 records=json.loads(Path('corpus/clauses.json').read_text());ids={r['id'] for r in records}
 assert {'GRI1','GRI2','GRI3','GRI6','H9617','H7323','N15','N96','P9617'}<=ids
 for r in records:assert hashlib.sha256(r['text'].encode()).hexdigest()==r['sha256']
 h=next(r for r in records if r['id']=='H9617');assert 'VACUUM' in h['text']
 assert len({r['id'] for r in records})==len(records)
def test_flask_not_material():
 e=extract({'description':'Stainless steel vacuum flask with plastic outer body'})
 assert e['articles']==['vacuum flask'];assert 'steel' in e['materials']
def test_glass_exclusion():assert extract({'description':'Glass inner for vacuum flask'})['articles']==['glass inner']
def test_embeddings_deterministic():
 emb=LocalEmbeddings();assert emb.embed_query('vacuum flask')==emb.embed_query('vacuum flask')
 assert len(emb.embed_query('test'))==768
def test_known_outside_article():
 assert extract({'description':'A laptop computer with metal shell'})['articles']==['out-of-scope article']
