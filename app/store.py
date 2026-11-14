import json, time
from redis import Redis
from .config import settings

def db(): return Redis.from_url(settings().redis_url,decode_responses=True,socket_timeout=3,socket_connect_timeout=3)
def put_run(rid, **fields):
    db().hset('run:'+rid,mapping={k:json.dumps(v) for k,v in fields.items()})
def get_run(rid): return {k:json.loads(v) for k,v in db().hgetall('run:'+rid).items()}
def event(rid,agent,action,**fields):
    from .telemetry import log
    entry={'run_id':rid,'agent':agent,'action':action,'timestamp':time.time(),**fields}
    db().rpush('events:'+rid,json.dumps(entry))
    # Full evidence lives once in durable audit; logs retain correlation and a pointer.
    log('audit',run_id=rid,agent=agent,action=action,timestamp=entry['timestamp'],audit_key='events:'+rid,prompt_version=fields.get('prompt_version'),latency=fields.get('latency'),error=fields.get('error'))
def events(rid): return [json.loads(x) for x in db().lrange('events:'+rid,0,-1)]
def quarantine(errors, body, correlation):
    import hashlib
    # Rejected content is not copied into logs; preserve hash and field-level errors.
    item={'id':correlation,'timestamp':time.time(),'errors':errors,'body_sha256':hashlib.sha256(body).hexdigest(),'agent_started':False}
    db().rpush('quarantine',json.dumps(item));return item
