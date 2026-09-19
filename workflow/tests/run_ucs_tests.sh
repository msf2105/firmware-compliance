#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

ANSIBLE_COLLECTIONS_PATH="tests:${ANSIBLE_COLLECTIONS_PATH:-}" \
  ansible-playbook \
    -i tests/inventory/local.yml \
    tests/playbooks/ucs_query_failure_blocks_remediation.yml
