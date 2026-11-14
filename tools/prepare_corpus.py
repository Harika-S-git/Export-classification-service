"""Reproducibly extract only permitted scope; source PDFs already downloaded.
No network or model needed at service startup. Pages are physical, 1-based.
"""
from pathlib import Path
import re,json,hashlib
from pypdf import PdfReader,PdfWriter
ROOT=Path('corpus');RAW=ROOT/'raw';records=[];sources=[]
def source(name,url,version,remark=''):
    p=RAW/name;r=PdfReader(p)
    sources.append({'file':name,'url':url,'version':version,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'pages':len(r.pages),'retrieved_at':'2026-11-13','remark':remark})
    return r
cbic=source('cbic-tariff-2022.pdf','https://taxbykk.com/wp-content/uploads/2023/03/HSN-Code-wef-01.01.2022.pdf','CBIC Customs Tariff effective 2022-01-01','CBIC-authored document obtained from a third-party mirror because CBIC returned HTTP 503. Historical; not confirmed current.')
dgft=source('Notification_ITCHS.pdf','https://content.dgft.gov.in/Website/Notification_ITCHS.pdf','ITC(HS) 2022 Schedule II, snapshot downloaded 2026-11-13','No assertion that all later amendments are consolidated.')
general=source('General%20Note%20on%20Export%20Policy.pdf','https://content.dgft.gov.in/Website/General%20Note%20on%20Export%20Policy.pdf','ITC(HS) 2022 general notes')
gri=source('gri-2022.pdf','https://www.wcoomd.org/-/media/wco/public/global/pdf/topics/nomenclature/instruments-and-tools/hs-nomenclature-2022/2022/0001_2022e-gir.pdf?la=en','WCO HS 2022 GRI','Authoritative HS rules used as substitute; CBIC-hosted GRI download unavailable. Corpus confirmation remains an Evaluation 1 task.')
def add(ident,text,kind,src,page,**kw):
    text=text.strip();assert text
    records.append({'id':ident,'text':text,'kind':kind,'source':src,'page':page,'sha256':hashlib.sha256(text.encode()).hexdigest(),**kw})
# Keep page-aligned chunks (at most ~1,500 words); canonical focused clauses below.
cache=ROOT/'cbic-pages.json'
cached=json.loads(cache.read_text()) if cache.exists() else {}
if isinstance(cached,dict) and cached.get('sha256')==sources[0]['sha256']:texts=cached['pages']
else:
    texts=[(p.extract_text() or '') if i in set(range(550,612)) | set(range(818,826)) else '' for i,p in enumerate(cbic.pages)]
    cache.write_text(json.dumps({'sha256':sources[0]['sha256'],'pages':texts}))
for i,t in enumerate(texts):
    if 'CHAPTER-73' in t or 'CHAPTER-96' in t or ('SECTION XV' in t and 'BASE METALS' in t):
        for j in range(0,len(t),4500):add(f'CBIC-P{i+1}-{j//4500}',t[j:j+4500],'context','cbic-tariff-2022.pdf',i+1)
# Section XV spans several pages; retain the whole notes, not only the exclusion.
sec=next(i for i,t in enumerate(texts) if 'SECTION XV' in t and 'BASE METALS' in t)
add('N15','\n'.join(texts[sec:sec+3]).split('CHAPTER 72')[0],'note','cbic-tariff-2022.pdf',sec+1)
add('N73',texts[599],'note','cbic-tariff-2022.pdf',600)
add('N96',texts[818],'note','cbic-tariff-2022.pdf',819)
# Headings are exact extracts up to first subordinate tariff line; metadata is our annotation.
annotations={
'7307':['pipe fitting'],'7315':['chain'],'7317':['nail'],'7318':['screw','bolt','nut'],
'7319':['sewing needle'],'7323':['tableware','scouring pad'],'7326':[],
'9603':['toothbrush'],'9606':['button'],'9607':['slide fastener'],'9608':['ball point pen'],
'9609':['pencil'],'9615':['comb'],'9617':['vacuum flask'],'7310':['container']}
for heading,articles in annotations.items():
    found=None
    for i,t in enumerate(texts):
        if not ('CHAPTER-73' in t or 'CHAPTER-96' in t):continue
        m=re.search(r'(?m)^\s*'+heading+r'[ \t]*(?:\n|(?=[A-Z]))',t)
        if m:
            rest=t[m.start():];end=re.search(r'(?m)^\s*(?!'+heading+r')\d{4}[ \t]+[A-Z]',rest)
            text=rest[:end.start()] if end and end.start()>5 else rest[:4000]
            # Heading may contain an inline code layout; cap at next heading.
            add('H'+heading,text,'heading','cbic-tariff-2022.pdf',i+1,heading=heading,articles=articles,keywords=re.findall('[a-z]+',' '.join(articles)));found=True;break
    if not found:raise RuntimeError('Heading not found '+heading)
# Policy chunks start at the relevant heading and include all its subordinate rows,
# including continuations across pages, with exact source text and page anchor.
dcache=ROOT/'dgft-pages.json'
dcached=json.loads(dcache.read_text()) if dcache.exists() else {}
if isinstance(dcached,dict) and dcached.get('sha256')==sources[1]['sha256']:dtexts=dcached['pages']
else:
    dtexts=[p.extract_text(extraction_mode='layout') or '' for p in dgft.pages]
    dcache.write_text(json.dumps({'sha256':sources[1]['sha256'],'pages':dtexts}))
for h in annotations:
    chap=h[:2];combined='';startpage=0;active=False
    for i,t in enumerate(dtexts):
        lines=t.splitlines()
        for line in lines:
            m=re.match(r'^\s*\d{1,2}\s+(\d{4,8})\s+',line)
            if m and len(m.group(1))==4:
                if m.group(1)==h:active=True;startpage=i+1
                elif active:active=False;break
            if active:combined+=line+'\n'
        if startpage and not active:break
    combined=re.split(r'Section [XVI]+,',combined)[0]
    combined=re.split(r'CHAPTER\s+(?!'+chap+r')\d{2}\b',combined)[0]
    if not combined:raise RuntimeError('Policy not found '+h)
    statuses=set(re.findall(r'\b(Free|Restricted|Prohibited|STE)\b',combined))
    policy='Free' if statuses=={'Free'} else '/'.join(sorted(statuses)) or 'unconfirmed'
    add('P'+h,combined,'policy','Notification_ITCHS.pdf',startpage,heading=h,policy=policy)
for i,t in enumerate(dtexts):
    if re.search(r'CHAPTER\s+(73|96)\b',t) or 'Section XV, BASE METALS' in t:
        add('DGFT-NOTES-'+str(i+1),re.split(r'CHAPTER\s+(?:73|96)',t,maxsplit=1)[-1],'context','Notification_ITCHS.pdf',i+1)
add('POLICY-GENERAL','\n'.join(p.extract_text() or '' for p in general.pages[1:3]),'policy','General%20Note%20on%20Export%20Policy.pdf',2)
t='\n'.join(p.extract_text() or '' for p in gri.pages)
for n in range(1,7):
    m=re.search(r'(?m)^\s*'+str(n)+r'\.\s',t); nxt=re.search(r'(?m)^\s*'+str(n+1)+r'\.\s',t)
    add('GRI'+str(n),t[m.start():nxt.start() if nxt else len(t)],'rule','gri-2022.pdf',1)
add('SCOPE','Project service scope: Customs Tariff Chapters 73 and 96 only. Unsupported articles and unresolved equal support after GRI 3 require specialist classification review. No filing, duties or shipping documentation.','scope','project-scope',1)
(ROOT/'clauses.json').write_text(json.dumps(records,indent=2));(ROOT/'sources.json').write_text(json.dumps(sources,indent=2))
print('Prepared',len(records),'clauses')
# Distribute scoped extracts instead of the out-of-scope full tariff and schedule.
for name,reader,indices in [('cbic-scoped.pdf',cbic,sorted(set([0]+list(range(sec,sec+3))+list(range(599,612))+list(range(818,826))))),('dgft-scoped.pdf',dgft,[i for i,t in enumerate(dtexts) if re.search(r'(?m)^\s*(73|96)\s+\d',t) or re.search(r'CHAPTER\s+(73|96)\b',t)])]:
    w=PdfWriter()
    for i in indices:w.add_page(reader.pages[i])
    with (ROOT/name).open('wb') as f:w.write(f)
