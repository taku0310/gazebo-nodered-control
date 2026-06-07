#!/usr/bin/env bash
set -e

XVFB_RES="${XVFB_RESOLUTION:-1280x800x24}"
VNC_PORT="${VNC_PORT:-5900}"
WEB_PORT="${WEB_PORT:-8080}"

echo "[entrypoint] Xvfb on ${DISPLAY} (${XVFB_RES})"
Xvfb "${DISPLAY}" -screen 0 "${XVFB_RES}" -ac +extension GLX +render -noreset \
    >/var/log/xvfb.log 2>&1 &

# Wait until X server is ready (≈3 s budget).
for _ in $(seq 1 30); do
    if xdpyinfo -display "${DISPLAY}" >/dev/null 2>&1; then break; fi
    sleep 0.1
done

echo "[entrypoint] x11vnc on :${VNC_PORT}"
x11vnc -display "${DISPLAY}" -nopw -forever -shared \
       -rfbport "${VNC_PORT}" -quiet \
    >/var/log/x11vnc.log 2>&1 &

echo "[entrypoint] noVNC websockify on :${WEB_PORT} (open /vnc.html in a browser)"
websockify --web=/usr/share/novnc "${WEB_PORT}" "localhost:${VNC_PORT}" \
    >/var/log/novnc.log 2>&1 &

source /opt/ros/humble/setup.bash

echo "[entrypoint] launching: $*"
exec "$@"
