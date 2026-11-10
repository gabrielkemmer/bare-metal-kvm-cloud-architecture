"""
Sanitized Reference Implementation: WebSocket-to-SSH PTY Root Console Bridge
Streams raw xterm-256color PTY frames between browser xterm.js and isolated KVM guest VMs
without exposing public SSH bastions or installing guest agents.
"""

import select
import socket
import paramiko


def bridge_websocket_to_vm_pty(ws, vm_internal_ip: str, ssh_pkey: paramiko.PKey) -> None:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=vm_internal_ip,
        port=22,
        username="root",
        pkey=ssh_pkey,
        timeout=8.0,
        look_for_keys=False,
        allow_agent=False,
    )
    chan = client.invoke_shell(term="xterm-256color", width=120, height=36)
    chan.setblocking(0)

    try:
        while not chan.closed:
            r, _, _ = select.select([chan], [], [], 0.015)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                ws.send(data.decode("utf-8", errors="replace"))

            incoming = ws.receive(timeout=0.005)
            if incoming is not None:
                chan.send(incoming)
    except socket.error:
        pass
    finally:
        chan.close()
        client.close()
