import math
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(frozen=True)
class MontagemResult:
    peca_l: float
    peca_a: float
    colunas: int
    linhas: int
    total: int
    inicio_x: float
    inicio_y: float
    largura_ocupada: float
    altura_ocupada: float
    aproveitamento: float
    desperdicio: float
    sobra_lateral: float
    sobra_superior: float
    planos: Optional[int]
    pecas_produzidas: Optional[int]
    margem_esquerda: float
    margem_direita: float
    margem_superior: float
    margem_inferior: float
    orientacao: str

    def to_dict(self):
        return asdict(self)


def calcular_montagem(
    papel_l: float,
    papel_a: float,
    peca_l: float,
    peca_a: float,
    espaco: float,
    margem: float,
    quantidade: Optional[float] = None,
    acrescentar_pinca: bool = False,
    orientacao: str = "Peça normal",
) -> MontagemResult:
    margem_esquerda = margem
    margem_direita = margem
    margem_superior = margem
    margem_inferior = 15.0 if acrescentar_pinca else margem

    area_util_l = max(0.0, papel_l - margem_esquerda - margem_direita)
    area_util_a = max(0.0, papel_a - margem_superior - margem_inferior)

    colunas = int((area_util_l + espaco) // (peca_l + espaco)) if peca_l > 0 else 0
    linhas = int((area_util_a + espaco) // (peca_a + espaco)) if peca_a > 0 else 0
    colunas = max(0, colunas)
    linhas = max(0, linhas)
    total = colunas * linhas

    largura_ocupada = colunas * peca_l + max(0, colunas - 1) * espaco
    altura_ocupada = linhas * peca_a + max(0, linhas - 1) * espaco

    inicio_x = margem_esquerda + max(0.0, area_util_l - largura_ocupada) / 2
    inicio_y = margem_inferior + max(0.0, area_util_a - altura_ocupada) / 2

    area_folha = papel_l * papel_a
    area_pecas = total * peca_l * peca_a
    aproveitamento = (area_pecas / area_folha) * 100 if area_folha > 0 else 0.0

    planos = None
    pecas_produzidas = None
    if quantidade is not None and quantidade > 0 and total > 0:
        planos = math.ceil(quantidade / total)
        pecas_produzidas = total * planos

    return MontagemResult(
        peca_l=peca_l,
        peca_a=peca_a,
        colunas=colunas,
        linhas=linhas,
        total=total,
        inicio_x=inicio_x,
        inicio_y=inicio_y,
        largura_ocupada=largura_ocupada,
        altura_ocupada=altura_ocupada,
        aproveitamento=aproveitamento,
        desperdicio=100.0 - aproveitamento,
        sobra_lateral=area_util_l - largura_ocupada,
        sobra_superior=area_util_a - altura_ocupada,
        planos=planos,
        pecas_produzidas=pecas_produzidas,
        margem_esquerda=margem_esquerda,
        margem_direita=margem_direita,
        margem_superior=margem_superior,
        margem_inferior=margem_inferior,
        orientacao=orientacao,
    )


def obter_opcoes(
    papel_l: float,
    papel_a: float,
    peca_l: float,
    peca_a: float,
    espaco: float,
    margem: float,
    quantidade: Optional[float] = None,
    acrescentar_pinca: bool = False,
):
    normal = calcular_montagem(
        papel_l, papel_a, peca_l, peca_a, espaco, margem,
        quantidade, acrescentar_pinca, "Peça normal",
    )
    rotacionada = calcular_montagem(
        papel_l, papel_a, peca_a, peca_l, espaco, margem,
        quantidade, acrescentar_pinca, "Peça rotacionada 90°",
    )

    # Mantém o mesmo critério do site: maior quantidade por folha.
    # Em empate, privilegia o melhor aproveitamento e a peça normal.
    return sorted(
        [normal, rotacionada],
        key=lambda item: (
            item.total,
            item.aproveitamento,
            item.orientacao == "Peça normal",
        ),
        reverse=True,
    )
