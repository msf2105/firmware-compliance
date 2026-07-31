from pathlib import Path
import unittest

import yaml


ROLE_PATH = Path(__file__).resolve().parents[1] / "roles" / "panos_firmware" / "tasks" / "main.yml"


def _task_named(tasks, name):
    return next(task for task in tasks if task.get("name") == name)


class PanosFirmwareRoleStaticTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = yaml.safe_load(ROLE_PATH.read_text())

    def test_unknown_panos_version_fails_closed_before_upgrade(self):
        normalize = _task_named(self.tasks, "Normalize PAN-OS running version")
        running_version = normalize["ansible.builtin.set_fact"]["running_version"]
        self.assertIn("default('unknown')", running_version)
        self.assertIn(", true", running_version)
        self.assertIn("string | trim", running_version)

        compliance = _task_named(self.tasks, "Determine PAN-OS compliance")
        compliant = compliance["ansible.builtin.set_fact"]["compliant"]
        self.assertIn("running_version != 'unknown'", compliant)

        upgrade = _task_named(self.tasks, "Upgrade PAN-OS (guarded)")
        self.assertIn("running_version != 'unknown'", upgrade["when"])


if __name__ == "__main__":
    unittest.main()
