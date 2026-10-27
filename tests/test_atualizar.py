# -*- coding: utf-8 -*-
"""
Testes LOCAIS do buscador (não acessam a internet).

As respostas da API aqui são simuladas com dados de exemplo para testar as regras.
Resultado de consulta REAL só aparece no log do GitHub Actions.

Rodar:  python -m unittest discover -s tests -v
"""
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import atualizar as A  # noqa: E402

HOJE = date(2026, 10, 27)
CAMPOS_SITE = ["id", "name", "role", "area", "zone", "source", "wa", "email", "info"]


def vaga(titulo, empresa="Empresa X", local="São José dos Pinhais, PR", descricao="",
         link="https://vagas.exemplo.com/1", fonte="freehire", **kw):
    return A.Vaga(fonte=fonte, uid=kw.pop("uid", "u1"), titulo=titulo, empresa=empresa, area=local,
                  local_busca=local, descricao=descricao, link=link, **kw)


def aceita(pessoa, v):
    return A.avaliar(pessoa, v, HOJE)[0]


def fh(slug, title, company, location, link=None, **extra):
    d = {"public_slug": slug, "title": title, "company": company, "location": location,
         "apply_url": link or f"https://vagas.exemplo.com/{slug}?utm_source=freehire"}
    d.update(extra)
    return d


def api_falsa(por_cidade, falhar_gupy=True):
    """Simula a FreeHire ignorando o termo q (como o log real sugere: 63 iguais)."""
    chamadas = []

    def buscar(url, params):
        chamadas.append((url, dict(params)))
        if "gupy" in url:
            if falhar_gupy:
                raise A.ErroAPI("gupy indisponível no teste")
            return {"data": [], "pagination": {"total": 0}}
        if params.get("offset"):
            return {"data": [], "meta": {}}
        lista = por_cidade.get(params["cities"], [])
        return {"data": lista, "meta": {"total": len(lista)}}

    buscar.chamadas = chamadas
    return buscar


class SemEspera(unittest.TestCase):
    def setUp(self):
        p = mock.patch.object(A.time, "sleep", lambda *_: None)
        p.start()
        self.addCleanup(p.stop)


