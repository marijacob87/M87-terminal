from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


PROJECT_PATH = Path(
    "/Users/marianejacob/Library/Mobile Documents/"
    "com~apple~CloudDocs/Documents/m87_terminal"
)


@dataclass(frozen=True)
class GitPublishResult:
    success: bool
    message: str


def _run_git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_PATH,
        text=True,
        capture_output=True,
        check=False,
        timeout=180,
    )


def publish_git_update(commit_message: str) -> GitPublishResult:
    """Executa git add, commit e push no projeto do M87 Terminal."""
    message = commit_message.strip()

    if not message:
        return GitPublishResult(
            False,
            "Escreva a atualização depois de #git.",
        )

    if not PROJECT_PATH.is_dir():
        return GitPublishResult(
            False,
            f"Pasta do projeto não encontrada:\n{PROJECT_PATH}",
        )

    try:
        add_result = _run_git("add", ".")
        if add_result.returncode != 0:
            detail = (add_result.stderr or add_result.stdout).strip()
            return GitPublishResult(False, f"Falha no git add.\n{detail}")

        diff_result = _run_git("diff", "--cached", "--quiet")
        has_staged_changes = diff_result.returncode == 1

        if diff_result.returncode not in (0, 1):
            detail = (diff_result.stderr or diff_result.stdout).strip()
            return GitPublishResult(
                False,
                f"Não foi possível verificar as alterações.\n{detail}",
            )

        if not has_staged_changes:
            return GitPublishResult(
                False,
                "Nenhuma alteração nova para enviar.",
            )

        commit_result = _run_git("commit", "-m", message)
        if commit_result.returncode != 0:
            detail = (commit_result.stderr or commit_result.stdout).strip()
            return GitPublishResult(False, f"Falha no commit.\n{detail}")

        push_result = _run_git("push")
        if push_result.returncode != 0:
            detail = (push_result.stderr or push_result.stdout).strip()
            return GitPublishResult(
                False,
                "Commit criado, mas o push falhou.\n"
                f"{detail}",
            )

        return GitPublishResult(
            True,
            "✓ Atualização enviada para o GitHub\n"
            f'Commit: "{message}"',
        )

    except FileNotFoundError:
        return GitPublishResult(
            False,
            "Git não encontrado neste Mac.",
        )
    except subprocess.TimeoutExpired:
        return GitPublishResult(
            False,
            "O Git demorou demais e a operação foi interrompida.",
        )
    except Exception as error:
        return GitPublishResult(
            False,
            f"Não foi possível enviar a atualização.\n{error}",
        )
