from pathlib import Path

import yaml


ROLE_TASKS = Path(__file__).resolve().parents[1] / "roles" / "aci_firmware" / "tasks" / "main.yml"
ASSERT_TASK = "Require ACI controller firmware version data"
POLICY_TASK = "Set ACI controller firmware policy (guarded)"


def main():
    tasks = yaml.safe_load(ROLE_TASKS.read_text())
    task_names = [task.get("name") for task in tasks]

    try:
        assert_index = task_names.index(ASSERT_TASK)
        policy_index = task_names.index(POLICY_TASK)
    except ValueError as exc:
        raise AssertionError(f"Missing expected ACI task: {exc}") from exc

    if assert_index > policy_index:
        raise AssertionError(f"{ASSERT_TASK!r} must run before {POLICY_TASK!r}")

    assert_task = tasks[assert_index]
    conditions = assert_task.get("ansible.builtin.assert", {}).get("that", [])
    if "_aci_controller_versions | length > 0" not in conditions:
        raise AssertionError(f"{ASSERT_TASK!r} must fail closed when no controller versions are parsed")

    determine_task = next(task for task in tasks if task.get("name") == "Determine ACI compliance")
    running_version = determine_task["ansible.builtin.set_fact"].get("running_version", "")
    if "_aci_controller_versions | first" not in running_version:
        raise AssertionError("ACI compliance must use the validated controller version list")


if __name__ == "__main__":
    main()
