# AIZU-CLI — CLI AI Agent untuk Termux

Agent AI yang jalan langsung di terminal, dengan TUI modern seperti Claude Code.
Bisa ngobrol, baca/tulis file, kelola Git, cari di internet, dan banyak lagi.

Hanya butuh **Python standar** — tanpa pip install. Panggil dengan: `python3 agent.py`

## ✨ Fitur Utama

### 🤖 AI Agent dengan Tool Calling
- **File operations**: read, write, edit, search, glob, grep
- **Web**: search (DuckDuckGo), fetch URL
- **Git**: status, log, diff, add, commit, push, pull, branch, checkout
- **Shell**: jalankan perintah terminal dengan streaming real-time

### 🧠 Memory System (Persistent)
Simpan fakta, preferensi, dan context secara persisten. Auto-recall saat chat.

```bash
/memory save user-prefers-python "User suka Python"
/memory search python
/memory list
```

### ⚡ Skills System (Reusable Templates)
7 built-in skills yang bisa di-invoke:

```bash
/skill review-code file=app.py
/skill explain-code file=main.py
/skill debug error="TypeError at line 42"
/skill write-tests file=utils.py framework=pytest
/skill refactor file=old.py focus=readability
/skill commit
/skill docs file=api.py
```

### ⏰ Scheduler (Cron Tasks)
Schedule tugas terjadwal:

```bash
/schedule add @daily "Cek status server"
/schedule add "*/5 * * * *" "Check logs"
/schedule add @every 2h "Backup database"
/schedule list
```

### 🔌 Plugin System
Extend AIZU dengan plugins:

```bash
/plugins          # Lihat plugin terinstall
/agent <task>     # Jalankan sub-agent
/agent --type explore|code-reviewer|implementer <task>
/agent --bg <task>  # Background agent
```

### 📋 Task Management
Track progress dengan task system:

```bash
/tasks                    # Lihat task list
/tasks create <desc>      # Buat task baru
/tasks update <id> <status>  # Update status
```

### 🎯 Plan Mode
Eksplorasi dulu sebelum implementasi:

```bash
/plan             # Toggle plan mode
```

### 💾 Session Management
Simpan dan resume percakapan:

```bash
/sessions              # Lihat session tersimpan
/save-session [nama]   # Simpan session
/resume <nama>         # Resume session
```

## Backend yang didukung

Semua pakai format API OpenAI, tinggal pilih:

| Backend     | Biaya            | Butuh internet | Dapat API key di            |
|-------------|------------------|----------------|-----------------------------|
| `groq`      | Gratis (free tier) | Ya           | https://console.groq.com    |
| `gemini`    | Gratis (free tier) | Ya           | https://aistudio.google.com |
| `openai`    | Bayar            | Ya             | https://platform.openai.com |
| `openrouter`| Sebagian gratis  | Ya             | https://openrouter.ai       |
| `ollama`    | Gratis, offline  | Tidak          | (model lokal di HP)         |
| `custom`    | Tergantung       | Ya             | masukkan URL & key sendiri  |

### Provider custom

Pilih `custom` saat setup (atau ketik `/provider`). Alurnya:
1. Masukkan **base URL** API (kompatibel OpenAI, mis. `https://.../v1`)
2. Masukkan **API key**
3. Sistem **memvalidasi** endpoint. Bila gagal, kamu diminta ulangi URL.
4. Setelah valid, sistem **mencari otomatis daftar model** dari API tersebut.
   Pilih lewat nomor, atau `/cari <kata>` untuk filter.

### Mode kerja

Ganti gaya jawaban dengan `/mode <nama>`:
- `chat` — asisten umum (default)
- `code` — fokus menulis & memperbaiki kode
- `ringkas` — jawaban sesingkat mungkin
- `shell` — utamakan perintah shell
- `detail` — jawaban lengkap dengan penjelasan mendalam
- `git` — fokus pada pekerjaan Git

## Cara pakai

### 1. Pilih backend & siapkan API key

