import hashlib
import json
import re
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

D = Path(__file__).resolve().parents[1] / "dados"
API = "https://freehire.me/api/v1/jobs/search"

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
ENFERMAGEM_BUSCAS = (
    "técnico de enfermagem pediatria", "técnico de enfermagem neonatal",
    "técnico de enfermagem pequeno príncipe", "técnico de enfermagem teste do pezinho",
    "técnico de enfermagem",
)
CONSULTAS = {
    "beatriz": (
        [("São José dos Pinhais", x) for x in ESCOLA_BUSCAS]
        + [(cidade, x) for cidade in ("Curitiba", "São José dos Pinhais") for x in ENFERMAGEM_BUSCAS]
    ),
    "sueli": [
        (cidade, cargo)
        for cidade in ("Curitiba", "Pinhais")
        for cargo in (
            "técnico de enfermagem", "auxiliar de enfermagem", "auxiliar de farmácia",
            "atendente de farmácia", "recepcionista clínica", "recepcionista hospital",
            "farmácia", "balconista de farmácia", "recepcionista laboratório",
        )
    ],
}

def normalizar(s):
    return "".join(
        c for c in unicodedata.normalize("NFKD", str(s or "").lower())
        if not unicodedata.combining(c)
    )

def enfermagem_infantil(titulo, empresa):
    t, e = normalizar(titulo), normalizar(empresa)
    if "enfermagem" not in t or not re.search(r"tecnic|auxiliar de enfermagem", t):
        return False
    return (
        any(x in t for x in (
            "pediatr", "neonat", "infantil", "crianca", "teste do pezinho",
            "vacinacao", "maternidade", "obstetricia",
        ))
        or "pequeno principe" in e
    )

def cidade_valida(local, pessoa, titulo="", empresa=""):
    local_norm = normalizar(local)
    cidade = re.split(r"\s*[,;|–-]\s*", local_norm)[0].strip()
    if pessoa == "beatriz":
        if cidade == "sao jose dos pinhais":
            return True
        return cidade == "curitiba" and enfermagem_infantil(titulo, empresa)
    return cidade in ("curitiba", "pinhais")

ESCOLA_TERMOS = (
    "educacao infantil", "auxiliar de professora", "auxiliar de professor",
    "auxiliar de sala", "auxiliar de turma", "auxiliar de classe",
    "auxiliar de creche", "auxiliar de educacao infantil", "auxiliar de ensino",
    "professora infantil", "professor infantil", "professora de educacao infantil",
    "professor de educacao infantil", "bercarista", "bercario",
    "recreadora infantil", "recreador infantil", "educadora infantil",
    "educador infantil", "pedagoga infantil", "pedagogo infantil",
    "atendente de creche", "atendente de sala", "assistente de sala",
    "monitor infantil", "monitora infantil", "monitor escolar",
    "monitora escolar", "auxiliar de desenvolvimento infantil",
    "atendente infantil", "secretaria escolar", "secretario escolar",
    "secretaria de escola", "secretario de escola", "recepcionista escolar",
    "recepcionista de escola", "auxiliar administrativo escolar",
    "assistente administrativo escolar", "assistente de secretaria escolar",
    "monitor de creche", "auxiliar pedagogico", "assistente de educacao infantil",
    "apoio infantil", "apoio escolar", "assistente pedagogico",
)
ESCOLA_CONTEXTO = (
    "escola", "colegio", "creche", "educacao infantil", "centro de educacao infantil",
    "cmei", "instituto de ensino", "grupo educacional",
)
CARGOS_GENERICOS_ESCOLA = (
    "auxiliar administrativo", "assistente administrativo",
    "recepcionista", "secretaria", "secretario",
    "auxiliar de secretaria", "auxiliar de apoio",
)
EXCLUSOES_ESCOLA = (
    "ensino medio", "ensino fundamental", "curso tecnico",
    "professor de ingles", "professor de matematica", "professor de portugues",
    "professor de historia", "professor de quimica", "professor de fisica",
    "professor de geografia", "professor de administracao",
    "professor de logistica", "professor de espanhol", "professor de biologia",
    "professor de filosofia", "professor de sociologia", "professor de artes",
    "professor de educacao fisica", "professor de informatica",
    "professor de formacao de docentes", "estagio em pedagogia",
    "estagiario de pedagogia", "estagiaria de pedagogia",
)

def cargo_valido(pessoa, titulo, empresa=""):
    t, e = normalizar(titulo), normalizar(empresa)
    if pessoa == "beatriz":
        if enfermagem_infantil(titulo, empresa):
            return True
        if "enfermagem" in t or any(x in t for x in EXCLUSOES_ESCOLA):
            return False
        if any(x in t for x in ESCOLA_TERMOS):
            return True
        # Cargos genéricos só entram quando o empregador é claramente uma escola.
        if any(x in e for x in ESCOLA_CONTEXTO) and any(x in t for x in CARGOS_GENERICOS_ESCOLA):
            return True
        return False

    # Regras da Sueli preservadas.
    if "enfermagem" in t:
        return any(x in t for x in ("tecnic", "auxiliar de enfermagem"))
    if "farmac" in t:
        return any(x in t for x in ("auxiliar", "atendente", "balconista", "tecnic"))
    if "recepcion" in t:
        return any(x in t or x in e for x in (
            "hospital", "clinica", "laboratorio", "centro medico",
            "centro de diagnostico", "ambulatorio", "unimed",
            "dasa", "pequeno principe", "rede d'or", "pilar hospital",
        ))
    return False

