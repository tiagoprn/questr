resource "libvirt_pool" "questr_pool" {
  name = "questr_pool"
  type = "dir"

  target = {
    path = "/kvm/questr/disks"
  }
}