Cara A — pakai environment variable (paling cepat):

```bash
export AGENT_BACKEND=groq
export AGENT_API_KEY='gsk_...'      # key dari console.groq.com
python3 agent.py
```

Cara B — pakai file config:

```bash
cp config.example.json config.json
# edit config.json, isi api_key kamu
python3 agent.py
```

### 2. Contoh sesi

```
kamu> buatkan file catatan.txt isinya daftar belanja

🔧 Running: write_file (catatan.txt)
✅ File written

🤖 Sudah kubuat catatan.txt berisi daftar belanja.

kamu> ada file apa aja di folder ini?

🔧 Running: list_dir (.)
✅ Directory listed

🤖 Ada agent.py, tools.py, catatan.txt, ...
```

### Perintah slash (di dalam chat)

Semua pengaturan bisa diatur langsung saat chat dengan mengetik `/`:

| Perintah          | Fungsi                                            |
|-------------------|---------------------------------------------------|
| `/help`           | Tampilkan daftar perintah                         |
| `/config`         | Lihat pengaturan saat ini (key disensor)          |
| `/backend <nama>` | Ganti backend: groq, openai, gemini, openrouter, ollama |
| `/key <api-key>`  | Atur API key                                      |
| `/model <nama>`   | Atur nama model                                   |
| `/url <base-url>` | Atur base URL endpoint (opsional)                 |
| `/save`           | Simpan pengaturan ke `config.json`                |
| `/tools`          | Daftar tool yang bisa dipakai agent               |
| `/mode [nama]`    | Lihat/ganti mode kerja                            |
| `/models [kata]`  | Cari & pilih model yang tersedia dari provider    |
| `/provider`       | Setup ulang provider custom (URL + key + model)   |
| `/memory`         | Kelola persistent memory                          |
| `/skill <name>`   | Invoke skill template                             |
| `/schedule`       | Kelola scheduled tasks                            |
| `/tasks`          | Kelola task list                                  |
| `/plan`           | Toggle plan mode                                  |
| `/sessions`       | Lihat session tersimpan                           |
| `/resume <nama>`  | Resume session                                    |
| `/plugins`        | Lihat plugin terinstall                           |
| `/agent <task>`   | Jalankan sub-agent                                |
| `/reset`          | Hapus riwayat percakapan                          |
| `/keluar`         | Keluar dari agent                                 |

Contoh: cukup jalankan `python3 agent.py`, lalu di dalam chat ketik:

```
/backend groq
/key gsk_xxxxxxxx
/save
```

Setelah `/save`, pengaturan tersimpan dan otomatis dipakai saat dijalankan lagi.

## Arsitektur

```
AIZU-CLI/
├── agent.py          # Main agent loop, chat, slash commands
├── tools.py          # Tool implementations (file, web, git, shell)
├── tui.py            # Terminal UI (Claude Code style)
├── memory.py         # Persistent memory system
├── skills.py         # Reusable prompt templates
├── scheduler.py      # Cron-based task scheduling
├── plugins.py        # Plugin system, hooks, sub-agents
├── mcp_bridge.py     # MCP (Model Context Protocol) compatibility
├── tasks.py          # Task management system
├── workflow.py       # Pipeline & parallel execution
├── config.json       # Configuration (auto-generated)
└── plugins/          # Plugin directory
    ├── calculator/
    ├── memory/
    ├── github/
    └── ...
```

## Untuk Ollama (offline)

```bash
pkg install ollama        # jika belum
ollama serve &            # jalankan server lokal
ollama pull llama3.2:1b   # model kecil, cocok untuk HP
export AGENT_BACKEND=ollama
python3 agent.py
```

## Keamanan
- Perintah shell yang jelas berbahaya (mis. `rm -rf /`) otomatis ditolak.
- Tool permission system: auto/ask/deny untuk setiap tool
- Tetap hati-hati: agent bisa menulis file & menjalankan perintah sesuai instruksi.

## License

MIT
