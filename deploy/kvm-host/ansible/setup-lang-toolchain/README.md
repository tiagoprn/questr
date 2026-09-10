# Language Toolchain Playbook

An Ansible playbook that installs and configures rust language toolchain on a remote Ubuntu VM.

## Purpose

This playbook bootstraps a development-ready Ubuntu 26.04 VM with the tools
needed to compile rust useful utilities, like `duf`, `dust`, etc.
toolchain is managed by its recommended version manager:

| Toolchain | Version manager | Install method |
|-----------|----------------|----------------|
| Rust      | `rustup`       | Snap (classic confinement) |

## Prerequisites

1. **Ansible** installed on the control node (see Host setup below).
2. **SSH access** from the control node to the target VM already configured.
3. A user with **sudo** privileges on the target VM (`ubuntu` user by default).

## Host setup

The control node (EndeavourOS) was prepared with:

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Ansible via uv
uv tool install --with-executables-from ansible-core,ansible-lint ansible
```

## Quick start

```bash
# Navigate to the playbook directory
cd playbook/setup-lang-toolchain

# Copy and edit the inventory file with the VM IP address
cp inventory.ini.example inventory.ini
# Edit inventory.ini — change the IP in ansible_host

# Run the playbook
ansible-playbook -i inventory.ini site.yml
```

The playbook will install the rust toolchain. It is safe to rerun —
see [Idempotency](#idempotency) below.

## What it installs

### Rust (via rustup installed through snap)

- **rustup** — installed via `snap install rustup --classic` (requires sudo)
- **Stable toolchain** — set as default and updated via `rustup`
- **rustc, cargo, rustup** — available after toolchain bootstrapping

The `--classic` flag is required for snap to access the system resources needed
to compile Rust crates. All `rustup` and `cargo` commands run as the `ubuntu`
user, not root.

## Verification

The playbook installs a representative tool for the rust stack to confirm the
toolchain works. Verification tasks are tagged with `verify`.

| Stack  | Verifies by installing | Verify command            |
|--------|------------------------|---------------------------|
| Rust   | `cargo-update`         | `cargo-install-update --version` |

Run only the verification tasks:

```bash
ansible-playbook -i inventory.ini site.yml --tags verify
```

Skip verification on a re-run:

```bash
ansible-playbook -i inventory.ini site.yml --skip-tags verify
```

## Idempotency

The playbook is designed to be **idempotent** — running it multiple times
produces the same result without unintended side effects. Each install task
is guarded by one of these mechanisms:

| Guard mechanism | Used for |
|----------------|----------|
| `creates` (Ansible module parameter) | cargo-update binary |
| `when` with `register` + stdout check | rustup snap, rustup default toolchain |
| `changed_when` with stdout inspection | rustup update, toolchain set |

This means you can safely re-run the playbook after a partial installation or
when upgrading individual components.

## Design decisions

- **One role per toolchain** — clean separation of concerns, easy to maintain
  or omit individual stacks.
- **Snap for rustup** — the writeloop.dev blog post has proven this method
  works reliably on Ubuntu without adding third-party APT repositories.
- **Privilege escalation (become: yes)** — limited to system prerequisites
  (`apt install curl build-essential`) and the `snap install rustup` command.
  All language toolchain commands run as the `ubuntu` user.
- **Configurable inventory** — the target VM IP is set in `inventory.ini`
  (example provided) so the playbook works with any Ubuntu VM.
- **Task timing** — a custom callback plugin (`callback_plugins/profile_tasks.py`)
  displays elapsed time per task and total playbook execution time. An `ansible.cfg`
  enables it automatically. Use `-v`, `-vv`, or `-vvv` for more verbose output.
