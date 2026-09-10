# Ubuntu VM — IaC (OpenTofu)

KVM virtual machine running **Ubuntu 26.04 LTS** ("Resolute") on EndeavourOS host `enterprise-d`,
managed with OpenTofu + the `dmacvicar/libvirt` provider. Hosts the `questr` app
on an EndeavourOS host, behind KVM + libvirt + virtiofs.

## 1. Architecture

### 1.2 Configuration

| Component   | Configuration                                    |
|-------------|--------------------------------------------------|
| OS          | Ubuntu 26.04 LTS ("Resolute") cloud image        |
| Machine     | pc-q35-9.2 (pinned, QEMU 11.0.2)                 |
| Firmware    | SeaBIOS                                          |
| CPU         | host-model                                       |
| RAM         | 4 GiB                                            |
| vCPUs       | 2                                                |
| Root disk   | virtio (`vda`), 80 GiB self-contained qcow2      |
|             | (flat master in `/kvm/templates/disks/`, |
|             |  uploaded by OpenTofu on apply)                  |
| Network     | virtio, NAT via libvirt `default` network         |
| Shared dir  | virtiofs at `/kvm/questr/shared`                       |
| PCIe        | 8 explicit `pcie-root-port` controllers          |
| Console     | Serial, written to file                          |
| IaC         | OpenTofu + `dmacvicar/libvirt` ~> 0.9             |

## 2. Prerequisites (first time on a new EndeavourOS machine - already executed)

### 2.1 Install packages

```bash
sudo pacman -S --needed \
  opentofu libvirt qemu-desktop edk2-ovmf \
  dnsmasq iptables-nft \
  virtiofsd
```

| Package | Why |
|---|---|
| `opentofu` | IaC tool (OSS Terraform fork) |
| `libvirt` | VM lifecycle manager |
| `qemu-desktop` | QEMU + KVM hypervisor |
| `edk2-ovmf` | UEFI firmware (OVMF) — available as fallback |
| `dnsmasq` | DHCP/DNS for libvirt's default NAT network |
| `iptables-nft` | NAT rules for the default network |
| `virtiofsd` | Userspace daemon for virtiofs shared folders |

> **Note on `bridge-utils`:** This package was removed from the Arch repositories.
> The `iproute2` package (part of the `base` group, pre-installed) provides the
> equivalent functionality. No manual bridge configuration is needed — the
> OpenTofu config in `main.tf` attaches the guest to libvirt's built-in
> `default` virtual network, which manages its own `virbr0` bridge via `dnsmasq`.

### 2.2 Enable and start libvirtd

```bash
sudo systemctl enable --now libvirtd
```

### 2.3 Verify KVM

```bash
virt-host-validate qemu
```

Expected core checks:

```
QEMU: Checking for hardware virtualization    : PASS (VMX)
QEMU: Checking if device '/dev/kvm' exists     : PASS
QEMU: Checking if device '/dev/kvm' accessible  : PASS
```

Two or three WARNs are normal on this laptop and do not affect the VM.
- `cgroup 'devices' controller` → OK — VM uses `qemu:///system`
- `No SEV / SEV-ES / SEV-SNP / TDX` → OK — Intel platform, not AMD; not a
  confidential workload

### 2.4 Ensure the `vmnet` libvirt network is active

```bash
sudo virsh net-start vmnet
sudo virsh net-autostart vmnet
```

### 2.5 Create storage directories

```bash
sudo mkdir -p /kvm/questr/templates/disks
sudo mkdir -p /kvm/questr/disks
sudo mkdir -p /kvm/questr/shared
sudo mkdir -p /kvm/questr/ssh

# Give your user ownership (libvirt runs as your user via qemu:///system)
sudo chown -R $USER:$USER /kvm
```

> The libvirt storage pool is created automatically by OpenTofu on
> `tofu apply` — no manual `virsh pool-define` step is needed.

### 2.6 Generate an SSH key for the VM

```bash
ssh-keygen -t ed25519 \
  -f /kvm/questr/ssh/questr_vm_ed25519 \
  -C "questr-vm@enterprise-d" \
  -N ""
```

This produces:
- `/kvm/questr/ssh/questr_vm_ed25519` — **private key** (keep on host)
- `/kvm/questr/ssh/questr_vm_ed25519.pub` — **public key** (injected into guest)

> Never copy the private key into the VM. The public key is sufficient.

### 2.7 Add your user to the `libvirt` group

```bash
sudo usermod -aG libvirt $USER
```

Log out and back in for the group change to take effect.

### 2.8 Storage layout reference

```
/kvm/questr/
├── templates/
│   └── disks/
│       └── questr-disk-flat.qcow2 → golden master (self-contained, copied from enterprise-d,
│                                    NEVER modified by OpenTofu or the destroy script)
├── disks/
│   └── questr-disk.qcow2          ← runtime disk (OpenTofu-managed, re-uploaded
│                                    from the templates master on every `make recreate`)
├── shared/                        ← virtiofs shared folder (↔ /host/shared in guest)
├── questr-vm-console.log          ← persistent serial console log
└── ssh/
    ├── questr_vm_ed25519          ← SSH private key (host only)
    └── questr_vm_ed25519.pub      ← SSH public key (injected into guest)
```

