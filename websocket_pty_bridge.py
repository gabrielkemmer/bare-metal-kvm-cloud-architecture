"""
Educational Reference Pattern: Non-Blocking PTY Multiplexing for xterm.js
Illustrates how browser terminals achieve <20ms latency using raw binary PTY frames.
Note: Standalone educational snippet — does not reflect internal production stack.
"""

import select


def stream_pty_frames(pty_channel, websocket_stream) -> None:
    """
    Conceptual event loop bridging a non-blocking pseudo-terminal (PTY)
    file descriptor with a binary WebSocket stream.
    """
    pty_channel.setblocking(0)
    while not pty_channel.closed:
        readable, _, _ = select.select([pty_channel], [], [], 0.015)
        if pty_channel in readable:
            chunk = pty_channel.recv(4096)
            if not chunk:
                break
            websocket_stream.send(chunk)

        client_input = websocket_stream.receive_nonblocking()
        if client_input:
            pty_channel.send(client_input)
