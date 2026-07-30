from pathlib import Path


def test_compliance_report_does_not_extract_complete_hostvars():
    tasks_file = (
        Path(__file__).resolve().parents[1]
        / "workflow"
        / "roles"
        / "compliance_report"
        / "tasks"
        / "main.yml"
    )
    task_text = tasks_file.read_text(encoding="utf-8")

    assert "map('extract', hostvars)" not in task_text
    assert "_report:" not in task_text

