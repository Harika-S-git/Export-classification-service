"""Build the final plain report, PDF, architecture and presentation from measured files."""
import json,csv,re,html,math
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4,landscape
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,KeepTogether
from reportlab.graphics.shapes import Drawing,Rect,String,Line,Polygon
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

ROOT=Path('.');e=json.loads(Path('results/evaluation.json').read_text());cache=json.loads(Path('results/cache-benchmark.json').read_text())
load=json.loads(Path('results/load-summary.json').read_text());profile=json.loads(Path('results/load-profile.json').read_text()) if Path('results/load-profile.json').exists() else {}
v1=e['summary']['v1'];v2=e['summary']['v2'];uc=cache['summary']['uncached'];wc=cache['summary']['warm_cached'];gain=(1-wc['p95_seconds']/uc['p95_seconds'])*100
metricrows='\n'.join('| '+m.replace('_',' ').title()+f' | {v1[m]:.4f} | {v2[m]:.4f} | {v2[m]-v1[m]:+.4f} |' for m in ['accuracy','groundedness','context_relevance','faithfulness','hallucination_rate'])
loadrows='\n'.join(f"| {r['workers']} | {r['clients']} | {r['n']} | {r['failures']} | {r['rps']:.3f} | {r['p50_seconds']:.1f} | {r['p95_seconds']:.1f} | {'Yes' if r['slo_met'] else 'No'} |" for r in load['rows'])
breaks={w:min((r['clients'] for r in load['rows'] if r['workers']==w and not r['slo_met']),default=None) for w in [1,3]}
report=f'''# Export Classification Check Service — Final Report
Course UE24AM342AA5 · Mini Project 07 · Logistics and Trade Compliance
Prepared 13 November 2026. Team names and SRNs: fill docs/TEAM.md.

## Problem and scope
Export misclassification can delay consignments and attract penalties. The system
accepts a product description and returns a proposed tariff classification,
retrieved evidence, snapshot export policy and one of three routes. A licensed
customs broker decides. It never files a declaration, calculates duty, or creates
shipping documents. Scope is Chapters 73 and 96, with explicitly bounded article
recognition; unsupported products escalate or request clarification.

The reference stainless-steel vacuum flask with a moulded plastic outer body is
proposed under heading 9617 using GRI 1. The heading names the article; Section XV
Note 1(m) excludes articles of Chapter 96 from material-based classification.
Multiple materials alone do not justify jumping to GRI 3. Missing capacity causes
clarification for the eight-digit split; 0.75 L belongs to 96170011, while 0.751 L
and 1 L belong to 96170012 in the frozen source snapshot. Glass inners are excluded.

## Corpus and confirmation
Bundled CBIC-authored 2022 tariff came from a labelled mirror after CBIC HTTP 503
failures. DGFT Notification_ITCHS.pdf and general notes came directly from DGFT.
WCO 2022 GRI substitutes for the unavailable CBIC-hosted rules. SHA256, original
versions, physical one-based page anchors and retrieval date are recorded in
corpus/sources.json. These are not asserted to be current law. Faculty confirmation
and amendment review remain pending; default POLICY_SNAPSHOT_CONFIRMED=false
routes otherwise clear cases to specialist policy review. Evaluation explicitly
acknowledged the frozen snapshot; no real shipment clearance is claimed.

## Agent design and boundaries
FastAPI validates before enqueue, Redis/RQ persists asynchronous jobs, and separate
classifier worker containers execute a LangGraph reasoning agent. A second
LangGraph agent runs in its own verifier service/process with an explicit JSON
handoff and independent canonical clause lookup. The provider stub is another
container; a compatible live provider is selected entirely by runtime configuration.
The diagram in docs/architecture.svg and ARCHITECTURE.md marks these boundaries.

The classifier chooses request_fields, corpus_search and clause_lookup tools from
its state. It retrieves material candidates, reads notes, derives an article query
from the modifying provisions, looks up rules/notes/policy and asks the provider to
propose. The verifier checks citation identity, exact text/hash, article fit,
applicable notes, rule and policy. Unsupported drafts trigger one alternate exact
lookup and another verification; failure returns no classification. The planner
is deliberately deterministic, not unrestricted LLM tool selection. This is a
material limitation against the strictest interpretation of A1.

Budgets: 20 decision steps, 14 tool calls, 45-second RQ hard execution timeout;
5-second local-tool/provider HTTP deadline; 15-second verifier handoff. Provider
calls retry at most twice with 150/300 ms exponential backoff. Redis shares a
three-failure circuit breaker across replicas, with 15-second cooldown and a
single half-open probe. Provider/verifier failures fall back to specialist review.
A dead worker is exposed as failed/escalated through polling; unfinished runs are
never promoted into verified answers.

## Design choices and rejected alternatives
A notebook and synchronous long-running API were rejected because this is a
service with durable asynchronous execution. Polling was chosen over callbacks
to avoid callback reachability and SSRF concerns. A single embedding search was
rejected because material similarity misses the article-naming provision. Two
prompts inside one process were rejected as insufficient agent separation.
Local hash word/trigram embeddings (768 dimensions), LangChain and FAISS give a
small, free, reproducible baseline without weight downloads. They sacrifice
semantic synonym recall; a sentence transformer is future work. Heading/note
clauses retain their legal context; background chunks are 4,500 characters.
Embedding caches are keyed by text hash plus algorithm version, and an atomic
manifest publishes immutable index generations. Repeated indexing returned an
identical manifest. Redis AOF is simple and persistent but is not high availability;
its every-second fsync can lose about a second on host failure.

## Fixed evaluation and deliberate change
The fixed set has 28 scenarios with expected headings, routes and supporting
passage IDs, including the reference, capacity boundaries, ordinary articles,
exclusions, out-of-scope goods and an unresolved composite. CLI: python -m
tools.evaluate. The deliberate change was material-first v1 to article-first v2,
with versioned prompt artifacts and the same corpus, scenarios and verifier.
This is a prompt/planner ablation under the deterministic stub, not an isolated
live-LLM prompt comparison. No credentialed real-provider results are invented.

| Metric | v1 | v2 | Absolute change |
|---|---|---|---|
{metricrows}

Exact expected heading-and-route accuracy improved from 23/28 to 28/28, an
increase of {(v2['accuracy']-v1['accuracy'])*100:.2f} percentage points. The five
baseline flask failures were rejected on both verification attempts (10 rejected
drafts), rather than returned as wrong classifications. All emitted final claims
remained supported; that is why groundedness/faithfulness/hallucination did not
improve further. Perfect final evidence proxies do not prove legal correctness.

Groundedness is supported final heading/rule/policy claims divided by emitted
claims, requiring both a returned citation and matching retrieved passage ID.
No emitted claims score 1 as safe abstention and are flagged separately.
Context relevance is gold-support IDs plus POLICY-GENERAL intersected with distinct
retrieved IDs, divided by distinct retrieved IDs. Exact-ID matching is conservative.
Faithfulness uses the same bounded claim consistency check as groundedness here,
so it is not an independent semantic judge. Hallucination is unsupported final
claims divided by emitted claims, zero for no claims. These explicit deterministic
proxies are the evaluator equivalent; no TruLens library execution is claimed.

## Reliability, guardrails and observability validation
26 unit tests passed inside a container. Integration evidence confirms malformed,
injected and toxic inputs produce 422 quarantine records without increasing the
run count; all three routes, verification retry, verifier outage, provider outage,
breaker-open fallback, feedback persistence and rate-limit 429 were exercised.
A Chromium browser test submitted the flask, displayed seven citations, saved
feedback and found no JavaScript errors. Screenshot and JSON evidence are in
results/. NFKC and regex screening cover free-text inputs and outputs; finite
outputs and limited tools constrain model authority, but multilingual/adversarial
coverage is a known weakness.

Structured audit records preserve each query, retrieved passage, prompt version,
latency, token/cost entry and verification. Correlation propagates through RQ and
HTTP; actual Jaeger traces include API, classifier, verifier and stub spans.
Prometheus endpoints and a Grafana dashboard are provisioned for completion p50/p95,
throughput, success/error rate, availability, per-agent steps/tools/retries,
uptime and container resources. Full simultaneous monitoring-stack startup was
not validated: this cloud root filesystem is 7.9 GB with Docker VFS and exhausted
space while extracting Grafana. Core services, three worker replicas and Jaeger
were validated after image flattening/source mounts. Portable Compose/Dockerfile
are included; a full clean-clone rehearsal on adequate storage remains necessary.

## Predeclared SLO and measured scaling
Before load testing, docs/SLO.md declared p95 complete-run latency at most 30 s
for 10 concurrent analysts with one worker. The complete interval begins before
submission and ends when polling observes a final result, including queue wait.
The workload uses a 750 ms delayed stub per provider call (two ordinary calls),
unique nonces and disabled whole-run caching. Each test admits traffic for 40 s
then drains outstanding runs; CSV throughput includes its measured interval.
The machine had a 2-core CPU quota and 8 GiB memory. To save VFS disk, Locust ran
as a separate process inside the API container, sharing its CPU budget. The
reproduction profile uses a separate Locust container.

| Workers | Clients | Completed | Failures | Runs/s | p50 s | p95 s | SLO met |
|---|---|---|---|---|---|---|---|
{loadrows}

With one worker, the first tested failure was {breaks[1]} concurrent clients;
10 passed, so the crossing lies above 10 and no higher than {breaks[1]} for this
workload, not at a precisely measured continuous boundary. With three workers,
first tested failure: {breaks[3] if breaks[3] else 'not reached in the tested range'}.
The initial three-worker/10-client startup run had one verifier ConnectError while the verifier was restarting (1/45 failed observations). It missed the 99% availability objective and is retained under results/load/startup. The primary table uses the repeated steady-state run after readiness; the startup failure is not discarded. Locust observed one fewer completed run per cell than the server profile because a final accepted request outlived its stopped polling client; profile counts and server-complete latency are retained to expose this censoring limitation.

The baseline bottleneck is the serial classifier queue: each worker executes one
run at a time, and queue waiting grows while execution remains much shorter.
Detailed queue/execution percentiles are in results/load-profile.json. Three
workers increase parallelism; the measured improvement is bounded by two shared
CPU cores, JSON/audit overhead and polling. Those secondary costs were not
independently isolated, so no sole secondary bottleneck is asserted.

## Cache, cost and feedback
Twelve uncached samples had p50 {uc['p50_seconds']:.4f} s and p95
{uc['p95_seconds']:.4f} s. Eleven warm-cache hits had p50 {wc['p50_seconds']:.4f} s
and p95 {wc['p95_seconds']:.4f} s, a {gain:.2f}% p95 reduction in this small sample.
The cold fill is retained separately. Whole-run cache keys include canonical
product, prompt version, corpus generation, provider mode and policy-confirmation
state; unverified and fault-injected runs are never cached.

Actual stub cost is $0 per run and $0 per 100 runs, both before and after caching.
There is no paid-provider dollar-saving claim. Mean uncached prompt-token estimate
was {uc['mean_prompt_tokens']:.0f}; warm hits made no model calls. Full retrieved
context and legal-note text dominate estimated token use; per-agent model-step
records identify classifier/verifier contributions. In real mode usage and runtime
USD-per-million rates are recorded at each call. Missing provider usage and free-tier
rate limits remain limitations. Rate limiting is per demo client label; real cost
control needs an authenticated gateway. Feedback is persisted and aggregated, and
a deterministic sample of live runs is charted over time as evidence quality.

## What did not work and remaining work
Genuine development failures included PDF-layout assumptions, container TLS trust,
VFS disk exhaustion, runtime file permissions, lowercase proxy bypass precedence,
and omitted null escalation fields. The incident log records symptoms and fixes.
The runbook covers provider failure and queue/worker failure. The full dashboard,
current CBIC corpus confirmation, robust multilingual guardrails and real-LLM
prompt/evaluation quality remain unproven. See the explicit F/A/L/D matrix instead
of assuming all guide requirements are fully met. The course guide itself allows
prioritisation; this project prioritises a working, auditable, fail-closed path.

## Submission and reproduction
README.md gives Docker-only startup, configuration, API usage, evaluation, load,
fault demonstration, indexing and recovery. Included deliverables are source,
source PDFs, scoped extracts, contracts, fixed tests/results, dashboards, report,
presentation, project plan and demo/viva notes. Fill actual names/SRNs, create and
push the GitHub repository, obtain evaluator corpus confirmation, and rehearse the
live demonstration. Those external actions have not been falsely marked complete.
'''
Path('docs/REPORT.md').write_text(report)
# A compact, explicit container-boundary diagram as both SVG and PDF drawing.
boxes=[(15,185,145,62,'Web client','External browser'),(195,185,145,62,'API container','Validation / 202 / polling'),(375,185,145,62,'Redis container','RQ / audit / cache / AOF'),(555,185,145,62,'Worker containers','Classifier LangGraph x1..3'),(555,75,145,62,'Verifier container','Canonical evidence graph'),(375,75,145,62,'Provider container','750 ms delayed stub'),(195,75,145,62,'Indexer + FAISS','Immutable generations'),(15,75,145,62,'Telemetry containers','Jaeger / Prom / Grafana')]
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="720" height="280" viewBox="0 0 720 280"><rect width="720" height="280" fill="#f5f8fb"/>']
for x,y,w,h,title,sub in boxes:
 sy=280-y-h;svg += [f'<rect x="{x}" y="{sy}" width="{w}" height="{h}" rx="8" fill="white" stroke="#168078" stroke-width="2"/>',f'<text x="{x+w/2}" y="{sy+25}" text-anchor="middle" font-family="sans-serif" font-size="12" fill="#15334b">{html.escape(title)}</text>',f'<text x="{x+w/2}" y="{sy+44}" text-anchor="middle" font-family="sans-serif" font-size="10" fill="#526576">{html.escape(sub)}</text>']
