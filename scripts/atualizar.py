import json
import re
import hashlib
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

from pathlib import Path
from html import unescape

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "dados"

CIDADES = {
    "beatriz": ["sao jose dos pinhais", "sjp"],
    "sueli": ["curitiba", "pinhais", "cajuru"]
}

CARGOS = {
    "beatriz": [
        "educacao infantil",
        "auxiliar de creche",
        "auxiliar de sala",
        "auxiliar de educacao",
        "bercario",
        "pedagogia",
        "professora infantil",
        "professor infantil"
    ],
    "sueli": [
        "tecnico de enfermagem",
        "auxiliar de enfermagem",
        "enfermagem",
        "atendente de farmacia",
        "balconista de farmacia",
        "recepcionista hospitalar",
        "recepcionista de clinica",
        "recepcionista de laboratorio"
    ]
}


def normalizar(texto):
    texto = str(texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return texto


def limpar(texto):
    texto = unescape(str(texto or ""))
    texto = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def ler(nome, padrao):
    caminho = D / nome

    if not caminho.exists():
        return padrao

    with caminho.open("r", encoding="utf-8") as arquivo:
        return json.load(arquivo)


def cidade_ok(texto, pessoa):
    t = normalizar(texto)
    return any(c in t for c in CIDADES[pessoa])


def cargo_ok(texto, pessoa):
    t = normalizar(texto)
    return any(c in t for c in CARGOS[pessoa])


def contato(texto):
    email = re.search(
        r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",
        texto,
        re.I
    )

    telefone = re.search(
        r"(?:\+?55\s*)?\(?41\)?[\s.-]*9\d{4}[\s.-]*\d{4}",
        texto
    )

    whatsapp = ""

    if telefone and "whatsapp" in normalizar(texto):
        whatsapp = re.sub(r"\D", "", telefone.group())

    return whatsapp, email.group() if email else ""


def processar():
    D.mkdir(parents=True, exist_ok=True)

    itens = ler("fontes.json", [])
    feeds = ler("feeds.json", [])

    if not isinstance(itens, list):
        raise ValueError("fontes.json precisa ser uma lista")

    if not isinstance(feeds, list):
        raise ValueError("feeds.json precisa ser uma lista")

    itens = list(itens)

    for feed in feeds:

        if not isinstance(feed, dict):
            continue

        url = str(feed.get("url", ""))
        pessoa = str(feed.get("pessoa", "")).lower()

        if pessoa not in CIDADES:
            continue

        if not url.startswith("https://"):
            continue

        try:
            requisicao = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 PainelVagas/1.0"
                }
            )

            with urllib.request.urlopen(
                requisicao,
                timeout=20
            ) as resposta:
                xml = resposta.read(2_000_000)

            raiz = ET.fromstring(xml)

            entradas = raiz.findall(".//item")

            for item in entradas[:100]:

                titulo = limpar(
                    item.findtext("title", "")
                )

                descricao = limpar(
                    item.findtext("description", "")
                )

                link = (
                    item.findtext("link", "") or ""
                ).strip()

                texto = f"{titulo} {descricao}"

                local = str(
                    feed.get("cidade", "")
                ).strip()

                if not cargo_ok(titulo, pessoa):
                    continue

                if not cidade_ok(
                    f"{texto} {local}",
                    pessoa
                ):
                    continue

                if not link.startswith("https://"):
                    continue

                whatsapp, email = contato(descricao)

                if pessoa == "beatriz":
                    cidade = "São José dos Pinhais, PR"
                    zona = "sjp"
                else:
                    cidade = (
                        local or
                        "Curitiba ou Pinhais, PR - conferir anúncio"
                    )

                    zona = (
                        "pinhais"
                        if normalizar(cidade).startswith("pinhais")
                        else "curitiba"
                    )

                identificador = hashlib.sha256(
                    link.encode("utf-8")
                ).hexdigest()[:16]

                itens.append({
                    "pessoa": pessoa,
                    "id": "rss-" + identificador,
                    "name": feed.get(
                        "nome",
                        "Vaga publicada"
                    ),
                    "role": titulo,
                    "area": cidade,
                    "zone": zona,
                    "source": link,
                    "wa": whatsapp,
                    "email": email,
                    "info": (
                        "Confira a localização e a "
                        "disponibilidade no anúncio."
                    )
                })

        except Exception as erro:
            print(
                "Falha ao consultar:",
                url,
                str(erro)[:150]
            )

    for pessoa in ("beatriz", "sueli"):

        resultado = []
        vistos = set()

        for vaga in itens:

            if not isinstance(vaga, dict):
                continue

            if str(
                vaga.get("pessoa", "")
            ).lower() != pessoa:
                continue

            obrigatorios = (
                "id",
                "name",
                "role",
                "area",
                "source"
            )

            if not all(
                vaga.get(campo)
                for campo in obrigatorios
            ):
                continue

            if not str(
                vaga["source"]
            ).startswith("https://"):
                continue

            if pessoa == "beatriz":

                if vaga.get("zone") != "sjp":
                    continue

                if not cidade_ok(
                    vaga["area"],
                    pessoa
                ):
                    continue

            if pessoa == "sueli":

                if vaga.get("zone") not in (
                    "curitiba",
                    "pinhais"
                ):
                    continue

            if vaga["id"] in vistos:
                continue

            vistos.add(vaga["id"])

            resultado.append({
                chave: valor
                for chave, valor in vaga.items()
                if chave != "pessoa"
            })

        caminho = D / f"{pessoa}.json"

        caminho.write_text(
            json.dumps(
                {"jobs": resultado},
                ensure_ascii=False,
                indent=2
            ) + "\n",
            encoding="utf-8"
        )

        print(
            pessoa,
            len(resultado),
            "vagas encontradas"
        )


if __name__ == "__main__":
    processar()
