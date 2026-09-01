import unittest
from unittest.mock import patch

from core.anydesk import (
    _open_machine_url,
    _select_opened_session,
    get_anydesk_suggestions,
    open_anydesk_machine,
)


class AnyDeskTests(unittest.TestCase):
    @patch("core.anydesk.threading.Thread")
    @patch("core.anydesk.subprocess.run")
    @patch("core.anydesk.os.path.isdir", return_value=True)
    def test_sends_id_after_anydesk_is_ready(self, _is_dir, run, thread):
        run.return_value.returncode = 0
        self.assertTrue(open_anydesk_machine("1657421817"))

        self.assertEqual(
            run.call_args.args[0],
            ["open", "-g", "-a", "AnyDesk"],
        )
        self.assertEqual(
            thread.call_args.kwargs["args"],
            ("1657421817", 0.8, False),
        )
        thread.return_value.start.assert_called_once()

    @patch("core.anydesk.subprocess.Popen")
    def test_rejects_invalid_machine_id(self, popen):
        self.assertFalse(open_anydesk_machine('1" & keystroke "w"'))
        popen.assert_not_called()

    def test_prinect_connects_directly_to_windows_console(self):
        prinect = next(
            item
            for item in get_anydesk_suggestions("prinect")
            if item["type"] == "anydesk_machine"
        )
        self.assertEqual(prinect["id"], "317203682")
        self.assertTrue(prinect["console"])

    @patch("core.anydesk.time.sleep")
    @patch("core.anydesk._select_opened_session")
    @patch("core.anydesk.subprocess.run")
    @patch("core.anydesk.subprocess.Popen")
    def test_selects_session_tab_after_opening_url(
        self,
        popen,
        _run,
        select_session,
        sleep,
    ):
        _open_machine_url("1657421817", 0.8)

        self.assertEqual(
            popen.call_args.args[0],
            [
                "open",
                "-b",
                "com.philandro.anydesk",
                "anydesk:1657421817",
            ],
        )
        self.assertEqual(sleep.call_args_list[0].args, (0.8,))
        self.assertEqual(sleep.call_args_list[1].args, (0.45,))
        select_session.assert_called_once_with(False)

    @patch("core.anydesk._accessibility_is_trusted", return_value=True)
    @patch("core.anydesk.subprocess.run")
    def test_uses_previous_tab_shortcut_and_console_confirmation(
        self,
        run,
        _trusted,
    ):
        run.return_value.returncode = 0
        _select_opened_session(confirm_console=True)

        command = run.call_args.args[0]
        self.assertIn('keystroke "[" using {command down, shift down}', command[2])
        self.assertIn('buttonName is "Conectar"', command[2])
        self.assertEqual(command[-1], "true")

    @patch("core.anydesk._accessibility_is_trusted", return_value=False)
    @patch("core.anydesk.subprocess.run")
    def test_does_not_send_shortcuts_without_accessibility(self, run, _trusted):
        self.assertFalse(_select_opened_session())
        run.assert_not_called()