for x1,y1,x2,y2 in [(160,216,195,216),(340,216,375,216),(520,216,555,216),(628,185,628,137),(555,106,520,106),(555,185,340,137),(195,106,160,106)]:svg.append(f'<line x1="{x1}" y1="{280-y1}" x2="{x2}" y2="{280-y2}" stroke="#526576" stroke-width="2"/>')
svg.append('<text x="360" y="270" text-anchor="middle" font-family="sans-serif" font-size="10">Every labelled service box is a deployment boundary; telemetry receives correlated events from all application services.</text></svg>');Path('docs/architecture.svg').write_text(''.join(svg))
# Register a readable Unicode font where available.
font='/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
if Path(font).exists():pdfmetrics.registerFont(TTFont('Body',font));bodyfont='Body'
else:bodyfont='Helvetica'
styles=getSampleStyleSheet()
for name in ('Normal','BodyText','Heading1','Heading2','Heading3'):styles[name].fontName=bodyfont
styles['BodyText'].fontSize=9;styles['BodyText'].leading=13;styles['Heading1'].fontSize=17;styles['Heading2'].fontSize=12
def architecture_drawing(width):
 d=Drawing(720,280)
 for x,y,w,h,title,sub in boxes:
  d.add(Rect(x,y,w,h,rx=8,ry=8,fillColor=colors.HexColor('#f5f8fb'),strokeColor=colors.HexColor('#168078'),strokeWidth=1.5))
  d.add(String(x+w/2,y+36,title,textAnchor='middle',fontName=bodyfont,fontSize=11,fillColor=colors.HexColor('#15334b')))
  d.add(String(x+w/2,y+18,sub,textAnchor='middle',fontName=bodyfont,fontSize=9,fillColor=colors.HexColor('#526576')))
 for x1,y1,x2,y2 in [(160,216,195,216),(340,216,375,216),(520,216,555,216),(628,185,628,137),(555,106,520,106),(555,185,340,137),(195,106,160,106)]:
  d.add(Line(x1,y1,x2,y2,strokeColor=colors.HexColor('#526576'),strokeWidth=1.5))
 d.add(String(360,20,'Labelled service boxes mark deployment boundaries; telemetry receives correlated application events.',textAnchor='middle',fontName=bodyfont,fontSize=9))
 factor=width/720;d.scale(factor,factor);d.width=width;d.height=280*factor
 return d
