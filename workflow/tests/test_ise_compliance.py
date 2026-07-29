import pathlib
import unittest

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar


ROLE_TASKS = pathlib.Path(__file__).resolve().parents[1] / "roles" / "ise_firmware" / "tasks" / "main.yml"


def load_task(name):
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    for task in tasks:
        if task.get("name") == name:
            return task
    raise AssertionError(f"task not found: {name}")


def render(value, variables):
    templar = Templar(loader=DataLoader(), variables=variables)
    return templar.template(value)


class IseComplianceTest(unittest.TestCase):
    def test_uses_version_and_patch_modules(self):
        tasks = yaml.safe_load(ROLE_TASKS.read_text())
        version_task = load_task("Query ISE version info (best effort)")
        patch_task = load_task("Query ISE installed patch info (best effort)")

        self.assertIn("cisco.ise.mnt_version_info", version_task)
        self.assertIn("cisco.ise.patch_info", patch_task)
        self.assertFalse(
            any("cisco.ise.backup_last_status_info" in task for task in tasks),
            "ISE compliance must not read backup status as firmware version",
        )

    def test_matching_version_and_patch_is_compliant(self):
        variables = {
            "golden_versions": {"ise": {"version": "3.3.0.430", "patch": "10"}},
            "_ise_ver": {"ise_response": {"version": "3.3.0.430"}},
            "_ise_patch": {
                "ise_response": {
                    "patchVersion": [
                        {"patchNumber": 3},
                        {"patchNumber": 10},
                    ]
                }
            },
        }

        observed_task = load_task("Determine ISE observed version and patch")
        variables["_ise_running_version"] = render(
            observed_task["ansible.builtin.set_fact"]["_ise_running_version"], variables
        )
        variables["_ise_patch_numbers"] = render(
            observed_task["ansible.builtin.set_fact"]["_ise_patch_numbers"], variables
        )

        compliance_task = load_task("Determine ISE compliance target (audit-only)")
        variables["running_ise_patch"] = render(
            compliance_task["ansible.builtin.set_fact"]["running_ise_patch"], variables
        )
        variables["running_version"] = render(
            compliance_task["ansible.builtin.set_fact"]["running_version"], variables
        )
        compliant = render(compliance_task["ansible.builtin.set_fact"]["compliant"], variables)

        self.assertEqual(variables["running_ise_patch"], "10")
        self.assertEqual(variables["running_version"], "3.3.0.430 patch 10")
        self.assertTrue(compliant)

    def test_missing_patch_response_is_not_compliant(self):
        variables = {
            "golden_versions": {"ise": {"version": "3.3.0.430", "patch": "3"}},
            "_ise_ver": {"ise_response": {"version": "3.3.0.430"}},
            "_ise_patch": {"failed": True},
        }

        observed_task = load_task("Determine ISE observed version and patch")
        variables["_ise_running_version"] = render(
            observed_task["ansible.builtin.set_fact"]["_ise_running_version"], variables
        )
        variables["_ise_patch_numbers"] = render(
            observed_task["ansible.builtin.set_fact"]["_ise_patch_numbers"], variables
        )

        compliance_task = load_task("Determine ISE compliance target (audit-only)")
        variables["running_ise_patch"] = render(
            compliance_task["ansible.builtin.set_fact"]["running_ise_patch"], variables
        )
        compliant = render(compliance_task["ansible.builtin.set_fact"]["compliant"], variables)

        self.assertEqual(variables["running_ise_patch"], "unknown")
        self.assertFalse(compliant)


if __name__ == "__main__":
    unittest.main()
