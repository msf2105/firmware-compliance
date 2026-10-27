# Credential Flow — Secret Server (prod) / Bitwarden (dev)

The `secret_server` role supports several backends behind one variable,
`credential_source`; every backend sets the same `dev_username` / `dev_password` /
`dev_enable` facts, so platform roles never change:

| `credential_source` | Backend | Per-host key | Auth (env) |
|---|---|---|---|
| `secret_server` | Delinea Secret Server (`community.general.tss`) | `secret_id` | `TSS_TOKEN` or `TSS_USERNAME`/`TSS_PASSWORD` (+`TSS_DOMAIN`) |
| `bitwarden_sm` | Bitwarden Secrets Manager (`bws`) — value is JSON `{"username","password","enable"}` | `bws_secret_id` | `BWS_ACCESS_TOKEN` |
| `bitwarden` | Bitwarden Password Manager (`bw`) — login item + custom field `enable` | `bw_item` | `BW_SESSION` |
| `vault` | ansible-vault `vault_device_credentials` dict | `secret_id` or `default` | vault password |
| `simulate` | none (demo inventory) | — | — |

The rest of this page describes the Secret Server path.

Device credentials are never stored in the repo or inventory. They are resolved
at run time from Delinea/Thycotic Secret Server.

## How it works

1. Each host in `inventory/hosts.yml` carries only a `secret_id` — the integer
   ID of that device's secret in Secret Server. No usernames, no passwords.
2. The `secret_server` role runs first for every host and calls the
   `community.general.tss` lookup, authenticating to Secret Server with env vars.
3. The lookup returns the secret's `items`; the role maps them into host-scoped
   facts by slug: `username` → `dev_username`, `password` → `dev_password`,
   `enable-password` → `dev_enable` (optional).
4. Platform roles consume those facts for the device connection. Everything is
   wrapped in `no_log: true`.

## Requirements

- Ansible collection: `community.general` (ships the `tss` lookup)
- Python SDK on the controller/runner: `pip install python-tss-sdk`
- Environment variables (injected, never in repo):
  - `TSS_BASE_URL` — e.g. `https://secretserver.example.com/SecretServer`
  - `TSS_USERNAME` / `TSS_PASSWORD` — service account, or
  - `TSS_TOKEN` — a pre-issued token (skips username/password)

## Secret layout expectation

Each device secret should expose fields with these slugs:

| Slug | Maps to | Required |
|------|---------|----------|
| `username` | `dev_username` | yes |
| `password` | `dev_password` | yes |
| `enable-password` | `dev_enable` | no (falls back to password) |

If your Secret Server template uses different slugs, set `tss_field_username`,
`tss_field_password`, `tss_field_enable` in group_vars — no code change needed.

## Alternative: DevOps Secrets Vault

If you use Delinea DevOps Secrets Vault (DSV) rather than Secret Server, swap the
lookup for `delinea.core.dsv` (client_id/client_secret auth). The rest of the
role — mapping fields into `dev_*` facts — stays the same.

## Security notes

- The `secret_server` role delegates the lookup to `localhost` (the runner), so
  Secret Server is contacted from the control node, not the devices.
- Never echo `dev_password` / `_tss_secret` in debug tasks — `no_log` is set for
  a reason. When troubleshooting, test the lookup in isolation with a throwaway
  secret, not by removing `no_log`.