# ---------------------------------------------------------------- escola
class TestEscolaBeatriz(SemEspera):
    def test_cargos_escolares_validos_sao_aceitos(self):
        titulos = [
            "Auxiliar de Sala", "Auxiliar de Professora", "Professor(a) de Educação Infantil",
            "Berçarista", "Atendente de Creche", "Monitora Infantil", "Monitor Escolar",
            "Auxiliar Pedagógico", "Assistente de Educação Infantil", "Apoio Escolar",
            "Recreadora Infantil", "Auxiliar de Classe", "Auxiliar de Ensino",
            "Auxiliar de Desenvolvimento Infantil", "Recepcionista Escolar", "Secretária Escolar",
            "Atendente de Sala", "PROFESSORA DE EDUCACAO INFANTIL", "Auxiliar de Educação Infantil - CMEI",
        ]
        for t in titulos:
            with self.subTest(t):
                r = aceita("beatriz", vaga(t))
                self.assertTrue(r.aceita, f"{t}: {r.motivo}")
                self.assertIn(r.categoria, A.CATS_ESCOLA)

    def test_regressao_bugs_do_codigo_antigo(self):
        # O código antigo rejeitava estes dois casos.
        r = aceita("beatriz", vaga("Professor(a) de Educação Infantil e Ensino Fundamental"))
        self.assertTrue(r.aceita, r.motivo)        # antigo: "ensino fundamental" excluía a vaga
        r = aceita("beatriz", vaga("Auxiliar de Sala", local="São José dos Pinhais/PR"))
        self.assertTrue(r.aceita, r.motivo)        # antigo: '/' quebrava a comparação de cidade
        r = aceita("beatriz", vaga("Auxiliar de Sala", local="Paraná, Brasil", ))
        self.assertFalse(r.aceita)

    def test_recepcao_administrativo_exige_evidencia_de_escola(self):
        self.assertTrue(aceita("beatriz", vaga("Recepcionista", empresa="Colégio Estadual Silveira")).aceita)
        self.assertTrue(aceita("beatriz", vaga("Auxiliar Administrativo", empresa="CMEI Pequenos Passos")).aceita)
        self.assertTrue(aceita("beatriz", vaga("Recepcionista", descricao="Atuar na recepção da escola.")).aceita)
        self.assertFalse(aceita("beatriz", vaga("Recepcionista", empresa="Clínica Bem Estar")).aceita)
        self.assertFalse(aceita("beatriz", vaga("Auxiliar Administrativo", empresa="Transportes Silva")).aceita)

    def test_beneficio_auxilio_creche_nao_e_evidencia(self):
        r = aceita("beatriz", vaga("Auxiliar Administrativo", empresa="Metalúrgica ABC",
                                   descricao="Benefícios: VT, VR, auxílio creche e bolsa de estudos."))
        self.assertFalse(r.aceita)

    def test_empresa_com_educacao_no_nome_nao_basta(self):
        self.assertFalse(aceita("beatriz", vaga("Auxiliar Administrativo", empresa="Grupo Educação Brasil")).aceita)
        # Grupo Marista também é dono de hospitais (Cajuru, Marcelino Champagnat)
        self.assertFalse(aceita("beatriz", vaga("Auxiliar Administrativo", empresa="Grupo Marista")).aceita)
        self.assertFalse(aceita("beatriz", vaga("Recepcionista", empresa="Autoescola Rota Certa")).aceita)

    def test_professores_de_disciplinas_incompativeis_sao_rejeitados(self):
        titulos = [
            "Professor de Inglês", "Professora de Espanhol", "Professor de Matemática",
            "Professor de Português", "Professor de Educação Física", "Professor de Curso Técnico em Enfermagem",
            "Docente Universitário - Administração", "Professor de Ensino Fundamental",
            "Professor de Inglês Infantil", "Professor de Educação Física - Educação Infantil",
            "Professor", "Auxiliar de Professor de Inglês",
        ]
        for t in titulos:
            with self.subTest(t):
                self.assertFalse(aceita("beatriz", vaga(t)).aceita, t)

    def test_falsos_positivos_genericos(self):
        for t in ("Auxiliar de Produção", "Auxiliar de Sala de Vacina", "Vendedora Moda Infantil",
                  "Auxiliar de Sala Cirúrgica", "Auxiliar de Limpeza", "Estagiário em Pedagogia"):
            with self.subTest(t):
                self.assertFalse(aceita("beatriz", vaga(t)).aceita, t)

    def test_colonia_rio_grande_ganha_prioridade(self):
        r1 = aceita("beatriz", vaga("Auxiliar de Sala", descricao="CMEI no bairro Colônia Rio Grande"))
        r2 = aceita("beatriz", vaga("Auxiliar de Sala"))
        self.assertGreater(r1.score, r2.score)


