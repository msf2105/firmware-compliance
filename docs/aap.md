# Running from Ansible Automation Platform (AAP)

The workflow is wired into **Ansible Automation Platform** (AAP) as an
automation job. This gives a gated, audit-logged "run firmware compliance"
button with survey-driven toggles, without handing anyone a shell.

## What's wired

- **Project**: `firmware-compliance` — syncs from this Git repo, branch `main`.
  The workflow lives under `workflow/` in the repo root.
- **Inventory**: `firmware-compliance-hosts` →
  `workflow/inventory/hosts.yml` (file inventory).
- **Credentials**: `firmware-compliance-secrets` credential type — holds
  `ANSIBLE_ROLES_PATH` plus the `TSS_*` / `SNOW_*` secret vars.
- **Job Template**: `Firmware Compliance (multi-platform)` →
  playbook `workflow/playbooks/site.yml`, with survey vars
  `apply_updates` and `reboot_after_upgrade`.

## The critical gotchas (learned the hard way)

### 1. Roles path must be RELATIVE

AAP clones the project repo to a temporary checkout and runs
`ansible-playbook` from that checkout as cwd. Two consequences:

- The playbook's own `ansible.cfg` (with `roles_path = roles`) is not at the
  cwd, so roles under `workflow/roles/` won't resolve automatically.
- Fix: set `ANSIBLE_ROLES_PATH=workflow/roles` (a **relative** path)
  in the job template's extra vars or environment. It resolves against the
  checkout cwd.

### 2. python-tss-sdk must be in the execution environment

The `community.general.tss` lookup needs the SDK in the AAP execution
environment. Add it to your custom execution environment definition:

```dockerfile
RUN pip install python-tss-sdk
```

If using the default execution environment, install it at runtime via a
pre-task or use a custom EE image that includes it.

## Environment variables to set in AAP

Define these in the job template or a dedicated credential:

| Var | Value |
|-----|-------|
| `ANSIBLE_ROLES_PATH` | `workflow/roles` (relative — do not change to absolute) |
| `TSS_BASE_URL` | your Secret Server URL |
| `TSS_USERNAME` / `TSS_PASSWORD` | service account |
| `SNOW_INSTANCE` / `SNOW_USERNAME` / `SNOW_PASSWORD` | ServiceNow service account |

The template ships with `CHANGE_ME` placeholders — fill in the real values in
the AAP UI (Credentials / Job Template extra vars), not in the repo.

## Running

1. AAP → Automation Execution → Templates → **Firmware Compliance (multi-platform)**.
2. Leave `apply_updates` blank/false for an audit; set `true` for remediation
   (inside the maintenance window).
3. Use the job template's **Limit** field to target one platform/host (e.g. `nxos`).
4. Review the job output and the `reports/` artifact.

## Verifying the wiring

An audit run with placeholder credentials will fail at the Secret Server lookup
(`Unable to detect server type` — expected, the URL is a placeholder) but only
after successfully loading all roles and passing the `secret_id` assertions.
That failure point proves the repo/inventory/credentials/roles-path wiring is
correct end to end.