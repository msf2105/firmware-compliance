from pathlib import Path
import unittest

import yaml


ROLE_TASKS = Path(__file__).parent / "workflow" / "roles" / "nxos_firmware" / "tasks" / "main.yml"


class NxosFirmwareRoleTest(unittest.TestCase):
    def test_nxos_install_block_requires_reboot_approval(self):
        tasks = yaml.safe_load(ROLE_TASKS.read_text())
        install_block = next(task for task in tasks if task.get("name") == "Upgrade NX-OS (guarded)")

        self.assertIn("reboot_after_upgrade | bool", install_block["when"])

        action_task = next(
            task for task in install_block["block"] if task.get("name") == "Record upgrade action"
        )
        action_message = action_task["ansible.builtin.set_fact"]["upgrade_action"]
        self.assertNotIn("deferred", action_message)
        self.assertNotIn("reboot_after_upgrade=false", action_message)


if __name__ == "__main__":
    unittest.main()
