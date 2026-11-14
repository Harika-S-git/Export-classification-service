import json
from pathlib import Path
rows=[
('reference','Stainless steel vacuum flask with a moulded plastic outer body.','9617','seek-product-clarification',{}),
('flask-small','Complete stainless steel vacuum flask with plastic casing','9617','clear-for-filing',{'capacity_l':.5}),
('flask-large','Stainless steel vacuum bottle for hot drinks','9617','clear-for-filing',{'capacity_l':1}),
('flask-boundary','Complete vacuum flask made of stainless steel','9617','clear-for-filing',{'capacity_l':.75}),
('flask-over','Complete vacuum flask made of stainless steel','9617','clear-for-filing',{'capacity_l':.751}),
('buttons-metal','Base metal buttons for garments','9606','clear-for-filing',{}),
('buttons-plastic','Plastic buttons for shirts','9606','clear-for-filing',{}),
('pen','Ball point pen with a steel body','9608','clear-for-filing',{}),
('pencil','Wooden pencil for writing','9609','clear-for-filing',{}),
('toothbrush','Manual plastic toothbrush for household use','9603','clear-for-filing',{}),
('comb','Plastic comb for grooming hair','9615','clear-for-filing',{}),
('zipper','Slide fastener for jackets','9607','clear-for-filing',{}),
('bolt','Steel bolts for general construction','7318','clear-for-filing',{}),
('screw','Stainless steel screws for household repair','7318','clear-for-filing',{}),
('nut','Steel nuts for fastening bolts','7318','clear-for-filing',{}),
('nail','Iron nails for woodworking','7317','clear-for-filing',{}),
('chain','Steel chain for lifting goods','7315','clear-for-filing',{}),
('pipe-fitting','Stainless steel pipe fitting elbow','7307','clear-for-filing',{}),
('saucepan','Stainless steel saucepan for cooking','7323','clear-for-filing',{}),
('scourer','Steel wool scouring pad for washing pots','7323','clear-for-filing',{}),
('sewing-needle','Steel sewing needle for use by hand','7319','clear-for-filing',{}),
('padlock','Steel padlock for warehouse doors',None,'specialist-classification-review',{}),
('glass-inner','Glass inner for a vacuum flask',None,'specialist-classification-review',{}),
('cosmetic-pencil','Cosmetic pencil for use on skin',None,'specialist-classification-review',{}),
('electric-toothbrush','Electric toothbrush with a motor',None,'specialist-classification-review',{}),
('unidentified','Manufactured metal article of unknown purpose',None,'seek-product-clarification',{}),
('composite-equal','Combined pen and toothbrush with equal function and no essential character',None,'specialist-classification-review',{}),
('non-vacuum','Stainless steel non-vacuum bottle for household use','7323','clear-for-filing',{})]
cases=[]
for i,(name,d,h,route,fields) in enumerate(rows):
 support=['GRI1','N15','N73','N96']+(['H'+h,'P'+h] if h else ['SCOPE'])
 if name=='composite-equal':support+=['GRI2','GRI3']
 cases.append({'id':f'{i+1:02}-{name}','product':{'description':d,**fields},'expected':{'heading':h,'route':route},'support':support,'rationale':'Frozen-snapshot evaluation; clear-for-filing requires POLICY_SNAPSHOT_CONFIRMED=true, and remains a proposed heading for broker review.'})
Path('eval/scenarios.json').write_text(json.dumps(cases,indent=2));print(len(cases),'cases')
