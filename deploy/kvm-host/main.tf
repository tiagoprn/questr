# Self-contained root disk, flattened on oa with `qemu-img convert -O qcow2`
# so it carries no backing-file dependency. The previous design (thin overlay
# over a base image fetched from the cloud-images `current` URL) was not
# portable: `current` is a moving target, and an overlay opened against a
# different base build reads garbage for unwritten clusters. This was the
# root cause of the 2026-07-27 boot loop on holodeck (silent real-mode hang
# at SeaBIOS, empty console log, 0 disk writes). ADR 20260619-064718.
#
# tofu uploads the master into the pool via create.content.url, which accepts
# local filesystem paths in the framework provider (the legacy flat `source`
# attribute was removed in v0.9). The uploaded qcow2 defines its own 80 GiB
# virtual size, so no `capacity` attribute is needed.
resource "libvirt_volume" "questr_disk" {
  name = "questr-disk.qcow2"
  pool = libvirt_pool.questr_pool.name

  target = {
    format = {
      type = "qcow2"
    }
  }

  create = {
    content = {
      url = "/kvm/questr/templates/disks/questr-disk-flat.qcow2"
    }
  }

  depends_on = [libvirt_pool.questr_pool]
}

resource "libvirt_domain" "questr_staging" {
  name        = "questr-staging"
  memory      = var.vm_memory_mb
  memory_unit = "MiB"
  vcpu        = var.vm_vcpu
  type        = "kvm"

  # q35 machine type + SeaBIOS + explicit PCIe root ports, with the machine
  # type PINNED to pc-q35-9.2: the versioned type this disk was created
  # under on oa (QEMU 9.2.4). Holodeck's QEMU 11.0.2 still ships it (verify
  # with `qemu-system-x86_64 -machine help`). Pinning prevents silent
  # virtual-hardware drift as distro QEMU updates, which is required for
  # the same disk to keep booting on both hosts.
  #
  # History:
  # - SeaBIOS + q35 without explicit PCIe root ports caused D3cold failures
  #   for all virtio-pci devices. The root cause was NOT SeaBIOS itself: it
  #   was the lack of pcie-root-port controllers in the PCI topology.
  #   Libvirt auto-generation placed virtio devices on PCI bridges, which
  #   don't handle PCIe power management correctly.
  # - The working "labs" VM at /kvm/labs/conf/labs.xml (Ubuntu 24.04, q35,
  #   SeaBIOS, all virtio devices working) proved that explicit pcie-root-port
  #   controllers fix the D3cold issue without needing OVMF.
  # - This configuration adds 8 pcie-root-port controllers (modeled after
  #   the labs VM).
  #
  # ADRs: 20260619-064718 (original debug trail), 20260619-090902 (e1000),
  #        20260619-092725 (rtl8139), 20260619-093701 (OVMF, reverted).
  os = {
    type         = "hvm"
    type_arch    = "x86_64"
    type_machine = "pc-q35-9.2"
  }

  # host-model selects the closest named CPU model to the host and exposes
  # its feature set. Unlike host-passthrough, the guest CPUID remains stable
  # when the disk moves between hosts with different Intel CPUs
  # (oa: ZimaBlade -> holodeck: ZenBook UX325JA i5-1035G1), which is what
  # makes the same disk portable. Cold-boot CPUID changes are safe: the
  # guest kernel re-probes CPU features at every boot.
  cpu = {
    mode = "host-model"
  }

  # Enable ACPI and APIC (required by modern guests), disable vmport
  # (VMware I/O port emulation, not needed, consistent with labs VM).
  features = {
    acpi    = true
    apic    = {}
    vm_port = { state = "off" }
  }

  # Shared memory for virtiofs (replaces the XML XSLT hack used in v0.8.x)
  memory_backing = {
    memory_source = { type = "memfd" }
    memory_access = { mode = "shared" }
  }

  devices = {
    # PCIe root port controllers, one per virtio device.
    # Without explicit pcie-root-ports, libvirt auto-generates the PCI topology
    # and may place virtio-pci devices on PCI bridges instead of PCIe links.
    # PCI bridges lack proper PCIe power management -> D3cold timeouts.
    # Each pcie-root-port creates a dedicated PCIe bus for its assigned device.
    # Modeled after the working "labs" VM at /kvm/labs/conf/labs.xml.
    controllers = [
      { type = "pci", model = "pcie-root", index = 0 },
      { type = "pci", model = "pcie-root-port", index = 1 },
      { type = "pci", model = "pcie-root-port", index = 2 },
      { type = "pci", model = "pcie-root-port", index = 3 },
      { type = "pci", model = "pcie-root-port", index = 4 },
      { type = "pci", model = "pcie-root-port", index = 5 },
      { type = "pci", model = "pcie-root-port", index = 6 },
      { type = "pci", model = "pcie-root-port", index = 7 },
      { type = "pci", model = "pcie-root-port", index = 8 },
    ]

    # Root disk on virtio (vda). With explicit pcie-root-port controllers,
    # virtio-pci devices exit D3cold correctly, the same configuration
    # proven in the labs VM (Ubuntu 24.04, q35, SeaBIOS, virtio disk + net).
    # Cloud-init ISO stays on SATA (cdrom on sata bus, same as labs VM).
    disks = [
      {
        source = {
          volume = {
            pool   = libvirt_pool.questr_pool.name
            volume = libvirt_volume.questr_disk.name
          }
        }
        target = {
          dev = "vda"
          bus = "virtio"
        }
        driver = {
          type    = "qcow2"
          discard = "unmap"
        }
      },
      {
        device = "cdrom"
        source = {
          volume = {
            pool   = libvirt_pool.questr_pool.name
            volume = libvirt_volume.questr_cloudinit.name
          }
        }
        target = {
          dev = "sda"
          bus = "sata"
        }
      }
    ]

    interfaces = [
      {
        type  = "network"
        model = { type = "virtio" }
        source = {
          network = {
            network = "vmnet"
          }
        }
        # Block apply until the guest has an IP: try DHCP lease first, then
        # qemu-guest-agent. A completed apply doubles as boot verification.
        wait_for_ip = {
          timeout = 300
          source  = "any"
        }
      }
    ]

    # virtiofs, replaces XSLT-injected <filesystem>
    filesystems = [
      {
        source = {
          mount = {
            dir = var.shared_host_path
          }
        }
        target = {
          dir = var.shared_guest_tag
        }
        access_mode = "passthrough"
        driver = {
          type  = "virtiofs"
          queue = 1024
        }
      }
    ]

    graphics = [
      {
        vnc = {
          auto_port = true
          listen    = "127.0.0.1"
        }
      }
    ]

    # QEMU agent channel
    channels = [
      {
        source = {
          unix = {
            mode = "bind"
          }
        }
        target = {
          virt_io = {
            name = "org.qemu.guest_agent.0"
          }
        }
      }
    ]

    # Serial console, written to a file on the host.
    #
    # We originally tried `pty = { path = "/dev/pts/0" }` (and previously
    # `target.type = "serial"` which is itself an invalid value). Both fail
    # in v0.9+:
    #
    #   1. `target.type = "serial"` is rejected by libvirt because "serial" is
    #      the XML element name, not a valid value for chr-target-type.
    #      (Bug already fixed in this file.)
    #
    #   2. `pty.path = "/dev/pts/0"` triggers a plan-vs-actual inconsistency:
    #      libvirt always allocates a fresh PTY regardless of the requested
    #      path, so planned "/dev/pts/0" never matches actual "/dev/pts/N".
    #      The provider raises:
    #        "Provider produced inconsistent result after apply"
    #        ".devices.serials[0].source.pty.path:
    #           was cty.StringVal("/dev/pts/0"),
    #           but now cty.StringVal("/dev/pts/22")"
    #      This is a documented provider bug (the provider's own error
    #      message acknowledges it).
    #
    # The robust workaround is a `file` source pointing at a literal host
    # path. libvirt does not allocate anything, planned == actual, and the
    # console log persists across VM reboots, strictly more useful for
    # debugging cloud-init and kernel issues. The log is co-located with
    # other operator-managed questr artifacts (/kvm/questr/{ssh, shared}/) so it survives the cleanup cycle and can be diffed across
    # runs.
    serials = [
      {
        source = {
          file = {
            path = "/kvm/questr/questr-staging-console.log"
          }
        }
        target = {
          port = 0
        }
      }
    ]
  }

  running = true

  depends_on = [
    libvirt_volume.questr_disk,
    libvirt_volume.questr_cloudinit
  ]
}
