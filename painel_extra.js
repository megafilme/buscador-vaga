/* Painel de vagas — extras compartilhados (Beatriz e Sueli)
 *  1) "Verificar agora" dispara o robô no GitHub Actions, mostra a barrinha até terminar
 *     e já carrega o resultado novo.
 *  2) Mostra quando o robô rodou pela última vez (sem precisar de chave).
 *  3) Lista opcional de sites onde a candidatura é feita por cadastro no próprio site.
 *
 *  A chave do GitHub fica SÓ neste aparelho (localStorage). Ela só é necessária para
 *  disparar o robô na hora; ver as vagas e o horário da última busca funciona sem ela.
 */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const cfg = JSON.parse(($('config-data') || {}).textContent || '{"name":"Beatriz"}');
  const PESSOA = cfg.name.toLowerCase();
  const NO_PAGES = location.hostname.endsWith('github.io');
  const OWNER = NO_PAGES ? location.hostname.split('.')[0] : 'megafilme';
  const REPO = (NO_PAGES && location.pathname.split('/').filter(Boolean)[0]) || 'buscador-vaga';
  const WORKFLOW = 'atualizar.yml';
  const API = 'https://api.github.com';
  const TOKEN_KEY = 'painel_github_token_v1';
  const DUR_KEY = 'painel_github_duracao_busca_v1';
  const SITES_KEY = 'painel_sites_cadastro_' + PESSOA + '_v1';
  const REPO_URL = `https://github.com/${OWNER}/${REPO}`;

  const ler = (k, padrao) => { try { const v = localStorage.getItem(k); return v === null ? padrao : JSON.parse(v); } catch { return padrao; } };
  const gravar = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* sem armazenamento */ } };
  const apagar = k => { try { localStorage.removeItem(k); } catch { /* idem */ } };
  let token = ler(TOKEN_KEY, '');
  let branch = 'main';
  let rodando = false;

  const make = (tag, txt, cls) => { const n = document.createElement(tag); if (txt !== undefined) n.textContent = txt; if (cls) n.className = cls; return n; };
  const hora = d => new Date(d).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  const quando = d => {
    const min = Math.round((Date.now() - new Date(d).getTime()) / 60000);
    if (min < 1) return 'agora há pouco';
    if (min < 60) return `há ${min} min`;
    const h = Math.floor(min / 60);
    return h < 24 ? `há ${h} h` : new Date(d).toLocaleDateString('pt-BR') + ' ' + hora(d);
  };
  const mmss = s => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const dormir = ms => new Promise(r => setTimeout(r, ms));

  /* ------------------------------------------------------------ estilos */
  const css = document.createElement('style');
  css.textContent = `
  .gh-run{margin-top:10px;background:#fff;border:1px solid #c3e1f0;border-radius:12px;padding:11px 12px}
  .gh-run[hidden]{display:none}
  .gh-top{display:flex;justify-content:space-between;gap:10px;font-size:13px;font-weight:800;color:var(--ink)}
  .gh-bar{height:12px;border-radius:99px;background:#e3edf3;overflow:hidden;margin:8px 0 6px;position:relative}
  .gh-fill{height:100%;width:0;border-radius:99px;background:linear-gradient(90deg,#0d766d,#16a085);transition:width .6s ease}
  .gh-bar.vivo .gh-fill{background-image:linear-gradient(90deg,#0d766d,#16a085),linear-gradient(45deg,rgba(255,255,255,.25) 25%,transparent 25%,transparent 50%,rgba(255,255,255,.25) 50%,rgba(255,255,255,.25) 75%,transparent 75%);background-size:100% 100%,24px 24px;background-blend-mode:overlay;animation:ghListras 1s linear infinite}
  @keyframes ghListras{to{background-position:0 0,24px 0}}
  .gh-passos{list-style:none;margin:6px 0 0;padding:0;font-size:12px;color:#4d6275}
  .gh-passos li{padding:2px 0}
  .gh-msg{font-size:12px;color:#4d6275;margin-top:4px}
  .gh-msg a{color:var(--accent);font-weight:700}
  .gh-ultima{font-size:12px;color:#4d6275;margin:6px 0 0}
  .gh-cfg ol{margin:6px 0 8px 18px;padding:0;font-size:12px;color:#4d6275}
  .gh-cfg li{margin:3px 0}
  .gh-cfg input{display:block;width:100%;margin:6px 0;border:1px solid #bdcad7;border-radius:9px;padding:10px;font-family:monospace;font-size:12px}
  .gh-cfg .linha{display:flex;gap:7px;flex-wrap:wrap}
  .sites-lista{display:grid;gap:9px;margin-top:8px}
  .site{border:1px solid var(--line);border-radius:12px;padding:11px 12px;background:#fbfcfd}
  .site.feito{border-color:#a9dcbf;background:#f2fbf6}
  .site h4{margin:0 0 3px;font-size:14px}
  .site p{margin:0 0 8px;font-size:12px;color:#5b7083}
  .site .linha{display:flex;gap:7px;flex-wrap:wrap}
  .sites-grupo{font-size:12px;font-weight:800;color:var(--accent);margin:14px 0 2px;text-transform:uppercase;letter-spacing:.03em}
  `;
  document.head.append(css);

  /* ------------------------------------------------------------ GitHub API */
  async function gh(caminho, opcoes = {}, comToken = true) {
    const headers = { Accept: 'application/vnd.github+json', ...(opcoes.headers || {}) };
    if (comToken && token) headers.Authorization = 'Bearer ' + token;
    const res = await fetch(API + caminho, { cache: 'no-store', ...opcoes, headers });
    if (!res.ok && res.status !== 204) {
      const erro = new Error(res.status === 401 ? 'Chave do GitHub inválida ou vencida.'
        : res.status === 403 || res.status === 404 ? 'A chave não tem permissão (Actions: leitura e escrita) neste repositório.'
        : res.status === 422 ? 'O GitHub recusou o disparo (o workflow precisa ter "workflow_dispatch").'
        : 'GitHub respondeu HTTP ' + res.status);
      erro.status = res.status;
      throw erro;
    }
    return res.status === 204 ? null : res.json();
  }

  // Com chave, os dados vêm direto do repositório (sem esperar o GitHub Pages republicar).
  window.painelFetch = async (url, opcoes = {}) => {
    const ehMeuJson = String(url).includes(`/dados/${PESSOA}.json`);
    if (token && ehMeuJson) {
      try {
        const res = await fetch(`${API}/repos/${OWNER}/${REPO}/contents/dados/${PESSOA}.json?ref=${encodeURIComponent(branch)}`, {
          cache: 'no-store', signal: opcoes.signal,
          headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github.raw+json' },
        });
        if (res.ok) return res;
      } catch (e) { if (e.name === 'AbortError') throw e; }
    }
    return fetch(url, opcoes);
  };

  /* ------------------------------------------------------------ interface: progresso */
  const live = document.querySelector('.livebox');
  const painel = make('div', undefined, 'gh-run'); painel.hidden = true;
  const topo = make('div', undefined, 'gh-top');
  const titulo = make('span', 'Pesquisando vagas…');
  const tempo = make('span', '0:00');
  topo.append(titulo, tempo);
  const barra = make('div', undefined, 'gh-bar');
  const fill = make('div', undefined, 'gh-fill');
  barra.append(fill);
  const passosUl = make('ul', undefined, 'gh-passos');
  const msg = make('div', '', 'gh-msg');
  painel.append(topo, barra, passosUl, msg);
  const ultima = make('p', '', 'gh-ultima');
  if (live) {
    const cabecalho = live.querySelector('.live-head');
    (cabecalho || live).after(painel);
    painel.before(ultima);
  }

  function progresso(pct, texto, animado) {
    fill.style.width = Math.max(3, Math.min(100, pct)).toFixed(0) + '%';
    barra.classList.toggle('vivo', !!animado);
    if (texto) titulo.textContent = texto;
  }
  function setMsg(texto, link) {
    msg.replaceChildren(document.createTextNode(texto));
    if (link) { msg.append(' '); const a = make('a', link[0]); a.href = link[1]; a.target = '_blank'; a.rel = 'noopener'; msg.append(a); }
  }
  const NOMES_PASSO = {
    'Set up job': 'Preparando o robô', 'Run actions/checkout@v4': 'Baixando o projeto',
    'Run actions/setup-python@v5': 'Instalando Python', 'Run python scripts/atualizar.py': 'Pesquisando vagas nas fontes',
    'Publicar alterações, se houver': 'Salvando o resultado', 'Complete job': 'Finalizando',
  };
  function desenharPassos(steps) {
    passosUl.replaceChildren();
    for (const s of steps) {
      if (/^Post /.test(s.name)) continue;
      const icone = s.status === 'completed' ? (s.conclusion === 'success' || s.conclusion === 'skipped' ? '✅' : '❌')
        : s.status === 'in_progress' ? '⏳' : '▫️';
      passosUl.append(make('li', `${icone} ${NOMES_PASSO[s.name] || s.name}`));
    }
  }

  /* ------------------------------------------------------------ última execução (sem chave) */
  async function mostrarUltima() {
    try {
      const r = await gh(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`, {}, !!token);
      const run = r && r.workflow_runs && r.workflow_runs[0];
      if (!run) { ultima.textContent = ''; return null; }
      if (run.status !== 'completed') {
        ultima.textContent = '🤖 O robô está pesquisando agora…';
      } else {
        const ok = run.conclusion === 'success';
        ultima.textContent = `🤖 Última busca do robô: ${quando(run.updated_at)} ${ok ? '✅' : '⚠️ (' + run.conclusion + ')'}`;
      }
      return run;
    } catch { ultima.textContent = ''; return null; }
  }

  /* ------------------------------------------------------------ acompanhar uma execução */
  async function acompanhar(run) {
    const inicio = new Date(run.run_started_at || run.created_at).getTime();
    const previsto = ler(DUR_KEY, 240); // segundos do passo de pesquisa na última vez
    let inicioBusca = null;
    const limite = Date.now() + 20 * 60 * 1000;
    while (Date.now() < limite) {
      const seg = (Date.now() - inicio) / 1000;
      tempo.textContent = mmss(Math.max(0, seg));
      let atual = run;
      try {
        atual = await gh(`/repos/${OWNER}/${REPO}/actions/runs/${run.id}`);
        const jobs = await gh(`/repos/${OWNER}/${REPO}/actions/runs/${run.id}/jobs`);
        const steps = (jobs.jobs && jobs.jobs[0] && jobs.jobs[0].steps) || [];
        desenharPassos(steps);
        const busca = steps.find(s => /atualizar\.py/.test(s.name));
        if (atual.status === 'queued' || !steps.length) {
          progresso(4, 'Na fila do GitHub…', true);
          setMsg('Esperando uma máquina do GitHub ficar livre (costuma levar alguns segundos).');
        } else if (busca && busca.status === 'in_progress') {
          if (!inicioBusca) inicioBusca = new Date(busca.started_at || Date.now()).getTime();
          const decorrido = (Date.now() - inicioBusca) / 1000;
          const pct = 15 + Math.min(75, 75 * decorrido / Math.max(60, previsto));
          progresso(pct, 'Pesquisando vagas…', true);
          setMsg(`Consultando FreeHire e Gupy (${mmss(decorrido)} de ~${mmss(previsto)} previstos).`);
        } else if (busca && busca.status === 'completed') {
          if (busca.started_at && busca.completed_at) {
            gravar(DUR_KEY, Math.round((new Date(busca.completed_at) - new Date(busca.started_at)) / 1000));
          }
          progresso(atual.status === 'completed' ? 100 : 93, 'Salvando o resultado…', atual.status !== 'completed');
          setMsg('Pesquisa terminada, gravando as vagas no repositório.');
        } else {
          progresso(10, 'Preparando o robô…', true);
          setMsg('Ligando a máquina e baixando o projeto.');
        }
      } catch (e) {
        setMsg('Falha ao consultar o andamento: ' + e.message + ' Tentando de novo…');
      }
      if (atual.status === 'completed') return atual;
      await dormir(4000);
    }
    throw new Error('Passou de 20 minutos sem terminar.');
  }

  async function acharMinhaExecucao(desde) {
    for (let i = 0; i < 25; i++) {
      const r = await gh(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?event=workflow_dispatch&per_page=5`);
      const run = (r.workflow_runs || []).find(x => new Date(x.created_at).getTime() >= desde - 90000);
      if (run) return run;
      progresso(4, 'Mandando o robô pesquisar…', true);
      await dormir(3000);
    }
    throw new Error('O GitHub não iniciou a execução. Confira a aba Actions do repositório.');
  }

  async function execucaoEmAndamento() {
    for (const status of ['in_progress', 'queued']) {
      const r = await gh(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?status=${status}&per_page=1`);
      if (r.workflow_runs && r.workflow_runs[0]) return r.workflow_runs[0];
    }
    return null;
  }

  async function contarVagasNaTela() {
    const n = document.querySelectorAll('article.job').length;
    return n;
  }

  /* ------------------------------------------------------------ botão "Verificar agora" */
  window.verificarAgora = async () => {
    if (rodando) return;
    if (!token) {
      window.refreshFeed && window.refreshFeed();
      painel.hidden = false;
      progresso(100, 'Lista recarregada', false);
      tempo.textContent = '';
      passosUl.replaceChildren();
      setMsg('Recarreguei o resultado da última busca do robô. Para o botão mandar o robô pesquisar NA HORA, configure a chave em “⚡ Atualização instantânea pelo GitHub” logo abaixo.');
      return;
    }
    rodando = true;
    const botao = $('refreshButton');
    if (botao) { botao.disabled = true; botao.textContent = 'Pesquisando…'; }
    painel.hidden = false;
    passosUl.replaceChildren();
    tempo.textContent = '0:00';
    progresso(3, 'Mandando o robô pesquisar…', true);
    setMsg('Disparando o robô no GitHub Actions.');
    try {
      const repo = await gh(`/repos/${OWNER}/${REPO}`);
      branch = repo.default_branch || branch;
      let run = await execucaoEmAndamento();
      if (run) {
        setMsg('O robô já estava pesquisando — acompanhando essa execução.');
      } else {
        const desde = Date.now();
        await gh(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ref: branch }),
        });
        run = await acharMinhaExecucao(desde);
      }
      const final = await acompanhar(run);
      if (final.conclusion === 'success') {
        progresso(100, 'Carregando o resultado…', true);
        await dormir(1500);
        if (window.refreshFeed) await window.refreshFeed();
        progresso(100, `✅ Pesquisa concluída às ${hora(final.updated_at)}`, false);
        setMsg(`${await contarVagasNaTela()} vaga(s) na lista. ${($('feedStatus') || {}).textContent || ''}`);
      } else {
        progresso(100, '❌ O robô terminou com erro', false);
        setMsg(`Resultado: ${final.conclusion}. As vagas anteriores continuam na lista.`, ['Ver detalhes no GitHub', final.html_url]);
      }
    } catch (e) {
      progresso(100, '⚠️ Não deu para pesquisar agora', false);
      setMsg(e.message + ' A lista continua com o resultado anterior.');
      if (e.status === 401) setMsg(e.message + ' Gere uma nova chave e cole em “⚡ Atualização instantânea pelo GitHub”.');
      if (window.refreshFeed) window.refreshFeed();
    } finally {
      rodando = false;
      if (botao) { botao.disabled = false; botao.textContent = 'Verificar agora'; }
      mostrarUltima();
    }
  };

  /* ------------------------------------------------------------ configuração da chave */
  if (live) {
    const det = make('details', undefined, 'gh-cfg');
    const sum = make('summary', '⚡ Atualização instantânea pelo GitHub (opcional)');
    const exp = make('p', '', 'mini');
    exp.textContent = 'Com a chave, o botão “Verificar agora” manda o robô pesquisar na hora e mostra a barrinha até terminar. A chave fica salva só neste aparelho. Crie assim (uma vez só):';
    const ol = make('ol');
    const passos = [
      ['Abra a página de criação de chave do GitHub: ', ['abrir no GitHub', 'https://github.com/settings/personal-access-tokens/new']],
      ['Em “Repository access”, escolha “Only select repositories” e marque ' + OWNER + '/' + REPO + '.'],
      ['Em “Permissions → Repository permissions”: Actions = Read and write; Contents = Read-only.'],
      ['Clique em “Generate token”, copie a chave (começa com github_pat_) e cole aqui embaixo.'],
    ];
    for (const [texto, link] of passos) {
      const li = make('li', texto);
      if (link) { const a = make('a', link[0]); a.href = link[1]; a.target = '_blank'; a.rel = 'noopener'; li.append(a); }
      ol.append(li);
    }
    const input = make('input'); input.type = 'password'; input.autocomplete = 'off'; input.placeholder = 'github_pat_...';
    const estado = make('p', token ? '🔐 Chave salva neste aparelho.' : 'Nenhuma chave salva.', 'mini');
    const linha = make('div', undefined, 'linha');
    const bSalvar = make('button', '💾 Salvar e testar', 'btn green'); bSalvar.type = 'button';
    const bRemover = make('button', 'Remover chave', 'btn ghost'); bRemover.type = 'button';
    bSalvar.addEventListener('click', async () => {
      const v = input.value.trim();
      if (!/^(github_pat_|ghp_)[A-Za-z0-9_]{20,}$/.test(v)) { alert('Cole a chave inteira do GitHub (começa com github_pat_).'); return; }
      const anterior = token; token = v;
      estado.textContent = 'Testando a chave…';
      try {
        await gh(`/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}`);
        gravar(TOKEN_KEY, v); input.value = '';
        estado.textContent = '✅ Chave funcionando e salva neste aparelho. Toque em “Verificar agora”.';
        mostrarUltima();
      } catch (e) {
        token = anterior;
        estado.textContent = '❌ ' + e.message;
      }
    });
    bRemover.addEventListener('click', () => {
      if (!confirm('Remover a chave deste aparelho? O botão volta a só recarregar a lista.')) return;
      token = ''; apagar(TOKEN_KEY); estado.textContent = 'Chave removida deste aparelho.';
    });
    linha.append(bSalvar, bRemover);
    const aviso = make('p', 'Segurança: a chave só vale para este repositório e só consegue rodar o robô e ler os arquivos. Dá para apagá-la a qualquer momento no GitHub (Settings → Developer settings → Personal access tokens).', 'mini');
    det.append(sum, exp, ol, input, linha, estado, aviso);
    const detAntigo = live.querySelector('details');
    (detAntigo || painel).before(det);
  }

  /* ------------------------------------------------------------ sites de cadastro (opcional) */
  const q = s => encodeURIComponent(s);
  const indeed = (termo, local) => `https://br.indeed.com/jobs?q=${q(termo)}&l=${q(local)}`;
  const linkedin = (termo, local) => `https://www.linkedin.com/jobs/search/?keywords=${q(termo)}&location=${q(local)}`;
  const gupy = termo => `https://portal.gupy.io/job-search/term=${q(termo)}`;
  const slug = s => s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  const bne = (termo, cidade) => `https://www.bne.com.br/vagas-de-emprego-para-${slug(termo)}-em-${slug(cidade)}-pr`;
  const vagascom = (termo, cidade) => `https://www.vagas.com.br/vagas-de-${slug(termo)}-em-${slug(cidade)}`;

  const SITES = {
    beatriz: [
      { grupo: 'Busca nos portais (São José dos Pinhais)', itens: [
        { nome: 'Indeed — Educação Infantil', desc: 'Muitas escolas pequenas anunciam aqui. Cadastre o currículo uma vez e candidate-se pelo site.', links: [['Educação infantil', indeed('educação infantil', 'São José dos Pinhais, PR')], ['Auxiliar de sala', indeed('auxiliar de sala', 'São José dos Pinhais, PR')]] },
        { nome: 'BNE — Banco Nacional de Empregos', desc: 'Tem vagas de auxiliar de sala em SJP. Exige cadastro no site.', links: [['Auxiliar de sala', bne('auxiliar de sala', 'São José dos Pinhais')], ['Professor de educação infantil', bne('professor de educação infantil', 'São José dos Pinhais')]] },
        { nome: 'Vagas.com', desc: 'Busca por cargo e cidade. Candidatura com cadastro no site.', links: [['Auxiliar de sala', vagascom('auxiliar de sala', 'São José dos Pinhais')], ['Educação infantil', vagascom('educação infantil', 'São José dos Pinhais')]] },
        { nome: 'LinkedIn Vagas', desc: 'Precisa de perfil no LinkedIn.', links: [['Educação infantil', linkedin('educação infantil', 'São José dos Pinhais, Paraná, Brasil')]] },
        { nome: 'Gupy — portal de vagas', desc: 'Escolas particulares usam muito. Um cadastro na Gupy vale para todas as empresas.', links: [['Educação infantil', gupy('educação infantil')], ['Auxiliar de sala', gupy('auxiliar de sala')]] },
      ] },
      { grupo: 'Bancos de talentos de redes de escolas (cadastro direto)', itens: [
        { nome: 'Elite Rede de Ensino', desc: 'Tem unidades em SJP (Centro e Afonso Pena). Vagas de inspetor escolar e apoio.', links: [['Abrir vagas', 'https://elite.gupy.io/']] },
        { nome: 'Colégio Positivo', desc: 'Banco de talentos para Educação Infantil (Curitiba).', links: [['Abrir vagas', 'https://colegiopositivo.gupy.io/']] },
        { nome: 'Grupo Positivo', desc: 'Vagas do grupo, inclusive professora regente de Educação Infantil.', links: [['Abrir vagas', 'https://positivo.gupy.io/']] },
        { nome: 'Colégio Everest Curitiba', desc: 'Banco de talentos de auxiliar de professor.', links: [['Abrir vagas', 'https://colegioeverestcuritiba.gupy.io/']] },
      ] },
    ],
    sueli: [
      { grupo: 'Busca nos portais (Curitiba e Pinhais)', itens: [
        { nome: 'Indeed', desc: 'Cadastre o currículo uma vez e candidate-se pelo site.', links: [['Técnico de enfermagem', indeed('técnico de enfermagem', 'Curitiba, PR')], ['Recepcionista clínica', indeed('recepcionista clínica', 'Curitiba, PR')], ['Farmácia (Pinhais)', indeed('farmácia', 'Pinhais, PR')]] },
        { nome: 'BNE — Banco Nacional de Empregos', desc: 'Exige cadastro no site.', links: [['Técnico de enfermagem', bne('técnico de enfermagem', 'Curitiba')], ['Auxiliar de farmácia', bne('auxiliar de farmácia', 'Curitiba')], ['Técnico de enfermagem (Pinhais)', bne('técnico de enfermagem', 'Pinhais')]] },
        { nome: 'Vagas.com', desc: 'Muitos hospitais de Curitiba anunciam aqui (inclusive o Pequeno Príncipe).', links: [['Técnico de enfermagem', vagascom('técnico de enfermagem', 'Curitiba')], ['Auxiliar de farmácia', vagascom('auxiliar de farmácia', 'Curitiba')]] },
        { nome: 'LinkedIn Vagas', desc: 'Precisa de perfil no LinkedIn.', links: [['Técnico de enfermagem', linkedin('técnico de enfermagem', 'Curitiba, Paraná, Brasil')]] },
        { nome: 'Gupy — portal de vagas', desc: 'Um cadastro na Gupy vale para hospitais e farmácias que usam a plataforma.', links: [['Técnico de enfermagem', gupy('técnico de enfermagem')], ['Farmácia', gupy('farmácia')]] },
      ] },
      { grupo: 'Hospitais, laboratórios e farmácias (cadastro direto)', itens: [
        { nome: 'Hospital Marcelino Champagnat', desc: 'Grupo Marista.', links: [['Abrir vagas', 'https://hospitalsaomarcelinochampagnat.gupy.io/']] },
        { nome: 'Hospital Universitário Cajuru', desc: 'Grupo Marista.', links: [['Abrir vagas', 'https://hospitaluniversitariocajuru.gupy.io/']] },
        { nome: 'Pilar Hospital / Vera Cruz', desc: 'Recepção e enfermagem.', links: [['Abrir vagas', 'https://pilarhospital.gupy.io/']] },
        { nome: 'Hapvida NotreDame Intermédica', desc: 'Hospitais Onix em Curitiba e região.', links: [['Abrir vagas', 'https://hapvidandi.gupy.io/']] },
        { nome: 'Rede D’Or', desc: 'Hospital Santa Cruz em Curitiba.', links: [['Abrir vagas', 'https://rededor.gupy.io/']] },
        { nome: 'RD Saúde (Raia e Drogasil)', desc: 'Atendente e balconista de farmácia.', links: [['Abrir vagas', 'https://rdsaude-farmacia.gupy.io/']] },
        { nome: 'Clamed (Drogaria Catarinense / Preço Popular)', desc: 'Farmácias.', links: [['Abrir vagas', 'https://clamedlojas.gupy.io/']] },
        { nome: 'Dasa (laboratórios)', desc: 'Coleta, recepção e técnica de enfermagem.', links: [['Abrir vagas', 'https://dasa.pandape.infojobs.com.br/']] },
      ] },
    ],
  };

  const lista = SITES[PESSOA];
  const jobs = $('jobs');
  if (lista && jobs) {
    let feitos = ler(SITES_KEY, {});
    const secao = make('section', undefined, 'utility');
    const cab = make('button', '', 'togglehead'); cab.type = 'button';
    const corpo = make('div', undefined, 'utility-body'); corpo.hidden = true;
    const total = lista.reduce((n, g) => n + g.itens.length, 0);
    const atualizarCab = () => { cab.textContent = `🌐 Sites para se cadastrar e enviar currículo (opcional) • ${Object.keys(feitos).length}/${total} feitos ▾`; };
    cab.addEventListener('click', () => { corpo.hidden = !corpo.hidden; });
    corpo.append(make('p', 'Nestes sites a candidatura é feita no próprio site: cria-se um cadastro, preenche os dados e anexa o currículo. Não é obrigatório — use quando quiser. Marque “Já me cadastrei” para lembrar onde já fez.', 'mini'));
    for (const g of lista) {
      corpo.append(make('div', g.grupo, 'sites-grupo'));
      const grade = make('div', undefined, 'sites-lista');
      for (const s of g.itens) {
        const card = make('div', undefined, 'site' + (feitos[s.nome] ? ' feito' : ''));
        card.append(make('h4', (feitos[s.nome] ? '✅ ' : '') + s.nome), make('p', s.desc));
        const linha = make('div', undefined, 'linha');
        for (const [rotulo, url] of s.links) {
          const a = make('a', '🔗 ' + rotulo, 'btn small ghost'); a.href = url; a.target = '_blank'; a.rel = 'noopener noreferrer';
          linha.append(a);
        }
        const marcar = make('button', feitos[s.nome] ? '↩️ Desmarcar' : '✅ Já me cadastrei', 'btn small ' + (feitos[s.nome] ? 'ghost' : 'soft'));
        marcar.type = 'button';
        marcar.addEventListener('click', () => {
          if (feitos[s.nome]) delete feitos[s.nome]; else feitos[s.nome] = new Date().toISOString();
          gravar(SITES_KEY, feitos);
          card.classList.toggle('feito', !!feitos[s.nome]);
          card.querySelector('h4').textContent = (feitos[s.nome] ? '✅ ' : '') + s.nome;
          marcar.textContent = feitos[s.nome] ? '↩️ Desmarcar' : '✅ Já me cadastrei';
          marcar.className = 'btn small ' + (feitos[s.nome] ? 'ghost' : 'soft');
          atualizarCab();
        });
        linha.append(marcar);
        card.append(linha);
        grade.append(card);
      }
      corpo.append(grade);
    }
    atualizarCab();
    secao.append(cab, corpo);
    jobs.after(secao);
  }

  /* ------------------------------------------------------------ início */
  (async () => {
    const run = await mostrarUltima();
    // Se o robô já estiver rodando quando a página abre e houver chave, acompanha na barrinha.
    if (token && run && run.status !== 'completed' && !rodando) window.verificarAgora();
  })();
  setInterval(() => { if (!rodando && document.visibilityState === 'visible') mostrarUltima(); }, 5 * 60 * 1000);
})();
