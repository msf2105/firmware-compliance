import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class FirmwareBatchSafetyTest(unittest.TestCase):
    def test_device_play_uses_bounded_batch_size(self):
        playbook = (REPO_ROOT / "workflow/playbooks/site.yml").read_text()

        device_play_match = re.search(
            r"- name: Firmware compliance across all platforms(?P<body>.*?)(?=\n# ---------- Play 3:)",
            playbook,
            re.DOTALL,
        )

        self.assertIsNotNone(device_play_match)
        self.assertIn(
            'serial: "{{ firmware_batch_size | default(1) | int }}"',
            device_play_match.group("body"),
        )

    def test_default_batch_size_is_one_device(self):
        golden_vars = (REPO_ROOT / "workflow/vars/golden_versions.yml").read_text()

        batch_size_match = re.search(r"^firmware_batch_size:\s*(\d+)\b", golden_vars, re.MULTILINE)

        self.assertIsNotNone(batch_size_match)
        self.assertEqual("1", batch_size_match.group(1))


if __name__ == "__main__":
    unittest.main()
