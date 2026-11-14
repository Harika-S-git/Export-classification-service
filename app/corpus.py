"""Local LangChain embeddings and FAISS; immutable citation text, incremental cache."""
import hashlib, json, os, re, time, threading
from pathlib import Path
import numpy as np
import faiss
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from .config import settings

class LocalEmbeddings(Embeddings):
    version='hash-word-char-v2-768'
    def embed_query(self,text):
        v=np.zeros(768,dtype=np.float32)
        words=re.findall(r'[a-z0-9]+',text.lower())
        features=words+[w[i:i+3] for w in words for i in range(max(0,len(w)-2))]
        for f in features:
            n=int.from_bytes(hashlib.sha256(f.encode()).digest()[:4],'little');v[n%768]+=1 if n&1024 else -1
        norm=np.linalg.norm(v)
        return (v/max(norm,1e-9)).tolist()
    def embed_documents(self,texts):return [self.embed_query(t) for t in texts]

LOCK=threading.Lock()
def build(force=False):
    s=settings();root=Path(s.data_dir);root.mkdir(parents=True,exist_ok=True)
    records=json.loads((Path(s.corpus_dir)/'clauses.json').read_text())
    raw=json.dumps(records,sort_keys=True).encode(); digest=hashlib.sha256(raw+LocalEmbeddings.version.encode()).hexdigest()
    manifest=root/'manifest.json'
    if manifest.exists() and json.loads(manifest.read_text())['digest']==digest and not force:return json.loads(manifest.read_text())
    start=time.monotonic(); emb=LocalEmbeddings();cache=root/'embeddings';cache.mkdir(exist_ok=True)
    vectors=[];new=0
    for r in records:
        r['sha256']=hashlib.sha256(r['text'].encode()).hexdigest()
        key=hashlib.sha256((r['text']+emb.version).encode()).hexdigest();p=cache/(key+'.npy')
        if p.exists() and not force:v=np.load(p)
        else:
            v=np.array(emb.embed_query(r['text']),dtype=np.float32);np.save(p,v);new+=1
        vectors.append(v)
    index=faiss.IndexFlatIP(768);index.add(np.array(vectors))
    gen=root/digest;gen.mkdir(exist_ok=True)
    faiss.write_index(index,str(gen/'index.faiss'));(gen/'records.json').write_text(json.dumps(records))
    m={'digest':digest,'built_at':time.time(),'chunks':len(records),'new_embeddings':new,'embedding':emb.version,'chunks_per_second':len(records)/max(time.monotonic()-start,.001),'sources':json.loads((Path(s.corpus_dir)/'sources.json').read_text())}
    tmp=root/'manifest.tmp';tmp.write_text(json.dumps(m,indent=2));os.replace(tmp,manifest)
    return m

class Corpus:
    def __init__(self):
        s=settings();root=Path(s.data_dir);m=json.loads((root/'manifest.json').read_text());gen=root/m['digest']
        self.manifest=m;self.records=json.loads((gen/'records.json').read_text());self.by_id={r['id']:r for r in self.records}
        self.index=faiss.read_index(str(gen/'index.faiss'));self.emb=LocalEmbeddings()
    def search(self,query,k=8,kind=None):
        _,ids=self.index.search(np.array([self.emb.embed_query(query)],dtype=np.float32),len(self.records))
        ranked=[self.records[i] for i in ids[0] if i>=0 and (not kind or self.records[i]['kind']==kind)]
        # Article-name lexical boost complements local vector similarity.
        q=set(re.findall('[a-z]+',query.lower()))
        ranked.sort(key=lambda r:len(q & set(r.get('keywords',[])))*3+len(q & set(re.findall('[a-z]+',r['text'].lower())))/20,reverse=True)
        return ranked[:k]
    def lookup(self,ident):return self.by_id.get(ident)

class TariffRetriever(BaseRetriever):
    model_config={'arbitrary_types_allowed':True}
    corpus: Corpus
    def _get_relevant_documents(self,query,*,run_manager):
        return [Document(page_content=r['text'],metadata=r) for r in self.corpus.search(query)]
