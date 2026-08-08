import pathlib
import unittest

import yaml


ROLE_TASKS = (
    pathlib.Path(__file__).resolve().parents[1]
    / "roles"
    / "preflight"
    / "tasks"
    / "main.yml"
)


def load_tasks():
    return yaml.safe_load(ROLE_TASKS.read_text())


def load_task(name):
    for task in load_tasks():
        if task.get("name") == name:
            return task
    raise AssertionError(f"Task {name!r} not found")


class PreflightWindowGuardTest(unittest.TestCase):
    def test_rejects_direct_window_override(self):
        task = load_task("Reject maintenance-window override")

        self.assertEqual(task["ansible.builtin.assert"]["that"], ["in_window is not defined"])
        self.assertIn("Do not pass in_window directly", task["ansible.builtin.assert"]["fail_msg"])

    def test_apply_clearance_uses_computed_internal_window(self):
        task = load_task("Compute apply clearance")
        expression = task["ansible.builtin.set_fact"]["apply_cleared"]

        self.assertIn("_preflight_in_window | bool", expression)
        self.assertNotIn("and (in_window | bool)", expression)

    def test_mode_announcement_uses_computed_internal_window(self):
        task = load_task("Announce mode")
        message = task["ansible.builtin.debug"]["msg"]

        self.assertIn("in_window={{ _preflight_in_window }}", message)
        self.assertNotIn("in_window={{ in_window }}", message)


if __name__ == "__main__":
    unittest.main()
