# kvm-host Ansible Playbooks

Two entry playbooks share one tree under `deploy/kvm-host/ansible/`:

| Playbook | Purpose | Make target |
|----------|---------|-------------|
| `setup-lang-toolchain.yml` | Installs and configures the Rust toolchain on the VM | `make provision` / `make provision-verify` |
| `vm-baseline.yml` | Staging baseline: Docker Engine, unattended security updates, Tailscale | `make baseline` / `make baseline-verify` |

Both discover the VM IP from the `vmnet` DHCP leases and run against the
`questr-staging` VM.

## Shared layout

```
ansible/
  setup-lang-toolchain.yml      # entry point: rust role
  vm-baseline.yml               # entry point: docker + unattended-upgrades + tailscale roles
  ansible.cfg                   # profile_tasks timing callback
  inventory.ini.example
  collections/
    requirements.yml            # ansible.posix (toolchain galaxy install)
  callback_plugins/
    profile_tasks.py            # per-task duration + total time
  vault/
    tailscale.yml               # ansible-vault encrypted auth key + hostname
    tailscale.yml.example       # plaintext reference for the encrypted file
  roles/
    rust/                       # snap rustup, stable toolchain, cargo-update
    docker/                     # official repo install, daemon.json, holds
    unattended-upgrades/        # 20auto-upgrades + security-only origins
    tailscale/                  # official repo install, tailscale up (no_log)
```

## Prerequisites

1. **Ansible** installed on the control node (see Host setup below).
2. **SSH access** from the control node to the target VM already configured.
3. A user with **sudo** privileges on the target VM (`ubuntu` user by default).

### Host setup

The control node (EndeavourOS) was prepared with:

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Ansible via uv
uv tool install --with-executables-from ansible-core,ansible-lint ansible
```

## Language toolchain playbook (`setup-lang-toolchain.yml`)

Bootstraps a development-ready Ubuntu 26.04 VM with the tools needed to
compile Rust and useful utilities like `duf`, `dust`, etc. The toolchain is
managed by its recommended version manager:

| Toolchain | Version manager | Install method |
|-----------|-----------------|----------------|
| Rust      | `rustup`        | Snap (classic confinement) |

### What it installs

- **rustup** — installed via `snap install rustup --classic` (requires sudo)
- **Stable toolchain** — set as default and updated via `rustup`
- **rustc, cargo, rustup** — available after toolchain bootstrapping

The `--classic` flag is required for snap to access the system resources needed
to compile Rust crates. All `rustup` and `cargo` commands run as the `ubuntu`
user, not root.

### Quick start (manual run)

```bash
cd /kvm/questr/git/questr/deploy/kvm-host/ansible

# Copy and edit the inventory file with the VM IP address
cp inventory.ini.example inventory.ini
# Edit inventory.ini — change the IP in ansible_host

# Run the playbook
ansible-playbook -i inventory.ini setup-lang-toolchain.yml
```

Or simply use the Makefile from the kvm-host root (IP auto-discovered):

```bash
make provision
```

It is safe to rerun — see [Idempotency](#idempotency) below.

### Verification

The playbook installs a representative tool for the Rust stack to confirm the
toolchain works. Verification tasks are tagged with `verify`.

| Stack | Verifies by installing | Verify command                 |
|-------|------------------------|--------------------------------|
| Rust  | `cargo-update`         | `cargo-install-update --version` |

```bash
ansible-playbook -i inventory.ini setup-lang-toolchain.yml --tags verify
# or from the kvm-host root:
make provision-verify
```

## VM baseline playbook (`vm-baseline.yml`)

Automates the security/baseline setup for the `questr-staging` VM after
`make create` or `make recreate`. Run it via `make baseline` from
`deploy/kvm-host/` (the target discovers the VM IP from the `vmnet` DHCP
leases).

### What it installs

| Component | Source | Notes |
|-----------|--------|-------|
| Docker Engine | Official apt repo (`resolute`) | Engine, CLI, containerd, buildx, Compose plugin |
| `daemon.json` | role file | Log caps `10m x 3`, matching the deployed compose stack |
| `apt-mark hold` | Engine packages | `docker-ce`, `docker-ce-cli`, `containerd.io` held against unattended upgrades |
| unattended-upgrades | Ubuntu repo | Security-only origins, no automatic reboots |
| Tailscale | official apt repo (`resolute`) | Joins the tailnet via `tailscale up` with a vaulted auth key (see below) |

### Tailscale and ansible-vault (D6)

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

Note: the engine packages are held with `apt-mark hold` on purpose: security
updates for them are applied manually (or by a future scheduled task), so
that running containers are never upgraded underneath a running daemon.

Run only the verification tasks (Docker/Compose versions,
unattended-upgrades enabled):

```bash
make baseline-verify
```

## Idempotency

Both playbooks are idempotent — running them multiple times produces the same
result without unintended side effects. Guards used:

| Guard mechanism | Used for |
|-----------------|----------|
| `creates` (Ansible module parameter) | cargo-update binary |
| `when` with `register` + stdout check | rustup snap, rustup default toolchain, snap installed |
| `changed_when` with stdout inspection | rustup update, toolchain set, apt-mark hold, tailscale up |

This means you can safely re-run either playbook after a partial installation
or when upgrading individual components.

## Design decisions

- **One role per concern** — clean separation, easy to maintain or omit.
- **Snap for rustup** — the writeloop.dev blog post has proven this method
  works reliably on Ubuntu without adding third-party APT repositories.
- **Privilege escalation (become: yes)** — limited to system-level tasks
  (apt, snap, systemd). Language toolchain commands run as the `ubuntu` user.
- **Configurable inventory** — the target VM IP is set in `inventory.ini`
  (example provided) so the playbooks work with any Ubuntu VM.
- **Task timing** — a custom callback plugin (`callback_plugins/profile_tasks.py`)
  displays elapsed time per task and total playbook execution time. The
  `ansible.cfg` enables it automatically. Use `-v`, `-vv`, or `-vvv` for more
  verbose output.
- **deb822 repositories** — Docker and Tailscale apt repos use the
  `deb822_repository` module; `apt_repository` is deprecated in ansible-core.