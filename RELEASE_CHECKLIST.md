# InterAct Desktop Agent — Release Preparation & Packaging Guide

This guide describes how to build, run, package, and troubleshoot the local **InterAct Desktop Agent** executable for Windows.

---

## Files Modified / Added for Deployment Hardening
- **`agent/agent_version.py`**: Central version and capability configurations.
- **`agent/config.py`**: Resolves port settings from environment variables (`INTERACT_AGENT_PORT`), `agent.cfg`, or defaults.
- **`agent/agent.cfg`**: Editable INI config file bundled next to the executable.
- **`agent/ws_server.py`**: Sends `agent_info` handshake immediately on connection; routes high-frequency logs to `DEBUG`.
- **`agent/main.py`**: Resolves config at startup; configures structured logging to both a file (`%LOCALAPPDATA%/InterAct/logs/interact-agent.log` when compiled) and standard error.
- **`agent/interact_agent.spec`**: PyInstaller spec file defining hidden imports and output configurations.
- **`frontend/src/lib/desktopAgent.ts`**: Adds exponential backoff reconnect, handshake verification, compatibility checks, and status callbacks.
- **`frontend/src/components/AgentStatusIndicator.tsx`**: React component displaying agent connection states.
- **`frontend/src/pages/RoomPage.tsx`**: Surfaces the connection status bar in the room view header for hosts.

---

## 1. Setup for Packaging (Developer Steps)

To compile the agent as a standalone Windows executable (`.exe`), ensure you have a Python environment ready (Python 3.10+ recommended) and run:

```bash
# Navigate to the agent folder
cd agent

# Install dependencies and pyinstaller
pip install -r requirements.txt
```

---

## 2. Packaging Steps

Build the single-file executable using the audited PyInstaller spec:

```bash
# Run PyInstaller with the spec file
pyinstaller --clean interact_agent.spec
```

Once complete:
- The compiled executable will be located in **`agent/dist/InterActAgent.exe`**.
- Copy the configuration template `agent.cfg` to the same folder as `InterActAgent.exe` so testers can customize their port settings.

---

## 3. Tester Setup Instructions (No Python Required)

1. **Extract/Download**: Download the `InterActAgent.exe` and `agent.cfg` files and place them in the same directory.
2. **Launch**: Double-click `InterActAgent.exe` to run the agent.
   - Note: Because it runs with `console=False`, there will be no command line console window shown. The transparent Qt overlay will run invisibly in the background.
3. **Verify running status**: 
   - Open the InterAct web app in a browser on the same machine.
   - Join a room as a **Host**.
   - Check the top header of the Room workspace. You should see a green **`🟢 Agent Connected`** status indicator.
4. **Log file location**: All logs are written to:
   - `%LOCALAPPDATA%\InterAct\logs\interact-agent.log` (e.g., `C:\Users\<username>\AppData\Local\InterAct\logs\interact-agent.log`).

---

## 4. Handshake Payload Reference

Immediately upon establishing a WebSocket connection, the agent sends the following handshake to the browser:

```json
{
  "event": "agent_info",
  "version": "1.0.0",
  "protocol_version": 1,
  "capabilities": [
    "cursor_presence",
    "annotations",
    "spotlight"
  ],
  "platform": "windows",
  "agent_port": 8765
}
```

If the browser's `BROWSER_PROTOCOL_VERSION` doesn't match the agent's `protocol_version`, the browser transitions to `incompatible`, shuts down the socket connection immediately, and displays **`⚠️ Agent Version Mismatch`**.

---

## 5. Troubleshooting Guide

### Issue: Status shows `🔴 Agent Disconnected`
- Ensure `InterActAgent.exe` is running in your Task Manager.
- Ensure the port in `agent.cfg` (default `8765`) matches `VITE_AGENT_PORT` in your browser's `.env` configuration.
- Check if another application is using port `8765` by running `netstat -ano | findstr 8765`. If it is in use, modify `agent.cfg` to use a different port (e.g. `8768`), restart the agent, and set `VITE_AGENT_PORT=8768` in the browser.

### Issue: Status shows `⚠️ Agent Version Mismatch`
- You are running an outdated version of the Desktop Agent executable relative to the browser interface.
- Close the current agent, download the latest compiled `InterActAgent.exe`, start it, and refresh the browser page.

### Reading Logs
- Open `%LOCALAPPDATA%\InterAct\logs\interact-agent.log` to view errors, warnings, and system logs.

---

## 6. Known Limitations

- **Localhost Only**: The architecture relies on same-machine loopback address communication (`127.0.0.1` / `localhost`). The agent will not accept remote websocket connections over external interfaces for security reasons.
- **Multiple Instances**: Only one instance of the agent can bind to a given port. Launching a second instance will log a port binding error in the log file and shut down immediately.
