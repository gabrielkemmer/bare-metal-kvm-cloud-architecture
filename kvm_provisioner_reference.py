"""
Educational Reference Pattern: Standard Linux KVM Copy-on-Write (CoW) Provisioning
Illustrates the architectural concept of backing-file overlays vs. full disk copies.
Note: Standalone educational snippet — does not reflect internal production paths or stack.
"""

from dataclasses import dataclass
import shlex


@dataclass(frozen=True)
class GuestSpec:
    domain_id: str
    os_profile: str
    vcpus: int
    memory_mb: int
    disk_gb: int


def build_cow_overlay_example(spec: GuestSpec) -> list[str]:
    """
    Demonstrates why Copy-on-Write (qcow2 backing file) boots in milliseconds
    compared to copying multi-gigabyte raw disk images across network storage.
    """
    safe_id = shlex.quote(spec.domain_id)
    return [
        # 1. Create a lightweight Copy-on-Write overlay pointing to a read-only base image
        f"qemu-img create -f qcow2 -F qcow2 -b /images/golden/{shlex.quote(spec.os_profile)}.qcow2 /volumes/{safe_id}.qcow2 {spec.disk_gb}G",
        # 2. Attach ephemeral cloud-init seed ISO for first-boot network & SSH key injection
        f"cloud-localds /volumes/{safe_id}-seed.iso user-data.yaml",
    ]
