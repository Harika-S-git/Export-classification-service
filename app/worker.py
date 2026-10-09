import os
from redis import Redis
from rq import Worker, Queue
conn=Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'))
if __name__=='__main__': Worker([Queue('classification',connection=conn)],connection=conn).work(with_scheduler=False)
