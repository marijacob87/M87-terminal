import unittest
from unittest.mock import Mock, patch

from core.command_preferences import normalize_code_list, order_commands
from core.startup import set_start_with_system


class PreferencesTest(unittest.TestCase):
    def test_normalizes_qsettings_code_values(self):
        self.assertEqual(normalize_code_list("pdf"), ["PDF"])
        self.assertEqual(
            normalize_code_list([" pdf ", "mon", ""]),
            ["PDF", "MON"],
        )
        self.assertEqual(normalize_code_list(None), [])

    def test_saved_command_order_is_stable_and_keeps_new_commands(self):
        commands = [
            {"code": "BM"},
            {"code": "MR"},
            {"code": "NEW"},
        ]
        self.assertEqual(
            [item["code"] for item in order_commands(commands, ["MR", "BM"])],
            ["MR", "BM", "NEW"],
        )

    def test_empty_saved_order_preserves_json_order(self):
        commands = [{"code": "BM"}, {"code": "MR"}]
        self.assertEqual(order_commands(commands, []), commands)

    @patch("core.startup.APP_PATH")
    @patch("core.startup.subprocess.run")
    def test_login_item_can_start_hidden(self, run, app_path):
        app_path.exists.return_value = True
        run.return_value = Mock(returncode=0, stderr="")
        success, _message = set_start_with_system(True, hidden=True)
        self.assertTrue(success)
        create_script = run.call_args_list[-1].args[0][-1]
        self.assertIn("hidden:true", create_script)


if __name__ == "__main__":
    unittest.main()
