"""
Production Pattern: Live Atomic External Snapshot & 1-Click XML Restore in Libvirt
Solves Libvirt's upstream limitation where `virsh snapshot-revert` is unsupported
for external `--disk-only --atomic` snapshots, and prevents self-referencing
`<backingStore>` XML chains during restore.
"""

import shlex
import xml.etree.ElementTree as ET


def create_live_external_snapshot_cmd(vm_name: str, snap_name: str, overlay_path: str) -> str:
    """
    Creates a live, non-disruptive external disk-only snapshot on a running qcow2 VM.
    Active writes pivot atomically to `overlay_path` while the base disk becomes read-only.
    """
    return (
        f"virsh snapshot-create-as --domain {shlex.quote(vm_name)} "
        f"--name {shlex.quote(snap_name)} "
        f"--disk-only --atomic "
        f"--diskspec vda,snapshot=external,file={shlex.quote(overlay_path)}"
    )


def patch_domain_xml_for_snapshot_restore(
    xml_text: str,
    target_dev: str,
    restore_to_path: str,
) -> str:
    """
    Repoint `<disk target=target_dev>`'s `<source file>` back to `restore_to_path`
    (the pre-snapshot base disk) and drop its `<backingStore>` subtree.

    Why dropping `<backingStore>` is critical:
    A naive string-replace of the source path leaves the overlay's `<backingStore>`
    pointing at `restore_to_path` one level down, creating a malformed,
    self-referencing backing chain that QEMU refuses to boot. Removing `<backingStore>`
    forces Libvirt to re-derive the true chain from the qcow2 header at start time.
    """
    root = ET.fromstring(xml_text)
    patched = False

    for disk in root.findall(".//devices/disk"):
        target = disk.find("target")
        if target is not None and target.get("dev") == target_dev:
            source = disk.find("source")
            if source is None:
                raise RuntimeError(f"Disk target '{target_dev}' has no <source> element")
            source.set("file", restore_to_path)
            source.attrib.pop("index", None)

            backing = disk.find("backingStore")
            if backing is not None:
                disk.remove(backing)
            patched = True

    if not patched:
        raise RuntimeError(f"Could not find disk target '{target_dev}' in domain XML")

    return ET.tostring(root, encoding="unicode")
