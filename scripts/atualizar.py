#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Buscador de vagas — Beatriz e Sueli.

Gera dados/beatriz.json e dados/sueli.json no MESMO formato usado pelo site:
    {"jobs": [{"id", "name", "role", "area", "zone", "source", "wa", "email", "info"}, ...]}

Usa só a biblioteca padrão do Python (não precisa instalar nada).

Fontes:
  - FreeHire  (https://freehire.me/api/v1/jobs/search)  — API pública.
  - Gupy      (https://portal.gupy.io/api/job-search/jobs) — endpoint público usado pela
                busca do portal.gupy.io (não exige login). NÃO é documentado oficialmente.
                (O endereço antigo portal.api.gupy.io passou a responder 404.)
                Para desligar: variável de ambiente USAR_GUPY=0.
  - dados/fontes.json (opcional) — vagas cadastradas à mão, como antes.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

# =====================================================================
# CONFIGURAÇÃO
# =====================================================================
D = Path(__file__).resolve().parents[1] / "dados"
ARQ_ESTADO = "estado_robo.json"          # memória do robô (última vez que cada vaga foi vista)

FREEHIRE_API = "https://freehire.me/api/v1/jobs/search"
GUPY_API = "https://portal.gupy.io/api/job-search/jobs"
USAR_GUPY = os.environ.get("USAR_GUPY", "1").strip().lower() not in ("0", "false", "nao", "não", "off")

TIMEOUT = 25                      # segundos por requisição
TENTATIVAS = 4                    # tentativas por requisição (espera 2s, 4s, 8s...)
PAUSA_ENTRE_REQUISICOES = 0.4     # educação com a API
POR_PAGINA = 100
MAX_PAGINAS_BUSCA = 3             # buscas por termo
MAX_PAGINAS_VARREDURA = 10        # varredura da cidade inteira (sem termo)
MAX_PAGINAS_GUPY = 3
# Escola em Curitiba entra como 2ª opção (abaixo das escolas de SJP). Para aceitar só SJP: False.
ACEITAR_ESCOLA_CURITIBA = os.environ.get("ESCOLA_CURITIBA", "1").strip().lower() not in ("0", "false", "nao", "não", "off")
DIAS_MANTER_SE_FONTE_FALHAR = 3   # vaga antiga só é mantida por até 3 dias se a fonte falhar
IDADE_MAXIMA_DIAS = 60            # anúncio publicado há mais que isso é descartado
AMOSTRAS_REJEICAO = 8             # quantos exemplos de rejeição mostrar por consulta
USER_AGENT = "PainelVagasPessoal/2.0 (+https://github.com/megafilme/buscador-vaga)"
EM_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"

NOME_FONTE = {"freehire": "FreeHire", "gupy": "Gupy", "manual": "fontes.json"}
PESSOAS = ("beatriz", "sueli")
CIDADES_PERMITIDAS = {"beatriz": {"sjp", "curitiba"}, "sueli": {"curitiba", "pinhais"}}

SJP, CWB, PINHAIS = "São José dos Pinhais", "Curitiba", "Pinhais"

# Termos de busca da Beatriz (escola) — mantidos do código original.
ESCOLA_BUSCAS = (
    "creche", "educação infantil", "auxiliar de professora", "auxiliar de sala",
    "berçarista", "pedagogia", "secretaria escolar", "secretária escolar",
    "auxiliar de secretaria", "recepcionista escolar", "auxiliar administrativo escolar",
    "auxiliar de desenvolvimento infantil", "atendente infantil", "monitor de creche",
    "auxiliar pedagógico", "assistente de educação infantil", "atendente de sala",
    "assistente de sala", "auxiliar de educação infantil", "recreadora infantil",
    "apoio escolar", "apoio infantil", "monitor escolar", "auxiliar de classe",
    "auxiliar de ensino", "professora de educação infantil",
)
ESCOLA_EXTRAS = ("escola", "colégio", "cmei", "educação infantil", "berçário")
# (termo, q_fields) — None = deixa a API usar os campos padrão (título + descrição).
ESCOLA_BUSCAS_CURITIBA = (
    ("educação infantil", None), ("auxiliar de sala", "title"), ("auxiliar de professora", "title"),
    ("professora de educação infantil", "title"), ("berçarista", "title"), ("creche", None),
    ("cmei", None), ("monitor escolar", "title"), ("auxiliar de classe", "title"),
    ("auxiliar pedagógico", "title"), ("recepcionista escolar", "title"), ("secretária escolar", "title"),
    ("escola", "title"), ("colégio", "title"),
)
ENFERMAGEM_INFANTIL_BUSCAS = (
    ("técnico de enfermagem", "title"),
    ("técnico em enfermagem", "title"),
    ("auxiliar de enfermagem", "title"),
    ("enfermagem pediatria", None),
    ("enfermagem neonatal", None),
    ("enfermagem maternidade", None),
    ("pequeno príncipe", None),
)
# Buscas da Sueli — preservadas exatamente como estavam.
SUELI_CARGOS = (
    "técnico de enfermagem", "auxiliar de enfermagem", "auxiliar de farmácia",
    "atendente de farmácia", "recepcionista clínica", "recepcionista hospital",
    "farmácia", "balconista de farmácia", "recepcionista laboratório",
)
GUPY_BEATRIZ_ESCOLA = (
    "educação infantil", "auxiliar de sala", "auxiliar de professor",
    "professor de educação infantil", "berçarista", "monitor", "auxiliar de classe",
    "creche", "escola", "secretaria escolar", "recepcionista", "auxiliar administrativo",
    "pedagógico",
    # Ampliação (a Gupy é a fonte que mais traz escola):
    "inspetor", "assistente de sala", "auxiliar de turma", "auxiliar de educação",
    "berçário", "cuidador", "professor", "apoio escolar", "atendente", "secretária",
    "colégio", "infantil",
)
GUPY_ENFERMAGEM = ("técnico de enfermagem", "técnico em enfermagem", "auxiliar de enfermagem",
                   "enfermagem pediatria", "enfermagem neonatal", "maternidade")
GUPY_SUELI_EXTRAS = ("técnica de enfermagem", "recepcionista", "recepção", "balconista",
                     "atendente de farmácia", "atendente de loja", "auxiliar de laboratório")

# Categorias (aparecem no log e definem a ordem no site)
CAT_ESCOLA = "Escola / educação infantil"
CAT_ESCOLA_ADM = "Escola — recepção/administrativo"
CAT_ENF_INF = "Enfermagem pediátrica/neonatal"
CAT_ENF = "Enfermagem"
CAT_FARM = "Farmácia"
CAT_RECEP = "Recepção saúde"
CATS_ESCOLA = (CAT_ESCOLA, CAT_ESCOLA_ADM)


# =====================================================================
# LOG
# =====================================================================
def log(msg: str = "") -> None:
    print(msg, flush=True)


def grupo_inicio(titulo: str) -> None:
    log(f"::group::{titulo}" if EM_ACTIONS else f"\n=== {titulo} ===")


def grupo_fim() -> None:
    if EM_ACTIONS:
        log("::endgroup::")


def aviso(msg: str) -> None:
    log(f"::warning::{msg}" if EM_ACTIONS else f"AVISO: {msg}")


# =====================================================================
# TEXTO
# =====================================================================
def normalizar(s) -> str:
    """minúsculas, sem acento, sem '(a)'/'/a' de gênero, pontuação vira espaço."""
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\((a|o|as|os|es)\)", "", s)          # professor(a) -> professor
    s = re.sub(r"(?<=\w)/(a|o|as|os)\b", "", s)        # professor/a  -> professor
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def texto_de(v) -> str:
    """Achata str / número / lista / dict em texto."""
    if v is None or v is False:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, dict):
        partes = [texto_de(v.get(k)) for k in ("name", "title", "label", "city", "state", "code", "value")]
        return ", ".join(p for p in partes if p)
    if isinstance(v, (list, tuple, set)):
        return ", ".join(p for p in (texto_de(x) for x in v) if p)
    return str(v)


def ler_data(v) -> Optional[date]:
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)):
            seg = v / 1000 if v > 10_000_000_000 else v
            return datetime.fromtimestamp(seg, tz=timezone.utc).date()
        return date.fromisoformat(str(v).strip()[:10])
    except (ValueError, OverflowError, OSError):
        return None


