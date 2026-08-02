from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE_TASKS = ROOT / "workflow" / "roles" / "iosxr_firmware" / "tasks" / "main.yml"
GOLDEN_VERSIONS = ROOT / "workflow" / "vars" / "golden_versions.yml"


def task_named(tasks, name):
    for index, task in enumerate(tasks):
        if task.get("name") == name:
            return index, task
    raise AssertionError(f"Task {name!r} not found")


def command_strings(task):
    commands = task["cisco.iosxr.iosxr_command"]["commands"]
    return [
        command.get("command", command) if isinstance(command, dict) else command
        for command in commands
    ]


class IOSXRInstallWorkflowTests(unittest.TestCase):
    def setUp(self):
        tasks = yaml.safe_load(ROLE_TASKS.read_text())
        self.golden = yaml.safe_load(GOLDEN_VERSIONS.read_text())["golden_versions"]
        self.upgrade_task = next(task for task in tasks if task.get("name") == "Upgrade IOS-XR (guarded)")
        self.block = self.upgrade_task["block"]

    def test_shipped_iosxr_iso_uses_install_replace(self):
        self.assertTrue(self.golden["iosxr"]["image_file"].endswith(".iso"))

        validate_index, validate_task = task_named(
            self.block, "Validate IOS-XR ISO replacement has reboot approval"
        )
        replace_index, replace_task = task_named(self.block, "install replace golden ISO")
        record_index, _ = task_named(self.block, "Record upgrade action")

        self.assertLess(validate_index, replace_index)
        self.assertLess(replace_index, record_index)
        self.assertIn("reboot_after_upgrade | bool", validate_task["ansible.builtin.assert"]["that"])
        self.assertIn(
            "install replace /harddisk:/{{ golden_versions.iosxr.image_file }} noprompt",
            command_strings(replace_task),
        )
        self.assertIn("reboot_after_upgrade | bool", replace_task["when"])
        self.assertTrue(any("regex_search('\\.iso$')" in condition for condition in replace_task["when"]))

    def test_iosxr_iso_is_not_sent_through_package_add_activate(self):
        _, add_task = task_named(self.block, "install add package source")
        _, activate_task = task_named(self.block, "install activate golden version")

        self.assertIn(
            "install add source /harddisk:/ {{ golden_versions.iosxr.image_file }}",
            command_strings(add_task),
        )
        for task in (add_task, activate_task):
            task_when = task["when"] if isinstance(task["when"], list) else [task["when"]]
            self.assertTrue(any("regex_search('\\.iso$')) is none" in condition for condition in task_when))


if __name__ == "__main__":
    unittest.main()
