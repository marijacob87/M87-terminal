from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pikepdf


class PdfPreservationError(RuntimeError):
    pass


@dataclass(frozen=True)
class PdfPreservationResult:
    output_intents: int
    icc_profiles: int
    source_pdfx: str

    @property
    def output_intent_preserved(self) -> bool:
        return self.output_intents > 0


def _pdfx_version(pdf: pikepdf.Pdf) -> str:
    value = pdf.docinfo.get("/GTS_PDFXVersion")
    return str(value).strip() if value is not None else ""


def _profile_fingerprints(intents) -> tuple[str, ...]:
    fingerprints = []

    for intent in intents:
        profile = intent.get("/DestOutputProfile")
        if profile is None:
            continue
        content = profile.read_bytes()
        fingerprints.append(hashlib.sha256(content).hexdigest())

    return tuple(fingerprints)


def preserve_output_intents(
    source_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
) -> PdfPreservationResult:
    """Copia OutputIntents e perfis ICC sem declarar conformidade PDF/X."""
    source = Path(source_path).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()

    if not source.is_file() or not output.is_file():
        raise PdfPreservationError(
            "Não foi possível localizar a origem ou a saída para preservar o ICC."
        )

    temporary_path = None

    try:
        with pikepdf.Pdf.open(source) as source_pdf:
            source_pdfx = _pdfx_version(source_pdf)
            source_intents = source_pdf.Root.get("/OutputIntents")

            if not source_intents:
                return PdfPreservationResult(0, 0, source_pdfx)

            source_profiles = _profile_fingerprints(source_intents)

            with pikepdf.Pdf.open(output) as output_pdf:
                copied_intents = []

                for intent in source_intents:
                    foreign_intent = intent
                    if not foreign_intent.is_indirect:
                        foreign_intent = source_pdf.make_indirect(
                            foreign_intent
                        )
                    copied_intents.append(
                        output_pdf.copy_foreign(foreign_intent)
                    )

                output_pdf.Root.OutputIntents = pikepdf.Array(
                    copied_intents
                )

                # Uma transformação pode invalidar a conformidade formal.
                # Mantemos o perfil de impressão, mas nunca afirmamos PDF/X
                # sem uma validação específica da norma.
                for key in (
                    "/GTS_PDFXVersion",
                    "/GTS_PDFXConformance",
                ):
                    if key in output_pdf.docinfo:
                        del output_pdf.docinfo[key]

                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{output.stem}_ICC_",
                    suffix=".pdf",
                    dir=str(output.parent),
                )
                os.close(descriptor)
                temporary_path = Path(temporary_name)
                temporary_path.unlink(missing_ok=True)
                output_pdf.save(temporary_path)

        with pikepdf.Pdf.open(temporary_path) as validated_pdf:
            validated_intents = validated_pdf.Root.get("/OutputIntents")
            if not validated_intents:
                raise PdfPreservationError(
                    "O OutputIntent não permaneceu na saída."
                )

            output_profiles = _profile_fingerprints(validated_intents)
            if output_profiles != source_profiles:
                raise PdfPreservationError(
                    "O perfil ICC da saída não corresponde ao original."
                )

        os.replace(temporary_path, output)
        temporary_path = None

        return PdfPreservationResult(
            output_intents=len(source_intents),
            icc_profiles=len(source_profiles),
            source_pdfx=source_pdfx,
        )
    except PdfPreservationError:
        raise
    except Exception as error:
        raise PdfPreservationError(
            f"Não foi possível preservar o OutputIntent/ICC: {error}"
        ) from error
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
