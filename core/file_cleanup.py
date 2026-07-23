"""Rotinas seguras para limpeza de arquivos usados pelo M87 Terminal.

Este módulo concentra operações de remoção para evitar implementações
repetidas em comandos diferentes. Nenhuma função apaga arquivos fora dos
locais recebidos explicitamente.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path


def tornar_gravavel(caminho: Path) -> None:
    """Adiciona permissão de escrita ao proprietário quando for possível."""
    try:
        modo_atual = caminho.stat().st_mode
        caminho.chmod(modo_atual | stat.S_IWUSR)
    except OSError:
        pass


def remover_caminho(caminho: Path, *, prefixo_log: str = "CL") -> bool:
    """Remove um arquivo, link ou pasta e informa se a operação terminou bem."""
    try:
        if caminho.is_symlink() or caminho.is_file():
            tornar_gravavel(caminho)
            caminho.unlink(missing_ok=True)
        elif caminho.is_dir():
            shutil.rmtree(
                caminho,
                onerror=lambda funcao, valor, _erro: (
                    tornar_gravavel(Path(valor)),
                    funcao(valor),
                ),
            )
        return True
    except Exception as erro:
        print(f"[{prefixo_log}] Não foi possível apagar {caminho}: {erro}")
        return False


def esvaziar_pasta(pasta: Path, *, prefixo_log: str = "CL") -> bool:
    """Remove somente o conteúdo da pasta, preservando a própria pasta."""
    if not pasta.exists():
        return True

    try:
        itens = list(pasta.iterdir())
    except Exception as erro:
        print(f"[{prefixo_log}] Não foi possível abrir {pasta}: {erro}")
        return False

    sucesso = True
    for item in itens:
        sucesso = remover_caminho(item, prefixo_log=prefixo_log) and sucesso
    return sucesso


def limpar_caches_python(raiz_projeto: Path) -> bool:
    """Remove apenas caches Python localizados dentro do projeto M87."""
    sucesso = True

    for pasta_cache in list(raiz_projeto.rglob("__pycache__")):
        sucesso = remover_caminho(
            pasta_cache,
            prefixo_log="CACHE",
        ) and sucesso

    for arquivo_pyc in list(raiz_projeto.rglob("*.pyc")):
        sucesso = remover_caminho(
            arquivo_pyc,
            prefixo_log="CACHE",
        ) and sucesso

    return sucesso
