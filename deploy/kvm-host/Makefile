.PHONY: help create recreate poweron poweroff pause resume reboot monitor console status status-full ssh provision provision-verify baseline baseline-verify autostart-on autostart-off autostart-status update-disk-template-from-current

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
	sudo virsh start questr-staging

poweroff: ## Force power off the VM (virsh destroy)
	sudo virsh destroy questr-staging

reboot: ## Graceful ACPI reboot
	sudo virsh reboot questr-staging

pause: ## Pause (suspend) the VM
	sudo virsh suspend questr-staging

resume: ## Resume a paused VM
	sudo virsh resume questr-staging

monitor: ## Watch the live serial console log (read-only)
	sudo tail -F /kvm/questr/questr-staging-console.log

console: ## Attach to the serial console (interactive, Ctrl+] to detach)
	sudo virsh console questr-staging

status: ## Show VM status
	@sudo virsh dominfo questr-staging 2>/dev/null || echo "VM not defined"

status-full: ## Show detailed VM status (state, CPU, memory, disk, IP)
	@echo "=== State ==="
	@sudo virsh dominfo questr-staging 2>/dev/null || echo "VM not defined"
	@echo ""
	@echo "=== vCPUs ==="
	@sudo virsh vcpuinfo questr-staging 2>/dev/null || true
	@echo ""
	@echo "=== Disks ==="
	@sudo virsh domblklist questr-staging 2>/dev/null || true
	@echo ""
	@echo "=== Network ==="
	@sudo virsh domifaddr questr-staging 2>/dev/null || true
	@echo ""
	@sudo virsh net-dhcp-leases vmnet 2>/dev/null | grep -E 'questr-staging|Expiry' || echo "(no leases)"

ssh: ## SSH into the VM (interactive IP selection via fzf)
	@IP=$$(sudo virsh net-dhcp-leases vmnet \
		| awk '/questr-staging/ {print $$5}' \
		| cut -d/ -f1 \
		| fzf --header="Select VM IP" --prompt="questr-staging > "); \
	if [ -n "$$IP" ]; then \
		echo "Connecting to $$IP..."; \
		ssh ubuntu@"$$IP" -i /kvm/questr/ssh/questr_staging_ed25519; \
	else \
		echo "No IP selected or no lease found."; \
	fi

baseline: ## Provision the VM baseline (Docker, unattended upgrades) via Ansible
	@IP=$$(sudo virsh net-dhcp-leases vmnet \
		| awk '/questr-staging/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_staging_ed25519 \
			--vault-password-file /kvm/questr/vault-password \
			vm-baseline.yml $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi

baseline-verify: ## Run only the baseline verification tasks
	@IP=$$(sudo virsh net-dhcp-leases vmnet \
		| awk '/questr-staging/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_staging_ed25519 \
			--vault-password-file /kvm/questr/vault-password \
			vm-baseline.yml --tags verify $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi

autostart-on: ## Enable autostart for the VM (start on host boot)
	sudo virsh autostart questr-staging

autostart-off: ## Disable autostart for the VM
	sudo virsh autostart --disable questr-staging

autostart-status: ## Show autostart status (enabled/disabled)
	@sudo virsh dominfo questr-staging 2>/dev/null | awk '/^Autostart:/ {print $$2 "d"}' || echo "VM not defined"

update-disk-template-from-current: ## Save current disk as recreate template
	@STATE=$$(sudo virsh domstate questr-staging 2>/dev/null || echo "undefined"); \
	if [ "$$STATE" = "running" ]; then \
		echo "ERROR: questr-staging is still running. Run 'make poweroff' first."; \
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
	@IP=$$(sudo virsh net-dhcp-leases vmnet \
		| awk '/questr-staging/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_staging_ed25519 \
			setup-lang-toolchain.yml $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi

provision-verify: ## Run only the verification tasks (cargo-update)
	@IP=$$(sudo virsh net-dhcp-leases vmnet \
		| awk '/questr-staging/ {print $$5}' \
		| cut -d/ -f1); \
	if [ -n "$$IP" ]; then \
		cd ansible && \
		ansible-playbook $(ANSIBLE_VERBOSITY) -i "$$IP," -u ubuntu \
			--private-key /kvm/questr/ssh/questr_staging_ed25519 \
			setup-lang-toolchain.yml --tags verify $(ANSIBLE_EXTRA_VARS); \
	else \
		echo "No IP found. Is the VM running?"; \
	fi
