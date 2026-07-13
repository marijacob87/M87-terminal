import math
import re
from datetime import datetime
from pathlib import Path


PADRAO_GRAFICA = re.compile(
    r"^#\s*(.*?)\s*-\s*\d+un\s+\d+Planos\s+.*?\s+\d{8}$",
    re.IGNORECASE,
)


def limpar_nome_base(nome: str) -> str:
    nome = nome.strip()

    correspondencia = PADRAO_GRAFICA.match(nome)

    if correspondencia:
        return correspondencia.group(1).strip()

    return nome.removeprefix("#").strip()


def calcular_planos(unidades: int, por_plano: int) -> int:
    if unidades <= 0:
        raise ValueError("A quantidade total deve ser maior que zero.")

    if por_plano <= 0:
        raise ValueError("As unidades por plano devem ser maiores que zero.")

    return math.ceil(unidades / por_plano)


def gerar_novo_nome(
    arquivo: str,
    unidades: int,
    por_plano: int,
    papel: str,
) -> Path:
    caminho = Path(arquivo)

    nome_base = limpar_nome_base(caminho.stem)
    planos = calcular_planos(unidades, por_plano)
    data = datetime.now().strftime("%d%m%Y")
    papel = papel.strip() or "Mat 350g"

    novo_nome = (
        f"# {nome_base} - "
        f"{unidades}un "
        f"{planos}Planos "
        f"{papel} "
        f"{data}"
        f"{caminho.suffix}"
    )

    destino = caminho.with_name(novo_nome)

    contador = 2

    while destino.exists() and destino != caminho:
        destino = caminho.with_name(
            f"# {nome_base} - "
            f"{unidades}un "
            f"{planos}Planos "
            f"{papel} "
            f"{data}_{contador}"
            f"{caminho.suffix}"
        )
        contador += 1

    return destino


def renomear_pdf(
    arquivo: str,
    unidades: int,
    por_plano: int,
    papel: str,
) -> Path:
    origem = Path(arquivo)

    if not origem.exists():
        raise FileNotFoundError("O PDF não foi encontrado.")

    destino = gerar_novo_nome(
        arquivo=arquivo,
        unidades=unidades,
        por_plano=por_plano,
        papel=papel,
    )

    origem.rename(destino)

    return destino