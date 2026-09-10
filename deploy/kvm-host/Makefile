.PHONY: help create recreate poweron poweroff pause resume reboot monitor console status status-full ssh provision provision-verify autostart-on autostart-off autostart-status update-disk-template-from-current

# Default target
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-12s\033[0m %s\n", $$1, $$2}'

create: ## Create the VM for the first time
	sudo tofu init
	sudo tofu apply
	echo "Now, run manually 'make monitor' to see the logs of the first boot process (which will install the packages through cloud-init)."

recreate: ## Tear down and rebuild the VM from scratch
	sudo ./scripts/vm-full-destroy.sh
	sudo tofu init
	sudo tofu apply
	echo "Now, run manually 'make monitor' to see the logs of the first boot process (which will install the packages through cloud-init)."

poweron: ## Power on the VM (if defined but not running)
	sudo virsh start questr-vm

poweroff: ## Force power off the VM (virsh destroy)
	sudo virsh destroy questr-vm

reboot: ## Graceful ACPI reboot
	sudo virsh reboot questr-vm

pause: ## Pause (suspend) the VM
	sudo virsh suspend questr-vm

resume: ## Resume a paused VM
	sudo virsh resume questr-vm

monitor: ## Watch the live serial console log (read-only)
	sudo tail -F /kvm/questr/questr-vm-console.log

console: ## Attach to the serial console (interactive, Ctrl+] to detach)
	sudo virsh console questr-vm

status: ## Show VM status
	@sudo virsh dominfo questr-vm 2>/dev/null || echo "VM not defined"

status-full: ## Show detailed VM status (state, CPU, memory, disk, IP)
	@echo "=== State ==="
	@sudo virsh dominfo questr-vm 2>/dev/null || echo "VM not defined"
	@echo ""
	@echo "=== vCPUs ==="
	@sudo virsh vcpuinfo questr-vm 2>/dev/null || true
	@echo ""
	@echo "=== Disks ==="
	@sudo virsh domblklist questr-vm 2>/dev/null || true
	@echo ""
	@echo "=== Network ==="
	@sudo virsh domifaddr questr-vm 2>/dev/null || true
	@echo ""
	@sudo virsh net-dhcp-leases default 2>/dev/null | grep -E 'questr-vm|Expiry' || echo "(no leases)"

ssh: ## SSH into the VM (interactive IP selection via fzf)
	@IP=$$(sudo virsh net-dhcp-leases default \
		| awk '/questr-vm/ {print $$5}' \
		| cut -d/ -f1 \
		| fzf --header="Select VM IP" --prompt="questr-vm > "); \
	if [ -n "$$IP" ]; then \
		echo "Connecting to $$IP..."; \
		ssh ubuntu@"$$IP" -i /kvm/questr/ssh/questr_vm_ed25519; \
	else \
		echo "No IP selected or no lease found."; \
	fi

autostart-on: ## Enable autostart for the VM (start on host boot)
	sudo virsh autostart questr-vm

autostart-off: ## Disable autostart for the VM
	sudo virsh autostart --disable questr-vm

autostart-status: ## Show autostart status (enabled/disabled)
	@sudo virsh dominfo questr-vm 2>/dev/null | awk '/^Autostart:/ {print $$2 "d"}' || echo "VM not defined"

update-disk-template-from-current: ## Save current disk as recreate template
	@STATE=$$(sudo virsh domstate questr-vm 2>/dev/null || echo "undefined"); \
	if [ "$$STATE" = "running" ]; then \
		echo "ERROR: questr-vm is still running. Run 'make poweroff' first."; \
		exit 1; \
	fi
	@echo "Freezing /kvm/questr/disks/questr-disk.qcow2 -> templates master..."
	sudo qemu-img convert -O qcow2 -p \
		/kvm/questr/disks/questr-disk.qcow2 \
		/kvm/questr/templates/disks/questr-disk-flat.qcow2
	sudo qemu-img check /kvm/questr/templates/disks/questr-disk-flat.qcow2
	@echo "Done. The next 'make recreate' will upload this new master."

ANSIBLE_EXTRA_VARS ?=
ANSIBLE_VERBOSITY ?= -vvv

provision: ## Provision the VM with language toolchains via Ansible
	@IP=$$(sudo virsh net-dhcp-leases default \
		| awk '/questr-vm/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible/setup-lang-toolchain && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_vm_ed25519 \
			site.yml $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi

provision-verify: ## Run only the verification tasks (cargo-update)
	@IP=$$(sudo virsh net-dhcp-leases default \
		| awk '/questr-vm/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible/setup-lang-toolchain && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_vm_ed25519 \
			site.yml --tags verify $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi
