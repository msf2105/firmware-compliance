from pathlib import Path
import unittest

import yaml


ROLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "roles"
    / "dnac_firmware"
    / "tasks"
    / "main.yml"
)


def _module_args(task, module_name):
    return task.get(module_name)


class DnacImageUrlGuardTest(unittest.TestCase):
    def test_apply_requires_import_url_before_recording_action(self):
        tasks = yaml.safe_load(ROLE_PATH.read_text())
        guarded_block = next(
            task
            for task in tasks
            if task.get("name") == "Import golden image + tag golden (guarded)"
        )["block"]

        guard_index = next(
            index
            for index, task in enumerate(guarded_block)
            if _module_args(task, "ansible.builtin.assert") is not None
        )
        import_index = next(
            index
            for index, task in enumerate(guarded_block)
            if _module_args(task, "cisco.catalystcenter.swim_image_url_import")
            is not None
        )
        action_index = next(
            index
            for index, task in enumerate(guarded_block)
            if task.get("name") == "Record upgrade action"
        )

        self.assertLess(guard_index, import_index)
        self.assertLess(import_index, action_index)

        guard = _module_args(guarded_block[guard_index], "ansible.builtin.assert")
        self.assertIn("image_url", " ".join(guard["that"]))
        self.assertIn("refusing to record", guard["fail_msg"])

        import_task = guarded_block[import_index]
        self.assertNotIn("when", import_task)
        source_url = import_task["cisco.catalystcenter.swim_image_url_import"][
            "payload"
        ][0]["sourceURL"]
        self.assertIn("| trim", source_url)


if __name__ == "__main__":
    unittest.main()
