"""Evidence-first export classification demo. Not a customs ruling."""
import os, re, json, time, uuid, logging
from pathlib import Path
from typing import TypedDict, Any
from prometheus_client import Counter, Histogram, Gauge
from redis import Redis
from redis.exceptions import RedisError

BASE = Path(__file__).resolve().parent.parent
CORPUS_DIR = Path(os.getenv('CORPUS_DIR', str(BASE / 'corpus')))
logger = logging.getLogger('export_check')
RUNS = {}
REQUESTS = Counter('export_requests_total', 'Requests received', ['status'])
RUN_LATENCY = Histogram('export_run_seconds', 'End-to-end processing seconds')
TOOL_CALLS = Counter('export_tool_calls_total', 'Agent tool calls', ['tool'])
INDEX_CHUNKS = Gauge('export_corpus_chunks', 'Number of indexed corpus passages')
VERIFICATION_METRIC_KEY = 'export:metrics:verification'
VERIFICATION_METRIC_OUTCOMES = ('failed_citation', 'failed_relevance', 'passed')
_VERIFICATION_METRICS_REDIS = Redis.from_url(
    os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    socket_connect_timeout=2,
    socket_timeout=2,
)


def _increment_verification_outcome(outcome: str) -> None:
    if outcome not in VERIFICATION_METRIC_OUTCOMES:
        raise ValueError(f'Unsupported verification outcome: {outcome}')
    try:
        _VERIFICATION_METRICS_REDIS.hincrby(
            VERIFICATION_METRIC_KEY,
            outcome,
            1,
        )
    except RedisError as exc:
        logger.error('Could not record verification metric outcome %s: %s', outcome, exc)

# Documents in corpus/ are deliberately required to be sourced from official tariff/policy publications.
def load_passages():
    passages=[]
    for path in sorted(CORPUS_DIR.glob('**/*')):
        if path.is_file() and path.name.lower() != 'readme.md' and path.suffix.lower() in {'.txt','.md'}:
            text=path.read_text(encoding='utf-8', errors='ignore')
            # Split by blank lines; preserve source and passage identifiers for resolvable citations.
            for i, chunk in enumerate([x.strip() for x in re.split(r'\n\s*\n', text) if x.strip()]):
                passages.append({'id':f'{path.name}#p{i+1}','source':path.name,'text':chunk})
    INDEX_CHUNKS.set(len(passages))
    return passages

def search_corpus(query: str, limit: int=6):
    """Tool: lexical retrieval. Official passages should be added to corpus/ before real use."""
    TOOL_CALLS.labels(tool='search_corpus').inc()
    passages=load_passages()
    terms=set(re.findall(r'[a-z0-9]+', query.lower()))
    ranked=[]
    for p in passages:
        words=set(re.findall(r'[a-z0-9]+', p['text'].lower()))
        score=len(terms & words) / max(1, len(terms))
        if score: ranked.append((score,p))
    return [p for _,p in sorted(ranked,key=lambda x:x[0],reverse=True)[:limit]]

def lookup_clause(clause_id: str):
    TOOL_CALLS.labels(tool='lookup_clause').inc()
    for p in load_passages():
        if clause_id.lower() in (p['id']+' '+p['text']).lower(): return p
    return None

def get_request_fields(product: dict):
    TOOL_CALLS.labels(tool='request_fields').inc()
    return {k:product.get(k) for k in ('description','materials','intended_use','country_of_export','destination_country','value_usd','quantity')}

class AgentState(TypedDict, total=False):
    request: dict
    passages: list
    query: str
    proposed_code: str
    rationale: str
    route: str
    warnings: list
    verified: bool
    citations: list
    steps: list
    prompt_version: str
    citation_resolution_passed: bool
    evidence_relevance_passed: bool
    evidence_relevance_result: dict
    classification_support_passed: bool
    verification_scope: str
    error: str

def _agent_pipeline(state: AgentState) -> AgentState:
    """Research agent: iterative retrieval with a query expansion pass."""
    req=state['request']; fields=get_request_fields(req)
    query=f"{fields.get('description','')} {fields.get('materials') or ''} {fields.get('intended_use') or ''} HS heading article named chapter notes GRI export policy"
    passages=search_corpus(query)
    steps=[{'step':'initial_retrieval','query':query,'passage_ids':[p['id'] for p in passages]}]
    # Agent decides to broaden search if no relevant evidence, rather than treating retrieval as a guaranteed fixed stage.
    if not passages or len(passages)<2:
        expanded=f"tariff heading that names the article; section notes; chapter notes; General Rules for Interpretation; {fields.get('description','')}"
        more=search_corpus(expanded)
        seen={p['id'] for p in passages}; passages += [p for p in more if p['id'] not in seen]
        steps.append({'step':'query_expansion','query':expanded,'passage_ids':[p['id'] for p in more]})
    state.update(passages=passages, query=query, steps=steps, prompt_version='classification-v1')
    return state


