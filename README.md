# Firmware Compliance

Multi-platform firmware **audit + guarded remediation** for enterprise network
infrastructure, built on Ansible. Checks running firmware against an approved
"golden" version matrix, pulls device credentials at run time from a secrets
manager (**Delinea Secret Server** in prod, **Bitwarden** in dev), and wraps every
change in a CAB-approved **ServiceNow** change record. Runs from **AWX / AAP**.

**Start here:** [docs/setup-guide.md](docs/setup-guide.md) — step-by-step setup
(lab, Bitwarden, ServiceNow PDI, AWX, promotion to prod) ·
[docs/demo-script.md](docs/demo-script.md) — demo talk track.

```bash
# 60-second rehearsal, no devices needed
cd workflow && SNOW_MODE=mock ansible-playbook playbooks/site.yml -i inventory/demo.yml
```

> **Safety first:** dry-run / audit is the default. A real firmware push only
> happens when three independent conditions are all true at once (see
> [docs/safety-model.md](docs/safety-model.md)).

## Platform coverage

| Platform | Ansible collection | Method | Remediation |
|----------|-------------------|--------|-------------|
| Cisco IOS / IOS-XE | `cisco.ios` | SSH (network_cli) | copy + MD5 + `install add`/activate (install mode) |
| Cisco IOS-XR | `cisco.iosxr` | SSH (network_cli) | install add/activate |
| Cisco NX-OS | `cisco.nxos` | SSH (network_cli) | install all |
| Cisco ASA | `cisco.asa` | SSH (network_cli) | boot image |
| Cisco ACI | `cisco.aci` | REST (local) | firmware policy |
| Cisco Catalyst Center | `cisco.catalystcenter` | REST (local) | SWIM import/tag/distribute/activate for managed devices |
| Cisco Catalyst SD-WAN | `ansible.builtin.uri` | SD-WAN Manager REST | edge install/activate (controllers report-only) |
| Cisco ISE | `cisco.ise` | REST (local) | **audit-only** |
| Cisco UCS | `cisco.ucs` | REST (local) | infra bundle |
| Palo Alto | `paloaltonetworks.panos` | REST (local) | PAN-OS download/install, HA-aware |
| F5 BIG-IP | `f5networks.f5_modules` | iControl REST | install to inactive volume, HA-aware |

Demo-ready and hardened: IOS-XE, Catalyst Center, SD-WAN, PAN-OS, F5. The other
Cisco roles (IOS-XR, NX-OS, ASA, ACI, ISE, UCS) are carried over unchanged.

## Documentation

- [docs/setup-guide.md](docs/setup-guide.md) — **step-by-step setup, dev → prod**
- [docs/demo-script.md](docs/demo-script.md) — demo talk track
- [docs/architecture.md](docs/architecture.md) — how the workflow is structured and flows
- [docs/safety-model.md](docs/safety-model.md) — the three-gate apply model and guardrails
- [docs/runbook.md](docs/runbook.md) — operating procedures: audit, remediate, roll back
- [docs/secret-server.md](docs/secret-server.md) — credential flow via Secret Server
- [docs/servicenow.md](docs/servicenow.md) — change-record integration
- [docs/aap.md](docs/aap.md) — running it from Ansible Automation Platform
- [docs/platform-notes.md](docs/platform-notes.md) — per-platform quirks and caveats

## Reference implementation

The complete, runnable Ansible project lives under [`workflow/`](workflow/).
See [workflow/README.md](workflow/README.md) for the quick-start.

## Status

Validated with ansible-lint (production profile), unit tests for version
comparison, and an end-to-end rehearsal (audit → open change → CAB approve →
apply → close) on the simulated inventory in CI. Live device sessions, Secret
Server/Bitwarden and ServiceNow calls need your lab or prod endpoints. Golden
versions and hosts shipped here are examples — replace them before an apply run.
