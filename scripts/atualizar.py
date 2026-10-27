import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from html import unescape

D = Path(__file__).resolve().parents[1] / "dados"
API = "https://freehire.me/api/v1/jobs/search"
CONSULTAS = {
    "beatriz": [("São José dos Pinhais", x) for x in ("creche", "educação infantil", "auxiliar de professora", "auxiliar de sala", "berçarista", "pedagogia")],
    "sueli": [(cidade, cargo) for cidade in ("Curitiba", "Pinhais") for cargo in ("técnico de enfermagem", "auxiliar de enfermagem", "auxiliar de farmácia", "atendente de farmácia", "recepcionista clínica", "recepcionista hospital")],
}
def normalizar(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower())
                   if not unicodedata.combining(c))

def cidade_valida(local, pessoa):
    cidade = normalizar(local).split(",")[0].strip()
    if pessoa == "beatriz":
        return cidade == "sao jose dos pinhais"
    return cidade in ("curitiba", "pinhais")

def cargo_valido(pessoa, titulo, empresa=""):
    t, e = normalizar(titulo), normalizar(empresa)
    if pessoa == "beatriz":
        if any(x in t for x in ("ensino medio", "ensino fundamental", "professor de ingles",
                               "professor de matematica", "professor de portugues",
                               "professor de historia", "professor de quimica",
                               "professor de fisica", "professor de geografia",
                               "professor de administracao", "professor de logistica",
                               "professor de espanhol", "professor de biologia",
                               "professor de filosofia", "professor de sociologia",
                               "professor de artes", "curso tecnico", "enfermagem")):
            return False
        return any(x in t for x in ("educacao infantil", "auxiliar de professora",
            "auxiliar de professor", "auxiliar de sala", "auxiliar de turma",
            "auxiliar de creche", "professora infantil", "professor infantil",
            "bercarista", "bercario", "recreadora infantil", "recreador infantil",
            "educadora infantil", "educador infantil", "pedagoga infantil",
            "pedagogo infantil", "atendente de creche", "monitor infantil",
            "monitora infantil"))
    if "enfermagem" in t:
        return any(x in t for x in ("tecnic", "auxiliar de enfermagem"))
    if "farmac" in t:
        return any(x in t for x in ("auxiliar", "atendente", "balconista", "tecnic"))
    if "recepcion" in t:
        return any(x in t or x in e for x in ("hospital", "clinica", "laboratorio",
            "centro medico", "centro de diagnostico", "ambulatorio",
            "unimed", "dasa", "pequeno principe", "rede d'or", "pilar hospital"))
    return False

def consultar(cidade, cargo):
    params = urllib.parse.urlencode({"cities": cidade, "q": cargo, "q_fields": "title", "limit": 100, "offset": 0})
    req = urllib.request.Request(API + "?" + params, headers={"User-Agent": "PainelVagasPessoal/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Resposta inesperada da API")
    if data.get("meta", {}).get("ignored_params"):
        raise ValueError("Filtros ignorados pela API: " + str(data["meta"]["ignored_params"]))
    return data["data"]

def executar():
    D.mkdir(parents=True, exist_ok=True)
    manual_path = D / "fontes.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else []
    if not isinstance(manual, list):
        raise ValueError("dados/fontes.json precisa ser uma lista")
    itens = list(manual)
    sucessos = {pessoa: 0 for pessoa in CONSULTAS}
    for pessoa, buscas in CONSULTAS.items():
        for cidade, cargo in buscas:
            try:
                encontrados = consultar(cidade, cargo)
                sucessos[pessoa] += 1
                print(pessoa, cidade, cargo, "API:", len(encontrados))
            except Exception as erro:
                print("ERRO API:", pessoa, cidade, cargo, repr(erro))
                continue
            for vaga in encontrados:
                if not isinstance(vaga, dict) or vaga.get("closed_at"):
                    continue
                titulo = str(vaga.get("title") or "")
                local = normalizar(" ".join([str(vaga.get("location") or "")] + [str(x) for x in vaga.get("cities", [])]))
                if not cargo_valido(pessoa, titulo, str(vaga.get("company") or "")):
                    continue
                if not cidade_valida(vaga.get("location") or "", pessoa):
                    continue
                if vaga.get("countries") and not any(normalizar(x) == "br" for x in vaga["countries"]):
                    continue
                link = str(vaga.get("apply_url") or vaga.get("url") or "")
                if not link.startswith("https://"):
                    continue
