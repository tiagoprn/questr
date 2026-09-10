variable "shared_host_path" {
  description = "Host path to expose to the VM via virtiofs"
  type        = string
  default     = "/kvm/questr/shared"
}

variable "shared_guest_tag" {
  description = "virtiofs mount tag referenced inside the guest fstab"
  type        = string
  default     = "host_shared"
}

variable "vm_memory_mb" {
  description = "Guest RAM in MiB"
  type        = number
  default     = 2048
}

variable "vm_vcpu" {
  description = "Number of virtual CPUs"
  type        = number
  default     = 2
}

variable "disk_size_bytes" {
  description = "Maximum guest disk size in bytes (default: 80 GiB)"
  type        = number
  default     = 85899345920
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key injected via cloud-init"
  type        = string
  default     = "/kvm/questr/ssh/questr_staging_ed25519.pub"
}
