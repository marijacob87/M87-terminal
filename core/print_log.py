import json
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


PLAN_PATTERN = re.compile(
    r"(?<!\d)(\d+)\s*(?:planos|pl)(?![A-Za-zÀ-ÿ])",
    re.IGNORECASE,
)


class PrintLogError(RuntimeError):
    pass


@dataclass(frozen=True)
class PrintLogEntry:
    name: str
    front: int
    back: int
    day: int
    operator: str = "Mariane"


def clean_record_name(name: str) -> str:
    stem = Path(name).stem.strip()
    return stem.removeprefix("#").strip()


def extract_plans(name: str) -> int:
    match = PLAN_PATTERN.search(Path(name).stem)
    return int(match.group(1)) if match else 0


def suggested_counts(name: str, page_count: int) -> tuple[int, int]:
    plans = extract_plans(name)
    if page_count <= 1:
        return plans, 0
    return plans, plans


def make_entry(
    name: str,
    page_count: int,
    *,
    plans: int | None = None,
    day: int | None = None,
) -> PrintLogEntry:
    if plans is None:
        front, back = suggested_counts(name, page_count)
    elif page_count <= 1:
        front, back = plans, 0
    else:
        front, back = plans, plans
    return PrintLogEntry(
        name=clean_record_name(name),
        front=front,
        back=back,
        day=day or datetime.now().day,
    )


def send_entries(
    endpoint: str,
    access_key: str,
    entries: Iterable[PrintLogEntry],
    *,
    allow_duplicates: bool = False,
    timeout: int = 15,
) -> dict:
    endpoint = endpoint.strip()
    access_key = access_key.strip()
    records = [asdict(entry) for entry in entries]
    if not endpoint.startswith("https://script.google.com/"):
        raise PrintLogError("Configure o endereço publicado do Google Apps Script.")
    if not access_key:
        raise PrintLogError("Configure a chave de acesso da planilha.")
    if not records:
        raise PrintLogError("Não há registros para enviar.")

    payload = json.dumps(
        {
            "access_key": access_key,
            "allow_duplicates": allow_duplicates,
            "records": records,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise PrintLogError(f"A planilha respondeu com erro HTTP {error.code}.") from error
    except urllib.error.URLError as error:
        raise PrintLogError(
            "Não foi possível acessar a planilha. Verifique a internet e tente novamente."
        ) from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PrintLogError("A resposta da planilha não é válida.") from error

    if not result.get("ok"):
        duplicates = result.get("duplicates") or []
        if duplicates:
            return result
        raise PrintLogError(result.get("error") or "A planilha recusou o registro.")
    return result
