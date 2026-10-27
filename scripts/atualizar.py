"""Valida e publica vagas verificadas de dados/fontes.json.
Não extrai anúncios automaticamente de sites terceiros.
"""
import json,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
items=json.loads((root/'dados/fontes.json').read_text(encoding='utf-8'))
for who in ('beatriz','sueli'):
    valid=[]
    for j in items:
        if j.get('pessoa','').lower()!=who: continue
        if not all(j.get(k) for k in ('id','name','role','area','source')): continue
        if not str(j['source']).startswith('https://'): continue
        if not (j.get('wa') or j.get('email')): continue
        if who=='beatriz' and (j.get('zone')!='sjp' or not ('São José dos Pinhais' in j['area'] or 'SJP' in j['area'])): continue
        if who=='sueli' and j.get('zone') not in ('curitiba','pinhais'): continue
        valid.append({k:v for k,v in j.items() if k!='pessoa'})
    (root/'dados'/f'{who}.json').write_text(json.dumps({'jobs':valid},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Listas verificadas. Sem fonte de coleta automática, não surgem novas vagas.')
