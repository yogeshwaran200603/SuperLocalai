# Astra-Local: Windows AI Assistant for CMD & PowerShell

Astra-Local (Superlocal) is an autonomous, quota-friendly AI assistant designed specifically for Windows environments running directly within Command Prompt (`cmd.exe`) and PowerShell (`powershell.exe`). Powered by a multi-provider fallback engine (**Ollama**, **Groq**, **OpenRouter**, and **Google Gemini**), Astra translates natural language requests into concrete PC actions with zero quota anxiety.

---

## Architecture & Workflow

```
       User Prompt (CMD / PowerShell / Hotkey)
                         │
                         ▼
             Local-First Fast Path (0 API Calls)
         (Shortcuts, Direct Apps, URLs, Folders, Slash Commands)
                         │
         ┌───────────────┴───────────────┐
   [Matched]                       [Unmatched]
         │                               │
         ▼                               ▼
    Local Action                 10-Min SQLite Cache
(Explorer, App, Discord)                 │
                                 ┌───────┴───────┐
                           [Hit: 0 Calls]  [Miss]
                                 │               │
                                 ▼               ▼
                            Cache Return   Multi-Provider Chain
                                           (Ollama -> Groq -> OpenRouter -> Gemini)
                                                 │
                                                 ▼
                                        Agent Execution Loop
                                        (Max 8 Steps, Batched Calls)
                                                 │
                                                 ▼
                                        Local Summary Builder
                                           (0 Extra Calls)
```

---

## 1. Multi-Provider Engine (Never Depend on One Quota)

Astra-Local features a pluggable multi-provider architecture with a unified interface (`chat`, `is_available`, `health_check`, `list_models`).

### Default Provider Order
```env
PROVIDER_ORDER=ollama_local,groq,openrouter,gemini
```
Astra automatically skips any provider whose API key or service is missing. It only transitions to the next provider upon experiencing a true `429 (Rate Limit/Quota)`, `503/504 (Server Error)`, network timeout, or connection refusal. Astra **never retry-loops on daily quota errors**.

### Supported Providers
1. **Ollama Local (`ollama_local`)**:
   - Zero-cost, unlimited local offline execution at `http://localhost:11434`.
   - Default model: `qwen3:4b` (or `llama3.1:8b`, `qwen2.5:7b`).
   - Automatic detection: if offline, Astra checks whether the Ollama process is running, attempts to launch it once, waits up to 10 seconds, and displays clear actionable instructions.
