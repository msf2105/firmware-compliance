# Firmware Compliance

Multi-platform firmware **audit + guarded remediation** for enterprise network
infrastructure, built on Ansible. Checks running firmware against an approved
"golden" version matrix across ten platform families, pulls device credentials
at run time from **Delinea/Thycotic Secret Server**, and wraps every change in a
**ServiceNow** change record.

> **Safety first:** dry-run / audit is the default. A real firmware push only
> happens when three independent conditions are all true at once (see
> [docs/safety-model.md](docs/safety-model.md)).

## Platform coverage

| Platform | Ansible collection | Method | Remediation |
|----------|-------------------|--------|-------------|
| Cisco IOS / IOS-XE | `cisco.ios` | SSH (network_cli) | boot-var + guarded reload |
| Cisco IOS-XR | `cisco.iosxr` | SSH (network_cli) | install add/activate |
| Cisco NX-OS | `cisco.nxos` | SSH (network_cli) | install all |
| Cisco ASA | `cisco.asa` | SSH (network_cli) | boot image |
| Cisco ACI | `cisco.aci` | REST (local) | firmware policy |
| Cisco Catalyst Center (DNAC) | `cisco.catalystcenter` | REST (local) | SWIM |
| Cisco ISE | `cisco.ise` | REST (local) | **audit-only** |
| Cisco UCS | `cisco.ucs` | REST (local) | infra bundle |
| Palo Alto | `paloaltonetworks.panos` | REST (local) | PAN-OS install |
| F5 BIG-IP | `f5networks.f5_modules` | iControl REST | image install |

## Documentation

- [docs/architecture.md](docs/architecture.md) — how the workflow is structured and flows
- [docs/safety-model.md](docs/safety-model.md) — the three-gate apply model and guardrails
- [docs/runbook.md](docs/runbook.md) — operating procedures: audit, remediate, roll back
- [docs/secret-server.md](docs/secret-server.md) — credential flow via Secret Server
- [docs/servicenow.md](docs/servicenow.md) — change-record integration
- [docs/semaphore.md](docs/semaphore.md) — running it from Semaphore UI
- [docs/platform-notes.md](docs/platform-notes.md) — per-platform quirks and caveats

## Reference implementation

The complete, runnable Ansible project lives under [`workflow/`](workflow/).
See [workflow/README.md](workflow/README.md) for the quick-start.

## Status

Structurally validated (syntax, inventory graph, task graph) and exercised
end-to-end through Semaphore against the real role/collection/lookup stack — the
only step that requires live infrastructure is the Secret Server / ServiceNow
connection and the device sessions themselves. Ships with **sample hosts and
example golden versions** that must be replaced with your real environment
before an apply run.
