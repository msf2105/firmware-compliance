# Credential Flow — Secret Server

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

If your Secret Server template uses different slugs, adjust the `selectattr`
filters in `roles/secret_server/tasks/main.yml`.

## Alternative: DevOps Secrets Vault

If you use Delinea DevOps Secrets Vault (DSV) rather than Secret Server, swap the
lookup for `delinea.core.dsv` (client_id/client_secret auth). The rest of the
role — mapping fields into `dev_*` facts — stays the same.

## Security notes

- The `secret_server` role delegates the lookup to `localhost` (the runner), so
  Secret Server is contacted from the control node, not the devices.
- Do not pass device credential variables such as `dev_password` or
  `ansible_password` through inventory, surveys, or `-e`; the role fails closed
  so Secret Server remains the only credential source for devices.
- Never echo `dev_password` / `_tss_secret` in debug tasks — `no_log` is set for
  a reason. When troubleshooting, test the lookup in isolation with a throwaway
  secret, not by removing `no_log`.