def hoje_brasil() -> date:
    return datetime.now(timezone(timedelta(hours=-3))).date()


def _re(p: str) -> re.Pattern:
    return re.compile(p)


# =====================================================================
# CIDADES  (São José dos Pinhais ≠ Pinhais ≠ Curitiba)
# =====================================================================
RE_SJP = _re(r"\b(sao jose dos pinhais|s jose dos pinhais|sao jose d pinhais|sj dos pinhais|s j pinhais|sjp)\b")
RE_PINHAIS = _re(r"\bpinhais\b")
RE_CURITIBA = _re(r"\b(curitiba|cwb)\b")


def cidades_do_local(*partes) -> set:
    """Retorna {'sjp','pinhais','curitiba'} encontrados no texto de localização.
    Procura no texto inteiro (aceita 'São José dos Pinhais/PR', '... - PR', 'PR, Brasil' etc.)."""
    texto = " ; ".join(normalizar(texto_de(p)) for p in partes if p)
    achadas = set()
    if RE_SJP.search(texto):
        achadas.add("sjp")
        texto = RE_SJP.sub(" ", texto)   # tira SJP antes de procurar "Pinhais"
    if RE_PINHAIS.search(texto):
        achadas.add("pinhais")
    if RE_CURITIBA.search(texto):
        achadas.add("curitiba")
    return achadas


# =====================================================================
# REGRAS — BEATRIZ (escola) e ENFERMAGEM INFANTIL
# =====================================================================
# Frases de benefício que NÃO indicam escola ("auxílio creche", "bolsa de estudos"...)
RE_RUIDO_DESCRICAO = _re(
    r"(auxilio|reembolso|vale|ajuda de custo|beneficio)\s*(de\s*)?creche"
    r"|creche\s*(para|p)\s*(os\s*)?filhos"
    r"|bolsas?\s*(de\s*)?estudos?"
    r"|(convenios?|descontos?|parcerias?)\s*(com|em)?\s*(escolas?|colegios?|faculdades?|universidades?|instituicoes de ensino)"
    r"|auxilio\s*educacao|auxilio\s*escola\w*"
)

RE_PAPEL_ESCOLA = _re(
    r"\bauxiliar (de |da |do )?(sala|turma|classe|creche|ensino|professor|professora|educacao infantil"
    r"|desenvolvimento infantil|bercario|maternal|educacao)\b"
    r"|\batendente (de |da )?(sala|creche|bercario|educacao infantil|infantil)\b"
    r"|\bassistente (de |da )?(sala|turma|classe|creche|professor|professora|educacao infantil|ensino)\b"
    r"|\bbercarista\b|\bbercario\b|\bpajem\b"
    r"|\b(monitor|monitora) (de |da )?(infantil|escolar|creche|alunos|recreio|patio|educacao infantil|transporte escolar|sala)\b"
    r"|\b(recreador|recreadora|recreacionista) (infantil|escolar)\b"
    r"|\b(educador|educadora|cuidador|cuidadora) (infantil|de creche|escolar|de criancas|de bercario)\b"
    r"|\b(auxiliar|assistente|agente) (de apoio )?(pedagogic[oa]|educacional)\b"
    r"|\b(profissional de )?apoio (escolar|infantil|a inclusao|inclusivo|pedagogico|educacional)\b"
    r"|\b(inspetor|inspetora) (de )?(alunos|escolar)\b"
    r"|\b(secretario|secretaria|auxiliar de secretaria|assistente de secretaria) (escolar|de escola|de colegio)\b"
    r"|\b(recepcionista|atendente) (escolar|de escola|de colegio|de creche)\b"
    r"|\b(auxiliar|assistente) administrativ[oa] (escolar|de escola|de colegio|educacional)\b"
    r"|\beducacao infantil\b|\bcmei\b"
)
RE_DOCENTE = _re(r"\b(professor|professora|professores|docente|teacher|instrutor|instrutora|tutor|tutora|regente)\b")
RE_NIVEL_INFANTIL = _re(
    r"\b(educacao infantil|infantil|bercario|bercarista|maternal|pre escola|creche|cmei|primeira infancia|ensino infantil)\b"
)
RE_NIVEL_OUTRO = _re(
    r"\b(ensino fundamental|fundamental|anos iniciais|anos finais|ensino medio|ensino superior|superior"
    r"|graduacao|pos graduacao|universitari\w*|faculdade|eja|pre vestibular|vestibular|curso tecnico|tecnico)\b"
)
# Disciplinas: sempre rejeitadas quando o cargo é de professor/auxiliar de professor.
RE_MATERIA = _re(
    r"\b(ingles|english|espanhol|frances|alemao|italiano|mandarim|libras|matematica|portugues|lingua portuguesa"
    r"|literatura|redacao|historia|geografia|ciencias|quimica|fisica|biologia|filosofia|sociologia|artes|arte"
    r"|musica|danca|teatro|educacao fisica|informatica|robotica|programacao|administracao|logistica"
    r"|contabilidade|direito|reforco escolar|natacao|judo|karate|xadrez|ballet|bale|curso tecnico)\b"
)
RE_DOCENTE_SUPERIOR = _re(r"\b(docente|professor|professora)\b.*\b(universitari\w*|ensino superior|faculdade|graduacao|pos graduacao|curso tecnico|tecnico)\b")
RE_ESTAGIO_PEDAGOGIA = _re(r"\bestagi\w* (em |de |da )?pedagogia\b")
RE_CONTEXTO_NAO_ESCOLAR = _re(
    r"\bsala (de )?(cirurgia|cirurgica|vacina|vacinacao|operacoes|embarque|cinema|vip|limpa|cofre|controle"
    r"|reuniao|maquinas|exames|emergencia|medicacao|gesso|parto)\b"
    r"|\b(cirurgi\w*|hospital\w*|odontolog\w*|dentist\w*|consultorio|clinica|farmac\w*|drogari\w*|loja|lojas"
    r"|moda|vendedor\w*|vendas|buffet|hotel|cinema|restaurante|cozinha|limpeza|producao|industria\w*"
    r"|almoxarifado|estoque|telemarketing|call center|academia|fitness|musculacao|autoescola|auto escola"
    r"|escola de conducao|cfc)\b"
)
RE_ADMIN_GENERICO = _re(
    r"\b(auxiliar administrativ[oa]|assistente administrativ[oa]|agente administrativ[oa]|recepcionista"
    r"|secretario|secretaria|auxiliar de secretaria|assistente de secretaria|auxiliar de apoio"
    r"|auxiliar de escritorio|atendente)\b"
)
RE_EVID_ESCOLA = _re(
    r"\b(escola|escolas|escolinha|colegio|colegios|creche|creches|cmei|cmeis|centro (municipal )?de educacao infantil"
    r"|educacao infantil|bercario|pre escola|jardim de infancia|ensino infantil|instituicao de ensino|educandario"
    r"|maple bear)\b"
)
RE_EVID_ESCOLA_EMPRESA = _re(RE_EVID_ESCOLA.pattern + r"|\bcei\b|\bmaternal\b")
RE_ESCOLA_FALSA = _re(r"\b(autoescola|auto escola|escola de conducao|cfc)\b")
RE_TITULO_GENERICO = _re(
    r"(auxiliar|assistente|monitor|monitora|atendente|educador|educadora|cuidador|cuidadora)"
    r"( (i|ii|iii|jr|junior|pleno|temporari[oa]|efetiv[oa]|pcd|vaga pcd|\d+))*"
)

