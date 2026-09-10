# VM Baseline Playbook

Automates the security/baseline setup for the `questr-staging` VM after
`make create` or `make recreate`. Run it via `make baseline` from
`deploy/kvm-host/` (the target discovers the VM IP from the `vmnet` DHCP
leases).

## What it installs

| Component | Source | Notes |
|-----------|--------|-------|
| Docker Engine | Official apt repo (`resolute`) | Engine, CLI, containerd, buildx, Compose plugin |
| `daemon.json` | role file | Log caps `10m x 3`, matching the deployed compose stack |
| `apt-mark hold` | Engine packages | `docker-ce`, `docker-ce-cli`, `containerd.io` held against unattended upgrades |
| unattended-upgrades | Ubuntu repo | Security-only origins, no automatic reboots |
| Tailscale | official apt repo (`resolute`) | Joins the tailnet via `tailscale up` with a vaulted auth key (see below) |

## Tailscale and ansible-vault (D6)

The baseline joins the VM to your tailnet. The auth key and hostname come
from `vault/tailscale.yml`, an **ansible-vault** encrypted file:

1. Create the vault password file **outside the repo** (never committed):

   ```bash
   echo 'your-vault-password' > /kvm/questr/vault-password
   chmod 600 /kvm/questr/vault-password
   ```

2. The checked-in `vault/tailscale.yml` is a placeholder encrypted with a
   dummy password (used only for agent-side syntax checks). Edit the real
   values and rekey it:

   ```bash
   ansible-vault edit vault/tailscale.yml \
     --vault-password-file /kvm/questr/vault-password   # after rekey
   ansible-vault rekey vault/tailscale.yml \
     --vault-password-file /tmp/dummy-pass   # the placeholder password
     --new-vault-password-file /kvm/questr/vault-password
   ```

3. Run `make baseline`; the Makefile passes
   `--vault-password-file /kvm/questr/vault-password` automatically.

Nothing secret is ever committed: the auth key exists only inside the
encrypted vars file and is passed to `tailscale up` with `no_log: true`.

## Idempotency

The playbook is idempotent. `make baseline-verify` runs only the
verification tasks (Docker/Compose versions, unattended-upgrades enabled).

## Structure

```
vm-baseline/
  site.yml                     # entry point: docker + unattended-upgrades + tailscale roles
  ansible.cfg                  # profile_tasks timing callback
  inventory.ini.example
  vault/
    tailscale.yml              # ansible-vault encrypted auth key + hostname
    tailscale.yml.example      # plaintext reference for the encrypted file
  roles/
    docker/                    # official repo install, daemon.json, holds
    unattended-upgrades/       # 20auto-upgrades + security-only origins
    tailscale/                 # official repo install, tailscale up (no_log)
```

Note: the engine packages are held with `apt-mark hold` on purpose: security
updates for them are applied manually (or by a future scheduled task), so
that running containers are never upgraded underneath a running daemon.