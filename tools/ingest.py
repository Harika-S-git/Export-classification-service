"""Idempotent raw-PDF -> clauses -> embeddings -> FAISS pipeline."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
from app.corpus import build
from app.config import settings
p=argparse.ArgumentParser();p.add_argument('--reembed',action='store_true');args=p.parse_args()
raw=Path(settings().corpus_dir)/'raw';digest=hashlib.sha256(b''.join(x.read_bytes() for x in sorted(raw.glob('*.pdf')))).hexdigest()
marker=Path(settings().data_dir)/'parsed-source-hash';marker.parent.mkdir(parents=True,exist_ok=True)
if not marker.exists() or marker.read_text()!=digest:
    subprocess.run([sys.executable,'-m','tools.prepare_corpus'],check=True,timeout=300);marker.write_text(digest)
print(json.dumps(build(args.reembed),indent=2))