def consultar(cidade, cargo):
    params = urllib.parse.urlencode({
        "cities": cidade, "q": cargo, "q_fields": "title", "limit": 100, "offset": 0,
    })
    req = urllib.request.Request(
        API + "?" + params,
        headers={"User-Agent": "PainelVagasPessoal/1.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        data = json.load(response)
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Resposta inesperada da API")
    if data.get("meta", {}).get("ignored_params"):
        raise ValueError("Filtros ignorados pela API: " + str(data["meta"]["ignored_params"]))
    return data["data"]

def chave_vaga(vaga):
    # Remove rastreamento para não contar o mesmo anúncio duas vezes.
    link = str(vaga.get("source") or "").strip()
    partes = urllib.parse.urlsplit(link)
    parametros = urllib.parse.parse_qsl(partes.query, keep_blank_values=True)
    parametros = [
        (k, v) for k, v in parametros
        if not k.lower().startswith("utm_") and k.lower() not in ("fbclid", "gclid")
    ]
    limpo = urllib.parse.urlunsplit((
        partes.scheme.lower(), partes.netloc.lower(),
        partes.path.rstrip("/"), urllib.parse.urlencode(sorted(parametros)), "",
    ))
    return limpo or str(vaga.get("id") or "")

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
            aceitas = 0
            for vaga in encontrados:
                if not isinstance(vaga, dict) or vaga.get("closed_at"):
                    continue
                titulo = str(vaga.get("title") or "")
                empresa = str(vaga.get("company") or "")
                local = str(vaga.get("location") or "")
                if not cargo_valido(pessoa, titulo, empresa):
                    continue
                if not cidade_valida(local, pessoa, titulo, empresa):
                    continue
                paises = vaga.get("countries")
                if paises and isinstance(paises, list) and not any(
                    normalizar(x) in ("br", "brasil", "brazil") for x in paises
                ):
                    continue
                link = str(vaga.get("apply_url") or vaga.get("url") or "")
                if not link.startswith("https://"):
                    continue
                uid = str(vaga.get("public_slug") or hashlib.sha256(link.encode()).hexdigest()[:16])
                escolar = pessoa == "beatriz" and not enfermagem_infantil(titulo, empresa)
                itens.append({
                    "pessoa": pessoa, "id": "api-" + uid,
                    "name": empresa or "Empresa não informada",
                    "role": titulo, "area": local, "zone": (
                        "curitiba" if normalizar(local).startswith("curitiba") else "sjp"
                    ) if pessoa == "beatriz" else (
                        "pinhais" if normalizar(local).split(",")[0].strip() == "pinhais"
                        else "curitiba"
                    ),
                    "source": link, "wa": "", "email": "",
                    "info": (
                        "Endereço da escola não confirmado; verificar proximidade da Colônia Rio Grande. "
                        if escolar else ""
                    ) + "Vaga obtida via API pública. Confira a disponibilidade no anúncio.",
                })
                aceitas += 1
            print("  ->", aceitas, "resultados compatíveis nesta consulta (antes de remover duplicatas)")
    for pessoa in CONSULTAS:
        if sucessos[pessoa] != len(CONSULTAS[pessoa]):
            print(pessoa, "Busca incompleta; arquivo anterior preservado para evitar perda de vagas")
            continue
        resultado, vistos = [], set()
        for vaga in itens:
            if not isinstance(vaga, dict) or str(vaga.get("pessoa", "")).lower() != pessoa:
                continue
            if not all(vaga.get(k) for k in ("id", "name", "role", "area", "source")):
                continue
            if not str(vaga["source"]).startswith("https://"):
                continue
            if not cidade_valida(vaga["area"], pessoa, vaga["role"], vaga["name"]):
                continue
            if not cargo_valido(pessoa, vaga["role"], vaga["name"]):
                continue
            chave = chave_vaga(vaga)
            if chave in vistos:
                continue
            vistos.add(chave)
            resultado.append({k: v for k, v in vaga.items() if k != "pessoa"})
        resultado.sort(key=lambda v: (
            0 if pessoa == "beatriz" and not enfermagem_infantil(v["role"], v["name"]) else 1,
            v["role"].lower(),
        ))
        destino = D / (pessoa + ".json")
        temporario = destino.with_suffix(".json.tmp")
        temporario.write_text(
            json.dumps({"jobs": resultado}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporario.replace(destino)
        print(pessoa, len(resultado), "vagas únicas e filtradas")

if __name__ == "__main__":
    executar()
