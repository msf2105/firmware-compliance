from pathlib import Path

import yaml


ROLE_TASKS = Path(__file__).resolve().parents[1] / "roles" / "aci_firmware" / "tasks" / "main.yml"
TASK_NAME = "Set ACI controller firmware policy (guarded)"


def main():
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    guarded_task = next((task for task in tasks if task.get("name") == TASK_NAME), None)

    if guarded_task is None:
        raise AssertionError(f"Could not find task: {TASK_NAME}")

    conditions = guarded_task.get("when", [])
    if isinstance(conditions, str):
        conditions = [conditions]

    required_conditions = {
        "not (compliant | bool)",
        "apply_cleared | bool",
        "reboot_after_upgrade | bool",
    }
    missing = required_conditions.difference(conditions)
    if missing:
        raise AssertionError(f"{TASK_NAME} is missing guard(s): {sorted(missing)}")


if __name__ == "__main__":
    main()
