from pathlib import Path
import unittest

import yaml


WORKFLOW_PATH = Path(__file__).resolve().parents[1]
SITE_PATH = WORKFLOW_PATH / "playbooks" / "site.yml"
SERVICENOW_ROLE_PATH = WORKFLOW_PATH / "roles" / "servicenow" / "tasks" / "main.yml"


def _flatten_tasks(tasks):
    for task in tasks:
        yield task
        for nested in task.get("block", []):
            yield nested


def _when_lines(task):
    when = task.get("when", [])
    if isinstance(when, str):
        return [when]
    return when


def _task_named(tasks, name):
    return next(task for task in _flatten_tasks(tasks) if task.get("name") == name)


class ServiceNowGatingStaticTest(unittest.TestCase):
    def test_service_now_mutations_require_run_opened_change(self):
        plays = yaml.safe_load(SITE_PATH.read_text())
        site_tasks = [task for play in plays for task in play.get("tasks", [])]
        role_tasks = yaml.safe_load(SERVICENOW_ROLE_PATH.read_text())

        publish_task = _task_named(site_tasks, "Publish change identifiers to all device hosts")
        self.assertIn("_snow_change_opened_sys_id", publish_task["ansible.builtin.add_host"])
        self.assertIn("_snow_change_opened_sys_id is defined", _when_lines(publish_task))
        self.assertIn("snow_change_sys_id == _snow_change_opened_sys_id", _when_lines(publish_task))

        open_register = _task_named(role_tasks, "Register change identifiers for downstream tasks")
        self.assertEqual(
            "{{ _snow_cr.record.sys_id }}",
            open_register["ansible.builtin.set_fact"]["_snow_change_opened_sys_id"],
        )

        for name in (
            "Add per-device result work note to change (apply mode)",
            "Close ServiceNow change (apply mode)",
            "Add work note to change",
            "Close change request",
        ):
            with self.subTest(task=name):
                when = _when_lines(_task_named(site_tasks + role_tasks, name))
                self.assertIn("(apply_updates | default(false)) | bool", when)
                self.assertIn("snow_change_sys_id is defined", when)
                self.assertIn("_snow_change_opened_sys_id is defined", when)
                self.assertIn("snow_change_sys_id == _snow_change_opened_sys_id", when)


if __name__ == "__main__":
    unittest.main()