RE_TEC_ENF = _re(r"\b(tecnic[oa]|tecnicos|tec|auxiliar|auxiliares) (de |em |da )?enfermagem\b")
RE_SINAL_INF_TITULO = _re(
    r"\b(pediatri\w*|pediatric\w*|neonat\w*|uti neo|utin|uti ped|utip|infantil|crianca|criancas"
    r"|recem nascid\w*|teste do pezinho|maternidade|obstetric\w*|alojamento conjunto|bercario|puericultura"
    r"|banco de leite|centro obstetrico|sala de parto|materno infantil)\b"
)
RE_SINAL_INF_DESCR = _re(
    r"\b(pediatri\w*|pediatric\w*|neonat\w*|uti neo|utin|uti ped|utip|recem nascid\w*|teste do pezinho"
    r"|alojamento conjunto|puericultura|banco de leite|centro obstetrico|maternidade|bercario|materno infantil)\b"
)
RE_EMPRESA_INF = _re(
    r"\b(pequeno principe|hospital infantil|hospital da crianca|maternidade|materno infantil|hospital materno"
    r"|pediatri\w*|neonat\w*)\b"
)
RE_VACINA = _re(r"\bvacin\w*\b")
RE_COLONIA = _re(r"\bcolonia rio grande\b")


@dataclass
class Resultado:
    aceita: bool
    motivo: str = ""
    categoria: str = ""
    score: int = 0
    nota: str = ""


def _rej(motivo: str) -> Resultado:
    return Resultado(False, motivo=motivo)


def _ok(categoria: str, score: int, nota: str = "") -> Resultado:
    return Resultado(True, categoria=categoria, score=score, nota=nota)


def limpar_descricao(descricao) -> str:
    return RE_RUIDO_DESCRICAO.sub(" ", normalizar(descricao))


def classificar_enfermagem_infantil(titulo, empresa="", descricao="") -> Resultado:
    t, e, d = normalizar(titulo), normalizar(empresa), limpar_descricao(descricao)
    if not RE_TEC_ENF.search(t):
        return _rej("enfermagem fora do perfil (não é técnico/auxiliar)")
    if RE_SINAL_INF_TITULO.search(t):
        return _ok(CAT_ENF_INF, 50)
    if RE_EMPRESA_INF.search(e):
        return _ok(CAT_ENF_INF, 45, "Hospital/maternidade com atendimento infantil.")
    if RE_VACINA.search(t):
        return _ok(CAT_ENF_INF, 38, "Sala de vacina: confirme se há vacinação infantil.")
    if RE_SINAL_INF_DESCR.search(d):
        return _ok(CAT_ENF_INF, 35, "Foco infantil citado só na descrição; confirme o setor.")
    return _rej("enfermagem sem foco infantil")


def enfermagem_infantil(titulo, empresa="", descricao="") -> bool:
    """Compatibilidade com o código antigo."""
    return classificar_enfermagem_infantil(titulo, empresa, descricao).aceita


def classificar_beatriz(titulo, empresa="", descricao="") -> Resultado:
    t, e, d = normalizar(titulo), normalizar(empresa), limpar_descricao(descricao)

    if "enfermag" in t or "enfermeir" in t:
        return classificar_enfermagem_infantil(titulo, empresa, descricao)
    if RE_ESTAGIO_PEDAGOGIA.search(t):
        return _rej("estágio em pedagogia (fora do perfil)")
    if RE_CONTEXTO_NAO_ESCOLAR.search(t):
        return _rej("cargo incompatível (contexto não escolar)")

    papel = RE_PAPEL_ESCOLA.search(t)
    docente = RE_DOCENTE.search(t)

    if (papel or docente) and RE_MATERIA.search(t):
        return _rej("professor de disciplina incompatível")
    if docente and RE_DOCENTE_SUPERIOR.search(t) and not RE_NIVEL_INFANTIL.search(t):
        return _rej("docente de curso técnico/superior")

    evid_escola = bool(
        (RE_EVID_ESCOLA_EMPRESA.search(e) and not RE_ESCOLA_FALSA.search(e))
        or RE_EVID_ESCOLA.search(t)
    )
    if papel:
        return _ok(CAT_ESCOLA, 100 if evid_escola else 90)
    if docente:
        if RE_NIVEL_INFANTIL.search(t):
            return _ok(CAT_ESCOLA, 95)
        if RE_NIVEL_OUTRO.search(t):
            return _rej("professor de outro nível de ensino")
        return _rej("professor sem foco em educação infantil")

    if RE_ADMIN_GENERICO.search(t):
        if evid_escola:
            return _ok(CAT_ESCOLA_ADM, 85 if RE_EVID_ESCOLA.search(t) else 80)
        if RE_EVID_ESCOLA.search(d) and not RE_ESCOLA_FALSA.search(d):
            return _ok(CAT_ESCOLA_ADM, 65, "Escola citada só na descrição; confirme o local.")
        return _rej("recepção/administrativo sem evidência de escola")

    if RE_TITULO_GENERICO.fullmatch(t) and RE_PAPEL_ESCOLA.search(d) and (RE_EVID_ESCOLA.search(d) or evid_escola):
        return _ok(CAT_ESCOLA, 60, "Título genérico; a descrição indica trabalho em escola.")

    return _rej("cargo incompatível")


