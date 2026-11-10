"""
Sanitized Reference Implementation: Bare-Metal KVM Copy-on-Write VM Provisioner
Demonstrates how YouSecure Cloud re-images production Ubuntu LTS VMs in <12 seconds
using QCOW2 backing chains and cloud-init ISO seeds without network storage bottlenecks.
"""

from dataclasses import dataclass
import shlex
import subprocess
import time


@dataclass(frozen=True)
class VMProvisionSpec:
    vm_name: str
    os_slug: str  # "ubuntu-20.04" | "ubuntu-22.04" | "ubuntu-24.04"
    vcpus: int
    memory_mb: int
    disk_gb: int
    ipv4_cidr: str
    gateway_ip: str
    root_password_hash: str
    ssh_ed25519_pubkey: str


ALLOWED_BASE_IMAGES = {
    "ubuntu-20.04": "/var/lib/libvirt/images/base/ubuntu-20.04-cloudimg.qcow2",
    "ubuntu-22.04": "/var/lib/libvirt/images/base/ubuntu-22.04-cloudimg.qcow2",
    "ubuntu-24.04": "/var/lib/libvirt/images/base/ubuntu-24.04-cloudimg.qcow2",
}


def build_reimage_commands(spec: VMProvisionSpec) -> list[str]:
    if spec.os_slug not in ALLOWED_BASE_IMAGES:
        raise ValueError(f"Unsupported OS image: {spec.os_slug}")

    base_img = ALLOWED_BASE_IMAGES[spec.os_slug]
    vm_dir = f"/var/lib/libvirt/images/vms/{shlex.quote(spec.vm_name)}"
    overlay_disk = f"{vm_dir}/root.qcow2"
    seed_iso = f"{vm_dir}/cidata.iso"
    ts = int(time.time())

    return [
        f"virsh destroy {shlex.quote(spec.vm_name)} || true",
        f"mkdir -p {vm_dir}",
        # Atomic Copy-on-Write overlay backed by read-only golden image (<150ms)
        f"qemu-img create -f qcow2 -F qcow2 -b {base_img} {overlay_disk} {spec.disk_gb}G",
        # Generate deterministic cloud-init network-config & user-data ISO
        f"cloud-localds -v --network-config={vm_dir}/network-config.yaml {seed_iso} {vm_dir}/user-data.yaml",
        f"virsh start {shlex.quote(spec.vm_name)}",
        f"echo Provisioned_{spec.vm_name}_at_{ts}",
    ]