story=[];lines=report.splitlines();buf=[]
def flush():
 if buf:story.append(Paragraph(html.escape(' '.join(buf)),styles['BodyText']));story.append(Spacer(1,7));buf.clear()
i=0
while i<len(lines):
 line=lines[i]
 if line.startswith('|'):
    flush();table=[]
    while i<len(lines) and lines[i].startswith('|'):
      cols=[c.strip() for c in lines[i].strip('|').split('|')]
      if not all(set(c)<=set('-: ') for c in cols):table.append([Paragraph(html.escape(c),styles['BodyText']) for c in cols])
      i+=1
    t=Table(table,hAlign='LEFT',repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e4f1ef')),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#bbcbd6')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5)]));story.extend([t,Spacer(1,10)]);continue
 if line.startswith('# '):flush();story.append(Paragraph(html.escape(line[2:]),styles['Heading1']))
 elif line.startswith('## '):
  flush();story.append(Paragraph(html.escape(line[3:]),styles['Heading2']))
  if line=='## Agent design and boundaries':story.extend([architecture_drawing(510),Spacer(1,8)])
 elif not line.strip():flush()
 else:buf.append(line)
 i+=1
flush()
def footer(canvas,doc):
 canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#526576'));canvas.drawString(42,25,'Mini Project 07 | Proposed classifications only | Frozen-corpus academic build');canvas.drawRightString(A4[0]-42,25,str(doc.page))