## 3. Creating the VM (first time)

If this is a fresh host (no existing golden master), copy the self-contained
disk image from the source host first:

```bash
# flatten the disk before copying:
#   sudo qemu-img convert -O qcow2 \
#     /kvm/questr/disks/questr-disk.qcow2 \
#     /kvm/questr/disks/questr-disk-flat.qcow2
#
# Then move the flattened disk as a template:
mv /kvm/questr/disks/questr-disk-flat.qcow2 \
    /kvm/questr/templates/disks/questr-disk-flat.qcow2
```

Then create the VM:

> TODO: Make a checkout of the questr repo into `/kvm/questr/git`
```bash
cd /kvm/questr/git/questr/deploy/kvm-host
make create
```

## 4. Re-creating the VM (after IaC changes)

```bash
cd /kvm/questr/git/questr/deploy/kvm-host
make recreate
```

The destroy script tears down the domain, volumes, pool, **the entire
`/kvm/questr/disks/` directory**, and local OpenTofu state -- a fully clean
slate. On the subsequent `tofu apply`, OpenTofu re-uploads the runtime disk
`questr-disk.qcow2` from the golden master in `/kvm/questr/templates/disks/`.

| What gets destroyed | What survives |
|---|---|
| Domain (questr-vm) | `/kvm/questr/templates/` -- golden master (NEVER touched by the destroy script) |
| All volumes in `questr_pool` | `/kvm/questr/ssh/` -- SSH keys |
| The pool itself | `/kvm/questr/shared/` -- virtiofs shared directory |
| `/kvm/questr/disks/` (directory + all files) | `/kvm/questr/questr-vm-console.log` -- serial log |

The golden master lives **outside** the pool directory, so `make recreate` is
always safe -- it never destroys data you cannot regenerate from the master.
The uploaded volume in `disks/` is disposable by design.

> NOTE: creating/recreating the VM provides the packages defined at `cloud-init-userdata.yaml`.
>       The language toolchains (Python via `uv`, Rust via `rustup`, Node.js via `nvm`) are
>       **not** installed by cloud-init. Run `make provision` after the VM is booted to set
>       them up — see [section 8](#8-provisioning-the-vm).

## 5. Monitoring the boot

```bash
cd /kvm/questr/git/questr/deploy/kvm-host
make monitor     # read-only: tail -F the console log
# or
make console     # interactive: virsh console (Ctrl+] to detach)
```

The serial console is written to a persistent log file at
`/kvm/questr/questr-vm-console.log`. It survives VM reboots and the
destroy script, so you can `diff` it across runs to compare boot behaviour.

## 6. Accessing the VM

```bash
cd /kvm/questr/git/questr/deploy/kvm-host
make ssh           # fzf-powered IP selection from DHCP leases
```

## 8. Provisioning the VM

After the VM is booted and accessible, run the Ansible playbook to install the
language toolchains:

```bash
cd /kvm/questr/git/questr/deploy/kvm-host
make provision
```

This automatically discovers the VM's IP from the libvirt DHCP lease and runs
the playbook located at `ansible/setup-lang-toolchain/`. It installs:

| Toolchain | Manager  | What gets installed |
|-----------|----------|---------------------|
| Rust      | `rustup` (snap) | Latest stable toolchain (rustc, cargo) |
> TODO: it must also install docker

The playbook is **idempotent** — you can run `make provision` again to update
toolchains or recover from a partial installation.

### Verbose output and timing

Every run shows per-task duration and total playbook time via a custom callback
plugin. For more detailed Ansible output, add the verbosity level:

```bash
make provision ANSIBLE_VERBOSITY=-vvv
make provision-verify ANSIBLE_VERBOSITY=-v
```

Run only the verification steps:

```bash
make provision-verify
```

This installs `cargo-update` (Rust) to confirm the rust toolchain is working.

## 9. Other useful commands

Run `make help` to see all available targets:

```
$ make help
autostart-off  Disable autostart for the VM
autostart-on   Enable autostart for the VM (start on host boot)
autostart-status Show autostart status (enabled/disabled)
console        Attach to the serial console (interactive, Ctrl+] to detach)
create         Create the VM for the first time
help           Show this help
monitor        Watch the live serial console log (read-only)
pause          Pause (suspend) the VM
poweron        Power on the VM (if defined but not running)
provision      Install language toolchains via Ansible
provision-verify Run only verification tasks (cargo-update)
reboot         Graceful ACPI reboot
recreate       Tear down and rebuild the VM from scratch
resume         Resume a paused VM
poweroff       Force power off the VM (virsh destroy)
ssh            SSH into the VM (interactive IP selection via fzf)
status         Show VM status
status-full    Show detailed VM status (state, CPU, memory, disk, IP)
```