# =====================================================================
# REGRAS — SUELI (preservadas e ampliadas)
# =====================================================================
RE_FARMACIA = _re(r"\b(farmac\w*|drogari\w*)\b")
RE_REDE_FARMACIA = _re(r"\b(farmac\w*|drogari\w*|raia|drogasil|droga raia|panvel|nissei|pague menos|extrafarma)\b")
RE_FARMACIA_FORA = _re(
    r"\b(producao|industria\w*|almoxarifado|logistica|estoque|representante|propagandista|farmaceutic[oa] (rt|responsavel)"
    r"|laboratorio farmaceutico)\b"
)
RE_PAPEL_FARMACIA = _re(r"\b(auxiliar\w*|atendente\w*|balconista\w*|tecnic\w*)\b")
RE_PAPEL_BALCAO = _re(
    r"\b(atendente|balconista|auxiliar de loja|operador de loja|atendente de loja|auxiliar de atendimento"
    r"|consultor de atendimento|auxiliar de farmacia)\b"
)
RE_CTX_SAUDE = _re(
    r"\b(hospital\w*|clinica\w*|policlinica|laboratorio\w*|centro medico|centro de diagnostico\w*|ambulatori\w*"
    r"|unimed|dasa|pequeno principe|rede d or|pilar hospital|medic[oa]s?|medica|odonto\w*|saude|diagnostic\w*"
    r"|exames|diagnostico por imagem|fisioterap\w*|oftalm\w*|dermatolog\w*|pronto atendimento|upa|consultorio"
    r"|frischmann)\b"
)
# "exames admissionais", "assistência médica" etc. aparecem em QUALQUER vaga — não contam.
RE_RUIDO_SAUDE = _re(
    r"exames?\s*(medicos?\s*)?(admissiona\w*|periodicos?|demissiona\w*|ocupaciona\w*)"
    r"|(plano|assistencia|convenio|seguro)\s*(de\s*)?(saude|medic\w*|odonto\w*|hospitalar)"
    r"|atendimento\s*medico\s*(e|ou)?\s*odontologico|medicina do trabalho|saude ocupacional"
)
RE_CTX_SAUDE_DESCR = _re(
    r"\b(pacientes?|consultorio|clinica medica|clinica odontologica|clinica de saude|centro clinico"
    r"|unidade de saude|recepcao hospitalar|recepcao da clinica|recepcao do hospital|laboratorio de analises"
    r"|agendamento de consultas|agendamento de exames|marcacao de consultas)\b"
)
RE_VET = _re(r"\b(veterinari\w*|pet shop|petshop|pet|vet\w*)\b")


def classificar_sueli(titulo, empresa="", descricao="") -> Resultado:
    t, e, d = normalizar(titulo), normalizar(empresa), limpar_descricao(descricao)

    if "enfermag" in t:
        if RE_TEC_ENF.search(t) or "tecnic" in t:
            return _ok(CAT_ENF, 50)
        return _rej("enfermagem fora do perfil (não é técnico/auxiliar)")

    if RE_FARMACIA.search(t):
        if RE_FARMACIA_FORA.search(t):
            return _rej("farmácia: indústria/estoque (fora do perfil)")
        if RE_PAPEL_FARMACIA.search(t):
            return _ok(CAT_FARM, 50)
        return _rej("farmácia: cargo fora do perfil (ex.: farmacêutico)")
    if RE_REDE_FARMACIA.search(e) and RE_PAPEL_BALCAO.search(t) and not RE_FARMACIA_FORA.search(t):
        return _ok(CAT_FARM, 45, "Atendimento em rede de farmácias.")

    if "recepcion" in t:
        if RE_VET.search(t) or RE_VET.search(e):
            return _rej("recepção veterinária (fora do perfil)")
        if RE_CTX_SAUDE.search(t) or RE_CTX_SAUDE.search(e):
            return _ok(CAT_RECEP, 50)
        d_saude = RE_RUIDO_SAUDE.sub(" ", d)
        if RE_CTX_SAUDE_DESCR.search(d_saude) and not RE_VET.search(d_saude):
            return _ok(CAT_RECEP, 40, "Contexto de saúde citado só na descrição; confirme o local.")
        return _rej("recepção sem contexto de saúde")

    return _rej("cargo incompatível")


def classificar_cargo(pessoa, titulo, empresa="", descricao="") -> Resultado:
    if pessoa == "beatriz":
        return classificar_beatriz(titulo, empresa, descricao)
    return classificar_sueli(titulo, empresa, descricao)


def cargo_valido(pessoa, titulo, empresa="") -> bool:
    """Compatibilidade com o código antigo."""
    return classificar_cargo(pessoa, titulo, empresa).aceita


# =====================================================================
# VAGA NORMALIZADA + AVALIAÇÃO COMPLETA
# =====================================================================
@dataclass
class Vaga:
    fonte: str
    uid: str
    titulo: str
    empresa: str
    area: str            # texto exibido no site
    local_busca: str     # todo texto de localização (para detectar cidade)
    descricao: str
    link: str
    encerrada: bool = False
    publicada: Optional[date] = None
    prazo: Optional[date] = None
    paises: str = ""


RE_BRASIL = _re(r"\b(br|bra|brasil|brazil)\b")
RE_LOCAL_GENERICO = _re(
    r"((pr|parana|brasil|brazil|br|regiao sul|sul|remoto|remote|hibrido|presencial|regiao metropolitana)\s*)*"
)


def avaliar(pessoa: str, v: Vaga, hoje: date) -> tuple[Resultado, set]:
    if v.encerrada or (v.prazo and v.prazo < hoje):
        return _rej("encerrada"), set()
    paises = normalizar(v.paises)
    if paises and not RE_BRASIL.search(paises):
        return _rej("fora do Brasil"), set()
    if v.publicada and (hoje - v.publicada).days > IDADE_MAXIMA_DIAS:
        return _rej(f"anúncio antigo (>{IDADE_MAXIMA_DIAS} dias)"), set()
    if not v.link.startswith("https://"):
        return _rej("sem link https"), set()

    # A localização principal do anúncio manda. Lista extra de cidades/regiões só vale quando
    # o local principal é genérico ("PR, Brasil"). Ex.: "PIRAI DO SUL, PR" não vira Curitiba.
    cidades = cidades_do_local(v.area)
    if not cidades and (not v.area.strip() or RE_LOCAL_GENERICO.fullmatch(normalizar(v.area))):
        cidades = cidades_do_local(v.local_busca)
    if not cidades & CIDADES_PERMITIDAS[pessoa]:
        return _rej("cidade incorreta"), cidades

    r = classificar_cargo(pessoa, v.titulo, v.empresa, v.descricao)
    if not r.aceita:
        return r, cidades

    if pessoa == "beatriz":
        if r.categoria in CATS_ESCOLA and "sjp" not in cidades:
            if not (ACEITAR_ESCOLA_CURITIBA and "curitiba" in cidades):
                return _rej("cidade incorreta (escola fora de São José dos Pinhais)"), cidades
            r.score -= 45   # Curitiba fica abaixo de qualquer escola de SJP (e acima da enfermagem)
            r.nota = ("Escola em Curitiba (fora de SJP): confira o deslocamento. " + r.nota).strip()
        if r.categoria in CATS_ESCOLA and RE_COLONIA.search(normalizar(f"{v.local_busca} {v.descricao}")):
            r.score += 10
            r.nota = ("Anúncio cita a Colônia Rio Grande. " + r.nota).strip()
    return r, cidades


NOMES_GENERICOS = {"", "pagina de carreira", "pagina de carreiras", "confidencial", "empresa confidencial"}


def nome_empresa(empresa: str, link: str) -> str:
    """Troca 'Página de Carreira' (nome genérico da Gupy) pelo subdomínio do link, ex.: rededor.gupy.io."""
    if normalizar(empresa) not in NOMES_GENERICOS:
        return empresa
    host = urllib.parse.urlsplit(link or "").netloc.lower()
    if host.endswith(".gupy.io") and host.count(".") >= 2:
        return f"{host.split('.')[0]} (Gupy)"
    return empresa or "Empresa não informada"


