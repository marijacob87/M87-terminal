import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


PADRAO_GRAFICA = re.compile(
    r"^#\s*(?P<base>.*?)\s*-\s*"
    r"(?P<units>\d+)un\s+(?P<plans>\d+)Planos\s+"
    r"(?P<paper>.+?)\s+(?P<date>\d{8})(?:_\d+)?$",
    re.IGNORECASE,
)
PADRAO_IMP = re.compile(
    r"^(?P<units>\d+)un(?:\s+cada arte)?(?:\s+cada_|\s+)(?P<plans>\d+)(?:Planos|pl|p)_"
    r"(?P<paper>[^_]+)_(?P<base>.+?)_"
    r"(?P<date>\d{8})(?:_\d+|\s+\(\d+\))?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProductionNameData:
    base: str
    units: int
    plans: int
    per_sheet: int
    paper: str


def parse_production_name(name: str) -> ProductionNameData | None:
    stem = Path(name).stem.strip()
    match = PADRAO_GRAFICA.match(stem) or PADRAO_IMP.match(stem)
    if not match:
        return None
    units = int(match.group("units"))
    plans = int(match.group("plans"))
    if units < 1 or plans < 1:
        return None
    return ProductionNameData(
        base=match.group("base").strip(),
        units=units,
        plans=plans,
        per_sheet=max(1, math.ceil(units / plans)),
        paper=match.group("paper").strip(),
    )


def limpar_nome_base(nome: str) -> str:
    nome = nome.strip()
    production = parse_production_name(nome)
    if production:
        return production.base

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
