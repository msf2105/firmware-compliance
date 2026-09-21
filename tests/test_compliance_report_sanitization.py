from pathlib import Path
import unittest


class ComplianceReportSanitizationTest(unittest.TestCase):
    def test_compliance_report_does_not_extract_complete_hostvars(self):
        tasks_file = (
            Path(__file__).resolve().parents[1]
            / "workflow"
            / "roles"
            / "compliance_report"
            / "tasks"
            / "main.yml"
        )
        task_text = tasks_file.read_text(encoding="utf-8")

        self.assertNotIn("map('extract', hostvars)", task_text)
        self.assertNotIn("_report:", task_text)


if __name__ == "__main__":
    unittest.main()

