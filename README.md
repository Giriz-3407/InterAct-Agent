# InterAct Desktop Agent

A lightweight desktop agent that provides a transparent Qt-based canvas overlay on Windows for remote cursor presence, click ripple animations, spotlight highlights, and freehand annotations. It connects to the InterAct web app via a local WebSocket server.

## Project Structure

The project has been structured into a production-ready layout:

```
InterAct-Agent/
│
├── main.py                # Main launcher and single-instance lock manager
│
├── src/                   # Python application package source code
│   ├── __init__.py        # Marks src as a package
│   ├── config.py          # Config loader (resolves agent.cfg)
│   ├── agent_version.py   # Version constants (single source of truth)
│   ├── ws_server.py       # Asyncio WebSocket server integrated with Qt
│   ├── ui.py              # Qt UI windows (Splash, Toast, Status Window)
│   └── overlay.py         # Transparent Qt painter canvas for overlay drawing
│
├── config/
│   └── agent.cfg          # User-editable configuration template
│
├── scripts/
│   └── test_client.py     # Local client simulator to mock cursor events
│
├── assets/                # Design assets (logos, icons, images)
├── installer/             # Build scripts for creating installers
├── logs/                  # Local log output folder (interact-agent.log)
├── dist/                  # PyInstaller compiled outputs (InterActAgent.exe)
├── build/                 # PyInstaller build cache
│
├── interact_agent.spec    # PyInstaller compiler specifications
├── requirements.txt       # Python package dependencies
├── RELEASE_CHECKLIST.md   # Deployment, packaging, and QA checklist
└── .gitignore             # Standard git ignore definitions
```

## Getting Started

### Development Mode

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Agent**:
   ```bash
   python main.py
   ```

3. **Run the Simulator (Test Client)**:
   ```bash
   python scripts/test_client.py
   ```

### Production Build

To compile a standalone Windows executable (`dist/InterActAgent.exe`):
```bash
pyinstaller --clean interact_agent.spec
```

Refer to [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) for detailed deployment steps.
