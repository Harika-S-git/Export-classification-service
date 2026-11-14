import json
from pathlib import Path
from app.api import app
from app.contracts import Submission,Product,Recommendation,Feedback,VerifyRequest
Path('docs/openapi.json').write_text(json.dumps(app.openapi(),indent=2))
Path('docs/json-schemas.json').write_text(json.dumps({c.__name__:c.model_json_schema() for c in [Submission,Product,Recommendation,Feedback,VerifyRequest]},indent=2))