def montar_item(pessoa: str, v: Vaga, r: Resultado, cidades: set) -> dict:
    if pessoa == "beatriz":
        zona = "sjp" if "sjp" in cidades else "curitiba"
    else:
        zona = "pinhais" if "pinhais" in cidades and "curitiba" not in cidades else "curitiba"
    uid = re.sub(r"[^A-Za-z0-9_-]", "", v.uid)[:80] or hashlib.sha256(v.link.encode()).hexdigest()[:16]
    prefixo = "api-" if v.fonte == "freehire" else f"{v.fonte}-"
    info = ""
    if pessoa == "beatriz" and r.categoria in CATS_ESCOLA and zona == "sjp" and "Colônia Rio Grande" not in r.nota:
        info += "Endereço da escola não confirmado; verificar proximidade da Colônia Rio Grande. "
    if r.nota:
        info += r.nota + " "
    info += f"Vaga obtida via API pública ({NOME_FONTE.get(v.fonte, v.fonte)}). Confira a disponibilidade no anúncio."
    return {
        "id": prefixo + uid,
        "name": nome_empresa(v.empresa, v.link),
        "role": v.titulo,
        "area": v.area or "Local não informado",
        "zone": zona,
        "source": v.link,
        "wa": "",
        "email": "",
        "info": info,
    }


# =====================================================================
# DEDUPLICAÇÃO
# =====================================================================
PARAMS_RASTREIO = {"fbclid", "gclid", "ref", "refid", "trk", "trackingid", "jobboardsource", "src", "origem", "origin"}


def normalizar_url(link) -> str:
    link = str(link or "").strip()
    if not link:
        return ""
    partes = urllib.parse.urlsplit(link)
    params = [
        (k, v) for k, v in urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in PARAMS_RASTREIO
    ]
    host = partes.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urllib.parse.urlunsplit((
        partes.scheme.lower(), host, partes.path.rstrip("/"), urllib.parse.urlencode(sorted(params)), "",
    ))


def chave_vaga(vaga: dict) -> str:
    """Compatibilidade com o código antigo."""
    return normalizar_url(vaga.get("source")) or str(vaga.get("id") or "")


def chaves_dedup(item: dict) -> set:
    ks = set()
    url = normalizar_url(item.get("source"))
    if url:
        ks.add("url:" + url)
    if item.get("id"):
        ks.add("id:" + str(item["id"]))
    nome = normalizar(item.get("name"))
    if item.get("role") and nome and nome != "empresa nao informada":
        ks.add(f"fp:{normalizar(item['role'])}|{nome}|{item.get('zone', '')}")
    return ks


# =====================================================================
# HTTP com tentativas e espera progressiva
# =====================================================================
class ErroAPI(Exception):
    pass


CODIGOS_TEMPORARIOS = {408, 425, 429, 500, 502, 503, 504}


def http_json(url: str, params: dict) -> dict:
    completo = url + "?" + urllib.parse.urlencode(params)
    ultimo = ""
    for tentativa in range(1, TENTATIVAS + 1):
        espera = 2 ** tentativa
        try:
            req = urllib.request.Request(
                completo, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                bruto = resp.read()
            return json.loads(bruto.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            if e.code not in CODIGOS_TEMPORARIOS:
                raise ErroAPI(f"{ultimo} (erro definitivo)") from e
            try:
                espera = max(espera, int(e.headers.get("Retry-After", "0")))
            except (TypeError, ValueError):
                pass
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError) as e:
            ultimo = f"rede/timeout: {getattr(e, 'reason', e)}"
        except json.JSONDecodeError:
            ultimo = "resposta não é JSON"
        if tentativa < TENTATIVAS:
            log(f"    tentativa {tentativa}/{TENTATIVAS} falhou ({ultimo}); nova tentativa em {min(espera, 30)}s")
            time.sleep(min(espera, 30))
    raise ErroAPI(f"{ultimo} após {TENTATIVAS} tentativas")


# =====================================================================
# FONTES
# =====================================================================
@dataclass(frozen=True)
class Consulta:
    pessoa: str
    grupo: str              # rótulo do log, ex.: "EDUCAÇÃO INFANTIL / ESCOLA"
    fonte: str              # "freehire" | "gupy"
    cidade: str
    termo: Optional[str]
    campos: Optional[str] = "title"
    max_paginas: int = MAX_PAGINAS_BUSCA


@dataclass
class RespostaFonte:
    vagas: list
    paginas: int = 0
    total_api: Optional[int] = None
    parametros: dict = field(default_factory=dict)
    obs: str = ""


def _lista_ignorados(v) -> list:
    if not v:
        return []
    if isinstance(v, dict):
        return [str(k) for k in v]
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v]
    return [str(v)]


class FreeHire:
    nome = "freehire"

    def __init__(self, buscar_json: Callable[[str, dict], dict]):
        self.buscar_json = buscar_json

    def buscar(self, c: Consulta) -> RespostaFonte:
        params = {"cities": c.cidade, "limit": POR_PAGINA}
        if c.termo:
            params["q"] = c.termo
            if c.campos:
                params["q_fields"] = c.campos
        resp = RespostaFonte(vagas=[], parametros=dict(params))
        vistos, offset = set(), 0
        for pagina in range(c.max_paginas):
            p = dict(params)
            if pagina:
                p["offset"] = offset
                time.sleep(PAUSA_ENTRE_REQUISICOES)
            dados = self.buscar_json(FREEHIRE_API, p)
            if not isinstance(dados, dict):
                raise ErroAPI("resposta da FreeHire não é um objeto JSON")
            lista = dados.get("data", dados.get("results"))
            if not isinstance(lista, list):
                raise ErroAPI(f"resposta da FreeHire sem lista de vagas (chaves: {sorted(dados)[:8]})")
            meta = dados.get("meta") if isinstance(dados.get("meta"), dict) else {}
            ignorados = _lista_ignorados(meta.get("ignored_params"))
            if ignorados:
                if pagina and set(ignorados) <= {"offset"}:
                    resp.obs = "API ignora 'offset' — paginação encerrada"
                    break
                raise ErroAPI(f"API ignorou filtros {ignorados} — resultado seria genérico")
            resp.paginas += 1
            total = meta.get("total")
            if isinstance(total, int):
                resp.total_api = total
            novos = 0
            for bruto in lista:
                v = self.converter(bruto)
                if v and v.uid not in vistos:
                    vistos.add(v.uid)
                    resp.vagas.append(v)
                    novos += 1
            offset += len(lista)
            if not lista or novos == 0:
                break
            if isinstance(total, int):
                if offset >= total:
                    break
            elif len(lista) < POR_PAGINA:
                break
        return resp

    @staticmethod
    def converter(b) -> Optional[Vaga]:
        if not isinstance(b, dict):
            return None
        titulo = texto_de(b.get("title")).strip()
        if not titulo:
            return None
        partes_local = [b.get(k) for k in ("location", "location_text", "cities", "city", "state", "regions")]
        area = next((texto_de(x).strip() for x in partes_local[:5] if texto_de(x).strip()), "")
        link = next(
            (s for s in (texto_de(b.get(k)).strip() for k in ("apply_url", "url", "freehire_url"))
             if s.startswith("https://")),
            "",
        )
        uid = texto_de(b.get("public_slug") or b.get("slug") or b.get("id")).strip()
        if not uid:
            uid = hashlib.sha256((link or titulo).encode()).hexdigest()[:16]
        status = normalizar(b.get("status"))
        return Vaga(
            fonte="freehire",
            uid=uid,
            titulo=titulo,
            empresa=texto_de(b.get("company") or b.get("company_name")).strip(),
            area=area,
            local_busca=" ; ".join(texto_de(x) for x in partes_local if x),
            descricao=texto_de(b.get("description") or b.get("description_text") or b.get("summary")),
            link=link,
            encerrada=bool(b.get("closed_at")) or status in ("closed", "expired", "encerrada", "inactive")
            or b.get("is_active") is False,
            publicada=ler_data(b.get("posted_at") or b.get("published_at") or b.get("date") or b.get("created_at")),
            paises=texto_de(b.get("countries") or b.get("country")),
        )