# ---------------------------------------------------------------- cidades
class TestCidades(SemEspera):
    def test_detectar_cidades(self):
        self.assertEqual(A.cidades_do_local("São José dos Pinhais, PR"), {"sjp"})
        self.assertEqual(A.cidades_do_local("Sao Jose dos Pinhais/PR - Brasil"), {"sjp"})
        self.assertEqual(A.cidades_do_local("Curitiba, Paraná, Brasil"), {"curitiba"})
        self.assertEqual(A.cidades_do_local("Pinhais - PR"), {"pinhais"})
        self.assertEqual(A.cidades_do_local(["Pinhais"]), {"pinhais"})
        self.assertEqual(A.cidades_do_local("Remoto"), set())

    def test_local_principal_manda(self):
        # Caso real: vaga de Piraí do Sul chegou com Curitiba numa lista secundária.
        v = A.Vaga(fonte="freehire", uid="x", titulo="Auxiliar de Sala", empresa="Escola X",
                   area="PIRAI DO SUL, PR, Brasil", local_busca="PIRAI DO SUL, PR, Brasil ; Curitiba",
                   descricao="", link="https://x.com/1")
        self.assertEqual(aceita("beatriz", v).motivo, "cidade incorreta")
        # Local principal genérico: aí sim usa a lista de cidades.
        v2 = A.Vaga(fonte="freehire", uid="y", titulo="Auxiliar de Sala", empresa="Escola X",
                    area="PR, Brasil", local_busca="PR, Brasil ; São José dos Pinhais",
                    descricao="", link="https://x.com/2")
        self.assertTrue(aceita("beatriz", v2).aceita)

    def test_curitiba_nao_vira_sjp_para_escola(self):
        # Escola em Curitiba: entra como 2ª opção, sempre abaixo de SJP, com zona "curitiba".
        v = vaga("Auxiliar de Sala", local="Curitiba, PR")
        r_cwb, cidades = A.avaliar("beatriz", v, HOJE)
        self.assertTrue(r_cwb.aceita)
        self.assertEqual(A.montar_item("beatriz", v, r_cwb, cidades)["zone"], "curitiba")
        r_sjp = aceita("beatriz", vaga("Recepcionista", empresa="Escola X"))   # pior cargo de SJP
        self.assertGreater(r_sjp.score, r_cwb.score)
        # Desligando a opção, Curitiba é rejeitada.
        with mock.patch.object(A, "ACEITAR_ESCOLA_CURITIBA", False):
            r = aceita("beatriz", vaga("Auxiliar de Sala", local="Curitiba, PR"))
            self.assertFalse(r.aceita)
            self.assertTrue(r.motivo.startswith("cidade incorreta"))

    def test_pinhais_nao_vira_sjp(self):
        self.assertFalse(aceita("beatriz", vaga("Auxiliar de Sala", local="Pinhais, PR")).aceita)
        self.assertFalse(aceita("sueli", vaga("Técnico de Enfermagem", local="São José dos Pinhais, PR")).aceita)
        self.assertTrue(aceita("sueli", vaga("Técnico de Enfermagem", local="Pinhais, PR")).aceita)
        self.assertTrue(aceita("sueli", vaga("Técnico de Enfermagem", local="Curitiba, PR")).aceita)


# ---------------------------------------------------------------- enfermagem
class TestEnfermagem(SemEspera):
    def test_pediatricas_identificadas(self):
        casos = [
            ("Técnico de Enfermagem - UTI Neonatal", "Hospital X", ""),
            ("Técnico(a) de Enfermagem Pediatria", "Hospital Y", ""),
            ("Técnico de Enfermagem", "Hospital Pequeno Príncipe", ""),
            ("Tec. Enfermagem - Maternidade", "Hospital Z", ""),
            ("Técnico em Enfermagem", "Hospital W", "Atuação na UTI pediátrica e alojamento conjunto."),
        ]
        for t, e, d in casos:
            with self.subTest(t):
                r = aceita("beatriz", vaga(t, empresa=e, descricao=d, local="Curitiba, PR"))
                self.assertTrue(r.aceita, r.motivo)
                self.assertEqual(r.categoria, A.CAT_ENF_INF)

    def test_genericas_nao_sao_pediatricas(self):
        v = vaga("Técnico de Enfermagem", empresa="Hospital Cajuru", local="Curitiba, PR",
                 descricao="Atuação em UTI adulto e pronto-socorro. Benefícios: auxílio creche.")
        self.assertFalse(aceita("beatriz", v).aceita)
        self.assertFalse(A.enfermagem_infantil("Técnico de Enfermagem", "Hospital Cajuru"))
        self.assertTrue(aceita("sueli", v).aceita)       # para a Sueli serve
        self.assertFalse(aceita("beatriz", vaga("Enfermeiro Pediatria", local="Curitiba, PR")).aceita)