SimpleDocTemplate('docs/REPORT.pdf',title='Export Classification Check Service — Final Report',author='Project contributors',pagesize=A4,rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=42).build(story,onFirstPage=footer,onLaterPages=footer)
# Eight concise slides, with actual numbers; no invented team identity.
slides=[('Export Classification Check Service',['UE24AM342AA5 · Mini Project 07','Evidence-backed proposals for Chapters 73 and 96','Names/SRNs: complete docs/TEAM.md','A licensed broker decides; the system never files.']),('Why the flask is difficult',['Steel similarity can lead to heading 7323.','GRI 1 gives priority to heading terms and relative notes.','Heading 9617 names complete vacuum flasks.','Section XV Note 1(m) excludes Chapter 96 articles.','Missing capacity requires clarification for the eight-digit item.']),('Two deployed agents',['API → Redis/RQ → classifier worker graph → verifier graph','Tools: corpus search, exact clause lookup, request fields','Notes produce an article query; failed verification searches again.','The independent verifier resolves canonical text and hashes.','Budgets and a specialist fallback bound every unfinished run.']),('Deployment and observability',['Separate API, queue, worker, verifier, provider and indexer boundaries','Scale classifier-worker to three without fixed worker ports.','Actual Jaeger traces span all four application services.','Prometheus/Grafana/resource configurations are included.','Full simultaneous monitoring startup remains unverified on the 7.9 GB VFS disk.']),('Evaluation: same 28 scenarios',[f"v1 correct 23/28 → v2 correct 28/28 (+{(v2['accuracy']-v1['accuracy'])*100:.2f} pp)",'10 incorrect baseline draft attempts rejected; zero wrong final flask answers.',f"Final groundedness {v2['groundedness']:.2f}; context relevance {v2['context_relevance']:.3f}.",'Faithfulness uses the same bounded evidence proxy; hallucination rate 0.','These are deterministic stub/planner results, not real-LLM legal accuracy.']),('Predeclared SLO and scaling',['Target: complete-run p95 ≤30 seconds at 10 concurrent clients.','750 ms delayed stub per model call; whole-run cache disabled.']+[f"{r['workers']} worker(s), {r['clients']} clients: {r['rps']:.2f} runs/s, p95 {r['p95_seconds']:.1f}s" for r in load['rows']]),('Reliability and cost',['26 container unit tests; integration and Chromium checks passed.','Rejects quarantined before agents; unsupported answers retry then escalate.','Provider/verifier failures, breaker and rate limit demonstrated.',f"Warm cache p95 {wc['p95_seconds']:.3f}s vs {uc['p95_seconds']:.3f}s ({gain:.1f}% lower).",'Actual stub cost: $0 per 100 runs; token counts are estimates.']),('Limits and demonstration',['Historical CBIC mirror + WCO GRI substitution need evaluator confirmation.','No credentialed live-LLM prompt comparison; bounded article lexicon.','Regex guardrails need stronger multilingual coverage.','Show ten demo items using docs/DEMO_AND_VIVA.md.','Complete real team details, GitHub push, corpus sign-off and live viva.'])]
from reportlab.pdfgen.canvas import Canvas
c=Canvas('docs/PRESENTATION.pdf',pagesize=(960,540));c.setTitle('Export Classification Check — Presentation');c.setAuthor('Project contributors')
for n,(title,bullets) in enumerate(slides,1):
 c.setFillColor(colors.HexColor('#f3f6f8'));c.rect(0,0,960,540,fill=1,stroke=0);c.setFillColor(colors.HexColor('#168078'));c.rect(0,510,960,30,fill=1,stroke=0)
 c.setFillColor(colors.HexColor('#16334b'));c.setFont(bodyfont,24);c.drawString(48,465,title)
 y=415
 if n==4:
  from reportlab.graphics import renderPDF
  renderPDF.draw(architecture_drawing(850),c,48,80)
  bullets=[]
 for bullet in bullets:
  p=Paragraph('• '+html.escape(bullet),styles['BodyText']);p.style.fontSize=14;p.style.leading=20;w,h=p.wrap(850,400);p.drawOn(c,55,y-h);y-=h+15
 c.setFont(bodyfont,9);c.setFillColor(colors.HexColor('#526576'));c.drawString(48,22,'MINI PROJECT 07 · PROPOSED CLASSIFICATION ONLY');c.drawRightString(910,22,f'{n}/{len(slides)}');c.showPage()
c.save();print('Built report, PDF, architecture and presentation.')
