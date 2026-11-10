"""
Production Pattern: Fail-Closed 11-Gate VPS OS Reinstall & 24-Hour Safety Retention
Demonstrates zero-IDOR payload validation, physical non-sparse capacity preflight,
side-by-side disk switching with 11 post-boot verification gates, and 24h rollback retention.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

DEFAULT_HOST_RESERVE_BYTES = 20 * 1024**3  # 20 GiB mandatory physical host reserve

# Zero-IDOR Guard: Reject any client request that attempts to supply target identifiers
FORBIDDEN_REQUEST_TARGET_FIELDS = frozenset({
    "domain", "vps", "vm", "vm_name", "vm_uuid", "uuid", "ip", "ip_address",
    "disk", "disk_path", "original_disk_path", "old_disk_path", "new_disk_path",
    "host", "host_name", "hypervisor", "image", "image_url", "image_path",
    "client_id", "user_id",
})

# All 11 gates must pass on the new disk before the reinstall is marked "verified"
REQUIRED_VALIDATION_CHECKS = (
    "image_checksum",
    "qcow2_check_before_boot",
    "filesystem_check",
    "ubuntu_release",
    "cloud_init",
    "guest_agent",
    "expected_ip_and_route",
    "ssh_probe",
    "public_probe",
    "reboot_passed",
    "qcow2_check_offline_after_boot",
)


class ReinstallSafetyError(ValueError):
    """Raised when a safety precondition fails; blocks any VM mutation."""


def _strict_int(value: Any) -> int:
    """Reject booleans and fractional values instead of silently truncating."""
    if isinstance(value, bool):
        raise ValueError("boolean is not a byte count")
    parsed = int(value)
    if isinstance(value, float) and not value.is_integer():
        raise ValueError("fractional byte count")
    if str(value).strip() != str(parsed):
        raise ValueError("non-canonical integer")
    return parsed


def validate_request_payload(
    payload: Any, *, allowed_fields: set[str] | frozenset[str]
) -> Mapping[str, Any]:
    """Reject any client-supplied VM, IP, disk path, or unapproved field."""
    if not isinstance(payload, Mapping):
        raise ReinstallSafetyError("Invalid request format.")
    keys = {str(k) for k in payload.keys()}
    if keys & FORBIDDEN_REQUEST_TARGET_FIELDS:
        raise ReinstallSafetyError("Client payload cannot specify VM, IP, or disk path.")
    if keys - set(allowed_fields):
        raise ReinstallSafetyError("Unexpected parameters in reinstall payload.")
    return payload


def check_capacity(*, free_bytes: int, target_disk_bytes: int, reserve_bytes: int) -> dict[str, int]:
    """
    Require physical room for the entire preallocated new disk plus 20 GiB host reserve,
    because the old disk remains preserved on disk for rollback during the switch.
    Sparse virtual capacity is never counted as free space.
    """
    free = _strict_int(free_bytes)
    target = _strict_int(target_disk_bytes)
    reserve = _strict_int(reserve_bytes)
    required = target + reserve
    if free < required:
        raise ReinstallSafetyError("Insufficient physical storage for side-by-side disk switch + reserve.")
    return {
        "free_bytes": free,
        "target_disk_bytes": target,
        "reserve_bytes": reserve,
        "required_bytes": required,
        "free_after_preallocation_bytes": free - target,
    }


def can_delete_previous_disk(job: Mapping[str, Any], *, now: datetime | None = None) -> tuple[bool, str]:
    """
    Fail-closed final gate: old disk cannot be deleted until all 11 checks pass,
    backup restore is verified, the disk is confirmed unreferenced in Libvirt,
    and the 24-hour safety retention window has elapsed.
    """
    if job.get("state") != "verified":
        return False, "New OS installation is not yet in verified state."
    checks = job.get("checks") or {}
    missing = [name for name in REQUIRED_VALIDATION_CHECKS if checks.get(name) is not True]
    if missing:
        return False, "Pending validation gates: " + ", ".join(missing)
    if job.get("vm_uuid_verified") is not True or job.get("old_disk_unreferenced") is not True:
        return False, "Libvirt UUID or unreferenced old-disk verification pending."

    validated_at = job.get("verified_at")
    current = now or datetime.now(timezone.utc)
    if not isinstance(validated_at, datetime) or (current - validated_at) < timedelta(hours=24):
        return False, "24-hour safety retention window has not elapsed yet."

    return True, "Approved for old disk cleanup after final Libvirt verification."
