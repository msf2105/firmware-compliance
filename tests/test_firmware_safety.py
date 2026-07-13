import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_role(role_name):
    return (ROOT / "workflow" / "roles" / role_name / "tasks" / "main.yml").read_text()


class FirmwareSafetyTests(unittest.TestCase):
    def test_ios_verifies_image_before_boot_change(self):
        text = read_role("ios_firmware")

        verify_idx = text.index("Verify IOS golden image is present")
        fail_idx = text.index("Fail when IOS golden image is missing")
        boot_idx = text.index("Set boot system to golden image")

        self.assertLess(verify_idx, fail_idx)
        self.assertLess(fail_idx, boot_idx)
        self.assertIn("cisco.ios.ios_command", text[verify_idx:fail_idx])
        self.assertIn("_ios_target_image_path", text[verify_idx:boot_idx])
        self.assertIn("Refusing to change boot system", text[fail_idx:boot_idx])
        self.assertIn("no such|error|not found|invalid", text[fail_idx:boot_idx])

    def test_asa_verifies_image_before_boot_change(self):
        text = read_role("asa_firmware")

        verify_idx = text.index("Verify ASA golden image is present")
        fail_idx = text.index("Fail when ASA golden image is missing")
        boot_idx = text.index("Set boot image to golden")

        self.assertLess(verify_idx, fail_idx)
        self.assertLess(fail_idx, boot_idx)
        self.assertIn("cisco.asa.asa_command", text[verify_idx:fail_idx])
        self.assertIn("_asa_target_image_path", text[verify_idx:boot_idx])
        self.assertIn("Refusing to change boot system", text[fail_idx:boot_idx])
        self.assertIn("no such|error|not found|invalid", text[fail_idx:boot_idx])

    def test_panos_install_is_gated_with_restart(self):
        text = read_role("panos_firmware")
        panos_software_idx = text.index("paloaltonetworks.panos.panos_software")
        record_idx = text.index("Record upgrade action")
        task_text = text[panos_software_idx:record_idx]

        self.assertIn("download: true", task_text)
        self.assertIn('install: "{{ reboot_after_upgrade | bool }}"', task_text)
        self.assertIn('restart: "{{ reboot_after_upgrade | bool }}"', task_text)
        self.assertNotIn("install: true", task_text)


if __name__ == "__main__":
    unittest.main()
