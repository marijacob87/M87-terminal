from pathlib import Path
import subprocess

from pypdf import PdfReader, PdfWriter


def executar_applescript(script: str) -> str | None:
    resultado = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )

    if resultado.returncode != 0:
        return None

    return resultado.stdout.strip()


def mostrar_mensagem(titulo: str, mensagem: str) -> None:
    titulo = titulo.replace('"', '\\"')
    mensagem = mensagem.replace('"', '\\"')

    subprocess.run(
        [
            "osascript",
            "-e",
            f'display dialog "{mensagem}" '
            f'with title "{titulo}" '
            f'buttons {{"OK"}} default button "OK"',
        ],
        capture_output=True,
    )


def mostrar_erro(mensagem: str) -> None:
    mensagem = mensagem.replace('"', '\\"')

    subprocess.run(
        [
            "osascript",
            "-e",
            f'display alert "Não foi possível intercalar" '
            f'message "{mensagem}" as critical',
        ],
        capture_output=True,
    )


def escolher_pdf(instrução: str) -> Path | None:
    instrução = instrução.replace('"', '\\"')

    script = (
        f'set arquivoEscolhido to choose file '
        f'with prompt "{instrução}" '
        f'of type {{"com.adobe.pdf"}}\n'
        f'POSIX path of arquivoEscolhido'
    )

    caminho = executar_applescript(script)

    if not caminho:
        return None

    return Path(caminho)


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


def tamanho_pagina(pagina) -> tuple[float, float]:
    return (
        round(float(pagina.mediabox.width), 2),
        round(float(pagina.mediabox.height), 2),
    )


def intercalar_pdf() -> None:
    

    arquivo_frentes = escolher_pdf(
        "1 de 2 — Escolha o PDF das FRENTES"
    )

    if arquivo_frentes is None:
        return

    arquivo_versos = escolher_pdf(
        "2 de 2 — Escolha o PDF dos VERSOS"
    )

    if arquivo_versos is None:
        return

    try:
        frentes = PdfReader(str(arquivo_frentes))
        versos = PdfReader(str(arquivo_versos))

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

        writer = PdfWriter()

        for indice, pagina_frente in enumerate(frentes.pages):
            writer.add_page(pagina_frente)

            if quantidade_versos == 1:
                writer.add_page(versos.pages[0])
            else:
                writer.add_page(versos.pages[indice])

        destino = gerar_nome_saida(arquivo_frentes.stem)

        with destino.open("wb") as arquivo_saida:
            writer.write(arquivo_saida)

        mostrar_mensagem(
            "PDF intercalado",
            "Arquivo criado com sucesso.\\n\\n"
            f"Frentes: {quantidade_frentes}\\n"
            f"Versos: {quantidade_versos}\\n"
            f"Resultado: {quantidade_frentes * 2} páginas\\n\\n"
            f"Salvo no Desktop como:\\n{destino.name}",
        )

    except Exception as erro:
        mostrar_erro(str(erro))


if __name__ == "__main__":
    intercalar_pdf()