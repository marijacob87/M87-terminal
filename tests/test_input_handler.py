import unittest
import plistlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.restart import restart_command, restart_m87_process


ROOT = Path(__file__).resolve().parents[1]


class InputHandlerTests(unittest.TestCase):
    def test_legacy_zip_updater_is_removed(self):
        self.assertFalse((ROOT / "core" / "update_manager.py").exists())
        self.assertFalse((ROOT / "core" / "project_zip.py").exists())
        self.assertFalse((ROOT / "000_LEIA_PRIMEIRO_M87.md").exists())

        input_source = (ROOT / "core" / "input_handler.py").read_text(
            encoding="utf-8"
        )
        context_source = (ROOT / "ui" / "pdf_context.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("#zip", input_source.casefold())
        self.assertNotIn(".zip", context_source.casefold())
        self.assertNotIn("handle_update_drop", context_source)

    def test_double_hash_uses_the_application_restart_path(self):
        source = (ROOT / "core" / "input_handler.py").read_text(encoding="utf-8")
        branch = source.split('if text == "##":', 1)[1].split(
            "# =========================", 1
        )[0]

        self.assertIn("app.restart_app()", branch)
        self.assertNotIn("QProcess", branch)
        self.assertNotIn("app.close()", branch)

    def test_restart_uses_explicit_main_instead_of_sys_argv(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "main.py").touch()

            executable, arguments = restart_command("/python", root)

            self.assertEqual(executable, "/python")
            self.assertEqual(
                arguments,
                ["/python", str((root / "main.py").resolve())],
            )

    def test_restart_prefers_valid_canonical_application(self):
        with TemporaryDirectory() as directory:
            app = Path(directory) / "M87 Terminal.app"
            executable = app / "Contents" / "MacOS" / "M87 Terminal"
            executable.parent.mkdir(parents=True)
            executable.touch()
            info = {
                "CFBundleIdentifier": "com.m87tools.terminal",
                "CFBundleExecutable": "M87 Terminal",
                "M87ProjectRoot": str(ROOT),
            }
            with (app / "Contents" / "Info.plist").open("wb") as stream:
                plistlib.dump(info, stream)
            with patch("core.restart.CANONICAL_APP", app):
                command, arguments = restart_command()

            self.assertEqual(command, str(executable))
            self.assertEqual(arguments, [str(executable)])

    def test_restart_opens_bundle_through_macos_launch_services(self):
        with patch("core.restart._canonical_launcher", return_value=Path("/app")), \
                patch("core.restart.os.getpid", return_value=4321), \
                patch("core.restart.subprocess.Popen") as popen:
            restart_m87_process()

        arguments = popen.call_args.args[0]
        self.assertEqual(
            arguments,
            [
                "/bin/sh", "-c",
                'while kill -0 "$1" 2>/dev/null; do sleep 0.05; done; '
                'exec /usr/bin/open -b "$2"',
                "m87-restart", "4321", "com.m87tools.terminal",
            ],
        )

    def test_restart_forces_current_process_to_exit_after_closing_windows(self):
        source = (ROOT / "ui" / "command_controller.py").read_text(encoding="utf-8")
        method = source.split("def restart_app(self):", 1)[1].split(
            "def rebuild_command_grid", 1
        )[0]

        self.assertIn("app.closeAllWindows()", method)
        self.assertIn("os._exit(0)", method)

    def test_enter_intercepts_double_hash_before_suggestions(self):
        source = (ROOT / "ui" / "command_controller.py").read_text(encoding="utf-8")
        execute_from_input = source.split("def execute_from_input(self):", 1)[1]
        before_suggestions = execute_from_input.split(
            "if self.execute_selected_suggestion():", 1
        )[0]

        self.assertIn('if text == "##":', before_suggestions)

    def test_tools_drop_does_not_depend_on_global_cursor_position(self):
        source = (ROOT / "ui" / "tools_dialog.py").read_text(encoding="utf-8")
        event_filter = source.split("def eventFilter(self, watched, event):", 1)[1]
        event_filter = event_filter.split("def _hide_overlay_if_cursor_left", 1)[0]

        self.assertIn("self._event_belongs_to_tools(watched)", event_filter)
        self.assertNotIn("self._cursor_is_inside()", event_filter)
        drop_gate = source.split("def _drop_is_enabled(self):", 1)[1]
        drop_gate = drop_gate.split("def _load_dropped_pdfs", 1)[0]
        self.assertIn("self.tabs.currentIndex() < self.tabs.count()", drop_gate)


if __name__ == "__main__":
    unittest.main()