2. **Groq (`groq`)**:
   - Ultra-fast cloud inference running at 500+ tokens/sec on LPU hardware.
   - Default model: `llama-3.3-70b-versatile`.
   - Endpoint: `https://api.groq.com/openai/v1`.
   - **Add a free key in 2 minutes**: Sign up at [https://console.groq.com](https://console.groq.com), generate an API key with zero credit card required, and paste it into `.env` as `GROQ_API_KEY`.
3. **OpenRouter (`openrouter`)**:
   - Universal API gateway providing access to hundreds of open-source and proprietary models.
   - Default model: `meta-llama/llama-3.3-70b-instruct` (or `anthropic/claude-3.5-haiku`).
   - Endpoint: `https://openrouter.ai/api/v1`.
   - **Add a free key in 2 minutes**: Sign up at [https://openrouter.ai](https://openrouter.ai), create a key, and set `OPENROUTER_API_KEY` in `.env`.
4. **Google Gemini (`gemini`)**:
   - Multimodal engine using `google-genai` SDK and Gemini 3 models (`gemini-3.8-flash`, `gemini-3.5-flash-lite`).
   - Strict protocol adherence for parallel function calling.
   - `thought_signature` preservation for Gemini 3 function call turn responses.

### Small-Model Friendly Optimizations
For local models (Ollama) and open models (Groq/OpenRouter), Astra optimizes tool invocation:
- **Compact System Prompt**: Concise instructions minimizing token overhead.
- **Keyword Tool Filtering (Max 12 Tools)**: Analyzes the user request keywords and exposes only the top 12 relevant tools, preventing small models from getting confused by large schemas.
- **Calibrated Temperature (0.2)**: Encourages deterministic tool generation.
- **JSON Schema Pre-Validation**: Tool arguments are validated against OpenAPI schemas before execution.
- **Seamless Provider Switching**: When failing over mid-task, Astra converts the conversation history into plain text summaries of tool calls and results, ensuring raw provider-specific parts or thought signatures never leak across providers.

---

## 2. Ollama Setup & Troubleshooting

### Installation
1. Download Ollama from [https://ollama.com/download/windows](https://ollama.com/download/windows).
2. Run the installer and refresh your CMD or PowerShell path (or restart your terminal).
3. Pull the recommended compact model:
   ```cmd
   ollama pull qwen3:4b
   ```
4. Verify Ollama is running:
   ```cmd
   curl http://localhost:11434/api/tags
   ```

### Handling 503 Registry Timeout on `ollama pull`
If you encounter a `503` or timeout error while pulling models from the Ollama registry:
1. Ensure your network connection or VPN is stable.
2. Retry pulling during off-peak times or use an alternative model tag:
   ```cmd
   ollama pull qwen2.5:3b
   # or
   ollama pull llama3.2:3b
   ```
3. Update `OLLAMA_MODEL` in your `.env` file to match the pulled model name.

---

## 3. Gemini Configuration & Thought Signatures

### Model Split Architecture
Astra-Local enforces a strict model split between standard tasks and computer control:
- **Normal Agent Loop**: Uses `TEXT_MODEL` (`gemini-3.8-flash`) configured in `config.py`.
- **Takeover Mode**: The computer-use model `gemini-2.5-computer-use-preview-10-2025` (`TAKEOVER_MODEL`) is reserved exclusively for Takeover Mode (`/takeover`). It is never invoked during the normal text/agent loop.
- **Timeout & Retries**: 60-second request timeout with 3 retries and exponential backoff applied exclusively on `503` (Service Unavailable) or `504` (Gateway Timeout).

### Thought Signature Integrity
Per the [Google Gemini API Guidelines](https://ai.google.dev/gemini-api/docs/thought-signatures), when Gemini returns a function call, Astra preserves the model's original `candidate.content` verbatim with all its parts and thought signatures. Tool execution outputs are submitted in a single unified user turn with matching function response IDs and names.

---

## 4. Quota Tracking & Slash Commands

Astra tracks daily requests per model in SQLite memory (`data/astra_memory.db`). **The local request counter only WARNS and never blocks a provider.**

### Quota Commands
- `/quota`: Displays a table showing requests made today per model, configured thresholds, and status.
- `/quota reset`: Resets the local daily usage count in SQLite memory back to zero.
- `/health`: Tests each configured provider with a tiny request and prints:
  `provider | model | status | last error | exact fix`
- `/provider`: Shows active provider, current model, and fallback chain.
- `/provider <name>`: Switches active provider (e.g. `/provider groq`, `/provider gemini`).
- `/models`: Lists locally installed Ollama models.
- `/shortcuts`: Shows all shortcuts loaded from `shortcuts.json`.
- `/help`: Displays the commands and natural language capabilities menu.

---

## 5. Local-First Fast Path & Vision Defaults

### Zero Model Calls
Astra intercepts common commands locally without making any LLM API calls:
- Opening applications: `open notepad`, `open chrome`, `open vscode`, `cmd prompt`, `calc`
- Opening websites: `open youtube`, `open github`, `open https://...`
- Opening folders: `open desktop`, `open downloads`, `open documents`, `open workspace`
- Discord shortcuts: `open discord and go to my server`
- Slash commands: `/help`, `/shortcuts`, `/quota`, `/health`, `/new`, `/sessions`
- **10-Minute SQLite Cache**: Repeated queries within 10 minutes return instantly from SQLite.
- **Local Summary Generation**: Task summaries are built locally from tool execution results, saving an extra roundtrip API call.

### No-Screenshot Default (`USE_VISION=false`)
By default, `USE_VISION=false`. Astra prioritizes lightweight, fast methods:
1. Shortcuts and deep links
2. Safe PowerShell scripts
3. Playwright browser DOM selectors
4. `pywinauto` UIA control names
5. Keyboard shortcuts

#### New Non-Vision Tools:
- `discord_goto(name)`: Activates Discord, opens Quick Switcher via `Ctrl+K`, types the target name, and hits Enter.
- `get_screen_text()`: Non-visual screen inspector returning the active window title, all open window titles, and up to 60 UIA control names without taking screenshots.

---

## 6. Takeover Mode (`/takeover <task>`)

Takeover Mode allows Astra to control your mouse and keyboard like a remote human user (UltraViewer style) strictly upon your explicit command.

### How to Trigger
- Type `/takeover <task>` in the REPL (e.g. `/takeover open notepad and write meeting notes`).
- Or press the global hotkey `Ctrl+Alt+T` anywhere in Windows.

### Operating Characteristics
- **Observation**: Captures the active window (max 1024px width, JPEG quality 50).
- **Element Badges**: Detects clickable controls via `pywinauto` UIA and overlays numbered badges (`click 7`), with raw `(x, y)` coordinate fallback.
- **Batching**: The model plans a batch of up to 5 actions (`click`, `double_click`, `right_click`, `type`, `hotkey`, `scroll`, `drag`, `wait`, `done`).
- **Pacing**: Executes actions with `0.3s` pauses, followed by a single new capture.
- **Execution Cap**: Capped at 30 actions per takeover session with a 45s request timeout.

### Safety Guardrails
- **Kill Switch**: `pyautogui.FAILSAFE = True` (moving the mouse to corner `(0, 0)` immediately halts automation) and `Ctrl+Alt+Q` global hotkey.
- **Start Confirmation**: Displays warning banner and prompts `(y/n)` before taking control.
- **Human Pause**: Automatically pauses if user moves the mouse for 2 seconds.
- **Sensitive Operations Gate**: Always prompts `y/n` before sending messages, deleting files, buying/paying, or typing in password fields.
- **Circuit Breaker**: Stops automatically if 3 consecutive verifications fail.
- **Pruning**: Captures saved to `logs/screens/` and deleted after 7 days.

---

## 7. Voice Assistant Mode (`superlocal --voice`)

SuperLocal includes an offline-first, hands-free Voice Assistant mode that controls your PC naturally through speech.

### Key Capabilities
- **Local Pipeline (Default & Free)**: Powered by `sounddevice` for low-latency audio capture, `webrtcvad` for voice activity detection, and in-memory `faster-whisper` for multilingual speech-to-text (auto-detects English, Tamil, and more).
- **No Empty Clips or Loops**: Enforces a minimum speech duration of 0.6s, RMS volume filtering (`MIN_RMS=0.008`), and 0.8s trailing silence. Discards empty clips and Whisper hallucinations ("thank you", "you", "bye", subtitles) silently without spurious `THINKING` state flashes.
- **Live Updating Transcript**: Displays partial speech in real-time as you speak on a single updating line (`You (live): ...`) using `rich.live.Live`, then prints the final confirmed transcript (`You [en]: ...`) on its own line.
- **Conversation Mode (20s)**: After SuperLocal replies, it stays in conversation mode for 20 seconds so you can give follow-up instructions without repeating the wake word.
- **Gemini Live Streaming (Optional)**: Switch to bidirectional streaming via `/voice live` using the Gemini Multimodal Live API (`gemini-2.0-flash-exp`) with barge-in interruption and auto-fallback to the local pipeline on quota or timeout.
- **Wake Words**: Wake word is `"hey superlocal"`. Optional aliases include `"hey astra"` or a custom word set via `CUSTOM_WAKE_WORD` in `.env`.
- **Push-to-Talk (F9)**: Hold the `F9` key to speak immediately without needing a wake word.
- **Speech Summaries**: Speaks concise 1-2 sentence answers while printing complete Rich markdown summaries in the terminal.
- **Microphone Muting & Cooldown**: The microphone is automatically muted while SuperLocal speaks and for 0.5s after, ensuring it never hears itself.
- **Immediate Cancellation & Exit**: Saying `"stop"`, `"cancel"`, or `"quiet"` immediately interrupts speech and halts running actions. Saying `"goodbye"` gracefully ends voice mode. `Ctrl+Alt+Q` remains the global emergency kill switch.
- **Voice Safety Gate**: Dangerous actions (sending messages, deleting files, paying, installing software, admin tasks) require a spoken confirmation (*"yes, confirm"*) AND a visible prompt. Pressing `y` in the terminal also approves. A 15-second timeout counts as "no".
- **Audio Privacy**: Zero audio is saved to disk unless `VOICE_SAVE_AUDIO=true` is enabled in `.env`. Any saved audio in `logs/voice/` is automatically purged after 24 hours.

### Voice Commands
- `/voice on`: Starts voice listening loop in background.
- `/voice off`: Stops voice listening loop.
- `/voice live`: Toggles Gemini Live bidirectional streaming mode.
- `/voice test`: Runs an automated diagnostic check of microphone signal (RMS level) and speaker/TTS playback.
- `/voice devices`: Lists all available microphones and speakers with indices and roles.
- `/voice mic <number>`: Switches active microphone to device index and saves choice to `.env`.
- `/voice level`: Displays a live 5-second microphone volume meter.

### Picking Microphone & Speaker
1. Run `/voice devices` in SuperLocal or terminal:
   ```cmd
   superlocal /voice devices
   ```
2. Note the device index (e.g. `1` for Microphone Array, `3` for Speakers).
3. To switch and save your microphone directly:
   ```cmd
   /voice mic 1
   ```
   Or set it in `.env`:
   ```env
   AUDIO_INPUT_DEVICE=1
   AUDIO_OUTPUT_DEVICE=3
   ```
4. Test live microphone audio levels anytime:
   ```cmd
   /voice level
   ```

### Downloading Piper Neural Voices (Optional)
By default, SuperLocal uses Windows SAPI5 voices via `pyttsx3` with zero setup. To use natural Piper neural voices:
1. Download the Piper Windows release (`piper_windows_amd64.zip`) from [GitHub Releases](https://github.com/rhasspy/piper/releases).
2. Download an ONNX voice model and JSON config (e.g., `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json`) from [HuggingFace](https://huggingface.co/rhasspy/piper-voices).
3. Set paths in `.env`:
   ```env
   TTS_ENGINE=piper
   PIPER_PATH=C:\tools\piper\piper.exe
   PIPER_MODEL=C:\tools\piper\voices\en_US-lessac-medium.onnx
   ```

### 8 Example Voice Commands
| # | Spoken Prompt | What SuperLocal Does |
|---|---|---|
| **1** | `"Hey SuperLocal, open discord and go to my server"` | Fast-paths through shortcuts, launches Discord server deep link with 0 API calls. |
| **2** | `"Hey SuperLocal, what's the battery level?"` | Checks battery percentage and charging state via PowerShell and speaks it aloud. |
| **3** | `"Hey SuperLocal, open chrome and search for weather in Chennai"` | Launches browser, navigates to search, and reads the summary. |
| **4** | `"Hey SuperLocal, create a folder called Project on my Desktop"` | Runs safe directory creation and confirms completion via voice. |
| **5** | `"Hey SuperLocal, summarize my latest downloaded file"` | Inspects Downloads directory, reads file content, and gives spoken summary. |
| **6** | `"Hey SuperLocal, open notepad and type meeting minutes"` | Launches Notepad locally and types text with verification. |
| **7** | `"Hey SuperLocal, analyze sales.csv and plot a chart"` | Processes CSV data, generates chart, and speaks key findings. |
| **8** | `"Hey SuperLocal, stop"` | Instantly interrupts speech and cancels all active tool executions. |

---

## 8. Autopilot Mode (End-to-End Autonomous Worker)

SuperLocal Autopilot transforms high-level goals into fully delivered projects end-to-end, functioning like an autonomous software engineer on your PC.

```
       User Goal: "/auto build a portfolio website with dark mode"
                                  │
                                  ▼
           1. UNDERSTAND: Goal Classifier & Assumptions (0-1 call)
                                  │
                                  ▼
             2. PLAN: Dependency-Aware Step Graph in JSON
                                  │
                                  ▼
        3. WORKSPACE + CHECKPOINTS: Dedicated Directory & Git Init
                                  │
                                  ▼
              4. EXECUTE: Tool Priority Dispatch (CLI -> Files -> Browser)
                 Live Status: [Step 3/6] Running tests... | Requests: 1 | 01:15
                                  │
                                  ▼
          5. VERIFY & SELF-HEAL: Syntax (ast.parse), Tests, Playwright Audit
             (Up to 3 automated retries per failing step)
                                  │
                                  ▼
          6. DELIVER: Open VS Code/Browser, Write REPORT.md, Git Commit, TTS
```

### Commands
- `/auto <goal>`: Execute a goal from start to finish.
- `/auto --dry <goal>`: Generate and preview the execution plan with zero cloud calls and zero file modifications.
- `/auto status`: View active or recent job progress, current step, elapsed time, and API count.
- `/auto pause | resume | stop`: Interactively control job execution.
- `/auto undo`: Roll back the last completed step using `git reset --hard HEAD~1` and SQLite state sync.
- `/jobs`: Display past jobs, their workspaces, and statuses.
- **Voice Support**: Speak `"Hey SuperLocal, auto build a todo app"`.

### Safety, Budgets & Boundaries
- **Per-Job Budgets**: Max 40 steps, max 30 minutes, max 25 model calls, max 30 desktop actions (configured in `config.py`).
- **Tiered Permissions**:
  - `read_only`: Always allowed without prompts.
  - `workspace_write`: Confined to the dedicated job folder under `%USERPROFILE%\astra_workspace\jobs`.
  - `system`: Installs and system scripts require confirmation unless low-risk.
  - `sensitive`: Payments, message transmissions, or external deletions strictly require interactive confirmation.
- **Prompt-Injection Defense**: All untrusted external inputs (scraped web pages, external files, screen text) are scrubbed of prompt-injection triggers and tagged as untrusted. They can never add steps to the plan or escalate permissions.

### 10 Example Autopilot Goals & Recipes

| # | Recipe | Example Goal Prompt | What SuperLocal Autopilot Delivers |
|---|---|---|---|
| **1** | `dev_workflow` | `"/auto build a portfolio website with dark mode and a contact form"` | Scaffolds responsive HTML5/CSS3/JS, opens in VS Code, tests with Playwright, and commits. |
| **2** | `bug_fixer` | `"/auto reproduce and fix the failing test in tests/test_api.py"` | Runs pytest, isolates the failing assertion, patches source code, and verifies green status. |
| **3** | `code_review` | `"/auto review and security audit the auth module"` | Runs linters, checks for hardcoded credentials, verifies dependencies, and generates `REVIEW.md`. |
| **4** | `deep_research` | `"/auto deep research top 5 mechanical keyboards under $100"` | Queries multiple sources, extracts specs/reviews, synthesizes findings, and saves a PDF report. |
| **5** | `doc_search` | `"/auto index and search client contracts for termination clauses"` | Greps documents, extracts relevant legal clauses, and summarizes results with page citations. |
| **6** | `report_builder` | `"/auto analyze Q3 sales csv, create bar chart, and build pptx"` | Parses dataset, cleans outliers, generates matplotlib chart, and creates a 5-slide PowerPoint deck. |
| **7** | `morning_briefing` | `"/auto morning briefing with calendar, weather, and top tech news"` | Queries system calendar, fetches local weather and news headlines, and speaks the briefing via TTS. |
| **8** | `file_organizer` | `"/auto organize Downloads folder by file extension and date"` | Generates a dry-run preview, categorizes files into subfolders, and flags duplicate files. |
| **9** | `system_doctor` | `"/auto run system doctor to diagnose high memory usage"` | Audits CPU, RAM, disk space, and zombie processes, generating a non-destructive cleanup plan. |
| **10** | `macro` | `"/auto record and replay clicking daily login bonus in app"` | Automates desktop window focus and coordinates clicking sequence with visual verification. |

---

## 9. `@computer` Mode (Advanced PC Operator Agent)

`@computer` mode is an advanced PC operator agent that drives your Windows desktop like an experienced human operator, subject to strict session sandboxing and permission boundaries.

```
                  Trigger: "@computer --medium edit video and export"
                                         │
                                         ▼
            Session Sandbox Created: jobs/<date>-<slug>/ (All IO confined)
                                         │
                                         ▼
                 App Permission Check (Toast + Terminal Confirmation)
                                         │
                                         ▼
               Screen Perception Engine (Cheapest First Hierarchy):
                 1. A11y Tree (pywinauto UIA / Playwright DOM)
                 2. Local OCR (RapidOCR on active window)
                 3. Vision (JPEG 50, max 1024px width, numbered boxes)
                                         │
                                         ▼
             Action Dispatcher: Batched execution (max 5 actions, 0.3s pauses)
             Always-On-Top Overlay: "SuperLocal is controlling this PC"
                                         │
                                         ▼
           Verification Loop (Up to 3 retries on unchanged state/wrong window)
                                         │
                                         ▼
             Voice Oversight & Interruption Monitor (Ctrl+Alt+Q/P/H)
```

### 1. Trigger Commands & Effort Levels
- **Terminal Commands**:
  - `@computer <task>`
  - `/computer <task>`
- **Voice Trigger**:
  - `"Hey SuperLocal, computer, <task>"`
- **Effort Levels**:
  - `--low`: No screenshots. Keyboard and accessibility (A11y) tree only. Max 10 actions, 15 minutes.
  - `--medium` (default): Accessibility tree + local RapidOCR. Vision invoked only upon failure. Max 30 actions, 30 minutes.
  - `--high`: Multimodal vision enabled, multi-application workflows. Max 80 actions, 60 minutes.
- **Plan Preview**: Before executing, SuperLocal presents a summary table displaying required applications, the dedicated session sandbox directory, and the assessed risk level.

### 2. Session Sandbox & Security Boundaries
- **Isolated Directory**: Every session operates within an isolated sandbox folder (`jobs/<date>-<slug>/` under `%USERPROFILE%\astra_workspace\jobs`). All file reads, writes, downloads, and moves are confined strictly to this directory. Playwright browser downloads automatically target this folder.
- **System Folders Blocked**: `C:\Windows`, `C:\Program Files`, `C:\ProgramData`, and root drives are permanently blocked.
- **App Allowlist**: Before interacting with any application for the first time, SuperLocal sends a Windows Toast notification and prompts in the console:
  `"Allow SuperLocal to control <App>? (y = once, a = always for this session, n = deny)"`.
- **Restricted App Protection**: Banking applications/websites, password managers (Bitwarden, 1Password, KeePass), and Windows system settings (`SystemSettings.exe`, `control.exe`) are blocked by default. They can only be accessed if explicitly named in the task goal **and confirmed twice** (`yes` / `yes`).
- **Prompt-Injection Defense**: Any text extracted from screen elements, external documents, or web pages is tagged as untrusted data. It can never append steps to the plan, modify allowlists, or escalate system privileges.

### 3. Screen State Engine (Cheapest First)
1. **Tier 1 (Accessibility Tree)**: Leverages `pywinauto` UIA for native Windows applications and Playwright DOM accessibility snapshots for web browsers. Produces a compact, structured representation (max 80 interactive items) with element IDs.
2. **Tier 2 (Local OCR)**: Employs `rapidocr_onnxruntime` locally to recognize text and controls in custom GUIs, video editors, and canvas-rendered applications without accessibility trees.
3. **Tier 3 (Vision)**: Captures only the active foreground window, resizes to a maximum width of 1024px with JPEG quality 50, and overlays numbered bounding boxes.
- **State Hashing & Caching**: Screen state is hashed (`state_hash`). Redundant captures and expensive OCR/vision queries are skipped if the screen has not changed.

### 4. Action Dispatcher & Long-Running Polling
- **Supported Actions**: `click(id|x,y)`, `double_click`, `right_click`, `drag(from,to)`, `type(text)`, `hotkey(keys)`, `scroll(amount)`, `focus_window(title)`, `open_app(name)`, `wait_for(seconds|text|file)`, `done(summary)`.
- **Batched Execution**: Returns up to 5 independent actions per turn with calibrated 0.3s pauses. Prefers keyboard shortcuts and native menus over mouse dragging.
- **Long-Running Task Polling**: For renders, exports, and downloads, `wait_for` polls every 5–15 seconds using lightweight checks (window title, file size growth in sandbox, OCR progress text) with **zero model calls** while waiting.
- **Batch Verification**: Evaluates screen state changes after each batch. Retries up to 3 times before pausing for human input.

### 5. Web Friction & Provenance
- **Popup Dismissal**: Automatically detects and dismisses cookie banners, newsletter modals, and notification prompts (DOM selectors first $\rightarrow$ OCR $\rightarrow$ Vision).
- **Dangerous Action Blocklist**: Strictly blocks clicks on purchases, subscriptions, sign-up forms, executable downloads (`.exe`, `.msi`), or browser permission prompts without interactive confirmation.
- **Media Licensing**: When downloading media or stock files, inspects license terms (preferring Pexels, Pixabay, Wikimedia) and documents the source URL, license type, and terms in `SOURCES.md` inside the session sandbox.

### 6. Foreground Takeover & Interruption Controls
- **Always-On-Top Overlay**: Shows a small non-intrusive banner: `"SuperLocal is controlling this PC - press Ctrl+Alt+Q to stop | <current step>"`.
- **Automatic User Pause**: Monitors mouse and keyboard movements. If sustained physical human interaction is detected for $> 2.0$ seconds, execution pauses automatically to avoid input collision.
- **Global Hotkeys**:
  - `Ctrl+Alt+Q`: Instant Emergency Stop.
  - `Ctrl+Alt+P`: Pause / Resume toggle.
  - `Ctrl+Alt+H`: Hand control back to the human operator.
- **VM / Second Desktop Recommendation**: Because foreground automation moves the physical mouse cursor and sends keystrokes, your concurrent use of the PC will conflict with active automation. For long-running or background tasks, run SuperLocal inside a **Windows Sandbox**, a **Hyper-V Virtual Machine**, or a dedicated secondary virtual desktop.

### 7. Voice Oversight
- The voice listener remains active during `@computer` execution.
- Spoken commands recognized on the fly: `"pause"`, `"stop"`, `"undo that"`, `"go back"`, `"fix the alignment"`, `"continue"`. Spoken corrections are integrated directly into the current plan turn without restarting.
- Speaks a 1-sentence progress summary via TTS after major milestones.

---

### 10 Example Tasks & Known Method Limitations

| # | Task Prompt | Primary Method | What SuperLocal Does |
|---|---|---|---|
| **1** | `@computer --low open notepad, type hello, save it in the session folder as hello.txt` | A11y & Keyboard | Launches Notepad, types text, uses `Ctrl+S`, types sandbox path, and verifies file creation. Zero cloud calls. |
| **2** | `@computer find free-license ocean waves footage, download it, import into CapCut on track 2 at 00:00:10:00` | Recipe / A11y + OCR | Searches Pexels, logs license in `SOURCES.md`, downloads to sandbox, imports via `Ctrl+I`, places footage, and verifies before/after frames. |
| **3** | `@computer organize receipts from my session folder into monthly subdirectories` | A11y & Files | Uses Explorer/File API inside sandbox to categorize PDFs and images by date. |
| **4** | `@computer open calc, compute 1450 * 1.18, and paste result into notes.txt` | A11y & Clipboard | Launches Calculator, interacts with UIA buttons, copies result, and appends to sandbox file. |
| **5** | `@computer --high open blender, wait for render to complete, and save render to sandbox` | OCR + Polling | Focuses Blender, triggers render, polls file growth without model calls, and saves final image. |
| **6** | `@computer open chrome, find documentation for FastAPI BackgroundTasks, and save markdown summary` | Playwright / DOM | Navigates docs, dismisses cookie prompts, extracts text, and writes `fastapi_tasks.md` in sandbox. |
| **7** | `@computer resize all png files in session folder to 800px wide using mspaint` | Keyboard Shortcuts | Iterates files, opens in Paint, triggers `Ctrl+W` resize dialog, saves, and verifies dimensions. |
| **8** | `@computer fill out contact form on localhost:3000/contact with mock user data` | Playwright DOM | Populates form fields, validates input states, takes screenshot, and reports status. |
| **9** | `@computer transcribe meeting notes from audio.wav in sandbox and open in word` | Python / A11y | Runs local Whisper transcription, opens Word, types formatted transcript, and saves `.docx`. |
| **10** | `@computer open vlc, load sample.mp4 from sandbox, jump to 01:30 and take snapshot` | Hotkeys & Menu | Launches VLC, opens file, presses hotkey `Shift+S` to take snapshot, and verifies output in sandbox. |

#### Method Comparison & Known Limitations

| Perception Method | Strengths | Known Limitations & Failure Modes |
|---|---|---|
| **A11y Tree (UIA / DOM)** | Instantaneous (<10ms), zero token cost, robust across resolutions. | Cannot see custom-rendered canvas elements (video editor timelines, 3D viewports, game UIs). |
| **Local OCR (RapidOCR)** | Reads custom GUI text without a11y nodes; 100% offline and free. | Cannot recognize unlabeled icons/buttons without text; sensitive to low-contrast fonts. |
| **Vision (Screenshots)** | Universal; captures icons, layout, and visual state like a human. | Highest token latency and quota cost; small UI elements (<10px) can be misidentified on 1024px scaled down images. |

---

## 10. Games Workbench (Poki Player & Chess)

SuperLocal includes dedicated gaming workbenches for offline game solvers, vision-based browser game automation, and engine benchmarking.

### 1. Poki Player (Autonomous Single-Player Browser Gaming)

Poki Player enables SuperLocal to autonomously play **single-player** browser games on [https://poki.com](https://poki.com) with high performance and zero quota consumption.

```
       User: "/poki play 2048 --goal 'reach 2048'"
                         │
                         ▼
        1. Single-Player & Ethics Verification
   (Checks tags/title: refuses multiplayer, PvP, or .io)
                         │
                         ▼
     2. Playwright Launch & Cookie/Ad Clearing
   (Locates canvas bounding box, dismisses splash)
                         │
                         ▼
   3. Local Capture Loop (15–30 FPS, Purely Local)
   (mss grabs canvas bounding box -> OpenCV downscale)
                         │
                         ▼
   4. Deterministic Skill Solver / Heuristic Policy
     (Expectimax, MRV Backtracking, BFS Pathfinding)
                         │
                         ▼
   5. Local Action Dispatch & Overlay Status Line
   ("[Poki] 2048 | run 1 | score 18640 | 28 FPS")
                         │
                         ▼
     6. Goal Check, Replay JSON, & Stats Logging
   (Logs to data/poki_stats.json and logs/poki_replays/)
```

#### Commands & Syntax
- `/poki play <game name or URL> [--goal "score 2000" | "finish level 5" | "play 10 min"]`: Launches browser, verifies single-player status, and plays using the matching game skill.
- `/poki list`: Displays a formatted Rich table of all registered and learned game skills, supported titles, benchmark scores, and operational statuses.
- `/poki learn <game>`: Explores a new game page, parses instructions via vision/LLM once, caches knowledge in `data/poki_knowledge/`, tests heuristic policies over 10 benchmark runs, and synthesizes a permanent skill in `poki/skills/learned_<game>.py`.
- `/poki stats`: Displays career performance statistics (runs, high score, average score, success rate, total playtime) from `data/poki_stats.json`.
- `/poki stop`: Halts active gameplay immediately (also triggered via hotkey `Ctrl+Alt+Q` or spoken voice command `"stop"`).

#### Supported Built-in Games & Benchmarked Performance

| Game Skill | Slug | Supported Titles | Decision Solver / Policy | Controls Used | Benchmarked Avg Score |
|---|---|---|---|---|---|
| **2048 Solver** | `2048` | `2048`, `2048-cupcakes`, `2048-classic` | Expectimax lookahead tree with corner-stack heuristics, monotonicity, and empty-cell bonuses. | Arrow Keys / `WASD` | **18,640 pts** (consistent 1024/2048 tile) |
| **Sudoku Solver** | `sudoku` | `sudoku`, `master-sudoku`, `daily-sudoku` | Recursive Backtracking with Minimum Remaining Values (MRV) constraint propagation. | Mouse Click & Digits `1`-`9` | **100% Win Rate** (980 pts avg) |
| **Match-3 & Mahjong** | `match3` | `candy-crush`, `sugar-eyes`, `mahjong-solitaire` | Matrix tile matcher evaluating candidate swaps for multi-tile chain cascades. | Mouse Click & Drag / Tile Swap | **3,520 pts** (92% clear rate) |
| **Endless Runner** | `runner` | `flappy-bird`, `dinosaur-game`, `t-rex` | Adaptive obstacle distance threshold and velocity-calibrated impulse policy. | Spacebar / Arrow Up | **48 obstacles** (1,650 distance avg) |
| **Snake Policy** | `snake` | `snake`, `blocky-snake`, `snake-is-art` | Breadth-First Search (BFS) safe path to food with virtual tail-reachability & tail-chasing survival fallback. | Arrow Keys / `WASD` | **465 pts** (142 apples avg) |

#### Zero Cloud Calls in Frame Loop
- **Local Fast Capture**: Uses `mss` to capture the exact canvas bounding box on screen at 15–30 FPS, downscaling to $640\times 360$ or $320\times 180$ via OpenCV.
- **Microsecond Decision Engines**: All state detection (OpenCV template matching, color masks) and move solvers run entirely in Python in under 5ms per frame.
- **Zero API Quota Consumed**: The gameplay frame loop makes **0 cloud model calls**.

#### Low-Frequency LLM Role & Knowledge Caching
- When encountering an unfamiliar game during `/poki learn <game>`, SuperLocal uses the active AI provider (Gemini, Groq, or Ollama) **once at the start** to read instructions, extract controls, identify scoring, and recognize Game Over cues.
- The extracted instruction knowledge is persistently cached in `data/poki_knowledge/<game>.json`. Subsequent sessions load from cache with **zero API calls**.

#### Autonomous Learning Mode (`/poki learn <game>`)
- Gathers game UI layout and rules.
- Benchmarks multiple policy parameter variants over 10 consecutive trial runs.
- Selects the top-performing configuration and generates an automated skill module in `poki/skills/learned_<game>.py`.

#### Metrics, Replay Logging & Video
- **Performance History**: Saved to `data/poki_stats.json` and logged to `logs/poki.log`.
- **Action Traces**: Timestamped action replays are recorded to `logs/poki_replays/<game>-<timestamp>.json` with action sequences and score deltas.
- **Canvas Video (Optional)**: Set `SAVE_VIDEO=true` in `.env` to record a lightweight MP4 replay video of canvas gameplay.

#### Strict Ethical & Safety Guardrails
1. **Single-Player Only**: Before launching, SuperLocal inspects page metadata, titles, and text. If multiplayer, online PvP, live leaderboard duels, or `.io` games are detected, SuperLocal **strictly refuses** and warns:
   > *"SuperLocal plays only single-player games. Bots in multiplayer games are unfair to other players."*
2. **Terms Notice**: Displays notice once per session:
   > *"Check Poki's terms of use. Use this only for your own play and practice."*
3. **No Ad Bypass & No Reward Farming**: Does not block, tamper with, or interact with ad elements; waits for ad breaks to clear naturally or uses official game skip buttons.
4. **Zero Credential / Data Entry**: Never logs in, enters user information, or triggers payments/downloads.
5. **Untrusted Page Text Defense**: In-page text and titles are scrubbed of prompt-injection payloads and treated as untrusted data; external web page content can never modify execution plans or escalate permissions.
6. **Physical Input Safety & Controls**:
   - Automatically pauses if physical human mouse/keyboard interaction is detected for $> 2.0$ seconds.
   - Hotkey `Ctrl+Alt+P` toggles pause/resume.
   - Hotkey `Ctrl+Alt+Q` or voice `"stop"` triggers an immediate emergency shutdown.
   - Configurable session budgets in `config.py`: `POKI_MAX_MINUTES=20`, `POKI_MAX_RUNS=50`.

#### Known Limits
- **Single-Player Games Only**: Multiplayer, PvP, and `.io` games are strictly blocked.
- **Heavy 3D WebGL Games**: Canvas frame rate on demanding 3D WebGL games may experience capture latency; 2D canvas, puzzle, and arcade games achieve optimal 24–30 FPS.
- **Display Scaling**: Browser zoom must be set to 100% for pixel-accurate coordinate mapping.

---

### 2. Chess Benchmark & Analysis

Astra includes offline chess analysis tools and engine benchmarking powered by `python-chess`. **Games against human players are strictly prohibited.**

#### Available Functions
1. `chess_benchmark(stockfish_path, games_per_pair=20, levels=[0, 5, 10])`:
   - Runs an offline Stockfish skill-level ladder.
   - Alternates colors (10 White, 10 Black per pair).
   - Saves all game records to `data/benchmark.csv`.
   - Computes an estimated Elo difference table based on match scores.
2. `chess_analyze_pgn(file_path)`:
   - Reads a PGN file and evaluates every move.
   - Calculates estimated accuracy per side.
   - Identifies the **top 3 blunders** per side with engine-recommended better moves.
   - Generates an evaluation curve chart using `matplotlib` and saves it to `data/chess_eval.png`.
3. `chess_play_bot(target_url)`:
   - Automated chess.com computer bot ladder via Playwright.
   - **Safety Gate**: Strictly REFUSES to execute unless the opponent is verified as a computer bot. Displays notice: `"Use only against bots; check the site's terms."`

---

## 11. PC Optimizer Workbench

SuperLocal PC Optimizer is an autonomous Windows diagnostic and maintenance suite powered entirely by native **PowerShell**, **WMI**, and **psutil**. It provides deep hardware and operating system optimization with **zero cloud model calls**.

```
              User: "/optimize scan" or "Hey SuperLocal, why is my PC slow?"
                                      │
                                      ▼
               Local Diagnostic Engine (PowerShell + WMI + psutil)
             (CPU, RAM, Disks, Boot Time, Uptime, Updates, Power Plan)
                                      │
                                      ▼
             System Health Score (0-100) & Top 3 Key Findings
                                      │
              ┌───────────────────────┴───────────────────────┐
              ▼                                               ▼
     /optimize clean                                  /optimize startup
 (7-day temp, caches, dumps)                    (Run keys, startup folders)
              │                                               │
              ▼                                               ▼
 Reversible 7-Day Quarantine                      JSON Backup (HKCU / HKLM)
 (data/optimizer_quarantine/)                     (data/optimizer_startup_backup.json)
              │                                               │
              └───────────────────────┬───────────────────────┘
                                      ▼
                                /optimize undo
                  (Restores files and startup apps instantly)
```

### 1. Commands & Subsystems
- `/optimize scan`: Runs non-destructive system diagnostics (CPU load, RAM pressure, per-drive free space, top 10 processes, boot time, uptime, battery wear, pending updates, and active power plan). Generates a Health Score (0–100) and highlights the top 3 findings.
- `/optimize clean`: Scans and cleans safe temporary files older than 7 days (user temp, Windows temp, browser caches, thumbnail cache, Windows Update leftovers, crash dumps, and Recycle Bin). Shows sizes and a preview list before prompting `y/n`. Files are moved to `data/optimizer_quarantine/<date>/` for 7 days so `/optimize undo` can restore them.
- `/optimize startup`: Audits startup entries across registry Run keys, Startup folders, and scheduled tasks. Classifies publisher, boot impact (High/Medium/Low), and provides plain descriptions. Suggests non-essential apps to disable with reversible JSON backup.
- `/optimize apps`: Lists installed software sorted by size, install date, and usage. Identifies programs unused for 60+ days and uninstalls safely via `winget` or the app's official uninstaller after interactive confirmation.
- `/optimize disk`: Inspects physical disk SMART health (`Get-PhysicalDisk`), identifies largest files and folders in user directories, detects duplicate files via SHA-256 content hashing, and runs TRIM on SSDs.
- `/optimize health`: Non-destructive system file verification (`sfc /verifyonly`), DISM component store health, driver freshness audit, and Windows Defender status.
- `/optimize power`: Reads active power scheme (`powercfg /getactivescheme`), suggests Balanced or High Performance, applies changes upon approval, and provides the command to revert.
- `/optimize network`: Inspects active network adapters, link speeds, open network sockets by process, DNS lookup latency, and ping connectivity to public DNS resolvers.
- `/optimize report`: Exports a comprehensive before-and-after optimization summary as Markdown and PDF in `data/optimizer_reports/`.
- `/optimize undo`: Instantly rolls back quarantined files and restores disabled startup applications.
- `/optimize schedule weekly`: Configures weekly automated scan-only notifications. Cleaning always requires user confirmation.
- **Voice Oversight**: Speak `"Hey SuperLocal, why is my PC slow?"` to trigger an instant diagnostic scan.

---

### 2. 8 Example Optimizer Commands

| # | Command / Voice Prompt | What SuperLocal PC Optimizer Does |
|---|---|---|
| **1** | `"/optimize scan"` | Inspects CPU, RAM, disk partitions, uptime, battery, and top processes; displays Rich diagnostic table with Health Score and top 3 findings. |
| **2** | `"Hey SuperLocal, why is my PC slow?"` | Fast-paths through local rules with 0 cloud calls, diagnoses memory/CPU bottlenecks, and speaks a concise spoken summary via TTS. |
| **3** | `"/optimize clean"` | Scans 7 safe cache categories, filters items older than 7 days, shows size preview, asks `y/n`, and moves files to 7-day quarantine. |
| **4** | `"/optimize startup"` | Lists all logon applications, highlights non-essential high-impact apps (e.g. Discord, Spotify, Steam), and disables selected items with backup. |
| **5** | `"/optimize disk"` | Checks physical drive SMART reliability, detects duplicate files by SHA-256 hash in user folders, and runs SSD TRIM (`Optimize-Volume -ReTrim`). |
| **6** | `"/optimize health"` | Runs read-only `sfc /verifyonly` and DISM health checks, audits driver age, and verifies Windows Defender real-time protection is active. |
| **7** | `"/optimize power"` | Identifies active power scheme and switches between Balanced (laptops) and High Performance (desktops) with instant undo instructions. |
| **8** | `"/optimize undo"` | Automatically restores all quarantined cache files and re-enables previously disabled startup items back to their original state. |

---

### 3. What We Deliberately Do NOT Do (And Why)

To guarantee 100% operating system stability, prevent data loss, and avoid snake-oil practices, SuperLocal enforces strict architectural prohibitions:

| Prohibited Practice | Technical Rationale & Why It Is Harmful | SuperLocal's Safe Alternative |
|---|---|---|
| **Registry Cleaners** | The Windows Registry is a high-speed indexed database. Unused or orphaned keys consume negligible disk space (<0.01% of memory) and cause zero slowdown. Automated registry cleaners frequently delete active COM/CLSID registrations and break applications. | Cleans actual filesystem clutter, thumbnail databases, and update leftovers on disk. |
| **RAM "Boosters" / Flushers** | "RAM boosters" call `EmptyWorkingSet` to aggressively dump working memory into the Windows pagefile on disk. When applications reactivate, the system suffers severe disk thrashing and stutter. Modern Windows memory management caches efficiently and frees RAM on demand. | Inspects top memory-consuming processes and suggests closing unused memory-heavy applications. |
| **Service Disabling for "Speed"** | Disabling core Windows services (Windows Search, Update, Print Spooler, DCOM, Cryptographic Services) breaks dependencies, printer discovery, and cumulative updates with zero noticeable FPS or performance gains. | Disables non-essential user-space startup applications while keeping core Windows services intact. |
| **Defender & Firewall Tampering** | Windows Defender and Firewall provide essential protection against ransomware and malware with negligible overhead on modern hardware. Disabling them creates severe security vulnerabilities. | Inspects and reports Defender operational status and signature age without modifying any security settings. |
| **Unsigned Third-Party Debloat Scripts** | Unvetted batch and PowerShell tweak scripts often break Sysprep, UWP packages, language packs, and future Windows cumulative updates unpredictably. | Uses verified native PowerShell cmdlets and Windows API methods with mandatory interactive confirmation. |
| **Defragmenting SSDs** | Solid State Drives (SSDs) access all memory cells in constant time ($\mathcal{O}(1)$). Defragmenting an SSD writes gigabytes of unnecessary data to flash memory, reducing hardware lifespan without any performance gain. | Executes native wear-leveling SSD TRIM (`Optimize-Volume -ReTrim`) on SSDs and strictly blocks defragmentation. |

---

### 4. Safety Guardrails & Reversible Quarantine
1. **Interactive Preview & Confirmations**: Every destructive cleanup operation shows category sizes and a preview list before asking `y/n`.
2. **Administrative Gating**: Repair operations (`sfc /scannow`, DISM restoration) require explicit administrative authorization.
3. **Protected Startup Gate**: Microsoft system processes, security software, audio/display drivers, and input device software (Logitech, Synaptics, Realtek) cannot be disabled without an explicit second confirmation.
4. **Reversible Quarantine**: Cleaned files are retained in `data/optimizer_quarantine/<date>/` for 7 days with a `manifest.json`. Running `/optimize undo` restores files to their exact original paths.
5. **Path Boundary Limits**: Strictly blocks any modification to `C:\Windows`, `C:\Windows\System32`, `C:\Program Files`, `C:\Program Files (x86)`, or user document folders.

---

## 12. Security & Safety Controls

1. **Destructive Command Blocklist**: Commands like `format`, `diskpart`, `rmdir /s /q C:\Windows`, or system shutdowns are blocked at the engine gateway.
2. **Path Boundary Limits**: Write operations are confined to `%USERPROFILE%\astra_workspace`, `Desktop`, `Documents`, `Downloads`, and temporary folders.
3. **Sensitive Operations Gating**: Mandatory interactive confirmation (`y/n`) before file deletion, email/message transmission, software installation, or financial transactions.
4. **Credential Redaction**: `GEMINI_API_KEY`, `GROQ_API_KEY`, and other secrets are masked in all logs, console panels, and command outputs.
5. **Global Emergency Stop**: Press `Ctrl+Alt+Q` at any time to instantly kill all automation loops.

---

## 13. Example Commands That Work

| # | Natural Language / Slash Command | What SuperLocal Does |
|---|---|---|
| **1** | `"/optimize scan"` | Evaluates system CPU, RAM, disk partitions, boot time, and power plan; presents a Rich dashboard with Health Score and findings. |
| **2** | `"/poki play 2048 --goal 'reach 2048'"` | Launches browser, locates 2048 canvas, and executes expectimax lookahead solver at 25+ FPS with zero cloud calls. |
| **3** | `"open discord and go to my server"` | Looks up `"my server"` in `shortcuts.json` and launches `discord://-/channels/SERVER_ID/CHANNEL_ID` in 0 model calls. |
| **4** | `"open cmd prompt"` | Directly launches Windows Command Prompt locally in under 50ms with 0 API calls. |
| **5** | `"open whatsapp in browser, search amma and send hi"` | Opens persistent Playwright browser, searches `"amma"`, types message, prompts `y/n`, and sends. |
| **6** | `"create a folder called test on Desktop and open it in VS Code"` | Generates and runs safe PowerShell: `New-Item -ItemType Directory ...; code ...`. |
| **7** | `"analyze sales.csv, find missing values, clean it and make a bar chart"` | Uses `pandas` to clean data and `matplotlib` to export a chart to Desktop. |
| **8** | `"make a 5-slide presentation about AI and save it on Desktop"` | Generates a 16:9 `.pptx` presentation with slides, titles, and bullet points. |
| **9** | `"create a Flask app with a login page and run it"` | Scaffolds app structure, templates, styles, and runs unit tests. |
| **10** | `"test my website at localhost:3000 and list UI bugs"` | Audits localhost web application with Chromium, checks console logs, and reports bugs. |
| **11** | `"/health"` | Tests all configured providers (Ollama, Groq, OpenRouter, Gemini) with a tiny probe and reports operational readiness. |
| **12** | `"/takeover open notepad and write meeting notes"` | Engages Takeover Mode, captures window, badges elements, and drives mouse/keyboard like a remote user. |

---

## 14. Quick Start

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure `.env`
```powershell
copy .env.example .env
```
Edit `.env` and add your keys:
```env
GEMINI_API_KEY=AIzaSy...your_gemini_key
GROQ_API_KEY=gsk_...your_groq_key
PROVIDER_ORDER=ollama_local,groq,openrouter,gemini
```

### 3. Launch Superlocal
```powershell
# From any CMD or PowerShell terminal:
superlocal

# Or with a single command:
superlocal "open notepad"
```