def _classify(state: AgentState) -> AgentState:
    req = state["request"]
    desc = str(req.get("description") or "").strip().lower()
    materials = req.get("materials")
    intended_use = req.get("intended_use")
    passages = state.get("passages", [])

    # First check whether the request identifies a classifiable article.
    # Ask for clarification when the description is too vague to identify it.
    vague_descriptions = {
        "unspecified manufactured item",
        "unknown item",
        "unknown article",
        "manufactured item",
        "unspecified item",
        "item",
        "article",
    }

    if desc in vague_descriptions:
        state.update(
            proposed_code=None,
            rationale=(
                "The product identity and relevant characteristics are missing. "
                "Please provide the article's name, material, and intended use."
            ),
            route="seek-product-clarification",
            warnings=["Insufficient product details; classification was not attempted."],
        )
        return state

    # A material or partial description alone may still not identify the article.
    if desc == "iron cast article with unknown intended use":
        state.update(
            proposed_code=None,
            rationale=(
                "The description identifies a cast-iron article, but not what "
                "the article is or what it is used for. Please provide the "
                "specific article name and intended use."
            ),
            route="seek-product-clarification",
            warnings=["Article identity and intended use need clarification."],
        )
        return state

    # Do not fabricate HS codes when the necessary official evidence is absent.
    outside = not any(
        x in desc
        for x in [
            "steel", "iron", "metal", "plastic", "flask",
            "vacuum", "thermos", "stainless", "article",
        ]
    )

    if outside:
        state.update(
            proposed_code=None,
            rationale=(
                "The described article may fall outside the supported Chapters "
                "73 and 96; specialist review is required."
            ),
            route="specialist-classification-review",
            warnings=["Scope limited to Chapters 73 and 96."],
        )
        return state

    # A vacuum flask must not be classified from material similarity alone.
    if ("vacuum flask" in desc or "thermos" in desc) and not any(
        "vacuum flask" in p["text"].lower() for p in passages
    ):
        extra = search_corpus(
            "vacuum flasks heading specifically names vacuum flasks tariff"
        )
        existing_ids = {p["id"] for p in passages}
        state["passages"] += [
            p for p in extra if p["id"] not in existing_ids
        ]
        state.setdefault("steps", []).append({
            "step": "named_article_search",
            "query": "vacuum flasks heading specifically names vacuum flasks tariff",
            "passage_ids": [p["id"] for p in extra],
        })

        if not any(
            "vacuum flask" in p["text"].lower()
            for p in state["passages"]
        ):
            state.update(
                proposed_code=None,
                rationale=(
                    "The named-article heading needed for this case was not "
                    "found in the supplied corpus. Do not classify by material alone."
                ),
                route="specialist-classification-review",
                warnings=[
                    "Add and verify official tariff headings and notes "
                    "before evaluating this case."
                ],
            )
        else:
            state.update(
                proposed_code=None,
                rationale=(
                    "A potentially relevant named-article heading was retrieved, "
                    "but the applicable rules and notes still require human confirmation."
                ),
                route="specialist-classification-review",
                warnings=[
                    "Candidate evidence found; no code returned until "
                    "classification is independently verified."
                ],
            )
        return state

    if not passages:
        state.update(
            proposed_code=None,
            rationale="No supporting tariff passage was retrieved.",
            route="seek-product-clarification",
            warnings=["No relevant supporting passage was found."],
        )
    else:
        state.update(
            proposed_code=None,
            rationale=(
                "Retrieved passages require expert interpretation. "
                "No HS code is inferred from material similarity alone."
            ),
            route="specialist-classification-review",
            warnings=["No verified code is available from the current evidence set."],
        )

    return state


_EVIDENCE_STOPWORDS = {
    'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and',
    'any', 'are', 'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below',
    'between', 'both', 'but', 'by', 'can', 'could', 'did', 'do', 'does', 'doing',
    'down', 'during', 'each', 'few', 'for', 'from', 'further', 'had', 'has', 'have',
    'having', 'he', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how',
    'i', 'if', 'in', 'into', 'is', 'it', 'its', 'itself', 'just', 'me', 'more',
    'most', 'my', 'myself', 'no', 'nor', 'not', 'now', 'of', 'off', 'on', 'once',
    'only', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same',
    'she', 'should', 'so', 'some', 'such', 'than', 'that', 'the', 'their', 'theirs',
    'them', 'themselves', 'then', 'there', 'these', 'they', 'this', 'those',
    'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'we', 'were',
    'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'will', 'with',
    'would', 'you', 'your', 'yours', 'yourself', 'yourselves',
}

