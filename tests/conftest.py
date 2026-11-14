import os
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('VERIFIER_URL','http://localhost:8001')
os.environ.setdefault('PROVIDER_URL','http://localhost:8002')
import tempfile
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='export-check-tests-')

os.environ['OTEL_EXPORTER_OTLP_ENDPOINT']=''
import pytest
from unittest.mock import patch
import app.store
@pytest.fixture(autouse=True)
def no_external_audit():
    with patch('app.store.event'):
        yield
