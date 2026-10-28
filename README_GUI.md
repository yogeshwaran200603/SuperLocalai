# SuperLocal Desktop GUI

A modern, standalone Windows desktop application for **SuperLocal** (Local AI Assistant) built with **Python 3.12** and **PySide6 (Qt 6)**.

SuperLocal provides an autonomous desktop companion operating locally on your PC, featuring full computer-use automation, voice assistance, end-to-end task execution (Autopilot), single-player browser gaming (Poki Player & OpenFront RTS), and PC optimization.

---

## Highlights

- **Native Windows 11 Fluent UI**: Dark and light themes, 8px spacing grid, rounded cards, Segoe UI typography, and responsive animations.
- **Engine / UI Decoupling**: Thread-safe architecture (`core/engine.py` and `core/events.py`). The UI thread never blocks during heavy tasks or model calls.
- **Zero Terminal Dependency**: Runs as a windowed Windows app with system tray minimization, while preserving **100% backward compatibility** for CLI terminal mode (`python main.py`).
- **Safety & Permissions**: Interactive approval cards for sensitive actions (file deletion, passwords, app control). Global countdown timer defaults to **Deny**.
- **Secure Keyring Storage**: API keys are securely stored in Windows Credential Manager and never written to disk in plain text or logged.

---

## Global Hotkeys & Shortcuts

| Shortcut | Description |
|---|---|
| **Ctrl + Alt + Space** | **Quick Command Bar**: Spotlight-style floating input at screen center. |
| **Ctrl + Alt + Q** | **Global Kill Switch**: Halts all automation, cancels active tools, and stops background tasks immediately. |
| **Ctrl + Alt + P** | **Pause / Resume**: Pauses or resumes execution of the active task. |
| **F9** | **Push-to-Talk**: Hold or toggle microphone input for voice commands. |
| **Enter** | Send message / prompt in Chat. |
| **Shift + Enter** | Insert newline in Chat editor. |
| **Escape** | Dismiss Quick Command Bar or cancel active modal. |

---

## Application Workbenches

1. **💬 Chat**:
   - Multi-line chat input with auto-expanding editor, Shift+Enter for newlines.
   - Slash-command autocomplete palette (`/auto`, `/computer`, `/poki`, `/openfront`, `/optimize`, `/help`, etc.).
   - Live collapsible Activity Panel showing task timeline, step-by-step tools, and elapsed time.
   - Safety approval dialogs with risk badges, countdown timers, and "Always for session" option.

2. **⚡ Tasks (Autopilot)**:
   - One-click end-to-end task execution (`/auto <goal>`) and dry-run planning (`/auto --dry`).
   - Jobs list with past and current workspaces (`jobs/<date>-<slug>/`).
   - Detailed plan viewer, execution logs, and `REPORT.md` summary viewer.
   - One-click undo to revert all changes made during a job.

3. **🎙️ Voice**:
   - Large animated interactive voice orb with 4 states:
     - **Idle**: Soft pulsating ambient glow.
     - **Listening**: Expanding ripple waves (cyan/teal).
     - **Thinking**: Rotating orbital arcs (amber/gold).
     - **Speaking**: Sound-reactive pulse modulated by real-time RMS audio level.
   - Live interim/partial transcripts and final speech cards.
   - Microphone and speaker selectors with live volume meter.

4. **🎮 Games**:
   - **Poki Player**: Single-player browser game launcher with canvas capture loop and stats. Strictly enforces single-player rules to prevent unfair multiplayer botting.
   - **OpenFront RTS**: Localhost training workbench strictly bound to `http://localhost:*` instances with structured game state inspection (territory, population, gold, military).

5. **🚀 PC Optimizer**:
   - System Diagnostics dashboard with live CPU, RAM, and Disk utilization gauges and PC Health Score (0-100).
   - Safe cleaner preview with checkboxes for temp files, browser caches, and Recycle Bin.
   - Startup items impact manager.
   - Zero model calls: powered entirely by PowerShell, WMI, and psutil.

6. **🛠️ Skills & Tools**:
   - Active built-in tools registry.
   - Model Context Protocol (MCP) server statuses.
   - Desktop Macro Recorder: Record operator clicks and keystrokes into reusable local skills.

7. **📜 History**:
   - Searchable past sessions and action logs.
   - Complete transcript viewer with detailed arguments and execution duration.
   - One-click "Export to Markdown" report generator.

8. **⚙️ Settings & Setup Wizard**:
   - First-run onboarding wizard for permissions, consent, provider keys, and default workspace folder.
   - Keyring credential inputs with per-provider Test buttons.
   - Fallback `PROVIDER_ORDER` drag-and-drop / Move Up / Down reordering.
   - Offline full-system diagnostic self-test.

---

## Control Overlay Pill

When SuperLocal executes automation or computer-use actions, a floating translucent pill appears at the top center of the screen:
- **"SuperLocal is in control • Ctrl+Alt+Q to stop"**
- Current active step indicator (e.g. `[shell_exec]`).
- Quick **Pause** and **Stop** buttons.

---

## Running the Application

### GUI Desktop Mode
```powershell
python -m superlocal.gui
```

### CLI Terminal Mode (Preserved)
```powershell
python main.py
```

### Running Unit Tests
```powershell
python -m pytest tests/test_core_engine.py tests/test_stage2_gui.py tests/test_stage3_settings.py tests/test_stage4_voice_tray.py tests/test_stage5_pages.py -v
```

---

## Building the Installer

### Step 1: Compile Distribution via PyInstaller
```powershell
pyinstaller superlocal.spec --noconfirm
```
Produces the standalone one-folder distribution in `dist/SuperLocal/`.

### Step 2: Build Windows Installer via Inno Setup
Compile `installer.iss` using Inno Setup Compiler:
```powershell
iscc installer.iss
```
Generates `dist/installer/SuperLocal_Setup_v1.0.0.exe` with desktop shortcut, Start Menu shortcut, and "Start with Windows" option.