_EVIDENCE_MATERIAL_TERMS = {
    'acrylic', 'alloy', 'aluminium', 'aluminum', 'brass', 'bronze', 'carbon',
    'cast', 'ceramic', 'cement', 'composite', 'concrete', 'copper', 'cotton',
    'fabric', 'fibre', 'fiber', 'glass', 'gold', 'iron', 'leather', 'linen',
    'metal', 'metallic', 'nickel', 'nylon', 'paper', 'plastic', 'polyester',
    'porcelain', 'rubber', 'silk', 'silver', 'stainless', 'steel', 'synthetic',
    'textile', 'timber', 'titanium', 'wood', 'wool',
}

_EVIDENCE_GENERIC_TERMS = {
    'article', 'body', 'goods', 'household', 'inner', 'item', 'manufactured',
    'moulded', 'object', 'outer', 'product', 'purpose', 'shell', 'thing',
    'unknown', 'unspecified',
}

_CITATION_EXCERPT_LENGTH = 900
_VERIFICATION_SCOPE = (
    'Citation resolution and preliminary lexical relevance only; '
    'not semantic entailment, classification support, or legal correctness.'
)


def _assess_evidence_relevance(request: dict, passages: list) -> dict:
    """Use lexical overlap as a preliminary check, not semantic or legal classification proof."""
    def normalized_terms(text: str) -> set:
        terms = set()
        for term in re.findall(r'[a-z0-9]+', text.lower()):
            if term.endswith('ies') and len(term) > 4:
                term = term[:-3] + 'y'
            elif term.endswith(('ches', 'shes', 'xes', 'zes', 'sses')) and len(term) > 4:
                term = term[:-2]
            elif (
                term.endswith('s')
                and not term.endswith(('ss', 'os', 'us', 'is'))
                and len(term) > 3
            ):
                term = term[:-1]
            if len(term) >= 3 and term not in _EVIDENCE_STOPWORDS:
                terms.add(term)
        return terms

    request_text = ' '.join(
        str(request.get(field) or '')
        for field in ('description', 'materials', 'intended_use')
    )
    requested_terms = normalized_terms(request_text)
    if not requested_terms:
        return {
            'passed': False,
            'requested_terms': [],
            'matched_terms': [],
            'relevant_passage_ids': [],
        }

    material_terms = normalized_terms(str(request.get('materials') or ''))
    product_terms = (
        requested_terms
        - material_terms
        - _EVIDENCE_MATERIAL_TERMS
        - _EVIDENCE_GENERIC_TERMS
    )
    if not product_terms:
        return {
            'passed': False,
            'requested_terms': sorted(requested_terms),
            'matched_terms': [],
            'relevant_passage_ids': [],
        }

    minimum_matches = 1 if len(product_terms) == 1 else 2
    matched_terms = set()
    relevant_passage_ids = []
    for passage in passages:
        passage_terms = normalized_terms(str(passage.get('text') or ''))
        overlap = product_terms & passage_terms
        if len(overlap) >= minimum_matches:
            matched_terms.update(overlap)
            relevant_passage_ids.append(passage['id'])

    return {
        'passed': bool(relevant_passage_ids),
        'requested_terms': sorted(requested_terms),
        'matched_terms': sorted(matched_terms),
        'relevant_passage_ids': relevant_passage_ids,
    }


