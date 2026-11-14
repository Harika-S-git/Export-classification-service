import csv,json,re
from pathlib import Path
rows=[]
for p in sorted(Path('results/load').glob('*_stats.csv')):
    m=re.match(r'w(\d+)-u(\d+)_stats',p.name)
    for r in csv.DictReader(p.open()):
        if r['Type']=='RUN' and r['Name']=='complete_run':
            rows.append({'workers':int(m[1]),'clients':int(m[2]),'n':int(r['Request Count']),'failures':int(r['Failure Count']),'rps':float(r['Requests/s']),'p50_seconds':float(r['50%'])/1000,'p95_seconds':float(r['95%'])/1000,'slo_met':float(r['95%'])<=30000,'source':str(p)})
rows.sort(key=lambda r:(r['workers'],r['clients']))
Path('results/load-summary.json').write_text(json.dumps({'slo_p95_seconds':30,'arrival_window_seconds':40,'stub_delay_seconds':.75,'cache':False,'rows':rows},indent=2));print(json.dumps(rows,indent=2))
