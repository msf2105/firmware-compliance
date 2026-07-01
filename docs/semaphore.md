# Running from Semaphore UI

The workflow is wired into Semaphore (Ansible-as-a-service) in the **EVE-NG**
project. This gives a gated, audit-logged "run firmware compliance" button with
survey-driven toggles, without handing anyone a shell.

## What's wired (EVE-NG project, id 4)

- **Repository**: `eve-lab` (id 5) → `file:///opt/eve-lab`, branch `main`.
  The workflow lives in that repo under `firmware-compliance/`.
- **Inventory**: `firmware-compliance-hosts` (id 8) →
  `firmware-compliance/inventory/hosts.yml` (file inventory).
- **Environment**: `firmware-compliance-env` (id 5) — holds `ANSIBLE_ROLES_PATH`
  plus the `TSS_*` / `SNOW_*` secret vars.
- **Template**: `Firmware Compliance (multi-platform)` (id 15) →
  playbook `firmware-compliance/playbooks/site.yml`, with survey vars
  `apply_updates` and `reboot_after_upgrade`.

## The critical gotchas (learned the hard way)

### 1. Roles path must be RELATIVE

Semaphore does **not** run from the bind-mount (`/opt/eve-lab`). It **clones**
the repo to `/tmp/semaphore/project_4/repository_5_template_15/` and runs
`ansible-playbook` from that checkout as cwd. Two consequences:

- The playbook's own `ansible.cfg` (with `roles_path = roles`) is not at the
  cwd, so roles under `firmware-compliance/roles/` won't resolve automatically.
- Fix: set `ANSIBLE_ROLES_PATH=firmware-compliance/roles` (a **relative** path)
  in the template's Environment. It resolves against the checkout cwd.

Do **not** use the absolute bind-mount path `/opt/eve-lab/firmware-compliance/roles`
— those files are mode 0600 owned by the host user, and the container's
`semaphore` user (uid 1001) gets `Permission denied`. The checkout is 0644 and
semaphore-owned, so the relative path works.

### 2. python-tss-sdk must be in the container's Ansible venv

The `community.general.tss` lookup needs the SDK inside the Semaphore app venv:

```bash
podman exec sem-app /opt/semaphore/apps/ansible/<ver>/venv/bin/pip install python-tss-sdk
```

This is wiped on an image rebuild (same as paramiko for network_cli) — re-install
after any rebuild.

## Environment variables to set in Semaphore

In the `firmware-compliance-env` environment:

| Var | Value |
|-----|-------|
| `ANSIBLE_ROLES_PATH` | `firmware-compliance/roles` (relative — do not change to absolute) |
| `TSS_BASE_URL` | your Secret Server URL |
| `TSS_USERNAME` / `TSS_PASSWORD` | service account |
| `SNOW_INSTANCE` / `SNOW_USERNAME` / `SNOW_PASSWORD` | ServiceNow service account |

The template ships with `CHANGE_ME` placeholders — fill in the real values in the
Semaphore UI (Project → Environment), not in the repo.

## Running

1. Semaphore → EVE-NG → Task Templates → **Firmware Compliance (multi-platform)**.
2. Leave `apply_updates` blank/false for an audit; set `true` for remediation
   (inside the maintenance window).
3. Use the task's **Limit** field to target one platform/host (e.g. `nxos`).
4. Review the run output and the `reports/` artifact.

## Verifying the wiring

An audit run with placeholder credentials will fail at the Secret Server lookup
(`Unable to detect server type` — expected, the URL is a placeholder) but only
after successfully loading all roles and passing the `secret_id` assertions.
That failure point proves the repo/inventory/environment/roles-path wiring is
correct end to end.