# ---------------------------------------------------------------- sueli
class TestSueli(SemEspera):
    def test_regras_sueli(self):
        ok = [("Auxiliar de Farmácia", "Drogaria X"), ("Balconista de Farmácia", "X"),
              ("Atendente", "Drogaria Nissei"), ("Recepcionista", "Clínica São Lucas"),
              ("Recepcionista Hospitalar", "X"), ("Recepcionista", "Laboratório Frischmann"),
              ("Auxiliar de Enfermagem", "X"), ("Técnico em Enfermagem", "X")]
        for t, e in ok:
            with self.subTest(t):
                self.assertTrue(aceita("sueli", vaga(t, empresa=e, local="Curitiba, PR")).aceita, t)
        nao = [("Farmacêutico", "Drogaria X"), ("Recepcionista", "Hotel Central"),
               ("Recepcionista", "Clínica Veterinária Pet"), ("Auxiliar de Sala", "Escola X"),
               ("Auxiliar de Produção Farmacêutica", "Indústria Y")]
        for t, e in nao:
            with self.subTest(t):
                self.assertFalse(aceita("sueli", vaga(t, empresa=e, local="Curitiba, PR")).aceita, t)

    def test_recepcionista_generica_nao_vira_saude(self):
        # Casos reais do JSON: recepcionista de RH/empresa comum entrou por causa de "exames".
        genericas = [
            ("Recepcionista", "ADECCO", "Benefícios: VT, VR, plano de saúde. Exames admissionais por conta da empresa."),
            ("Recepcionista", "The Foursales Company", "Atendimento a clientes e visitantes. Assistência médica."),
            ("Recepcionista Curitiba", "Laboratório Vetex", ""),
        ]
        for t, e, d in genericas:
            with self.subTest(e):
                self.assertFalse(aceita("sueli", vaga(t, empresa=e, descricao=d, local="Curitiba, PR")).aceita)
        r = aceita("sueli", vaga("Recepcionista", empresa="Agência RH",
                                 descricao="Recepção da clínica, agendamento de consultas e atendimento a pacientes.",
                                 local="Curitiba, PR"))
        self.assertTrue(r.aceita, r.motivo)

    def test_nome_pagina_de_carreira(self):
        self.assertEqual(A.nome_empresa("Página de Carreira", "https://rededor.gupy.io/jobs/1"), "rededor (Gupy)")
        self.assertEqual(A.nome_empresa("Dasa", "https://x.gupy.io/jobs/1"), "Dasa")


# ---------------------------------------------------------------- outros filtros
class TestFiltrosGerais(SemEspera):
    def test_encerrada_antiga_e_sem_https(self):
        self.assertEqual(aceita("beatriz", vaga("Auxiliar de Sala", encerrada=True)).motivo, "encerrada")
        self.assertEqual(aceita("beatriz", vaga("Auxiliar de Sala", prazo=HOJE - timedelta(days=1))).motivo, "encerrada")
        self.assertFalse(aceita("beatriz", vaga("Auxiliar de Sala", publicada=HOJE - timedelta(days=200))).aceita)
        self.assertFalse(aceita("beatriz", vaga("Auxiliar de Sala", link="http://inseguro.com/x")).aceita)
        self.assertFalse(aceita("beatriz", vaga("Auxiliar de Sala", paises="PT")).aceita)

    def test_url_normalizada(self):
        a = A.normalizar_url("https://WWW.Site.com/vaga/1/?utm_source=x&id=2&fbclid=9")
        b = A.normalizar_url("https://site.com/vaga/1?id=2")
        self.assertEqual(a, b)


