# DEBUG VERSION: data source + questr_vm_ip + ssh_command outputs removed
# because they would fail without an IP. Restore the original once the
# issue is fixed.

output "shared_host_path" {
  description = "Host directory exposed to the VM"
  value       = var.shared_host_path
}

output "shared_guest_mount" {
  description = "Mount point inside the guest VM"
  value       = "/host/shared"
}
