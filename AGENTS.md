# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **single Ansible product** (`firmware-compliance`): multi-platform
network firmware **audit + guarded remediation**. There is **no server, database,
build, or frontend** — the "application" is the Ansible playbook. Run everything
from the `workflow/` directory.

### Running / testing (all from `workflow/`)

- Lint / static check: `ansible-playbook playbooks/site.yml --syntax-check`
  (there is no `ansible-lint`/`yamllint` config; those tools are not installed).
- Inventory / task graph: `ansible-playbook playbooks/site.yml --list-hosts` /
  `--list-tasks`.
- Run the app (safe audit, the default): `ansible-playbook playbooks/site.yml`
  (see `workflow/README.md` for `--limit`, apply-mode, and other usage).

### Non-obvious caveats

- **ansible-core version:** the base image ships `ansible-core 2.16.3`, which is
  **too old** for the collections pinned in `workflow/requirements.yml`
  (`community.general >= 13.1.0` needs `ansible-core >= 2.17`). The update script
  installs a compatible `ansible-core` into user site-packages; the `/usr/bin/ansible*`
  wrappers automatically load it (user site precedes system `dist-packages`). If
  you see `Collection community.general does not support Ansible version 2.16.3`,
  the upgrade did not take effect.
- **No live infrastructure here:** real runs need reachable devices plus `TSS_*`
  (Delinea Secret Server) and, for apply mode, `SNOW_*` (ServiceNow) env vars —
  none of which can be provisioned in this VM. With the shipped sample inventory
  (placeholder URLs), an audit run **intentionally fails at the Secret Server
  lookup** (`Unable to detect server type via health check endpoints`) *after*
  every role loads and the `secret_id` assertions pass. That failure point is the
  documented end-to-end wiring proof — not a real error. Play 3 (the report play)
  is not reached in this no-infra case because all device hosts fail in Play 2.
- **Latent bug in `roles/compliance_report`:** its first task, *"Build compliance
  record set"*, uses `map('combine', ...)` over `hostvars` and errors on modern
  ansible-core (`expected dicts but got a 'HostVarsVars'` — `HostVarsVars` is not
  a mutable mapping). The `_report` fact it sets is **never used** (dead code),
  but it would break Play 3's report generation on a real run where devices
  succeed. The actual report table + JSON artifact are built from `_rows` in the
  later tasks, which work. Not fixed here (env-setup scope only).
- Secrets are never stored in the repo; `workflow/reports/*` and
  `workflow/backups/*` are gitignored runtime artifacts.
