#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
export ANSIBLE_CONFIG="$PWD/ansible.cfg"

reject_output="$(
  ansible-playbook -i tests/inventory/local.yml tests/playbooks/preflight_reject_override.yml \
    -e apply_cleared=true -e apply_updates=false 2>&1
)" && {
  echo "Expected preflight to reject a direct apply_cleared override." >&2
  exit 1
}

if [[ "$reject_output" != *"apply_cleared is computed by the preflight role"* ]]; then
  echo "Preflight failed, but not for the expected override rejection." >&2
  printf '%s\n' "$reject_output" >&2
  exit 1
fi

ansible-playbook -i tests/inventory/local.yml tests/playbooks/preflight_dry_run.yml
ansible-playbook -i tests/inventory/local.yml tests/playbooks/compliance_report_includes_missing.yml
