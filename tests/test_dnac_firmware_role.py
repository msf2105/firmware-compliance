import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_role(role_name):
    return (ROOT / "workflow" / "roles" / role_name / "tasks" / "main.yml").read_text()


class DnacFirmwareRoleTests(unittest.TestCase):
    def test_compliance_comes_from_per_device_image_status(self):
        text = read_role("dnac_firmware")

        query_idx = text.index("Get network device image compliance")
        determine_idx = text.index("Determine Catalyst Center device compliance")
        import_idx = text.index("Import golden image when repository image is missing")

        self.assertLess(query_idx, determine_idx)
        self.assertLess(determine_idx, import_idx)
        self.assertIn("cisco.catalystcenter.network_device_images_info", text[query_idx:determine_idx])
        self.assertIn("networkDeviceImageStatus", text[query_idx:import_idx])
        self.assertIn("UP_TO_DATE", text[query_idx:import_idx])
        self.assertIn("_catc_device_image_rows | length > 0", text[determine_idx:import_idx])
        self.assertNotIn("compliant: \"{{ (_catc_images", text[determine_idx:import_idx])

    def test_role_uses_current_catalyst_center_module_parameters(self):
        text = read_role("dnac_firmware")

        self.assertIn("catalystcenter_host", text)
        self.assertIn("cisco.catalystcenter.swim_import_via_url", text)
        self.assertNotIn("dnac_host", text)
        self.assertNotIn("dnac_username", text)
        self.assertNotIn("dnac_password", text)
        self.assertNotIn("swim_image_url_import", text)

    def test_import_requires_known_state_and_image_url(self):
        text = read_role("dnac_firmware")

        fail_idx = text.index("Refuse Catalyst Center remediation when state query failed")
        import_block_idx = text.index("Import golden image when repository image is missing")
        require_idx = text.index("Require Catalyst Center image URL before import")
        import_idx = text.index("Import software image via URL")
        record_idx = text.index("Record upgrade action")

        self.assertLess(fail_idx, import_block_idx)
        self.assertLess(require_idx, import_idx)
        self.assertLess(import_idx, record_idx)
        self.assertIn("_catc_images is failed", text[fail_idx:import_block_idx])
        self.assertIn("_catc_device_images is failed", text[fail_idx:import_block_idx])
        self.assertIn("golden_versions.dnac.image_url is defined", text[require_idx:import_idx])
        self.assertIn("golden_versions.dnac.image_url | length", text[require_idx:import_idx])


if __name__ == "__main__":
    unittest.main()