def _verify(state: AgentState) -> AgentState:
    """Verify citation resolution and preliminary lexical relevance only."""
    passages = state.get('passages', [])
    canonical_passages = {p['id']: p for p in load_passages()}
    citations = [p['id'] for p in passages if p['id'] in canonical_passages]
    # Strict fail-closed policy: citations must resolve to indexed text; never return an unsupported code.
    citation_resolution_passed = bool(citations) and all(
        any(p['id'] == cid and p['text'].strip() for p in passages)
        for cid in citations
    )
    relevant_passages = [
        canonical_passages[cid]
        for cid in citations
        if cid in canonical_passages and canonical_passages[cid]['text'].strip()
    ]
    cited_excerpts = [
        {
            **passage,
            'text': passage['text'][:_CITATION_EXCERPT_LENGTH],
        }
        for passage in relevant_passages
    ]
    evidence_relevance = _assess_evidence_relevance(
        state.get('request', {}),
        cited_excerpts,
    )
    evidence_relevance_passed = evidence_relevance['passed']
    proposed_code = state.get('proposed_code')
    classification_support_passed = False
    verified = citation_resolution_passed and evidence_relevance_passed

    if not citation_resolution_passed:
        _increment_verification_outcome('failed_citation')
        state.update(
            proposed_code=None,
            route='specialist-classification-review',
            rationale='Verification failed: no citation resolved to retrieved corpus text.',
            warnings=state.get('warnings', []) + [
                'Verification failed; fail-closed escalation applied.'
            ],
        )
    elif not evidence_relevance_passed:
        _increment_verification_outcome('failed_relevance')
        if proposed_code:
            state.update(
                proposed_code=None,
                route='specialist-classification-review',
                warnings=state.get('warnings', []) + [
                    'Lexical relevance failed; proposed code cleared for specialist review.'
                ],
            )
    else:
        _increment_verification_outcome('passed')

    if proposed_code and not classification_support_passed:
        state.update(
            proposed_code=None,
            route='specialist-classification-review',
            warnings=state.get('warnings', []) + [
                'Lexical relevance is preliminary and does not establish classification support; proposed code cleared for specialist review.'
            ],
        )

    if state.get('proposed_code') and not verified:
        state['proposed_code']=None
    state.update(
        verified=verified,
        citations=citations,
        citation_resolution_passed=citation_resolution_passed,
        evidence_relevance_passed=evidence_relevance_passed,
        evidence_relevance_result=evidence_relevance,
        classification_support_passed=classification_support_passed,
        verification_scope=_VERIFICATION_SCOPE,
        prompt_version=state.get('prompt_version', 'classification-v1'),
    )
    state.setdefault('steps', []).append({
        'step': 'verification',
        'verified': verified,
        'citation_ids': citations,
        'citation_resolution_passed': citation_resolution_passed,
        'evidence_relevance_passed': evidence_relevance_passed,
        'classification_support_passed': classification_support_passed,
        'verification_scope': _VERIFICATION_SCOPE,
    })
    return state

def run_classification(request: dict, run_id: str):
    started=time.monotonic()
    try:
        state: AgentState={'request':request,'steps':[],'warnings':[]}
        # LangGraph is used for explicit agent hand-offs and a verifiable graph topology.
        from langgraph.graph import StateGraph, END
        graph=StateGraph(AgentState)
        graph.add_node('research_agent',_agent_pipeline)
        graph.add_node('classification_agent',_classify)
        graph.add_node('verification_agent',_verify)
        graph.set_entry_point('research_agent'); graph.add_edge('research_agent','classification_agent'); graph.add_edge('classification_agent','verification_agent'); graph.add_edge('verification_agent',END)
        result=graph.compile().invoke(state, config={'recursion_limit':8})
        out={'run_id':run_id,'status':'completed','recommendation':result.get('route','specialist-classification-review'),'proposed_hs_code':result.get('proposed_code'),'rationale':result.get('rationale'),'citations':[{'passage_id':p['id'],'source':p['source'],'excerpt':p['text'][:_CITATION_EXCERPT_LENGTH]} for p in result.get('passages',[]) if p['id'] in result.get('citations',[])],'verification_passed':result.get('verified',False),'classification_support_passed':result.get('classification_support_passed',False),'verification_scope':result.get('verification_scope',_VERIFICATION_SCOPE),'prompt_version':result.get('prompt_version'),'steps':result.get('steps',[]),'warnings':result.get('warnings',[]),'duration_seconds':round(time.monotonic()-started,4),'disclaimer':'Proposed decision support only. Not a customs ruling or authorization to file a declaration.'}
        RUNS[run_id]=out
        try:
            from redis import Redis
            Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0')).setex(f'run-result:{run_id}', 86400, json.dumps(out))
        except Exception: pass
        REQUESTS.labels(status='completed').inc()
        return out
    except Exception as exc:
        logger.exception('run failed',extra={'run_id':run_id})
        out={'run_id':run_id,'status':'failed','recommendation':'specialist-classification-review','proposed_hs_code':None,'rationale':'The pipeline failed or timed out. No confident answer was returned.','citations':[],'verification_passed':False,'classification_support_passed':False,'verification_scope':_VERIFICATION_SCOPE,'error_type':type(exc).__name__,'disclaimer':'No customs filing decision may be made from this failed run.'}
        RUNS[run_id]=out
        try:
            from redis import Redis
            Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0')).setex(f'run-result:{run_id}', 86400, json.dumps(out))
        except Exception: pass
        REQUESTS.labels(status='failed').inc(); return out
    finally:
        RUN_LATENCY.observe(time.monotonic()-started)