class Gupy:
    nome = "gupy"

    def __init__(self, buscar_json: Callable[[str, dict], dict]):
        self.buscar_json = buscar_json
        self.desativada = ""        # se a API cair de vez (404), para de insistir nesta execução
        self.sem_filtro_cidade = False

    def _pedir(self, p: dict) -> dict:
        try:
            return self.buscar_json(GUPY_API, p)
        except ErroAPI as e:
            msg = str(e)
            if "city" in p and ("HTTP 400" in msg or "HTTP 422" in msg):
                # API não aceita o filtro de cidade: busca sem ele e filtra a cidade localmente.
                self.sem_filtro_cidade = True
                return self.buscar_json(GUPY_API, {k: v for k, v in p.items() if k != "city"})
            if "HTTP 404" in msg or "HTTP 410" in msg:
                self.desativada = msg
            raise

    def buscar(self, c: Consulta) -> RespostaFonte:
        if self.desativada:
            raise ErroAPI(f"Gupy desativada nesta execução ({self.desativada})")
        params = {"jobName": c.termo or "", "limit": POR_PAGINA}
        if not self.sem_filtro_cidade:
            params["city"] = c.cidade
        resp = RespostaFonte(vagas=[], parametros=dict(params))
        vistos, offset = set(), 0
        for pagina in range(c.max_paginas):
            p = dict(params, offset=offset)
            if pagina:
                time.sleep(PAUSA_ENTRE_REQUISICOES)
                if self.sem_filtro_cidade:
                    p.pop("city", None)
            dados = self._pedir(p)
            if not isinstance(dados, dict) or not isinstance(dados.get("data"), list):
                raise ErroAPI("resposta da Gupy em formato inesperado")
            lista = dados["data"]
            pag = dados.get("pagination") if isinstance(dados.get("pagination"), dict) else {}
            total = pag.get("total")
            if isinstance(total, int):
                resp.total_api = total
            resp.paginas += 1
            novos = 0
            for bruto in lista:
                v = self.converter(bruto)
                if v and v.uid not in vistos:
                    vistos.add(v.uid)
                    resp.vagas.append(v)
                    novos += 1
            offset += len(lista)
            if not lista or novos == 0:
                break
            if isinstance(total, int):
                if offset >= total:
                    break
            elif len(lista) < POR_PAGINA:
                break
        alvo = normalizar(c.cidade)
        if resp.vagas:
            na_cidade = sum(1 for v in resp.vagas if alvo in normalizar(v.local_busca))
            resp.obs = (f"{na_cidade}/{len(resp.vagas)} vagas recebidas estão em {c.cidade}"
                        + (" (API sem filtro de cidade; filtrado localmente)" if self.sem_filtro_cidade else ""))
        return resp

    @staticmethod
    def converter(b) -> Optional[Vaga]:
        if not isinstance(b, dict):
            return None
        titulo = texto_de(b.get("name")).strip()
        link = texto_de(b.get("jobUrl")).strip()
        if not titulo or not b.get("id"):
            return None
        cidade, estado = texto_de(b.get("city")).strip(), texto_de(b.get("state")).strip()
        area = ", ".join(x for x in (cidade, estado) if x) or ("Remoto" if b.get("isRemoteWork") else "")
        empresa = texto_de(b.get("careerPageDisplayName") or b.get("careerPageName") or b.get("companyName")).strip()
        if str(b.get("careerPageLogo") or "").endswith("confidencial_logo.png"):
            empresa = "Confidencial"
        return Vaga(
            fonte="gupy",
            uid=str(b.get("id")),
            titulo=titulo,
            empresa=empresa,
            area=area,
            local_busca=area,
            descricao=texto_de(b.get("description")),
            link=link,
            publicada=ler_data(b.get("publishedDate") or b.get("publishedAt")),
            prazo=ler_data(b.get("applicationDeadline")),
            paises=texto_de(b.get("country")),
        )


def montar_consultas(usar_gupy: bool = True) -> list:
    cs = []
    # ---------------- BEATRIZ ----------------
    # Varredura: todas as vagas de SJP, sem depender do parâmetro q (que a API relaxa).
    cs.append(Consulta("beatriz", "VARREDURA SJP (sem termo)", "freehire", SJP, None, None, MAX_PAGINAS_VARREDURA))
    cs += [Consulta("beatriz", "EDUCAÇÃO INFANTIL / ESCOLA", "freehire", SJP, t) for t in ESCOLA_BUSCAS]
    # Nome da escola/colégio costuma vir no título ou na descrição ("Recepcionista - Colégio X").
    cs += [Consulta("beatriz", "EDUCAÇÃO INFANTIL / ESCOLA", "freehire", SJP, t, None) for t in ESCOLA_EXTRAS]
    if ACEITAR_ESCOLA_CURITIBA:
        cs += [Consulta("beatriz", "ESCOLA CURITIBA (2ª opção)", "freehire", CWB, t, campos)
               for t, campos in ESCOLA_BUSCAS_CURITIBA]
    cs += [
        Consulta("beatriz", "ENFERMAGEM INFANTIL", "freehire", cidade, t, campos)
        for cidade in (CWB, SJP) for t, campos in ENFERMAGEM_INFANTIL_BUSCAS
    ]
    if usar_gupy:
        cs += [Consulta("beatriz", "EDUCAÇÃO INFANTIL / ESCOLA", "gupy", SJP, t, None, MAX_PAGINAS_GUPY)
               for t in GUPY_BEATRIZ_ESCOLA]
        if ACEITAR_ESCOLA_CURITIBA:
            cs += [Consulta("beatriz", "ESCOLA CURITIBA (2ª opção)", "gupy", CWB, t, None, MAX_PAGINAS_GUPY)
                   for t in GUPY_BEATRIZ_ESCOLA]
        cs += [Consulta("beatriz", "ENFERMAGEM INFANTIL", "gupy", cidade, t, None, MAX_PAGINAS_GUPY)
               for cidade in (CWB, SJP) for t in GUPY_ENFERMAGEM]
    # ---------------- SUELI ----------------
    cs.append(Consulta("sueli", "VARREDURA PINHAIS (sem termo)", "freehire", PINHAIS, None, None, MAX_PAGINAS_VARREDURA))
    cs += [Consulta("sueli", "SAÚDE / FARMÁCIA", "freehire", cidade, cargo)
           for cidade in (CWB, PINHAIS) for cargo in SUELI_CARGOS]
    if usar_gupy:
        cs += [Consulta("sueli", "SAÚDE / FARMÁCIA", "gupy", cidade, cargo, None, MAX_PAGINAS_GUPY)
               for cidade in (CWB, PINHAIS) for cargo in SUELI_CARGOS + GUPY_SUELI_EXTRAS]
    return cs


# =====================================================================
# ARQUIVOS
# =====================================================================
def escrever_json_seguro(caminho: Path, dados) -> None:
    texto = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
    json.loads(texto)  # garante JSON válido antes de substituir
    tmp = caminho.with_name(caminho.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, caminho)


def ler_json(caminho: Path, padrao):
    if not caminho.exists():
        return padrao
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        aviso(f"não consegui ler {caminho.name} ({e}); ignorando")
        return padrao


