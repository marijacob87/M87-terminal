import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from core.whatsapp_download import (
    WhatsAppRequest,
    _filename_from_media_title,
    _is_outgoing_labels,
    _message_matches,
    _validate_completed_batch,
    available_path,
    output_directory,
    parse_whatsapp_command,
    WhatsAppDownloadError,
)


class WhatsAppCommandTests(unittest.TestCase):
    def test_parses_contact_with_or_without_baixar(self):
        today = date(2026, 7, 29)
        expected = WhatsAppRequest("Pedro Reis", today)

        self.assertEqual(
            parse_whatsapp_command("WPP BAIXAR Pedro Reis HOJE", today),
            expected,
        )
        self.assertEqual(
            parse_whatsapp_command('wpp "Pedro Reis" hoje', today),
            expected,
        )

    def test_rejects_incomplete_command(self):
        self.assertIsNone(parse_whatsapp_command("WPP Pedro Reis"))
        self.assertIsNone(parse_whatsapp_command("WPP HOJE"))

    def test_matches_only_contact_and_requested_day(self):
        request = WhatsAppRequest("Pedro Reis", date(2026, 7, 29))

        self.assertTrue(_message_matches("[10:15, 29/07/2026] Pedro Reis:", request))
        self.assertFalse(_message_matches("[10:15, 28/07/2026] Pedro Reis:", request))
        self.assertFalse(_message_matches("[10:15, 29/07/2026] Mariane:", request))

    def test_existing_download_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "arte.pdf").touch()

            self.assertEqual(
                available_path(folder, "arte.pdf"),
                folder / "arte (2).pdf",
            )

    def test_downloads_are_saved_directly_on_desktop(self):
        request = WhatsAppRequest("Pedro Reis", date(2026, 7, 29))
        desktop = Path("/tmp/Desktop")

        with patch("core.whatsapp_download.DOWNLOAD_ROOT", desktop):
            self.assertEqual(output_directory(request), desktop)

    def test_partial_batch_is_never_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            saved = Path(directory) / "recebido.pdf"
            saved.write_bytes(b"%PDF")

            with self.assertRaises(WhatsAppDownloadError):
                _validate_completed_batch(
                    expected=2,
                    pending={("mensagem-2", "document-thumb"): {}},
                    saved_paths=[saved],
                )

    def test_complete_batch_requires_non_empty_files(self):
        with tempfile.TemporaryDirectory() as directory:
            valid = Path(directory) / "valido.pdf"
            empty = Path(directory) / "vazio.pdf"
            valid.write_bytes(b"%PDF")
            empty.touch()

            _validate_completed_batch(1, {}, [valid])
            with self.assertRaises(WhatsAppDownloadError):
                _validate_completed_batch(1, {}, [empty])

    def test_outgoing_messages_are_excluded_in_both_languages(self):
        self.assertTrue(_is_outgoing_labels(["Você:", "Lida"]))
        self.assertTrue(_is_outgoing_labels(["You:", "Delivered"]))
        self.assertFalse(_is_outgoing_labels(["Pedro Reis:", "Encaminhar mídia"]))

    def test_expected_filename_is_read_from_document_card(self):
        self.assertEqual(
            _filename_from_media_title('Baixar "Cardapio Braza.pdf"'),
            "Cardapio Braza.pdf",
        )
        self.assertEqual(_filename_from_media_title("Abrir imagem"), "")


if __name__ == "__main__":
    unittest.main()
