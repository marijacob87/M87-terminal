import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.calculator import calculate, is_calculation
from core.code_tools import (
    calculate_ean13_check_digit,
    ean13_pattern,
    normalize_ean13,
)
from core.montagem_calculator import calcular_montagem, obter_opcoes
from core.pdf_rename import calcular_planos, gerar_novo_nome, limpar_nome_base
from core.state import DEFAULT_STATE, load_window_state, save_window_state
from core.suggestion_engine import command_score, get_suggestions


class CalculatorTests(unittest.TestCase):
    def test_calculates_and_formats_decimal_comma(self):
        self.assertEqual(calculate("(10 + 5) / 4"), "3,75")

    def test_rejects_unsafe_expression(self):
        self.assertFalse(is_calculation("__import__('os')"))
        with self.assertRaises((SyntaxError, ValueError)):
            calculate("__import__('os').system('echo unsafe')")


class Ean13Tests(unittest.TestCase):
    def test_calculates_known_check_digit(self):
        self.assertEqual(calculate_ean13_check_digit("560123456789"), "2")

    def test_normalizes_twelve_digits(self):
        code, message = normalize_ean13("560123456789")
        self.assertEqual(code, "5601234567892")
        self.assertIn("calculado", message)
        self.assertEqual(len(ean13_pattern(code)), 95)

    def test_rejects_wrong_check_digit(self):
        code, message = normalize_ean13("5601234567890")
        self.assertIsNone(code)
        self.assertIn("incorreto", message)


class MontagemTests(unittest.TestCase):
    def test_calculates_grid_and_plans(self):
        result = calcular_montagem(
            papel_l=320,
            papel_a=450,
            peca_l=90,
            peca_a=50,
            espaco=2,
            margem=10,
            quantidade=100,
        )
        self.assertEqual((result.colunas, result.linhas), (3, 8))
        self.assertEqual(result.total, 24)
        self.assertEqual(result.planos, 5)
        self.assertEqual(result.pecas_produzidas, 120)

    def test_best_option_is_first(self):
        options = obter_opcoes(320, 450, 90, 50, 2, 10)
        self.assertGreaterEqual(options[0].total, options[1].total)


class PdfRenameTests(unittest.TestCase):
    def test_cleans_previous_production_name(self):
        name = "# Convite - 100un 5Planos Mat 350g 24072026"
        self.assertEqual(limpar_nome_base(name), "Convite")

    def test_rounds_plans_up(self):
        self.assertEqual(calcular_planos(101, 20), 6)

    def test_generates_name_without_renaming_file(self):
        path = gerar_novo_nome("/tmp/Convite.pdf", 101, 20, "Couché")
        self.assertTrue(path.name.startswith("# Convite - 101un 6Planos Couché "))
        self.assertEqual(path.suffix, ".pdf")


class SuggestionTests(unittest.TestCase):
    commands = [
        {"code": "AD", "label": "Abrir Downloads"},
        {"code": "APP", "label": "Abrir Aplicativo"},
        {"code": "BM", "label": "Bloquear Mac"},
    ]

    def test_exact_code_has_highest_priority(self):
        self.assertEqual(command_score(self.commands[0], "AD"), 0)
        suggestions = get_suggestions("AD", self.commands)
        self.assertEqual(suggestions[0]["code"], "AD")

    def test_internal_developer_commands_stay_hidden(self):
        self.assertEqual(get_suggestions("#git atualização", self.commands), [])


class StateTests(unittest.TestCase):
    def test_round_trip_uses_atomic_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            with patch("core.state.STATE_FILE", state_file):
                save_window_state(10, 20, 430, 240)
                self.assertEqual(
                    load_window_state(),
                    {"x": 10, "y": 20, "width": 430, "height": 240},
                )
                self.assertFalse(Path(f"{state_file}.tmp").exists())

    def test_invalid_json_returns_default(self):
        with tempfile.TemporaryDirectory() as directory:
            state_file = Path(directory) / "state.json"
            state_file.write_text("{inválido", encoding="utf-8")
            with patch("core.state.STATE_FILE", state_file):
                self.assertEqual(load_window_state(), DEFAULT_STATE)


if __name__ == "__main__":
    unittest.main()
