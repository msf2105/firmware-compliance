from pathlib import Path

import yaml


ROLE_PATH = Path(__file__).resolve().parents[1] / "roles" / "dnac_firmware" / "tasks" / "main.yml"


def _flatten_tasks(tasks):
    for task in tasks:
        yield task
        for nested in task.get("block", []):
            yield nested


def _module_args(task, module_name):
    return task.get(module_name)


def test_dnac_role_uses_supported_catalystcenter_module_contract():
    tasks = list(_flatten_tasks(yaml.safe_load(ROLE_PATH.read_text())))

    query = next(
        task
        for task in tasks
        if _module_args(task, "cisco.catalystcenter.swim_image_details_info") is not None
    )
    query_args = _module_args(query, "cisco.catalystcenter.swim_image_details_info")
    assert "catalystcenter_host" in query_args
    assert "catalystcenter_username" in query_args
    assert "catalystcenter_password" in query_args
    assert "catalystcenter_verify" in query_args
    assert not any(key.startswith("dnac_") for key in query_args)

    golden_presence = next(
        task
        for task in tasks
        if task.get("name") == "Determine Catalyst Center golden-image presence"
    )
    set_fact = golden_presence["ansible.builtin.set_fact"]
    assert "catalystcenter_response.response" in set_fact["running_version"]
    assert "catalystcenter_response.response" in set_fact["compliant"]

    import_task = next(
        task
        for task in tasks
        if _module_args(task, "cisco.catalystcenter.swim_import_via_url") is not None
    )
    import_args = _module_args(import_task, "cisco.catalystcenter.swim_import_via_url")
    assert "catalystcenter_host" in import_args
    assert "catalystcenter_username" in import_args
    assert "catalystcenter_password" in import_args
    assert "catalystcenter_verify" in import_args
    assert not any(key.startswith("dnac_") for key in import_args)

    assert all(
        "cisco.catalystcenter.swim_image_url_import" not in task for task in tasks
    )
