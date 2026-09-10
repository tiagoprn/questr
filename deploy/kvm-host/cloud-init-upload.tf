# Upload the cloud-init ISO into the pool
# v0.9+ requires a separate libvirt_volume to copy the generated ISO
resource "libvirt_volume" "questr_cloudinit" {
  name = "questr-init.iso"
  pool = libvirt_pool.questr_pool.name

  # Explicitly preserve ISO format so cloud-init detects the data source
  # via the "cidata" filesystem label. Without this, the provider may
  # default to qcow2 and break NoCloud detection.
  target = {
    format = {
      type = "iso"
    }
  }

  create = {
    content = {
      url = libvirt_cloudinit_disk.questr_init.path
    }
  }

  depends_on = [libvirt_cloudinit_disk.questr_init]
}
