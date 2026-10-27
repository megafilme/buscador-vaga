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
    "beatriz": [("São José dos Pinhais", x) for x in ("creche", "infantil", "pedagogia", "auxiliar")],
    "sueli": [(cidade, cargo) for cidade in ("Curitiba", "Pinhais") for cargo in ("enfermagem", "farmacia", "recepcionista", "hospital")],
}
CARGOS = {
    "beatriz": ("creche", "infantil", "pedagog", "bercario", "auxiliar de sala", "educador", "professor"),
    "sueli": ("enferm", "farmac", "recepcion", "hospital", "clinica", "laboratorio"),
}
CIDADES = {"beatriz": ("sao jose dos pinhais",), "sueli": ("curitiba", "pinhais")}

def normalizar(s):
    return "".join(c for c in unicodedata.normalize("NFKD", str(s or "").lower()) if not unicodedata.combining(c))

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
    sucessos = 0
    for pessoa, buscas in CONSULTAS.items():
        for cidade, cargo in buscas:
            try:
                encontrados = consultar(cidade, cargo)
                sucessos += 1
                print(pessoa, cidade, cargo, "API:", len(encontrados))
            except Exception as erro:
                print("ERRO API:", pessoa, cidade, cargo, repr(erro))
                continue
            for vaga in encontrados:
                if not isinstance(vaga, dict) or vaga.get("closed_at"):
                    continue
                titulo = str(vaga.get("title") or "")
                local = normalizar(" ".join([str(vaga.get("location") or "")] + [str(x) for x in vaga.get("cities", [])]))
                if not any(x in normalizar(titulo) for x in CARGOS[pessoa]):
                    continue
                if not any(x in local for x in CIDADES[pessoa]):
                    continue
                if vaga.get("countries") and not any(normalizar(x) == "br" for x in vaga["countries"]):
                    continue
                link = str(vaga.get("apply_url") or vaga.get("url") or "")
                if not link.startswith("https://"):
                    continue
                uid = str(vaga.get("public_slug") or hashlib.sha256(link.encode()).hexdigest()[:16])
                itens.append({
                    "pessoa": pessoa, "id": "api-" + uid,
                    "name": str(vaga.get("company") or "Empresa não informada"),
                    "role": titulo, "area": str(vaga.get("location") or cidade),
                    "zone": "sjp" if pessoa == "beatriz" else ("pinhais" if "pinhais" in local and "curitiba" not in local else "curitiba"),
                    "source": link, "wa": "", "email": "",
                    "info": "Vaga obtida via API pública. Confira a disponibilidade no anúncio."
                })
    if not sucessos:
        raise RuntimeError("Nenhuma consulta à API funcionou; arquivos existentes foram preservados.")
    for pessoa in CONSULTAS:
        resultado, vistos = [], set()
        for vaga in itens:
            if not isinstance(vaga, dict) or str(vaga.get("pessoa", "")).lower() != pessoa:
                continue
            if not all(vaga.get(k) for k in ("id", "name", "role", "area", "source")):
                continue
            if not str(vaga["source"]).startswith("https://"):
                continue
            if pessoa == "beatriz" and (vaga.get("zone") != "sjp" or "sao jose dos pinhais" not in normalizar(vaga["area"])):
                continue
            if pessoa == "sueli" and vaga.get("zone") not in ("curitiba", "pinhais"):
                continue
            if vaga["id"] in vistos:
                continue
            vistos.add(vaga["id"])
            resultado.append({k: v for k, v in vaga.items() if k != "pessoa"})
        (D / (pessoa + ".json")).write_text(json.dumps({"jobs": resultado}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(pessoa, len(resultado), "vagas")

if __name__ == "__main__":
    executar()
