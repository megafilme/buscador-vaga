"""Coleta vagas de feeds RSS públicos configurados em dados/feeds.json.
Não contorna login, bloqueio, captcha nem extrai WhatsApp de páginas arbitrárias.
"""
import json, re, hashlib, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path
from html import unescape
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'dados'
feeds=json.loads((D/'feeds.json').read_text(encoding='utf-8'))
manual=json.loads((D/'fontes.json').read_text(encoding='utf-8'))
all_items=list(manual)
for feed in feeds:
    url=feed.get('url','')
    if not url.startswith('https://'): continue
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'VagasPainel/1.0 (RSS reader)'})
        with urllib.request.urlopen(req,timeout=20) as resp:
            xml=resp.read(2_000_000)
        tree=ET.fromstring(xml)
        entries=tree.findall('.//item')
        for item in entries[:100]:
            title=unescape(''.join(item.findtext('title','').split()))
            link=item.findtext('link','').strip()
            description=unescape(re.sub('<[^>]*>',' ',item.findtext('description','')))
            combined=(title+' '+description).lower()
            who=feed.get('pessoa','').lower()
            if who=='beatriz':
                if not any(x in combined for x in ('infantil','creche','berçário','bercario','pedagogia','auxiliar de sala')):continue
                if 'são josé dos pinhais' not in combined and 'sao jose dos pinhais' not in combined:continue
                area='São José dos Pinhais, PR';zone='sjp'
            elif who=='sueli':
                if not any(x in combined for x in ('enfermagem','hospital','recepcionista','clínica','clinica')):continue
                if not any(x in combined for x in ('curitiba','cajuru','pinhais')):continue
                area='Curitiba ou Pinhais, PR (conferir anúncio)';zone='curitiba'
            else:continue
            if not link.startswith('https://'):continue
            # Apenas contatos explicitamente publicados no anúncio do feed.
            phone=re.search(r'(?:\+?55\s*)?\(?41\)?[\s.-]*9?\d{4}[\s.-]*\d{4}',description)
            wa=re.sub(r'\D','',phone.group()) if phone and 'whatsapp' in combined else ''
            mail=re.search(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}',description,re.I)
            email=mail.group() if mail else ''
            if not wa and not email:continue
            all_items.append({'pessoa':who,'id':'rss-'+hashlib.sha256(link.encode()).hexdigest()[:16], 'name':feed.get('nome','Anúncio público'), 'role':title,'area':area,'zone':zone,'source':link,'wa':wa,'email':email,'info':'Anúncio obtido de feed público; confira localização e disponibilidade antes de enviar.'})
    except Exception as exc:
        print('Feed indisponível:',url,str(exc)[:160])
for who in ('beatriz','sueli'):
    valid=[];seen=set()
    for j in all_items:
        if j.get('pessoa','').lower()!=who:continue
        if not all(j.get(k) for k in ('id','name','role','area','source')):continue
        if not str(j['source']).startswith('https://') or not (j.get('wa') or j.get('email')):continue
        if who=='beatriz' and (j.get('zone')!='sjp' or not ('São José dos Pinhais' in j['area'] or 'SJP' in j['area'])):continue
        if who=='sueli' and j.get('zone') not in ('curitiba','pinhais'):continue
        if j['id'] in seen:continue
        seen.add(j['id']);valid.append({k:v for k,v in j.items() if k!='pessoa'})
    path=D/f'{who}.json'
    path.write_text(json.dumps({'jobs':valid},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(who,len(valid),'vagas no feed')