def carregar_manuais(dir_dados: Path) -> list:
    manual = ler_json(dir_dados / "fontes.json", [])
    if not isinstance(manual, list):
        raise ValueError("dados/fontes.json precisa ser uma lista")
    return [x for x in manual if isinstance(x, dict)]


# =====================================================================
# EXECUÇÃO
# =====================================================================
@dataclass
class RelatorioPessoa:
    ok: int = 0
    falhas: int = 0
    fontes_com_falha: set = field(default_factory=set)
    por_grupo: dict = field(default_factory=dict)       # grupo -> Counter
    motivos: Counter = field(default_factory=Counter)
    recebidas: int = 0
    duplicadas: int = 0


RE_PARECE_ESCOLA = _re(
    r"\b(escola|escolar|colegio|creche|cmei|educacao infantil|bercari\w*|pedagog\w*|professor\w*|docente"
    r"|auxiliar de sala|auxiliar de classe|auxiliar de ensino|monitor\w* (infantil|escolar)|recreador\w*)\b"
)


def parece_escola(v: Vaga) -> bool:
    return bool(RE_PARECE_ESCOLA.search(normalizar(f"{v.titulo} {v.empresa}")))


def balde_motivo(motivo: str) -> str:
    if motivo.startswith("cidade incorreta"):
        return "cidade"
    if motivo in ("encerrada", "fora do Brasil", "sem link https") or motivo.startswith("anúncio antigo"):
        return "outros"
    return "cargo"


def _log_consulta(c: Consulta, resp: RespostaFonte, cont: Counter, amostras: list, repetida_de: str) -> None:
    termo = f'"{c.termo}"' if c.termo else "(sem termo)"
    rejeitadas = cont["recebidas"] - cont["aceitas"] - cont["duplicada"]
    # Linha de resumo FORA do grupo: aparece mesmo com o log recolhido.
    log(f"{c.pessoa.upper()} · {c.grupo} · {NOME_FONTE[c.fonte]} · {c.cidade} · {termo} → "
        f"recebidas {cont['recebidas']} | aceitas {cont['aceitas']} | duplicadas {cont['duplicada']} | "
        f"rejeitadas {rejeitadas}" + (" | (conjunto repetido)" if repetida_de else ""))
    grupo_inicio("    ↳ detalhes")
    log(f"  Parâmetros: {resp.parametros}")
    total = f" (total informado pela API: {resp.total_api})" if resp.total_api is not None else ""
    log(f"  Páginas: {resp.paginas} | Recebidas: {cont['recebidas']}{total}")
    log(f"  Aceitas: {cont['aceitas']} | Duplicadas: {cont['duplicada']} | "
        f"Rejeitadas: {cont['recebidas'] - cont['aceitas'] - cont['duplicada']}")
    for motivo, n in sorted(((m, n) for m, n in cont.items() if m not in ("recebidas", "aceitas", "duplicada")),
                            key=lambda x: -x[1]):
        log(f"    - {motivo}: {n}")
    if resp.obs:
        log(f"  Obs.: {resp.obs}")
    if repetida_de:
        log(f"  ATENÇÃO: a API devolveu exatamente o MESMO conjunto da busca \"{repetida_de}\" — "
            f"o termo provavelmente foi relaxado/ignorado pela API (o filtro local resolve isso).")
    if amostras:
        log("  Exemplos rejeitados (título — empresa — local):")
        for a in amostras:
            log(f"    · [{a[0]}] {a[1]} — {a[2]} — {a[3]}")
    grupo_fim()


