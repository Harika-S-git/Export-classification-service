import sys
sys.path.insert(0,'.')
from pydantic import ValidationError
from app.main import ProductRequest

def valid(**overrides):
    data={'description':'Steel bottle for beverages','destination_country':'United States'}
    data.update(overrides); return data

def test_valid_contract():
    x=ProductRequest(**valid()); assert x.country_of_export=='India'

def test_rejects_short_description():
    try: ProductRequest(**valid(description='cup'))
    except ValidationError: return
    assert False, 'short description should be rejected'

def test_rejects_same_export_destination():
    try: ProductRequest(**valid(destination_country='India'))
    except ValidationError: return
    assert False, 'same origin and destination should be rejected'

def test_rejects_negative_value():
    try: ProductRequest(**valid(value_usd=-1))
    except ValidationError: return
    assert False, 'negative value should be rejected'
