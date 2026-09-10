#!/usr/bin/env bash
#
# vm-full-destroy.sh — Tear down the questr VM and all its libvirt resources
# in a single idempotent command. Run it when you need a fully clean slate
# before `tofu apply`.
#
# Usage: sudo ./scripts/vm-full-destroy.sh [--dry-run]
#
#   --dry-run   Print what would be deleted without actually doing it.
#   -h, --help  Show this help.
#
# What this script removes (in order):
#   1. The questr-staging domain (destroy + undefine, if defined)
#   2. The libvirt volumes in questr_pool:
#        - questr-init.iso
#        - questr-disk.qcow2
#        - ubuntu-base.qcow2 (legacy, only if present from the pre-flatten design)
#   3. The questr_pool itself (destroy + undefine)
#   4. The local disk directory /kvm/questr/disks
#   5. Local OpenTofu state files in TF_DIR:
#        - .terraform/
#        - terraform.tfstate
#        - terraform.tfstate.backup
#        - .terraform.lock.hcl
#
# What this script PRESERVES (operator-managed, not tofu-managed):
#   - /kvm/questr/ssh/                     (SSH keys)
#   - /kvm/questr/shared/                  (shared directory for virtiofs)
#   - /kvm/questr/questr-staging-console.log    (live console log)
#
# After this script completes, run:
#   tofu init && tofu plan && tofu apply
#
# Idempotent: safe to re-run. Every step uses `|| true` so missing resources
# do not cause failure.
#

set -euo pipefail

VM_NAME="questr-staging"
POOL_NAME="questr_pool"
DISK_DIR="/kvm/questr/disks"
# Self-locating default: the terraform directory is this script's parent,
# so the script is correct on any host checkout without hardcoded paths.
TF_DIR="${TF_DIR:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)}"

DRY_RUN=false

usage() {
    sed -n '2,32p' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h | --help) usage ;;
        *)
            echo "Unknown argument: $1" >&2
            usage
            ;;
    esac
done

# ----- preflight -------------------------------------------------------------

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "[FATAL] required command not found: $1" >&2
        exit 2
    fi
}

require_cmd virsh

if [[ $EUID -ne 0 ]]; then
    echo "[FATAL] must run as root (sudo $0 ...)" >&2
    exit 2
fi

# ----- color output ----------------------------------------------------------

if [[ -t 1 ]]; then
    BOLD=$'\e[1m'
    DIM=$'\e[2m'
    RED=$'\e[31m'
    GRN=$'\e[32m'
    YLW=$'\e[33m'
    BLU=$'\e[34m'
    RST=$'\e[0m'
else
    BOLD=""
    DIM=""
    RED=""
    GRN=""
    YLW=""
    BLU=""
    RST=""
fi

section() { printf "\n%s== %s ==%s\n" "$BOLD$BLU" "$*" "$RST"; }
ok() { printf "%s[ok]%s %s\n" "$GRN" "$RST" "$*"; }
warn() { printf "%s[warn]%s %s\n" "$YLW" "$RST" "$*"; }
fail() { printf "%s[fail]%s %s\n" "$RED" "$RST" "$*"; }
info() { printf "%s[i]%s %s\n" "$DIM" "$RST" "$*"; }

# ----- dry-run wrapper -------------------------------------------------------
# `run CMD...` prints the command (and skips execution) under --dry-run.

run() {
    if [[ $DRY_RUN == true ]]; then
        printf "  %s[dry-run]%s %s\n" "$YLW" "$RST" "$*"
    else
        "$@"
    fi
}

# ----- main ------------------------------------------------------------------

printf "questr VM full teardown\n"
printf "  VM_NAME    = %s\n" "$VM_NAME"
printf "  POOL_NAME  = %s\n" "$POOL_NAME"
printf "  DISK_DIR   = %s\n" "$DISK_DIR"
printf "  TF_DIR     = %s\n" "$TF_DIR"
printf "  DRY_RUN    = %s\n" "$DRY_RUN"

# --- 1. domain ---------------------------------------------------------------
section "1. Domain: $VM_NAME"

if virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    info "destroying domain"
    run virsh destroy "$VM_NAME" || true
    ok "domain destroyed (or was not running)"

    info "undefining domain"
    run virsh undefine "$VM_NAME" || true
    ok "domain undefined"
else
    info "domain $VM_NAME not defined (skipped)"
fi

# --- 2. volumes in pool ------------------------------------------------------
section "2. Volumes in pool: $POOL_NAME"

if virsh pool-info "$POOL_NAME" >/dev/null 2>&1; then
    for vol in questr-init.iso questr-disk.qcow2 ubuntu-base.qcow2; do
        if virsh vol-info --pool "$POOL_NAME" "$vol" >/dev/null 2>&1; then
            info "deleting volume $vol"
            run virsh vol-delete --pool "$POOL_NAME" "$vol" || true
            ok "volume $vol deleted"
        else
            info "volume $vol not present (skipped)"
        fi
    done

    info "destroying pool"
    run virsh pool-destroy "$POOL_NAME" || true
    ok "pool destroyed (or was not active)"

    info "undefining pool"
    run virsh pool-undefine "$POOL_NAME" || true
    ok "pool undefined"
else
    info "pool $POOL_NAME not defined (skipped)"
fi

# --- 3. disk directory -------------------------------------------------------
section "3. Disk directory: $DISK_DIR"

if [[ -d $DISK_DIR ]]; then
    info "removing $DISK_DIR"
    run rm -rf "$DISK_DIR"
    ok "disk directory removed"
else
    info "disk directory not present (skipped)"
fi

# --- 4. tofu state files -----------------------------------------------------
section "4. OpenTofu state files in: $TF_DIR"

if [[ -d $TF_DIR ]]; then
    pushd "$TF_DIR" >/dev/null

    for path in .terraform terraform.tfstate terraform.tfstate.backup .terraform.lock.hcl; do
        if [[ -e $path ]]; then
            info "removing $path"
            run rm -rf "$path"
            ok "$path removed"
        else
            info "$path not present (skipped)"
        fi
    done

    popd >/dev/null
else
    warn "TF_DIR not found: $TF_DIR (tofu state files skipped)"
fi

# --- summary -----------------------------------------------------------------
section "Result"

if [[ $DRY_RUN == true ]]; then
    warn "DRY RUN — nothing was actually deleted"
    info "re-run without --dry-run to apply"
else
    ok "teardown complete"
fi

echo ""
info "preserved (operator-managed, not tofu-managed):"
echo "  - /kvm/questr/ssh/                       (SSH keys)"
echo "  - /kvm/questr/shared/                    (shared directory)"
echo "  - /kvm/questr/questr-staging-console.log      (live console log)"
echo ""

if [[ $DRY_RUN != true ]]; then
    info "next step: tofu init && tofu plan && tofu apply"
fi
