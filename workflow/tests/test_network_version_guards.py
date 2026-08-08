import pathlib
import unittest

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar


WORKFLOW_ROOT = pathlib.Path(__file__).resolve().parents[1]

PLATFORMS = {
    "ios": {
        "role": "ios_firmware",
        "observed_task": "Determine IOS compliance",
        "facts_task": "Set IOS compliance facts",
        "upgrade_task": "Upgrade IOS (guarded)",
        "observed_fact": "_ios_observed_version",
        "facts_var": "_ios_facts",
    },
    "asa": {
        "role": "asa_firmware",
        "observed_task": "Determine ASA compliance",
        "facts_task": "Set ASA compliance facts",
        "upgrade_task": "Upgrade ASA (guarded)",
        "observed_fact": "_asa_observed_version",
        "facts_var": "_asa_facts",
    },
    "nxos": {
        "role": "nxos_firmware",
        "observed_task": "Determine NX-OS compliance",
        "facts_task": "Set NX-OS compliance facts",
        "upgrade_task": "Upgrade NX-OS (guarded)",
        "observed_fact": "_nxos_observed_version",
        "facts_var": "_nx_facts",
    },
    "iosxr": {
        "role": "iosxr_firmware",
        "observed_task": "Determine IOS-XR compliance",
        "facts_task": "Set IOS-XR compliance facts",
        "upgrade_task": "Upgrade IOS-XR (guarded)",
        "observed_fact": "_iosxr_observed_version",
        "facts_var": "_xr_facts",
    },
}


def load_tasks(role):
    path = WORKFLOW_ROOT / "roles" / role / "tasks" / "main.yml"
    return yaml.safe_load(path.read_text())


def load_task(role, name):
    for task in load_tasks(role):
        if task.get("name") == name:
            return task
    raise AssertionError(f"Task {name!r} not found in {role}")


def render(value, variables):
    templar = Templar(loader=DataLoader(), variables=variables)
    return templar.template(value)


class NetworkVersionGuardTest(unittest.TestCase):
    def test_empty_or_missing_versions_are_unknown_and_not_safe_to_apply(self):
        for platform, meta in PLATFORMS.items():
            with self.subTest(platform=platform):
                variables = {
                    "golden_versions": {platform: {"version": "17.9"}},
                    meta["facts_var"]: {"ansible_facts": {"ansible_net_version": ""}},
                }

                observed_task = load_task(meta["role"], meta["observed_task"])
                observed_expr = observed_task["ansible.builtin.set_fact"][meta["observed_fact"]]
                observed = render(observed_expr, variables)
                self.assertEqual(observed, "")

                variables[meta["observed_fact"]] = observed
                facts = load_task(meta["role"], meta["facts_task"])["ansible.builtin.set_fact"]
                self.assertFalse(render(facts["firmware_version_known"], variables))
                self.assertEqual(render(facts["running_version"], variables), "unknown")
                self.assertFalse(render(facts["compliant"], variables))

                variables[meta["facts_var"]] = {"ansible_facts": {}}
                observed = render(observed_expr, variables)
                self.assertEqual(observed, "")

    def test_known_versions_can_be_marked_compliant(self):
        for platform, meta in PLATFORMS.items():
            with self.subTest(platform=platform):
                variables = {
                    "golden_versions": {platform: {"version": "17.9"}},
                    meta["facts_var"]: {"ansible_facts": {"ansible_net_version": "17.9"}},
                }

                observed_task = load_task(meta["role"], meta["observed_task"])
                observed_expr = observed_task["ansible.builtin.set_fact"][meta["observed_fact"]]
                variables[meta["observed_fact"]] = render(observed_expr, variables)

                facts = load_task(meta["role"], meta["facts_task"])["ansible.builtin.set_fact"]
                self.assertTrue(render(facts["firmware_version_known"], variables))
                self.assertEqual(render(facts["running_version"], variables), "17.9")
                self.assertTrue(render(facts["compliant"], variables))

    def test_guarded_upgrade_requires_known_version(self):
        for platform, meta in PLATFORMS.items():
            with self.subTest(platform=platform):
                upgrade_task = load_task(meta["role"], meta["upgrade_task"])
                self.assertIn("firmware_version_known | bool", upgrade_task["when"])


if __name__ == "__main__":
    unittest.main()
