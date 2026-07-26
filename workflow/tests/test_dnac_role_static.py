from pathlib import Path
import unittest

import yaml


ROLE_PATH = Path(__file__).resolve().parents[1] / "roles" / "dnac_firmware" / "tasks" / "main.yml"


def _flatten_tasks(tasks):
    for task in tasks:
        yield task
        for nested in task.get("block", []):
            yield nested


def _module_args(task, module_name):
    return task.get(module_name)


class DnacRoleStaticTest(unittest.TestCase):
    def test_dnac_role_uses_supported_catalystcenter_module_contract(self):
        tasks = list(_flatten_tasks(yaml.safe_load(ROLE_PATH.read_text())))

        query = next(
            task
            for task in tasks
            if _module_args(task, "cisco.catalystcenter.swim_image_details_info") is not None
        )
        query_args = _module_args(query, "cisco.catalystcenter.swim_image_details_info")
        self.assertIn("catalystcenter_host", query_args)
        self.assertIn("catalystcenter_username", query_args)
        self.assertIn("catalystcenter_password", query_args)
        self.assertIn("catalystcenter_verify", query_args)
        self.assertFalse(any(key.startswith("dnac_") for key in query_args))

        golden_presence = next(
            task
            for task in tasks
            if task.get("name") == "Determine Catalyst Center golden-image presence"
        )
        set_fact = golden_presence["ansible.builtin.set_fact"]
        self.assertIn("catalystcenter_response.response", set_fact["running_version"])
        self.assertIn("catalystcenter_response.response", set_fact["compliant"])

        import_task = next(
            task
            for task in tasks
            if _module_args(task, "cisco.catalystcenter.swim_import_via_url") is not None
        )
        import_args = _module_args(import_task, "cisco.catalystcenter.swim_import_via_url")
        self.assertIn("catalystcenter_host", import_args)
        self.assertIn("catalystcenter_username", import_args)
        self.assertIn("catalystcenter_password", import_args)
        self.assertIn("catalystcenter_verify", import_args)
        self.assertFalse(any(key.startswith("dnac_") for key in import_args))

        self.assertTrue(
            all("cisco.catalystcenter.swim_image_url_import" not in task for task in tasks)
        )


if __name__ == "__main__":
    unittest.main()
