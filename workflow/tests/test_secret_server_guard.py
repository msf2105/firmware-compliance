#!/usr/bin/env python3
"""Regression tests for Secret Server credential-source enforcement."""

from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


WORKFLOW_DIR = Path(__file__).resolve().parents[1]


class SecretServerGuardTest(unittest.TestCase):
    def run_secret_server_role(self, extra_var):
        inventory = textwrap.dedent(
            """\
            all:
              hosts:
                localhost:
                  ansible_connection: local
                  secret_id: 1001
              vars:
                tss_base_url: https://secretserver.example.com/SecretServer
            """
        )
        playbook = textwrap.dedent(
            """\
            - hosts: all
              gather_facts: false
              tasks:
                - ansible.builtin.include_role:
                    name: secret_server
            """
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            inventory_path = temp_path / "inventory.yml"
            playbook_path = temp_path / "playbook.yml"
            inventory_path.write_text(inventory, encoding="utf-8")
            playbook_path.write_text(playbook, encoding="utf-8")

            env = os.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = str(WORKFLOW_DIR / "roles")

            return subprocess.run(
                [
                    "ansible-playbook",
                    "-i",
                    str(inventory_path),
                    str(playbook_path),
                    "-e",
                    extra_var,
                ],
                cwd=WORKFLOW_DIR,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

    def test_rejects_pre_supplied_device_credential_vars(self):
        for variable in ("dev_password", "ansible_password"):
            with self.subTest(variable=variable):
                result = self.run_secret_server_role(f"{variable}=injected")

                self.assertNotEqual(result.returncode, 0)
                output = result.stdout + result.stderr
                self.assertIn(
                    f"pre-supplied credential variable '{variable}'",
                    output,
                )


if __name__ == "__main__":
    unittest.main()
