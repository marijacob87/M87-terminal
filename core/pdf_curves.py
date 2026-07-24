from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox


_active_processes: set[QProcess] = set()


def _script_path() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts" / "convert_pdf_to_curves.py"


def _show_temporary_status(parent, text: str, milliseconds: int = 6000) -> None:
    """Mostra uma mensagem discreta na área inferior do M87."""
    if parent is None or not hasattr(parent, "session_result_label"):
        return

    parent.session_result_label.setText(text)
    parent.session_result_label.show()

    if hasattr(parent, "ajustar_altura_ao_conteudo"):
        QTimer.singleShot(0, parent.ajustar_altura_ao_conteudo)

    if hasattr(parent, "clear_session_result"):
        QTimer.singleShot(milliseconds, parent.clear_session_result)


def _choose_output_path(source: Path, parent) -> Path | None:
    """Abre a caixa nativa Salvar Como do macOS.

    O nome sugerido preserva o original. A pessoa pode escolher o próprio
    arquivo original para substituí-lo, mudar o nome ou salvar em outra pasta.
    """
    suggested = source

    selected, _filter = QFileDialog.getSaveFileName(
        parent,
        "Salvar PDF convertido em curvas",
        str(suggested),
        "Arquivo PDF (*.pdf)",
    )

    if not selected:
        return None

    output = Path(selected).expanduser()
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")

    return output.resolve()


def converter_pdf_em_curvas(pdf_path: str, parent=None) -> bool:
    """Converte os textos do PDF em vetores usando Ghostscript.

    Antes da conversão, abre a caixa nativa Salvar Como. É possível escolher o
    arquivo original para substituí-lo, definir outro nome ou outra pasta.
    """
    source = Path(pdf_path).expanduser().resolve()
    parent = parent or QApplication.activeWindow()

    if not source.is_file() or source.suffix.lower() != ".pdf":
        QMessageBox.critical(parent, "M87 • CURVAS", "O arquivo selecionado não é um PDF válido.")
        return False

    script = _script_path()
    if not script.is_file():
        QMessageBox.critical(
            parent,
            "M87 • CURVAS",
            f"Não encontrei o conversor:\n{script}",
        )
        return False

    output = _choose_output_path(source, parent)
    if output is None:
        _show_temporary_status(parent, "CURVAS cancelado.", 3000)
        return False

    process = QProcess(parent)
    process.setProgram(sys.executable)
    process.setArguments([str(script), str(source), str(output)])
    process.setProcessChannelMode(QProcess.SeparateChannels)
    _active_processes.add(process)

    def finished(exit_code: int, _exit_status) -> None:
        stdout = bytes(process.readAllStandardOutput()).decode("utf-8", errors="replace").strip()
        stderr = bytes(process.readAllStandardError()).decode("utf-8", errors="replace").strip()
        _active_processes.discard(process)

        try:
            data = json.loads(stdout.splitlines()[-1]) if stdout else {}
        except Exception:
            data = {}

        if exit_code == 0 and data.get("ok"):
            saved_path = Path(data["output"])
            replaced_original = bool(data.get("replaced_original"))

            if replaced_original:
                text = "CURVAS concluído • arquivo original substituído."
            else:
                text = f"CURVAS concluído • salvo como {saved_path.name}"

            source_pdfx = str(data.get("source_pdfx") or "").strip()
            if source_pdfx:
                profile_status = (
                    "perfil ICC preservado"
                    if data.get("output_intent_preserved")
                    else "sem OutputIntent incorporado"
                )
                text += (
                    f"\n⚠ Origem {source_pdfx} • {profile_status} • "
                    "PDF/X não reconfirmado"
                )

            _show_temporary_status(parent, text, 10000)

            # Se o original foi substituído, atualiza a leitura do PDF ativo.
            if replaced_original and hasattr(parent, "handle_pdf_drop"):
                QTimer.singleShot(0, lambda: parent.handle_pdf_drop(str(saved_path)))
            return

        message = data.get("message") or stderr or stdout or "A conversão falhou sem retornar detalhes."
        QMessageBox.critical(parent, "M87 • CURVAS", message)
        _show_temporary_status(parent, "CURVAS não concluído.", 5000)

    def process_error(_error) -> None:
        _active_processes.discard(process)
        QMessageBox.critical(
            parent,
            "M87 • CURVAS",
            f"Não consegui iniciar o conversor.\n\n{process.errorString()}",
        )
        _show_temporary_status(parent, "Não foi possível iniciar CURVAS.", 5000)

    process.finished.connect(finished)
    process.errorOccurred.connect(process_error)
    process.start()

    if not process.waitForStarted(1500):
        _active_processes.discard(process)
        QMessageBox.critical(
            parent,
            "M87 • CURVAS",
            f"Não consegui iniciar o conversor.\n\n{process.errorString()}",
        )
        return False

    _show_temporary_status(parent, "CURVAS em processamento…", 900000)
    return True
