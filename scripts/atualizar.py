        return False
    return any(c in t for c in CIDADES[pessoa])

def cargo_ok(texto, pessoa):
    t = normalizar(texto)
    return any(c in t for c in CARGOS[pessoa])

def contato(texto):
    email = re.search(r'[\w.+-]+@[\w.-]+\.[a-z]{2,}', texto, re.I)
    tel = re.search(r'(?:\+?55\s*)?\(?41\)?[\s.-]*9\d{4}[\s.-]*\d{4}', texto)
    wa = re.sub(r'\D', '', tel.group()) if tel and 'whatsapp' in normalizar(texto) else ''
    return wa, email.group() if email else ''

itens = list(ler('fontes.json', []))
feeds = ler('feeds.json', [])
if not isinstance(feeds, list):
    raise ValueError('dados/feeds.json precisa conter uma lista JSON, como []')

for feed in feeds:
    url = feed.get('url', '')
    pessoa = feed.get('pessoa', '').lower()
    if pessoa not in CIDADES or not url.startswith('https://'):
        continue
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; PainelVagas/1.0)'})
        with urllib.request.urlopen(req, timeout=20) as resposta:
            xml = resposta.read(2_000_000)
        raiz = ET.fromstring(xml)
        entradas = raiz.findall('.//item')
        for item in entradas[:100]:
            titulo = limpar(item.findtext('title', ''))
            descricao = limpar(item.findtext('description', ''))
            link = (item.findtext('link', '') or '').strip()
            texto = f'{titulo} {descricao}'
            # A cidade pode estar na descrição ou na configuração específica do feed.
            local = str(feed.get('cidade', '')).strip()
            if not cargo_ok(titulo, pessoa) or not cidade_ok(f'{texto} {local}', pessoa):
                continue
            if not link.startswith('https://'):
                continue
            wa, email = contato(descricao)
            cidade = 'São José dos Pinhais, PR' if pessoa == 'beatriz' else (local or 'Curitiba ou Pinhais, PR — conferir anúncio')
            zona = 'sjp' if pessoa == 'beatriz' else ('pinhais' if normalizar(cidade).startswith('pinhais') else 'curitiba')
            itens.append({
                'pessoa': pessoa, 'id': 'rss-' + hashlib.sha256(link.encode()).hexdigest()[:16],
                'name': feed.get('nome', 'Vaga publicada'), 'role': titulo,
                'area': cidade, 'zone': zona, 'source': link,
                'wa': wa, 'email': email,
                'info': 'Confira cidade, data e disponibilidade diretamente no anúncio.'
            })
    except Exception as erro:
        print('Falha ao consultar', url, str(erro)[:150])

for pessoa in ('beatriz', 'sueli'):
    resultado, vistos = [], set()
    for vaga in itens:
        if vaga.get('pessoa', '').lower() != pessoa:
            continue
        if not all(vaga.get(c) for c in ('id', 'name', 'role', 'area', 'source')):
            continue
        if not str(vaga['source']).startswith('https://'):
            continue
        if pessoa == 'beatriz' and (vaga.get('zone') != 'sjp' or not cidade_ok(vaga['area'], pessoa)):
            continue
        if pessoa == 'sueli' and vaga.get('zone') not in ('curitiba', 'pinhais'):
            continue
        if vaga['id'] in vistos:
            continue
        vistos.add(vaga['id'])
        resultado.append({k: v for k, v in vaga.items() if k != 'pessoa'})
    (D / f'{pessoa}.json').write_text(json.dumps({'jobs': resultado}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(pessoa, len(resultado), 'vagas')