# ---------------------------------------------------------------- HTTP
class TestHTTP(SemEspera):
    def test_tenta_de_novo_em_erro_temporario(self):
        respostas = [
            urllib.error.HTTPError("u", 503, "x", {}, None),
            urllib.error.URLError("timeout"),
        ]

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"data": [], "meta": {}}'

        def abrir(req, timeout):
            if respostas:
                raise respostas.pop(0)
            return Resp()

        with mock.patch.object(A.urllib.request, "urlopen", abrir):
            self.assertEqual(A.http_json("https://x", {}), {"data": [], "meta": {}})

    def test_erro_definitivo_nao_insiste(self):
        n = []

        def abrir(req, timeout):
            n.append(1)
            raise urllib.error.HTTPError("u", 404, "x", {}, None)

        with mock.patch.object(A.urllib.request, "urlopen", abrir):
            with self.assertRaises(A.ErroAPI):
                A.http_json("https://x", {})
        self.assertEqual(len(n), 1)

    def test_paginacao_para_quando_api_repete_pagina(self):
        pagina = [fh(f"s{i}", "Auxiliar de Sala", "Escola", SJP_TXT) for i in range(100)]
        chamadas = []

        def buscar(url, params):
            chamadas.append(params)
            return {"data": pagina, "meta": {}}   # ignora offset e repete

        resp = A.FreeHire(buscar).buscar(A.Consulta("beatriz", "t", "freehire", A.SJP, None, None, 10))
        self.assertEqual(len(resp.vagas), 100)
        self.assertEqual(len(chamadas), 2)

    def test_gupy_404_desativa_sem_insistir(self):
        n = []

        def buscar(url, params):
            n.append(url)
            raise A.ErroAPI("HTTP 404 (erro definitivo)")

        g = A.Gupy(buscar)
        for _ in range(5):
            with self.assertRaises(A.ErroAPI):
                g.buscar(A.Consulta("beatriz", "t", "gupy", A.SJP, "auxiliar de sala", None, 2))
        self.assertEqual(len(n), 1)
        self.assertTrue(n[0].startswith("https://portal.gupy.io/api/job-search/jobs"))

    def test_gupy_sem_filtro_de_cidade(self):
        vistos = []

        def buscar(url, params):
            vistos.append(dict(params))
            if "city" in params:
                raise A.ErroAPI("HTTP 400 (erro definitivo)")
            return {"data": [{"id": 1, "name": "Auxiliar de Sala", "city": "São José dos Pinhais",
                              "state": "Paraná", "jobUrl": "https://x.gupy.io/jobs/1"},
                             {"id": 2, "name": "Auxiliar de Sala", "city": "Recife", "state": "PE",
                              "jobUrl": "https://y.gupy.io/jobs/2"}], "pagination": {"total": 2}}

        resp = A.Gupy(buscar).buscar(A.Consulta("beatriz", "t", "gupy", A.SJP, "auxiliar de sala", None, 2))
        self.assertEqual(len(resp.vagas), 2)
        self.assertNotIn("city", vistos[-1])
        self.assertIn("1/2", resp.obs)

    def test_filtro_ignorado_vira_erro(self):
        def buscar(url, params):
            return {"data": [], "meta": {"ignored_params": ["cities"]}}
        with self.assertRaises(A.ErroAPI):
            A.FreeHire(buscar).buscar(A.Consulta("beatriz", "t", "freehire", A.SJP, "x"))


SJP_TXT = "São José dos Pinhais, Paraná, Brasil"


