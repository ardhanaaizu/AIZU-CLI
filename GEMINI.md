# AIZU-CLI — Context & Project Memory

Dokumen memori ini mencatat seluruh konteks dan progress proyek **AIZU-CLI** agar dapat langsung dilanjutkan pada sesi berikutnya.

## 📌 Identitas Proyek
- **Nama Proyek:** AIZU-CLI
- **Pemilik / User:** ardhanaaizu
- **Bahasa Komunikasi:** Bahasa Indonesia
- **Tujuan:** CLI AI Agent canggih dengan antarmuka TUI modern (bergaya Claude Code) yang berjalan langsung di terminal (Termux / Windows / Linux) berbasis Python standar (tanpa dependensi eksternal pip yang rumit).

## 📂 Lokasi File & Direktori Terkait
- **Repositori Utama:** `C:\Users\ardha\AIZU-CLI`
- **Folder Terkait / Sandbox:** `C:\Users\ardha\AIZU-CLI-lasted` (memiliki folder tambahan seperti `kasir-app`, `dokumen`, `speedtest`)
- **Launcher:**
  - Windows: `C:\Users\ardha\AIZU-CLI\aizu.bat`
  - Linux / Termux: `C:\Users\ardha\bin\aizu` (menjalankan `$HOME/AIZU-CLI/agent.py`)
- **Proyek Ekosistem AIZU Terkait:**
  - `C:\Users\ardha\Music\jarvis` — AIZU v3.0 Local-First Fullstack Assistant (FastAPI backend + React frontend + paket `aizu`).

## ⚙️ Status Git & Konfigurasi (Per 11 September 2026)
- **Repository:** `https://github.com/ardhanaaizu/AIZU-CLI.git`
- **Branch:** `main`
- **Commit Terakhir:** `f9556a0` — `feat: Claude Code-style TUI overhaul + diff display + interrupt handling`
- **Git Status:** Bersih (Clean, up-to-date with origin/main)
- **Konfigurasi Aktif (`config.json`):**
  - `backend`: `custom`
  - `base_url`: `https://console.aaizu.id/v1`
  - `model`: `ag/gemini-pro-agent`
  - `mode`: `chat`

## 🧩 Arsitektur & Modul Utama AIZU-CLI
1. **`agent.py`**: Core loop agent, tool execution, REPL loop, multi-backend API integration.
2. **`tui.py`**: TUI modern bergaya Claude Code (linear output, box rendering, markdown, diff view, syntax highlighting).
3. **`tools.py`**: Tool calling bawaan (file read/write/edit/search/grep, DuckDuckGo search, URL fetch, Git commands, shell runner).
4. **`memory.py`**: Sistem memori persisten (fakta, preferensi, context recall otomatis).
5. **`skills.py`**: Template skill reusable (review-code, explain-code, debug, write-tests, refactor, commit, docs).
6. **`scheduler.py`**: Penjadwalan tugas otomatis (cron-style task runner).
7. **`plugins.py` & `plugins/`**: Sistem ekstensi plugin (9 plugin bawaan aktif).
8. **`tasks.py`**: Pelacak daftar tugas (TODO/in-progress/done).
9. **`telegram_bridge.py`**: Integrasi bot Telegram (termasuk kirim dokumen PDF).
10. **`generate_surat.py` / `user_data.py`**: Template generator dokumen dan manajemen profil user.

---
*Status: Siap dilanjutkan pada sesi diskusi berikutnya.*
