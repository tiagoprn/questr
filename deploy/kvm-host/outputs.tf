# VM IP + ssh_command outputs. Provider v0.9 no longer exports an IP from
# libvirt_domain, so the address comes from the dedicated data source
# (DHCP leases, no guest agent needed). try() keeps plan/apply tolerant
# before the VM exists or has a lease; a completed apply already doubles as
# boot verification via main.tf's wait_for_ip.

data "libvirt_domain_interface_addresses" "questr_staging" {
  depends_on = [libvirt_domain.questr_staging]
  domain     = libvirt_domain.questr_staging.id
  source     = "lease"
}

locals {
  questr_staging_ip = try(
    [for a in data.libvirt_domain_interface_addresses.questr_staging.interfaces[0].addrs :
    a.addr if a.type == "ipv4"][0],
    null
  )
}

output "questr_staging_ip" {
  description = "IPv4 address of the staging VM on the vmnet NAT network"
  value       = local.questr_staging_ip
  depends_on  = [libvirt_domain.questr_staging]
}

output "ssh_command" {
  description = "Ready-to-run SSH command into the staging VM (key: /kvm/questr/ssh/questr_staging_ed25519)"
  value       = local.questr_staging_ip == null ? null : "ssh ubuntu@${local.questr_staging_ip} -i /kvm/questr/ssh/questr_staging_ed25519"
  depends_on  = [libvirt_domain.questr_staging]
}

output "shared_host_path" {
  description = "Host directory exposed to the VM"
  value       = var.shared_host_path
}

output "shared_guest_mount" {
  description = "Mount point inside the guest VM"
  value       = "/host/shared"
}