# ---------------------------------------------------------------- execução completa
class TestExecucao(SemEspera):
    def setUp(self):
        super().setUp()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.api = {
            A.SJP: [
                fh("a1", "Auxiliar de Sala", "CMEI Sol", SJP_TXT),
                fh("a2", "Professor(a) de Educação Infantil", "Colégio Lua", "São José dos Pinhais/PR"),
                fh("a3", "Auxiliar de Produção", "Fábrica", SJP_TXT),
                fh("a4", "Professor de Inglês", "Escola de Idiomas", SJP_TXT),
                fh("a5", "Recepcionista", "Escola Estrela", SJP_TXT),
                # mesma vaga com outro slug e link com rastreamento -> duplicada
                fh("a1b", "Auxiliar de Sala", "CMEI Sol", SJP_TXT,
                   link="https://vagas.exemplo.com/a1?utm_source=outro"),
                fh("a6", "Auxiliar de Sala", "CMEI Fechado", SJP_TXT, closed_at="2026-10-01"),
            ],
            A.CWB: [
                fh("c1", "Técnico de Enfermagem - UTI Neonatal", "Hospital A", "Curitiba, PR"),
                fh("c2", "Técnico de Enfermagem", "Hospital B", "Curitiba, PR"),
                fh("c3", "Auxiliar de Sala", "Escola Curitiba", "Curitiba, PR"),
                fh("c4", "Auxiliar de Farmácia", "Drogaria X", "Curitiba, PR"),
            ],
            A.PINHAIS: [fh("p1", "Recepcionista", "Clínica Pinhais", "Pinhais, PR")],
        }

    def ler(self, pessoa):
        return json.loads((self.dir / f"{pessoa}.json").read_text(encoding="utf-8"))

    def test_escola_sjp_antes_de_escola_curitiba(self):
        A.executar(self.dir, api_falsa(self.api), HOJE, usar_gupy=False)
        jobs = self.ler("beatriz")["jobs"]
        zonas_escola = [j["zone"] for j in jobs if j["role"] in ("Auxiliar de Sala", "Recepcionista",
                                                                 "Professor(a) de Educação Infantil")]
        self.assertEqual(zonas_escola, ["sjp", "sjp", "sjp", "curitiba"])
        cwb = [j for j in jobs if j["zone"] == "curitiba" and j["role"] == "Auxiliar de Sala"][0]
        self.assertIn("Curitiba", cwb["info"])

    @mock.patch.object(A, "ACEITAR_ESCOLA_CURITIBA", False)
    def test_formato_e_conteudo(self):
        A.executar(self.dir, api_falsa(self.api), HOJE, usar_gupy=False)
        bea, sue = self.ler("beatriz"), self.ler("sueli")
        self.assertEqual(list(bea), ["jobs"])
        for j in bea["jobs"] + sue["jobs"]:
            self.assertEqual(list(j), CAMPOS_SITE)
            self.assertTrue(j["source"].startswith("https://"))
        roles_b = [j["role"] for j in bea["jobs"]]
        # Escolas primeiro, depois enfermagem infantil
        self.assertEqual(roles_b[:3].count("Auxiliar de Sala") + roles_b[:3].count("Recepcionista")
                         + roles_b[:3].count("Professor(a) de Educação Infantil"), 3)
        self.assertEqual(roles_b.count("Auxiliar de Sala"), 1)                 # duplicada e encerrada fora
        self.assertIn("Técnico de Enfermagem - UTI Neonatal", roles_b)
        self.assertNotIn("Técnico de Enfermagem", roles_b)                     # genérica fora
        self.assertNotIn("Professor de Inglês", roles_b)
        self.assertNotIn("Auxiliar de Produção", roles_b)
        self.assertTrue(all(j["zone"] in ("sjp", "curitiba") for j in bea["jobs"]))
        roles_s = {j["role"] for j in sue["jobs"]}
        self.assertEqual(roles_s, {"Técnico de Enfermagem", "Técnico de Enfermagem - UTI Neonatal",
                                   "Auxiliar de Farmácia", "Recepcionista"})
        pin = [j for j in sue["jobs"] if j["role"] == "Recepcionista"][0]
        self.assertEqual(pin["zone"], "pinhais")

    def test_urls_duplicadas_eliminadas(self):
        A.executar(self.dir, api_falsa(self.api), HOJE, usar_gupy=False)
        urls = [A.normalizar_url(j["source"]) for j in self.ler("beatriz")["jobs"]]
        self.assertEqual(len(urls), len(set(urls)))

    def test_falha_total_da_api_nao_apaga_arquivos(self):
        for p in ("beatriz", "sueli"):
            (self.dir / f"{p}.json").write_text('{"jobs": [{"id": "x"}]}\n', encoding="utf-8")
        antes = {p: (self.dir / f"{p}.json").read_bytes() for p in ("beatriz", "sueli")}

        def sempre_falha(url, params):
            raise A.ErroAPI("fora do ar")

        A.executar(self.dir, sempre_falha, HOJE, usar_gupy=True)
        for p in ("beatriz", "sueli"):
            self.assertEqual((self.dir / f"{p}.json").read_bytes(), antes[p])

    def test_falha_parcial_mantem_vaga_recente_e_descarta_antiga(self):
        A.executar(self.dir, api_falsa(self.api), HOJE - timedelta(days=1), usar_gupy=False)
        # Agora a vaga a5 sumiu e uma consulta da FreeHire falha
        api2 = {k: [v for v in vs if v["public_slug"] != "a5"] for k, vs in self.api.items()}
        base = api_falsa(api2)
        n = {"i": 0}

        def falha_uma(url, params):
            n["i"] += 1
            if n["i"] == 3:
                raise A.ErroAPI("timeout simulado")
            return base(url, params)

        A.executar(self.dir, falha_uma, HOJE, usar_gupy=False)
        self.assertIn("Recepcionista", [j["role"] for j in self.ler("beatriz")["jobs"]])  # mantida (1 dia)

        # 10 dias depois, ainda falhando: não mantém mais
        n["i"] = 0
        A.executar(self.dir, falha_uma, HOJE + timedelta(days=10), usar_gupy=False)
        self.assertNotIn("Recepcionista", [j["role"] for j in self.ler("beatriz")["jobs"]])

    def test_sem_falha_vaga_que_sumiu_sai(self):
        A.executar(self.dir, api_falsa(self.api), HOJE, usar_gupy=False)
        api2 = {k: [v for v in vs if v["public_slug"] != "a5"] for k, vs in self.api.items()}
        A.executar(self.dir, api_falsa(api2), HOJE, usar_gupy=False)
        self.assertNotIn("Recepcionista", [j["role"] for j in self.ler("beatriz")["jobs"]])

    def test_fontes_manuais_continuam_funcionando(self):
        manual = [{"pessoa": "beatriz", "id": "m1", "name": "CMEI Manual", "role": "Berçarista",
                   "area": "São José dos Pinhais", "zone": "sjp", "source": "https://exemplo.com/m1",
                   "wa": "", "email": "", "info": "manual"}]
        (self.dir / "fontes.json").write_text(json.dumps(manual), encoding="utf-8")
        A.executar(self.dir, api_falsa(self.api), HOJE, usar_gupy=False)
        ids = [j["id"] for j in self.ler("beatriz")["jobs"]]
        self.assertIn("m1", ids)

    def test_gupy_convertida(self):
        gupy = {"data": [{"id": 77, "name": "Auxiliar de Sala", "careerPageName": "Colégio G",
                          "city": "São José dos Pinhais", "state": "Paraná", "country": "Brasil",
                          "jobUrl": "https://colegiog.gupy.io/jobs/77", "publishedDate": "2026-10-20T10:00:00Z",
                          "description": "Vaga em escola"}], "pagination": {"total": 1}}

        def buscar(url, params):
            if "gupy" in url:
                return gupy if params.get("city") == A.SJP else {"data": [], "pagination": {"total": 0}}
            return {"data": [], "meta": {}}

        A.executar(self.dir, buscar, HOJE, usar_gupy=True)
        jobs = self.ler("beatriz")["jobs"]
        self.assertEqual([j["id"] for j in jobs], ["gupy-77"])


if __name__ == "__main__":
    unittest.main()