def executar(dir_dados=None, buscar_json=None, hoje: Optional[date] = None, usar_gupy: Optional[bool] = None) -> dict:
    dir_dados = Path(dir_dados or D)
    buscar_json = buscar_json or http_json
    hoje = hoje or hoje_brasil()
    usar_gupy = USAR_GUPY if usar_gupy is None else usar_gupy
    dir_dados.mkdir(parents=True, exist_ok=True)

    fontes = {"freehire": FreeHire(buscar_json), "gupy": Gupy(buscar_json)}
    consultas = montar_consultas(usar_gupy)
    rel = {p: RelatorioPessoa() for p in PESSOAS}
    aceitas = {p: [] for p in PESSOAS}            # (Resultado, item, fonte)
    vistas = {p: set() for p in PESSOAS}
    assinaturas: dict = {}
    quase_escola: dict = {}   # vagas com cara de escola que a Beatriz NÃO recebeu (para conferência)

    log(f"Buscador de vagas — {hoje.isoformat()} — fontes: FreeHire{' + Gupy' if usar_gupy else ''} + fontes.json")
    log(f"{len(consultas)} consultas programadas.")

    # 1) Vagas manuais (dados/fontes.json) — entram primeiro e vencem duplicatas.
    for item in carregar_manuais(dir_dados):
        pessoa = str(item.get("pessoa", "")).lower()
        if pessoa not in PESSOAS:
            continue
        if not all(item.get(k) for k in ("id", "name", "role", "area", "source")):
            log(f"  fontes.json: item incompleto ignorado: {item.get('id')}")
            continue
        if not str(item["source"]).startswith("https://"):
            log(f"  fontes.json: item sem link https ignorado: {item.get('id')}")
            continue
        cidades = cidades_do_local(item["area"])
        r = classificar_cargo(pessoa, item["role"], item["name"])
        if not (cidades & CIDADES_PERMITIDAS[pessoa]) or not r.aceita or (
            pessoa == "beatriz" and r.categoria in CATS_ESCOLA and "sjp" not in cidades
            and not (ACEITAR_ESCOLA_CURITIBA and "curitiba" in cidades)
        ):
            log(f"  fontes.json: '{item['role']}' ({item['area']}) não passou no filtro de {pessoa}: "
                f"{r.motivo or 'cidade incorreta'}")
            continue
        limpo = {k: v for k, v in item.items() if k != "pessoa"}
        ks = chaves_dedup(limpo)
        if ks & vistas[pessoa]:
            continue
        vistas[pessoa] |= ks
        aceitas[pessoa].append((r, limpo, "manual"))

    # 2) Consultas às APIs
    for c in consultas:
        rp = rel[c.pessoa]
        cont = rp.por_grupo.setdefault(c.grupo, Counter())
        try:
            resp = fontes[c.fonte].buscar(c)
            rp.ok += 1
        except ErroAPI as e:
            rp.falhas += 1
            rp.fontes_com_falha.add(c.fonte)
            cont["consultas com erro"] += 1
            log(f"ERRO {NOME_FONTE[c.fonte]} · {c.pessoa} · {c.cidade} · {c.termo or '(sem termo)'}: {e}")
            continue
        finally:
            time.sleep(PAUSA_ENTRE_REQUISICOES)

        local = Counter(recebidas=len(resp.vagas))
        amostras = []
        for v in resp.vagas:
            r, cidades = avaliar(c.pessoa, v, hoje)
            if not r.aceita:
                local[r.motivo] += 1
                if len(amostras) < AMOSTRAS_REJEICAO:
                    amostras.append((r.motivo, v.titulo, v.empresa or "?", v.area or "?"))
                if c.pessoa == "beatriz" and parece_escola(v):
                    quase_escola.setdefault((v.titulo, v.empresa), (r.motivo, v.titulo, v.empresa or "?", v.area or "?"))
                continue
            item = montar_item(c.pessoa, v, r, cidades)
            ks = chaves_dedup(item)
            if ks & vistas[c.pessoa]:
                local["duplicada"] += 1
                continue
            vistas[c.pessoa] |= ks
            aceitas[c.pessoa].append((r, item, v.fonte))
            local["aceitas"] += 1

        uids = sorted(v.uid for v in resp.vagas)
        repetida_de = ""
        if len(uids) >= 5:
            assin = hashlib.sha1("|".join(uids).encode()).hexdigest()
            chave = (c.fonte, c.cidade, assin)
            repetida_de = assinaturas.get(chave, "")
            assinaturas.setdefault(chave, c.termo or "(sem termo)")
            if repetida_de == (c.termo or "(sem termo)"):
                repetida_de = ""

        cont.update(local)
        rp.recebidas += local["recebidas"]
        rp.duplicadas += local["duplicada"]
        for m, n in local.items():
            if m not in ("recebidas", "aceitas", "duplicada"):
                rp.motivos[m] += n
        _log_consulta(c, resp, local, amostras, repetida_de)

    # 3) Gravação por pessoa (com preservação em caso de falha)
    estado_arq = dir_dados / ARQ_ESTADO
    estado = ler_json(estado_arq, {})
    if not isinstance(estado, dict):
        estado = {}
    resumo = {}
    linhas_md = ["## Buscador de vagas", "", "| Pessoa | Consultas OK | Falhas | Vagas no arquivo | Por categoria |",
                 "|---|---|---|---|---|"]

    for pessoa in PESSOAS:
        rp = rel[pessoa]
        destino = dir_dados / f"{pessoa}.json"
        log(f"\n================ RESUMO {pessoa.upper()} ================")
        log(f"  Consultas: {rp.ok} ok / {rp.falhas} com erro"
            + (f" (fontes com erro: {', '.join(sorted(NOME_FONTE[f] for f in rp.fontes_com_falha))})"
               if rp.fontes_com_falha else ""))

        if rp.ok == 0:
            aviso(f"{pessoa}: nenhuma consulta funcionou — arquivo {destino.name} PRESERVADO sem alteração.")
            resumo[pessoa] = {"gravado": False, "vagas": None}
            linhas_md.append(f"| {pessoa} | 0 | {rp.falhas} | preservado | — |")
            continue

        # estado anterior desta pessoa (se não existir, semeia a partir do JSON atual)
        est_p = estado.get(pessoa)
        if not isinstance(est_p, dict):
            est_p = {}
            anterior = ler_json(destino, {})
            for j in (anterior.get("jobs", []) if isinstance(anterior, dict) else []):
                if isinstance(j, dict) and str(j.get("id", "")).startswith(("api-", "gupy-")):
                    fonte = "gupy" if str(j["id"]).startswith("gupy-") else "freehire"
                    est_p[j["id"]] = {"visto": hoje.isoformat(), "fonte": fonte, "score": 0,
                                      "categoria": "", "vaga": j}

        atuais = aceitas[pessoa]
        ids_atuais = {item["id"] for _, item, _ in atuais}
        mantidas, expiradas = [], 0
        for vid, ent in est_p.items():
            if vid in ids_atuais or not isinstance(ent, dict) or not isinstance(ent.get("vaga"), dict):
                continue
            visto = ler_data(ent.get("visto"))
            dias = (hoje - visto).days if visto else 999
            if ent.get("fonte") in rp.fontes_com_falha and dias <= DIAS_MANTER_SE_FONTE_FALHAR:
                ks = chaves_dedup(ent["vaga"])
                if not ks & vistas[pessoa]:
                    vistas[pessoa] |= ks
                    mantidas.append(ent)
            else:
                expiradas += 1

        lista = [(r.score, r.categoria, item) for r, item, _ in atuais]
        lista += [(int(e.get("score") or 0), e.get("categoria") or "(mantida)", e["vaga"]) for e in mantidas]
        lista.sort(key=lambda x: (-x[0], normalizar(x[2].get("role"))))
        jobs = [item for _, _, item in lista]

        escrever_json_seguro(destino, {"jobs": jobs})

        novo_est = {}
        for r, item, fonte in atuais:
            if fonte != "manual":
                novo_est[item["id"]] = {"visto": hoje.isoformat(), "fonte": fonte, "score": r.score,
                                        "categoria": r.categoria, "vaga": item}
        for e in mantidas:
            novo_est[e["vaga"]["id"]] = e
        estado[pessoa] = novo_est

        por_cat = Counter(cat for _, cat, _ in lista)
        log(f"  Recebidas (somando todas as consultas): {rp.recebidas}")
        log(f"  Duplicadas descartadas: {rp.duplicadas}")
        log("  Rejeições por motivo:")
        for m, n in rp.motivos.most_common():
            log(f"    - {m}: {n}")
        log("  Por grupo de busca:")
        for g, ct in rp.por_grupo.items():
            baldes = Counter()
            for m, n in ct.items():
                if m not in ("recebidas", "aceitas", "duplicada", "consultas com erro"):
                    baldes[balde_motivo(m)] += n
            log(f"    {pessoa.upper()} - {g}")
            log(f"      Recebidas: {ct['recebidas']} | Aceitas: {ct['aceitas']} | Duplicadas: {ct['duplicada']} | "
                f"Cidade incorreta: {baldes['cidade']} | Cargo incompatível: {baldes['cargo']} | "
                f"Encerrada/antiga/sem link: {baldes['outros']}"
                + (f" | Consultas com erro: {ct['consultas com erro']}" if ct["consultas com erro"] else ""))
        log("  Total final por categoria:")
        for cat, n in por_cat.most_common():
            log(f"    - {cat}: {n}")
        if mantidas:
            log(f"  {len(mantidas)} vaga(s) mantida(s) da execução anterior porque uma fonte falhou "
                f"(limite {DIAS_MANTER_SE_FONTE_FALHAR} dias).")
        if expiradas:
            log(f"  {expiradas} vaga(s) antiga(s) removida(s) por não aparecerem mais.")
        if pessoa == "beatriz":
            log(f"  Vagas com cara de ESCOLA que foram rejeitadas: {len(quase_escola)}")
            for motivo, titulo, empresa, area in list(quase_escola.values())[:30]:
                log(f"    · [{motivo}] {titulo} — {empresa} — {area}")
            if not quase_escola and not por_cat.get(CAT_ESCOLA) and not por_cat.get(CAT_ESCOLA_ADM):
                log("    (nenhuma vaga de escola veio das fontes nesta execução — a falta é da fonte, não do filtro)")
        log(f"  >>> {pessoa}: {len(jobs)} vagas únicas gravadas em dados/{destino.name}")
        resumo[pessoa] = {"gravado": True, "vagas": len(jobs), "por_categoria": dict(por_cat),
                          "mantidas": len(mantidas)}
        cats = ", ".join(f"{c}: {n}" for c, n in por_cat.most_common()) or "—"
        linhas_md.append(f"| {pessoa} | {rp.ok} | {rp.falhas} | {len(jobs)} | {cats} |")

    escrever_json_seguro(estado_arq, estado)

    resumo_md = os.environ.get("GITHUB_STEP_SUMMARY")
    if resumo_md:
        try:
            with open(resumo_md, "a", encoding="utf-8") as f:
                f.write("\n".join(linhas_md) + "\n")
        except OSError:
            pass
    return resumo


if __name__ == "__main__":
    executar()
    sys.exit(0)
