import argparse,json
from app.corpus import build
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--reembed',action='store_true');a=p.parse_args();print(json.dumps(build(a.reembed),indent=2))
