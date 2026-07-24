from __future__ import annotations

from pathlib import Path
import subprocess

import pikepdf


def executar_applescript(script: str) -> str | None:
    """Executa AppleScript e devolve o texto de saída, ou None se cancelar/falhar."""
    resultado = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        check=False,
    )

    if resultado.returncode != 0:
        return None

    caminho = resultado.stdout.strip()
    return caminho or None


def _escape_applescript(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace('"', '\\"')


def mostrar_mensagem(titulo: str, mensagem: str) -> None:
    titulo = _escape_applescript(titulo)
    mensagem = _escape_applescript(mensagem)

    subprocess.run(
        [
            "osascript",
            "-e",
            f'display dialog "{mensagem}" '
            f'with title "{titulo}" '
            f'buttons {{"OK"}} default button "OK"',
        ],
        capture_output=True,
        check=False,
    )


def mostrar_erro(mensagem: str) -> None:
    mensagem = _escape_applescript(mensagem)

    subprocess.run(
        [
            "osascript",
            "-e",
            f'display alert "Não foi possível intercalar" '
            f'message "{mensagem}" as critical',
        ],
        capture_output=True,
        check=False,
    )


def escolher_pdf(instrucao: str) -> Path | None:
    instrucao = _escape_applescript(instrucao)

    # O filtro por extensão é mais confiável no Finder do que depender
    # apenas do UTI "com.adobe.pdf" em versões diferentes do macOS.
    script = (
        f'set arquivoEscolhido to choose file '
        f'with prompt "{instrucao}" '
        f'of type {{"pdf", "com.adobe.pdf"}}\n'
        f'POSIX path of arquivoEscolhido'
    )

    caminho = executar_applescript(script)
    if not caminho:
        return None

    arquivo = Path(caminho).expanduser()
    if arquivo.suffix.lower() != ".pdf":
        mostrar_erro("O arquivo escolhido não é um PDF.")
        return None

    return arquivo


def gerar_nome_saida(nome_base: str) -> Path:
    desktop = Path.home() / "Desktop"
    destino = desktop / f"{nome_base}_INTERCALADO.pdf"

    if not destino.exists():
        return destino

    numero = 2
    while True:
        destino = desktop / f"{nome_base}_INTERCALADO_{numero}.pdf"
        if not destino.exists():
            return destino
        numero += 1


def _numero_caixa(valor) -> float:
    return round(float(valor), 3)


def tamanho_pagina(pagina: pikepdf.Page) -> tuple[float, float]:
    caixa = pagina.MediaBox
    largura = _numero_caixa(caixa[2]) - _numero_caixa(caixa[0])
    altura = _numero_caixa(caixa[3]) - _numero_caixa(caixa[1])
    return round(largura, 2), round(altura, 2)


def intercalar_pdf() -> None:
    arquivo_frentes = escolher_pdf("1 de 2 — Escolha o PDF das FRENTES")
    if arquivo_frentes is None:
        return

    arquivo_versos = escolher_pdf("2 de 2 — Escolha o PDF dos VERSOS")
    if arquivo_versos is None:
        return

    try:
        with pikepdf.Pdf.open(arquivo_frentes) as frentes, pikepdf.Pdf.open(
            arquivo_versos
        ) as versos:
            quantidade_frentes = len(frentes.pages)
            quantidade_versos = len(versos.pages)

            if quantidade_frentes == 0:
                mostrar_erro("O PDF das frentes não possui páginas.")
                return

            if quantidade_versos == 0:
                mostrar_erro("O PDF dos versos não possui páginas.")
                return

            if quantidade_versos not in (1, quantidade_frentes):
                mostrar_erro(
                    f"Frentes: {quantidade_frentes} páginas\\n"
                    f"Versos: {quantidade_versos} páginas\\n\\n"
                    "O PDF dos versos precisa ter apenas 1 página "
                    "ou a mesma quantidade de páginas das frentes."
                )
                return

            tamanho_frente = tamanho_pagina(frentes.pages[0])
            tamanho_verso = tamanho_pagina(versos.pages[0])

            if tamanho_frente != tamanho_verso:
                mostrar_erro(
                    "Frentes e versos possuem tamanhos diferentes.\\n\\n"
                    f"Frente: {tamanho_frente[0]} × {tamanho_frente[1]} pt\\n"
                    f"Verso: {tamanho_verso[0]} × {tamanho_verso[1]} pt"
                )
                return

            saida = pikepdf.Pdf.new()

            for indice, pagina_frente in enumerate(frentes.pages):
                saida.pages.append(pagina_frente)
                pagina_verso = versos.pages[0] if quantidade_versos == 1 else versos.pages[indice]
                saida.pages.append(pagina_verso)

            destino = gerar_nome_saida(arquivo_frentes.stem)
            saida.save(destino)

        mostrar_mensagem(
            "PDF intercalado",
            "Arquivo criado com sucesso.\\n\\n"
            f"Frentes: {quantidade_frentes}\\n"
            f"Versos: {quantidade_versos}\\n"
            f"Resultado: {quantidade_frentes * 2} páginas\\n\\n"
            f"Salvo no Desktop como:\\n{destino.name}",
        )

    except pikepdf.PasswordError:
        mostrar_erro("Um dos PDFs está protegido por senha.")
    except pikepdf.PdfError as erro:
        mostrar_erro(f"Um dos PDFs está danificado ou é inválido.\\n\\n{erro}")
    except Exception as erro:
        mostrar_erro(str(erro))


if __name__ == "__main__":
    intercalar_pdf()
