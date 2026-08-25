import unittest
from unittest.mock import Mock, patch

from core.network_volumes import (
    _mount_responds,
    get_network_status,
    select_network_volumes,
)


class NetworkVolumeTests(unittest.TestCase):
    def test_selects_one_volume_by_name_or_alias(self):
        self.assertEqual(select_network_volumes("NAS")[0]["key"], "NAS")
        self.assertEqual(select_network_volumes("arquivos")[0]["key"], "NAS")
        self.assertEqual(select_network_volumes("mimaki")[0]["key"], "MIM")

    def test_empty_target_selects_all_volumes(self):
        self.assertEqual(len(select_network_volumes()), 3)
        self.assertEqual(select_network_volumes("inexistente"), ())

    @patch("core.network_volumes._mount_responds", return_value=True)
    @patch("core.network_volumes._mounted_smb_paths")
    def test_network_status_requires_mounted_accessible_volume(
        self,
        mounted_paths,
        mount_responds,
    ):
        mounted_paths.return_value = {
            "/Volumes/Pasta Mimaki",
            "/Volumes/Trabalhos PFI",
            "/Volumes/Trabalhos",
        }

        status = get_network_status()

        self.assertEqual(status, {"MIM": True, "PFI": True, "NAS": True})
        self.assertEqual(mount_responds.call_count, 3)

    @patch("core.network_volumes._mount_responds", return_value=True)
    @patch("core.network_volumes._mounted_smb_paths")
    def test_unmounted_volume_is_offline_even_when_server_exists(
        self,
        mounted_paths,
        mount_responds,
    ):
        mounted_paths.return_value = {"/Volumes/Trabalhos"}

        status = get_network_status()

        self.assertEqual(status, {"MIM": False, "PFI": False, "NAS": True})
        mount_responds.assert_called_once_with("/Volumes/Trabalhos", 1.2)

    @patch("core.network_volumes.subprocess.run")
    def test_access_check_reads_directory_instead_of_only_cached_metadata(
        self,
        run,
    ):
        run.return_value = Mock(returncode=0)

        self.assertTrue(_mount_responds("/Volumes/Trabalhos", 1.2))

        command = run.call_args.args[0]
        self.assertEqual(command[0], "/usr/bin/find")
        self.assertEqual(command[1], "/Volumes/Trabalhos")
        self.assertIn("-quit", command)


if __name__ == "__main__":
    unittest.main()
