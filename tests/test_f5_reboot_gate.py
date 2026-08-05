from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
F5_TASKS = REPO_ROOT / "workflow" / "roles" / "f5_firmware" / "tasks" / "main.yml"


def extract_task_block(task_name):
    lines = F5_TASKS.read_text(encoding="utf-8").splitlines()
    marker = f"- name: {task_name}"

    for index, line in enumerate(lines):
        if line.strip() == marker:
            indent = len(line) - len(line.lstrip())
            end = len(lines)
            for next_index in range(index + 1, len(lines)):
                next_line = lines[next_index]
                if (
                    next_line.strip().startswith("- name:")
                    and len(next_line) - len(next_line.lstrip()) == indent
                ):
                    end = next_index
                    break
            return "\n".join(lines[index:end])

    raise AssertionError(f"task not found: {task_name}")


class F5RebootGateTests(unittest.TestCase):
    def test_bigip_install_is_gated_by_reboot_activation(self):
        install_task = extract_task_block("Install image and activate target volume (guarded)")

        self.assertIn("f5networks.f5_modules.bigip_software_install:", install_task)
        self.assertIn("state: activated", install_task)
        self.assertIn("when: reboot_after_upgrade | bool", install_task)

    def test_deferred_path_does_not_use_installed_state(self):
        role_text = F5_TASKS.read_text(encoding="utf-8")

        self.assertNotIn("state={{ 'activated' if reboot_after_upgrade", role_text)
        self.assertIn("install/activation deferred: reboot_after_upgrade=false", role_text)


if __name__ == "__main__":
    unittest.main()
