# Painéis de vagas — Beatriz e Sueli

1. Crie um repositório público no GitHub e envie **todo o conteúdo desta pasta**, incluindo `.github/workflows/atualizar.yml`.
2. Em **Settings > Pages**, escolha **Deploy from a branch**, `main`, pasta `/ (root)` e salve.
3. Abra `https://SEU-USUARIO.github.io/NOME-DO-REPOSITORIO/` para acessar os dois painéis.
4. O GitHub Actions confere a lista `dados/fontes.json` a cada 5 minutos (horário aproximado; o GitHub pode atrasar ou pular execuções). O painel consulta `dados/beatriz.json` e `dados/sueli.json` a cada 5 minutos enquanto estiver aberto.

**IMPORTANTE:** o fluxo incluído valida e publica registros adicionados a `dados/fontes.json`; ele **não pesquisa automaticamente** LinkedIn, Burh, Indeed ou WhatsApp. Para coletar anúncios novos de verdade, será preciso adicionar uma fonte autorizada/API e um coletor específico. Não há login necessário para a lista manual; integrações externas podem exigir credenciais.

Formato de cada item em `dados/fontes.json`: `{"pessoa":"beatriz","id":"id-unico","name":"Nome da escola","role":"Auxiliar de berçário","area":"Centro, São José dos Pinhais","zone":"sjp","wa":"41999999999","email":"","source":"https://exemplo.com/anuncio"}`. Use **apenas contatos reais e publicamente divulgados**, nunca o número fictício do exemplo. Para Sueli, use `pessoa: sueli` e `zone: curitiba` ou `pinhais`.

As marcações de enviado/oculto/removido ficam no armazenamento local de cada navegador, não sincronizadas entre aparelhos. Recomenda-se backup antes de mudar de domínio ou dispositivo.

## Coleta de anúncios RSS
O script `scripts/atualizar.py` agora também lê fontes RSS públicas configuradas em `dados/feeds.json`, além dos registros manuais. Exemplo: `[{"pessoa":"beatriz","nome":"Fonte de vagas","url":"https://exemplo.org/vagas.rss"}]`. O endereço precisa ser **um RSS real**, com anúncios, localização e contato de recrutamento publicado. Não cole a página inicial do Burh ou do LinkedIn. Sem fontes RSS válidas, o robô não descobre novas vagas. Não há garantia de novas vagas a cada 5 minutos. O script não faz scraping de sites fechados nem descobre WhatsApps ocultos.
