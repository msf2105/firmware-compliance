from pathlib import Path
import unittest

import yaml


ROLE_TASKS = Path(__file__).resolve().parents[1] / "workflow" / "roles" / "iosxr_firmware" / "tasks" / "main.yml"


def task_named(tasks, name):
    for index, task in enumerate(tasks):
        if task.get("name") == name:
            return index, task
    raise AssertionError(f"Task {name!r} not found")


def command_strings(task):
    commands = task["cisco.iosxr.iosxr_command"]["commands"]
    return [command.get("command", command) if isinstance(command, dict) else command for command in commands]


class IOSXRInstallWorkflowTests(unittest.TestCase):
    def test_activate_is_committed_before_reporting_success(self):
        tasks = yaml.safe_load(ROLE_TASKS.read_text())

        upgrade_task = next(task for task in tasks if task.get("name") == "Upgrade IOS-XR (guarded)")
        block = upgrade_task["block"]

        activate_index, activate_task = task_named(block, "install activate golden version")
        commit_index, commit_task = task_named(block, "install commit activated version")
        record_index, record_task = task_named(block, "Record upgrade action")

        self.assertLess(activate_index, commit_index)
        self.assertLess(commit_index, record_index)
        self.assertEqual(commit_task.get("when"), activate_task.get("when"))
        self.assertIn("install commit", command_strings(commit_task))
        self.assertIn("+ activate + commit", record_task["ansible.builtin.set_fact"]["upgrade_action"])


if __name__ == "__main__":
    unittest.main()
