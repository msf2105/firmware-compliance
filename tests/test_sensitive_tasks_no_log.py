from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]

SENSITIVE_MODULES = {
    "cisco.aci.aci_firmware_policy",
    "cisco.aci.aci_rest",
    "cisco.catalystcenter.swim_image_details_info",
    "cisco.catalystcenter.swim_image_url_import",
    "cisco.ise.backup_last_status_info",
    "cisco.ise.node_services_profiler_probe_config_info",
    "cisco.ucs.ucs_managed_objects",
    "cisco.ucs.ucs_query",
    "f5networks.f5_modules.bigip_device_info",
    "f5networks.f5_modules.bigip_software_image",
    "f5networks.f5_modules.bigip_software_install",
    "f5networks.f5_modules.bigip_ucs_fetch",
    "paloaltonetworks.panos.panos_export",
    "paloaltonetworks.panos.panos_facts",
    "paloaltonetworks.panos.panos_software",
    "servicenow.itsm.change_request",
}


def iter_tasks(tasks):
    for task in tasks or []:
        if not isinstance(task, dict):
            continue

        yield task

        for block_key in ("block", "rescue", "always"):
            yield from iter_tasks(task.get(block_key))


class SensitiveTasksNoLogTest(unittest.TestCase):
    def test_credential_bearing_modules_are_redacted(self):
        offenders = []

        for task_file in sorted((ROOT / "workflow" / "roles").glob("*/tasks/*.yml")):
            with task_file.open(encoding="utf-8") as handle:
                tasks = yaml.safe_load(handle)

            for task in iter_tasks(tasks):
                module_names = SENSITIVE_MODULES.intersection(task)
                if module_names and task.get("no_log") is not True:
                    offenders.append(
                        f"{task_file.relative_to(ROOT)}: {task.get('name', '<unnamed>')} "
                        f"uses {', '.join(sorted(module_names))} without no_log"
                    )

        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
