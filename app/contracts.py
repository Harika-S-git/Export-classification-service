import re, unicodedata
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator

BAD = re.compile(r'ignore\s+(all\s+|any\s+|previous\s+|prior\s+)*(instructions|rules)|system\s*prompt|developer\s*message|<\s*/?\s*(system|assistant)|jailbreak|reveal\s+(secrets|credentials)|execute\s+(code|command)|classify\s+as\s+\d|override\s+(policy|rules)',re.I)
TOXIC = re.compile(r'\b(fuck|shit|kill yourself|idiot)\b',re.I)
def safe_text(value):
    value=unicodedata.normalize('NFKC',value)
    if BAD.search(value): raise ValueError('prompt_injection_detected')
    if TOXIC.search(value): raise ValueError('toxicity_detected')
    if any(ord(c)<32 and c not in '\n\t' for c in value): raise ValueError('control_character')
    return value.strip()

class Contract(BaseModel): model_config=ConfigDict(extra='forbid',str_strip_whitespace=True,strict=True)
class Material(Contract):
    name: Literal['stainless_steel','steel','iron','plastic','glass','wood','other']
    percent: float=Field(gt=0,le=100,allow_inf_nan=False)
class Product(Contract):
    description: str=Field(min_length=10,max_length=2000)
    intended_use: str=Field(default='',max_length=300)
    materials: list[Material]=Field(default_factory=list,max_length=8)
    capacity_l: float|None=Field(default=None,gt=0,le=100,allow_inf_nan=False)
    vacuum_insulated: bool|None=None
    complete: bool=True
    destination: str=Field(default='US',pattern=r'^[A-Z]{2}$')
    quantity: int=Field(default=1,strict=True,ge=1,le=1000000)
    @field_validator('description','intended_use')
    @classmethod
    def guard(cls,v): return safe_text(v)
    @model_validator(mode='after')
    def cross(self):
        if self.materials and abs(sum(m.percent for m in self.materials)-100)>.01:
            raise ValueError('materials percentages must total 100')
        if len({m.name for m in self.materials})!=len(self.materials): raise ValueError('duplicate material')
        d=self.description.lower()
        if self.vacuum_insulated is False and 'vacuum' in d and 'non-vacuum' not in d:
            raise ValueError('vacuum_insulated contradicts description')
        if not self.complete and self.capacity_l is not None: raise ValueError('capacity applies only to complete vessels')
        return self
class Submission(Contract):
    product: Product
    prompt_version: Literal['v1','v2']='v2'
    cache: bool=True
    nonce: str=Field(default='',max_length=64,pattern=r'^[a-zA-Z0-9_-]*$')
    fault: Literal['none','unsupported','timeout','provider_down','verifier_down']='none'
class Feedback(Contract):
    satisfactory: bool
    reason: str=Field(min_length=3,max_length=500)
    @field_validator('reason')
    @classmethod
    def guard(cls,v): return safe_text(v)
class Citation(Contract):
    id: str
    text: str
    source: str
    page: int
    sha256: str
class Recommendation(Contract):
    heading: str|None=None
    tariff_item: str|None=None
    rule: str|None=None
    route: Literal['clear-for-filing','seek-product-clarification','specialist-classification-review']
    basis: str
    export_policy: str='unconfirmed'
    citations: list[Citation]=Field(default_factory=list)
    verified: bool=False
    proposed_only: bool=True
    disclaimer: str='Proposed classification only. A licensed customs broker decides; this service never files a declaration.'
    prompt_version: str
    mode: str
    entities: dict=Field(default_factory=dict)
    cost_usd: float=0
    prompt_tokens: int=0
    completion_tokens: int=0
    cache_hit: bool=False
class VerifyRequest(Contract):
    run_id: str=Field(pattern=r'^[a-f0-9-]{36}$')
    product: Product
    proposed: dict
    evidence: list[dict]=Field(max_length=200)
    prompt_version: Literal['v1','v2']
    fault: str='none'

class Accepted(Contract):
    run_id: str
    status_url: str
    trace_url: str
class RunStatus(BaseModel):
    run_id: str
    status: Literal['queued','running','completed','escalated']
    submitted_at: float
    started_at: float|None=None
    finished_at: float|None=None
    duration_seconds: float|None=None
    result: Recommendation|None=None
    error: str|None=None
    correlation_id: str
    request: Submission
class TraceResponse(Contract):
    run_id: str
    events: list[dict]
class FeedbackReceipt(Contract):
    persisted: bool
class AnalyticsResponse(Contract):
    feedback_count: int
    satisfactory_rate: float|None
    quality: list[dict]
    quarantine_count: int
    breaker_open_until: str|None
class HealthResponse(Contract):
    status: str
    corpus: str
    mode: str
class CorpusResponse(Contract):
    digest: str
    built_at: float
    chunks: int
    new_embeddings: int
    embedding: str
    chunks_per_second: float
    sources: list[dict]
class StubRequest(Contract):
    prompt_version: Literal['v1','v2']
    product: Product
    candidates: list[dict]=Field(max_length=32)
    passages: list[dict]=Field(max_length=200)
    fault: Literal['none','unsupported','timeout','provider_down','verifier_down']='none'
class StubResponse(Contract):
    answer: dict
    usage: dict
    provider: str
