resource "libvirt_cloudinit_disk" "questr_init" {
  name = "questr-init.iso"

  user_data = templatefile("${path.module}/cloud-init-userdata.yaml", {
    ssh_public_key = trimspace(file(var.ssh_public_key_path))
  })

  # meta_data is REQUIRED in the v0.9+ provider
  meta_data = <<-EOF
    instance-id: questr-staging-001
    local-hostname: questr-staging
  EOF

  # Use a match pattern instead of a hard-coded interface name.
  # On modern systemd the NIC is named enp1s0 / ens3 / eno1 — not eth0.
  # The pattern "en*" matches all predictable interface names.
  network_config = <<-EOF
    version: 2
    ethernets:
      default:
        match:
          name: en*
        dhcp4: true
  EOF
}
