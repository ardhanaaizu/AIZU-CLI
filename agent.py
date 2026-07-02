#!/usr/bin/env python3
"""
agent.py — CLI AI Agent sederhana untuk Termux.

Mendukung backend apa pun yang kompatibel dengan API OpenAI:
  - Groq, OpenAI, OpenRouter, Google Gemini (mode kompatibel), Ollama lokal.

Tidak butuh library eksternal — hanya pustaka standar Python.

Konfigurasi lewat environment variable atau file config.json:
  AGENT_BACKEND   : groq | openai | gemini | openrouter | ollama  (default: groq)
  AGENT_API_KEY   : API key backend (tidak perlu untuk ollama)
  AGENT_MODEL     : nama model (opsional, ada default per backend)
  AGENT_BASE_URL  : override URL endpoint (opsional)
"""

import json
import os
import sys
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

try:
    import termios
    import tty
    _HAS_TTY = True
except ImportError:           # Windows / lingkungan tanpa termios
    _HAS_TTY = False

import tools
from plugins import PluginManager, HookManager, SubAgent, SpecializedAgent, BackgroundAgentManager, AGENT_TYPES, list_plugins
from tui import AizuTUI, StreamingTUI, Terminal, Colors, ThinkingIndicator
from tasks import TaskManager, get_task_manager
from memory import get_memory_manager, create_memory_tools
from skills import get_skill_manager
from scheduler import get_scheduler, parse_cron_shortcut


# ---------------------------------------------------------------------------
# Loading animation
# ---------------------------------------------------------------------------
THINKING_FRAMES = [
    "\033[33m✻\033[0m Berpikir",
    "\033[33m✻\033[0m Berpikir.",
    "\033[33m✻\033[0m Berpikir..",
    "\033[33m✻\033[0m Berpikir...",
    "\033[33m✻\033[0m Menalar",
    "\033[33m✻\033[0m Menalar.",
    "\033[33m✻\033[0m Menalar..",
    "\033[33m✻\033[0m Memahami konteks",
    "\033[33m✻\033[0m Memahami konteks.",
    "\033[33m✻\033[0m Menghubungkan ide",
    "\033[33m✻\033[0m Menghubungkan ide.",
]

ANALYZING_FRAMES = [
    "\033[36m◎\033[0m Menganalisis",
    "\033[36m◎\033[0m Menganalisis.",
    "\033[36m◎\033[0m Menganalisis..",
    "\033[36m◎\033[0m Memeriksa struktur",
    "\033[36m◎\033[0m Memeriksa struktur.",
    "\033[36m◎\033[0m Mengevaluasi",
    "\033[36m◎\033[0m Mengevaluasi.",
]

WORKING_FRAMES = [
    "\033[32m▸\033[0m Mengerjakan",
    "\033[32m▸\033[0m Mengerjakan.",
    "\033[32m▸\033[0m Mengerjakan..",
    "\033[32m▸\033[0m Menyiapkan",
    "\033[32m▸\033[0m Menyiapkan.",
    "\033[32m▸\033[0m Memproses",
    "\033[32m▸\033[0m Memproses.",
]

SEARCHING_FRAMES = [
    "\033[35m◇\033[0m Mencari",
    "\033[35m◇\033[0m Mencari.",
    "\033[35m◇\033[0m Mencari..",
    "\033[35m◇\033[0m Scanning",
    "\033[35m◇\033[0m Scanning.",
    "\033[35m◇\033[0m Mengambil data",
    "\033[35m◇\033[0m Mengambil data.",
]

TOOL_FRAMES = [
    "\033[33m→\033[0m Menjalankan",
    "\033[33m→\033[0m Menjalankan.",
    "\033[33m→\033[0m Menjalankan..",
    "\033[33m→\033[0m Executing",
    "\033[33m→\033[0m Executing.",
]

CODING_FRAMES = [
    "\033[32m✎\033[0m Menulis kode",
    "\033[32m✎\033[0m Menulis kode.",
    "\033[32m✎\033[0m Menulis kode..",
    "\033[32m✎\033[0m Editing line",
    "\033[32m✎\033[0m Editing line.",
    "\033[32m✎\033[0m Writing function",
    "\033[32m✎\033[0m Writing function.",
    "\033[32m✎\033[0m Implementing",
    "\033[32m✎\033[0m Implementing.",
]


class LoadingAnimation:
    """Animasi loading sederhana untuk terminal."""

    def __init__(self, frames=None, delay=0.15):
        self.frames = frames or THINKING_FRAMES
        self.delay = delay
        self.running = False
        self.thread = None
        self.frame_idx = 0

    def start(self, text=None):
        """Mulai animasi loading."""
        self.running = True
        self.frame_idx = 0
        if text:
            self.frames = [f"{text}"] * len(self.frames)
        self.thread = threading.Thread(target=self._animate, daemon=True)
        self.thread.start()

    def _animate(self):
        """Thread animasi."""
        while self.running:
            sys.stdout.write(f"\r\033[K{self.frames[self.frame_idx % len(self.frames)]}")
            sys.stdout.flush()
            self.frame_idx += 1
            time.sleep(self.delay)

    def stop(self, final_text=None):
        """Hentikan animasi dan tampilkan teks akhir."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        # Bersihkan baris
        sys.stdout.write(f"\r\033[K")
        sys.stdout.flush()
        if final_text:
            sys.stdout.write(f"\r{final_text}\n")
            sys.stdout.flush()


def show_tool_animation(tool_name, args):
    """Tampilkan animasi saat menjalankan tool."""
    if "search" in tool_name or "fetch" in tool_name:
        anim = LoadingAnimation(SEARCHING_FRAMES)
    elif "git" in tool_name:
        anim = LoadingAnimation(WORKING_FRAMES)
    elif "edit" in tool_name:
        anim = LoadingAnimation(CODING_FRAMES)
        # Tampilkan info file yang diedit
        path = args.get("path", "")
        if path:
            anim.stop(f"  \033[32m✎\033[0m Editing \033[36m{path}\033[0m")
            anim.start()
    elif "write" in tool_name:
        anim = LoadingAnimation(CODING_FRAMES)
        path = args.get("path", "")
        if path:
            anim.stop(f"  \033[32m✎\033[0m Writing \033[36m{path}\033[0m")
            anim.start()
    else:
        anim = LoadingAnimation(TOOL_FRAMES)
    anim.start()
    return anim

# ---------------------------------------------------------------------------
# Preset backend: base_url + model default. Semua pakai format OpenAI.
# ---------------------------------------------------------------------------
PRESETS = {
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "needs_key": True,
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "needs_key": True,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct",
        "needs_key": True,
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "needs_key": True,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llama3.2:1b",
        "needs_key": False,
    },
    "custom": {
        "base_url": "",          # diisi user saat setup
        "model": "",             # dipilih dari daftar model API
        "needs_key": True,
    },
}

SYSTEM_PROMPT = (
    "Namamu adalah Aizu, asisten AI CLI yang cerdas dan membantu. "
    "Bila ditanya siapa namamu, jawab bahwa kamu adalah Aizu. "
    "\n\n"
    "KAMU MEMILIKI TOOL BERIKUT (gunakan bila diperlukan):"
    "\n"
    "📁 File: read_file, write_file, edit_file, edit_file_improved, list_dir, search_files, glob_files, grep_content, read_file_lines"
    "\n"
    "🌐 Web: web_search (cari internet), web_fetch (ambil dari URL)"
    "\n"
    "🔧 Git: git_status, git_log, git_diff, git_add, git_commit, git_push, git_pull, git_branch, git_checkout"
    "\n"
    "💻 Shell: run_shell (jalankan perintah terminal)"
    "\n"
    "🧠 Memory: memory_save, memory_search, memory_list, memory_get, memory_delete"
    "\n\n"
    "FITUR TAMBAHAN:"
    "\n"
    "- Memory system: Simpan fakta/preferensi user secara persisten. Gunakan memory_save untuk simpan, memory_search untuk recall."
    "\n"
    "- Plugin system: Tool, backend, mode, dan command baru bisa ditambah via plugin"
    "\n"
    "- Sub-agent: Gunakan /agent <task> untuk delegasi task ke child agent"
    "\n"
    "- Specialized agents: /agent --type explore|code-reviewer|implementer <task>"
    "\n"
    "- Background agents: /agent --bg <task> untuk jalankan di background"
    "\n"
    "- Plan mode: /plan untuk masuk mode eksplorasi sebelum implementasi"
    "\n"
    "- Task management: /tasks untuk lihat, buat, dan update task"
    "\n"
    "- Skills: /skill <name> untuk invoke reusable prompt templates"
    "\n"
    "- Scheduler: /schedule untuk set tugas terjadwal (cron)"
    "\n"
    "- Hooks: Lifecycle hooks tersedia untuk integrasi plugin"
    "\n\n"
    "ATURAN KERJA:"
    "\n"
    "1. Gunakan tool secara aktif untuk menyelesaikan tugas. Jangan hanya menjelaskan — LAKUKAN."
    "\n"
    "2. Untuk tugas kompleks, pecah menjadi langkah-langkah dan kerjakan satu per satu."
    "\n"
    "3. Selalu cek status dulu sebelum melakukan sesuatu (misal: git status sebelum commit)."
    "\n"
    "4. Untuk edit file, gunakan edit_file_improved (lebih presisi) atau edit_file."
    "\n"
    "5. Untuk cari file, gunakan glob_files (pattern) atau grep_content (regex)."
    "\n"
    "6. Bila butuh informasi dari internet, gunakan web_search atau web_fetch."
    "\n"
    "7. Bila ditanya sesuatu yang butuh riset, cari dulu di internet."
    "\n"
    "8. Untuk tugas kompleks, gunakan plan mode (/plan) untuk eksplorasi dulu sebelum implementasi."
    "\n"
    "9. Simpan fakta penting tentang user ke memory (memory_save) agar bisa recall nanti."
    "\n\n"
    "PENTING - JANGAN LOOP:"
    "\n"
    "- Jalankan perintah install HANYA SEKALI. Output di-stream real-time, progress terlihat langsung."
    "\n"
    "- JANGAN cek status install berulang kali. JANGAN panggil run_shell lagi."
    "\n"
    "- JANGAN panggil run_shell dengan perintah yang sama lebih dari 1 kali."
    "\n"
    "- Setelah run_shell selesai, langsung jawab final ke user."
    "\n\n"
    "Gaya bicara: ringkas, jelas, langsung ke inti. Bahasa Indonesia."
    "\n"
    "Untuk perintah berbahaya (hapus file, overwrite), jelaskan dulu sebelum jalankan."
)

# Nama identitas asisten — dipakai sebagai label balasan di terminal.
ASSISTANT_NAME = "aizu"

# Pricing per 1K tokens (USD) - untuk cost estimation
PRICING = {
    # Groq (free tier)
    "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0},
    "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
    "gemma2-9b-it": {"input": 0.0, "output": 0.0},

    # OpenAI
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},

    # Gemini
    "gemini-2.0-flash": {"input": 0.0, "output": 0.0},  # Free tier
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},

    # OpenRouter (varies, using averages)
    "meta-llama/llama-3.3-70b-instruct": {"input": 0.00059, "output": 0.00079},
    "anthropic/claude-3-haiku": {"input": 0.00025, "output": 0.00125},
    "anthropic/claude-3-sonnet": {"input": 0.003, "output": 0.015},

    # Default (estimasi)
    "default": {"input": 0.001, "output": 0.002}
}

# Exchange rate USD to IDR
USD_TO_IDR = 15800  # Approximate

# Tool Permission Settings
# "auto" = execute without asking
# "ask" = ask user before executing
# "deny" = never execute
TOOL_PERMISSIONS = {
    # File operations - safe
    "read_file": "auto",
    "list_dir": "auto",
    "search_files": "auto",
    "get_file_info": "auto",

    # File operations - need confirmation
    "write_file": "ask",
    "edit_file": "ask",
    "fs_write_file": "ask",
    "fs_edit_file": "ask",

    # File operations - dangerous
    "delete_file": "ask",
    "fs_delete_file": "ask",
    "move_file": "ask",
    "fs_move_file": "ask",

    # Shell - dangerous
    "run_shell": "ask",

    # Git - some need confirmation
    "git_status": "auto",
    "git_log": "auto",
    "git_diff": "auto",
    "git_branch": "auto",
    "git_add": "auto",
    "git_commit": "ask",
    "git_push": "ask",
    "git_pull": "ask",
    "git_checkout": "ask",

    # Web - safe
    "web_search": "auto",
    "web_fetch": "auto",
    "fetch_url": "auto",
    "fetch_json": "auto",

    # Memory - safe
    "memory_save_fact": "auto",
    "memory_search_facts": "auto",
    "memory_list_facts": "auto",
    "memory_delete_fact": "ask",
    "memory_save_preference": "auto",
    "memory_get_preference": "auto",
    "memory_list_preferences": "auto",
    "memory_save_conversation": "auto",
    "memory_search_conversations": "auto",
    "memory_get_stats": "auto",

    # GitHub - some need confirmation
    "github_get_repo": "auto",
    "github_list_issues": "auto",
    "github_get_issue": "auto",
    "github_list_pull_requests": "auto",
    "github_search_repos": "auto",
    "github_get_user": "auto",
    "github_list_repo_files": "auto",

    # Calculator - safe
    "calculate": "auto",
}

# Default permission for unknown tools
DEFAULT_TOOL_PERMISSION = "auto"

# ---------------------------------------------------------------------------
# Banner ASCII ala hacker.
# ---------------------------------------------------------------------------
BANNER = r"""
   █████╗ ██╗███████╗██╗   ██╗      ██████╗██╗     ██╗
  ██╔══██╗██║╚══███╔╝██║   ██║     ██╔════╝██║     ██║
  ███████║██║  ███╔╝ ██║   ██║     ██║     ██║     ██║
  ██╔══██║██║ ███╔╝  ██║   ██║     ██║     ██║     ██║
  ██║  ██║██║███████╗╚██████╔╝     ╚██████╗███████╗██║
  ╚═╝  ╚═╝╚═╝╚══════╝ ╚═════╝       ╚═════╝╚══════╝╚═╝
"""

# ---------------------------------------------------------------------------
# Mode kerja: tiap mode menambah instruksi pada system prompt.
# ---------------------------------------------------------------------------
MODES = {
    "chat": {
        "desc": "Asisten umum, percakapan biasa",
        "extra": "",
    },
    "code": {
        "desc": "Fokus menulis & memperbaiki kode, sertakan contoh",
        "extra": " Fokus pada penulisan kode yang benar dan idiomatik. "
                 "Tampilkan kode lengkap dalam blok kode. Jelaskan seperlunya.",
    },
    "ringkas": {
        "desc": "Jawaban sesingkat mungkin",
        "extra": " Jawab sesingkat mungkin, langsung ke inti, tanpa basa-basi.",
    },
    "shell": {
        "desc": "Asisten terminal, utamakan perintah shell",
        "extra": " Utamakan penyelesaian lewat perintah shell. "
                 "Selalu jelaskan perintah sebelum menjalankannya.",
    },
    "detail": {
        "desc": "Jawaban lengkap dengan penjelasan mendalam",
        "extra": " Berikan penjelasan lengkap, mendalam, dan terstruktur. "
                 "Sertakan contoh, langkah-langkah, dan tips tambahan. "
                 "Cocok untuk belajar atau tugas rumit.",
    },
    "git": {
        "desc": "Fokus pada pekerjaan git",
        "extra": " Fokus pada workflow git. "
                 "Selalu cek status sebelum commit. "
                 "Buat commit message yang jelas dan deskriptif.",
    },
}
DEFAULT_MODE = "chat"


def build_system_prompt(mode):
    """Gabungkan system prompt dasar dengan tambahan dari mode."""
    extra = MODES.get(mode, MODES[DEFAULT_MODE])["extra"]
    return SYSTEM_PROMPT + extra


CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
SESSIONS_DIR = os.path.expanduser("~/.aizu/sessions")


# ---------------------------------------------------------------------------
# Session Persistence
# ---------------------------------------------------------------------------
def save_session(messages, session_name=None):
    """Simpan session ke file JSON.

    Args:
        messages: List of message dicts
        session_name: Optional nama session (default: timestamp)

    Returns:
        str: Path ke file session yang disimpan
    """
    os.makedirs(SESSIONS_DIR, exist_ok=True)

    if session_name is None:
        session_name = datetime.now().strftime("%Y%m%d_%H%M%S")

    session_file = os.path.join(SESSIONS_DIR, f"{session_name}.json")

    session_data = {
        "name": session_name,
        "created": datetime.now().isoformat(),
        "message_count": len(messages),
        "messages": messages
    }

    with open(session_file, 'w', encoding='utf-8') as f:
        json.dump(session_data, f, indent=2, ensure_ascii=False)

    return session_file


def load_session(session_name):
    """Load session dari file.

    Args:
        session_name: Nama session atau path file

    Returns:
        list: Messages list atau None jika gagal
    """
    # Coba sebagai path langsung
    if os.path.exists(session_name):
        session_file = session_name
    else:
        # Coba sebagai nama session
        session_file = os.path.join(SESSIONS_DIR, f"{session_name}.json")

    if not os.path.exists(session_file):
        return None

    try:
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get("messages", [])
    except Exception as e:
        print(f"\033[31m[Session] Error load: {e}\033[0m")
        return None


def list_sessions():
    """List semua session yang tersimpan.

    Returns:
        list: List of dicts berisi info session
    """
    if not os.path.exists(SESSIONS_DIR):
        return []

    sessions = []
    for filename in os.listdir(SESSIONS_DIR):
        if filename.endswith('.json'):
            filepath = os.path.join(SESSIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                sessions.append({
                    "name": data.get("name", filename.replace('.json', '')),
                    "created": data.get("created", "unknown"),
                    "message_count": data.get("message_count", 0),
                    "file": filepath
                })
            except:
                pass

    # Sort by created (newest first)
    sessions.sort(key=lambda x: x.get("created", ""), reverse=True)
    return sessions


def delete_session(session_name):
    """Hapus session.

    Args:
        session_name: Nama session atau path file

    Returns:
        bool: True jika berhasil
    """
    if os.path.exists(session_name):
        session_file = session_name
    else:
        session_file = os.path.join(SESSIONS_DIR, f"{session_name}.json")

    if os.path.exists(session_file):
        try:
            os.remove(session_file)
            return True
        except:
            return False
    return False

# Context management settings
MAX_CONTEXT_MESSAGES = 20  # Maksimal pesan yang dikirim ke API
CACHE_SUMMARY_TOKENS = 100  # Estimasi token untuk summary percakapan lama

# Plan mode state
_plan_mode = False
_plan_content = ""

def is_plan_mode():
    """Cek apakah dalam plan mode."""
    return _plan_mode

def set_plan_mode(enabled):
    """Set plan mode."""
    global _plan_mode
    _plan_mode = enabled

def get_plan_content():
    """Ambil konten plan."""
    return _plan_content

def set_plan_content(content):
    """Set konten plan."""
    global _plan_content
    _plan_content = content


def compress_messages(messages, max_messages=MAX_CONTEXT_MESSAGES, cfg=None):
    """Kompresi pesan untuk hemat token.

    Strategi:
    - Simpan system prompt selalu
    - Simpan 5 pesan terakhir (recent context)
    - Pesan lama di-summary menggunakan LLM (jika cfg tersedia)
    - Fallback: truncate ke 100 karakter per pesan
    """
    if len(messages) <= max_messages:
        return messages

    # Pisahkan system prompt
    system_msg = messages[0] if messages[0]["role"] == "system" else None
    other_msgs = messages[1:] if system_msg else messages

    # Simpan 5 pesan terakhir
    recent = other_msgs[-5:]
    old = other_msgs[:-5]

    if not old:
        return messages

    # Coba LLM-based summarization
    summary_text = None
    if cfg and cfg.get("api_key"):
        summary_text = _summarize_with_llm(old, cfg)

    # Fallback: simple truncation
    if not summary_text:
        summary_parts = []
        for msg in old:
            if msg["role"] == "user":
                content = msg.get("content", "")[:150]
                summary_parts.append(f"User: {content}")
            elif msg["role"] == "assistant" and not msg.get("tool_calls"):
                content = msg.get("content", "")[:150]
                summary_parts.append(f"Assistant: {content}")
        summary_text = "Ringkasan percakapan sebelumnya:\n" + "\n".join(summary_parts[-10:])

    summary_msg = {"role": "user", "content": summary_text}
    compressed = [summary_msg] + recent

    # Tambah system prompt di awal
    if system_msg:
        compressed = [system_msg] + compressed

    return compressed


def _summarize_with_llm(messages, cfg):
    """Summarize messages menggunakan LLM.

    Args:
        messages: Messages yang mau di-summary
        cfg: Config dict dengan API key

    Returns:
        str: Summary text atau None jika gagal
    """
    try:
        # Build conversation text
        conv_parts = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                conv_parts.append(f"User: {content[:200]}")
            elif role == "assistant" and content:
                conv_parts.append(f"Assistant: {content[:200]}")

        if not conv_parts:
            return None

        conv_text = "\n".join(conv_parts[-15:])  # Max 15 messages

        # Call LLM for summary
        url = cfg["base_url"] + "/chat/completions"
        payload = {
            "model": cfg["model"],
            "messages": [
                {"role": "system", "content": "Buat ringkasan singkat (maksimal 300 kata) dari percakapan berikut. Fokus pada topik utama, keputusan, dan hasil. Gunakan bahasa Indonesia."},
                {"role": "user", "content": conv_text}
            ],
            "temperature": 0.3,
            "max_tokens": 500
        }

        headers = {"Content-Type": "application/json"}
        if cfg["api_key"]:
            headers["Authorization"] = "Bearer " + cfg["api_key"]

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content:
                return f"📝 Ringkasan percakapan sebelumnya:\n{content}"
    except Exception:
        pass  # Fallback ke simple summary

    return None


def count_tokens_approx(text):
    """Estimasi kasar jumlah token (1 token ≈ 4 karakter)."""
    return len(text) // 4


def get_context_info(messages):
    """Hitung informasi context untuk ditampilkan."""
    total_chars = sum(len(msg.get("content", "")) for msg in messages)
    approx_tokens = count_tokens_approx(str(messages))
    return {
        "messages": len(messages),
        "chars": total_chars,
        "approx_tokens": approx_tokens,
    }


def load_config():
    """Gabungkan config dari file config.json (opsional) dan environment variable.

    Tidak keluar bila API key kosong — key bisa diisi nanti lewat perintah /key.
    """
    cfg = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[peringatan] gagal baca config.json: {e}")

    backend = os.environ.get("AGENT_BACKEND", cfg.get("backend", "groq")).lower()
    if backend not in PRESETS:
        print(f"[peringatan] backend tidak dikenal: {backend}, dipakai 'groq'.")
        backend = "groq"

    preset = PRESETS[backend]
    api_key = os.environ.get("AGENT_API_KEY", cfg.get("api_key", ""))
    model = os.environ.get("AGENT_MODEL", cfg.get("model", preset["model"]))
    base_url = os.environ.get("AGENT_BASE_URL", cfg.get("base_url", preset["base_url"]))
    mode = os.environ.get("AGENT_MODE", cfg.get("mode", DEFAULT_MODE))
    if mode not in MODES:
        mode = DEFAULT_MODE

    return {
        "backend": backend,
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key": api_key,
        "mode": mode,
        # Daftar provider custom tersimpan, di-index dengan base domain.
        "saved_providers": cfg.get("saved_providers", {}),
    }


def save_config(cfg):
    """Simpan config saat ini ke config.json.

    base_url & daftar provider tersimpan ikut disimpan agar tetap teringat.
    """
    data = {
        "backend": cfg["backend"],
        "api_key": cfg["api_key"],
        "model": cfg["model"],
        "base_url": cfg["base_url"],
        "mode": cfg.get("mode", DEFAULT_MODE),
        "saved_providers": cfg.get("saved_providers", {}),
    }
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        return f"Config tersimpan di {CONFIG_PATH}"
    except Exception as e:
        return f"ERROR menyimpan config: {e}"


def domain_of(url):
    """Ambil base domain dari sebuah URL untuk dipakai sebagai index provider.

    Contoh: https://api.openrouter.ai/v1 -> 'api.openrouter.ai'
    """
    try:
        net = urllib.parse.urlparse(url).netloc
        return net or url.rstrip("/")
    except Exception:
        return url.rstrip("/")


def remember_provider(cfg, url, key, model):
    """Simpan provider custom ke daftar, di-index dengan base domain, lalu tulis ke disk.

    Mengembalikan nama index (domain) yang dipakai.
    """
    idx = domain_of(url)
    cfg.setdefault("saved_providers", {})[idx] = {
        "base_url": url.rstrip("/"),
        "api_key": key,
        "model": model,
    }
    save_config(cfg)
    return idx


def choose_saved_provider(cfg):
    """Tampilkan daftar provider tersimpan dan aktifkan yang dipilih.

    Return True bila ada yang dipilih & diterapkan.
    """
    saved = cfg.get("saved_providers", {})
    if not saved:
        print("  Belum ada provider tersimpan. Tambah lewat /provider atau /backend custom.")
        return False
    names = list(saved.keys())
    print("\033[36mProvider tersimpan:\033[0m")
    for i, n in enumerate(names, 1):
        info = saved[n]
        print(f"  {i:>2}. {n}  \033[90m(model: {info.get('model', '?')})\033[0m")
    try:
        inp = input("Pilih nomor (kosong = batal): ").strip()
    except (EOFError, KeyboardInterrupt):
        return False
    if not inp:
        return False
    try:
        idx = int(inp) - 1
    except ValueError:
        print("  Input bukan nomor.")
        return False
    if not (0 <= idx < len(names)):
        print("  Nomor di luar rentang.")
        return False
    info = saved[names[idx]]
    cfg["backend"] = "custom"
    cfg["base_url"] = info["base_url"].rstrip("/")
    cfg["api_key"] = info.get("api_key", "")
    cfg["model"] = info.get("model", "")
    save_config(cfg)   # jadikan provider ini default aktif berikutnya
    print(f"  \033[32mAktif: {names[idx]} | model: {cfg['model']}\033[0m")
    return True


def apply_backend(cfg, backend):
    """Ganti backend dan sesuaikan base_url + model ke preset-nya."""
    backend = backend.lower()
    if backend not in PRESETS:
        return f"Backend tidak dikenal. Pilihan: {', '.join(PRESETS)}"
    preset = PRESETS[backend]
    cfg["backend"] = backend
    cfg["base_url"] = preset["base_url"].rstrip("/")
    cfg["model"] = preset["model"]
    note = "" if preset["needs_key"] else " (tidak butuh API key)"
    return f"Backend -> {backend} | model default: {cfg['model']}{note}"


def mask_key(key):
    if not key:
        return "(belum diatur)"
    return key[:4] + "..." + key[-4:] if len(key) > 8 else "****"


SLASH_HELP = """Perintah yang tersedia:
  /help                tampilkan bantuan ini
  /config              lihat pengaturan saat ini
  /backend <nama>      ganti backend: groq | openai | gemini | openrouter | ollama
  /key <api-key>       atur API key
  /model <nama>        atur nama model
  /url <base-url>      atur base URL endpoint (opsional)
  /save                simpan pengaturan ke config.json
  /tools               daftar tool yang bisa dipakai agent
  /mode [nama]         lihat/ganti mode (chat, code, ringkas, shell, detail, git)
  /models [kata]       cari & pilih model yang tersedia dari provider
  /provider            setup ulang provider custom (URL + key + model)
  /providers           pilih provider custom yang tersimpan (per domain)
  /reset               hapus riwayat percakapan
  /sessions            lihat session tersimpan
  /resume <nama>       resume session sebelumnya
  /save-session [nama] simpan session saat ini
  /delete-session <nama> hapus session
  /permissions [tool] [auto|ask|deny] lihat/atur permission tool
  /plugins             lihat plugin yang terinstall
  /agent <task>        jalankan sub-agent dengan worktree isolation
  /agent --type <tipe> <task>  jalankan specialized agent (explore|code-reviewer|implementer)
  /agent --bg <task>   jalankan sub-agent di background
  /agents              lihat background agents
  /plan                masuk/keluar plan mode (eksplorasi dulu sebelum implementasi)
  /tasks               lihat task list
  /tasks create <desc> buat task baru
  /tasks update <id> <status> update task status
  /memory              lihat/simpan/cari memory
  /memory save <name> <content> simpan memory
  /memory search <query> cari memory
  /skill <name> [args] invoke skill template
  /schedule            lihat/tambah scheduled tasks
  /schedule add <cron> <prompt> tambah scheduled task
  /keluar              keluar dari agent

Tool yang tersedia:
  File    : read_file, write_file, edit_file, edit_file_improved, list_dir, search_files, glob_files, grep_content, read_file_lines
  Web     : web_search, web_fetch
  Git     : git_status, git_log, git_diff, git_add, git_commit, git_push, git_pull, git_branch, git_checkout
  Shell   : run_shell
  Memory  : memory_save, memory_search, memory_list, memory_get, memory_delete"""


# Daftar slash command untuk autocomplete (nama, keterangan singkat).
COMMANDS = [
    ("/help", "tampilkan bantuan"),
    ("/config", "lihat pengaturan saat ini"),
    ("/backend", "ganti penyedia AI"),
    ("/provider", "setup provider custom (URL+key)"),
    ("/providers", "pilih provider custom tersimpan"),
    ("/key", "atur API key"),
    ("/model", "atur model manual"),
    ("/models", "cari & pilih model dari API"),
    ("/mode", "ganti mode kerja"),
    ("/url", "atur base URL endpoint"),
    ("/save", "simpan pengaturan"),
    ("/tools", "daftar tool agent"),
    ("/sessions", "lihat session tersimpan"),
    ("/resume", "resume session"),
    ("/save-session", "simpan session"),
    ("/delete-session", "hapus session"),
    ("/permissions", "atur permission tool"),
    ("/plugins", "lihat plugin terinstall"),
    ("/agent", "jalankan sub-agent"),
    ("/agents", "lihat background agents"),
    ("/plan", "masuk/keluar plan mode"),
    ("/tasks", "lihat/kelola task list"),
    ("/memory", "kelola persistent memory"),
    ("/skill", "invoke skill template"),
    ("/schedule", "kelola scheduled tasks"),
    ("/reset", "hapus riwayat percakapan"),
    ("/keluar", "keluar dari agent"),
]
MAX_SUGGEST = 8


def _match_commands(buf):
    """Cari command yang cocok dengan teks yang sedang diketik."""
    low = buf.lower()
    return [(c, h) for c, h in COMMANDS if c.startswith(low)][:MAX_SUGGEST]


def prompt_with_completion(prompt_text, visible_len):
    """Baca input dengan rekomendasi slash command live (type-ahead).

    Saat user mengetik teks diawali '/', daftar command yang cocok muncul
    di bawah baris input. Navigasi:
      - Panah Atas/Bawah : pindah sorotan antar opsi
      - Tab              : lengkapi ke opsi tersorot (atau prefiks terpanjang)
      - Enter            : kirim. Bila ada opsi tersorot, command itu yang dikirim.
    Fallback ke input() biasa bila bukan terminal.
    """
    if not (_HAS_TTY and sys.stdin.isatty() and sys.stdout.isatty()):
        return input(prompt_text)

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    buf = ""
    sel = -1   # indeks opsi tersorot; -1 = tidak ada (mode mengetik)

    def render():
        sug = _match_commands(buf) if buf.startswith("/") else []
        out = ["\r\033[J", prompt_text, buf]   # \033[J: bersihkan dari kursor ke bawah
        if sug:
            for i, (c, h) in enumerate(sug):
                if i == sel:
                    # Opsi tersorot: video terbalik.
                    out.append(f"\r\n  \033[7m {c}  {h} \033[0m")
                else:
                    out.append(f"\r\n  \033[36m{c}\033[0m  \033[90m{h}\033[0m")
            out.append(f"\033[{len(sug)}A")    # naik kembali ke baris input
            col = visible_len + len(buf)
            out.append("\r" + (f"\033[{col}C" if col else ""))
        sys.stdout.write("".join(out))
        sys.stdout.flush()

    try:
        tty.setcbreak(fd)              # ICANON+ECHO off, sinyal & OPOST tetap aktif
        render()
        while True:
            ch = sys.stdin.read(1)
            if ch in ("\r", "\n"):                 # Enter -> selesai
                sug = _match_commands(buf) if buf.startswith("/") else []
                if sug and 0 <= sel < len(sug):
                    buf = sug[sel][0]              # pakai command tersorot
                sys.stdout.write("\r\033[J" + prompt_text + buf + "\r\n")
                sys.stdout.flush()
                return buf
            elif ch == "\x03":                     # Ctrl-C
                raise KeyboardInterrupt
            elif ch == "\x04":                     # Ctrl-D
                if not buf:
                    raise EOFError
            elif ch in ("\x7f", "\x08"):           # Backspace
                buf = buf[:-1]
                sel = -1
                render()
            elif ch == "\t":                       # Tab -> autocomplete
                sug = _match_commands(buf) if buf.startswith("/") else []
                if 0 <= sel < len(sug):
                    buf = sug[sel][0] + " "
                    sel = -1
                elif len(sug) == 1:
                    buf = sug[0][0] + " "
                elif len(sug) > 1:
                    # lengkapi ke prefiks terpanjang yang sama
                    names = [c for c, _ in sug]
                    pre = os.path.commonprefix(names)
                    if len(pre) > len(buf):
                        buf = pre
                render()
            elif ch == "\x1b":                     # escape seq (panah)
                seq = sys.stdin.read(2)
                sug = _match_commands(buf) if buf.startswith("/") else []
                if seq == "[B" and sug:            # panah bawah
                    sel = sel + 1 if sel + 1 < len(sug) else 0
                    render()
                elif seq == "[A" and sug:          # panah atas
                    sel = sel - 1 if sel - 1 >= 0 else len(sug) - 1
                    render()
                # panah kiri/kanan & lainnya diabaikan
            elif ch and ch.isprintable():
                buf += ch
                sel = -1
                render()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def handle_slash(line, cfg, messages, plugin_mgr=None, hook_mgr=None, tui=None):
    """Tangani perintah slash. Return True jika program harus berhenti.

    Args:
        line: Input user (misal: '/mode code')
        cfg: Config dict
        messages: List of message dicts
        plugin_mgr: PluginManager instance (optional)
        hook_mgr: HookManager instance (optional)
        tui: AizuTUI instance (optional)
    """
    def tui_print(text, style="normal"):
        """Print to TUI if available, otherwise console"""
        if tui:
            if style == "error":
                tui.add_error(text)
            elif style == "success":
                tui.add_success(text)
            elif style == "info":
                tui.add_info(text)
            elif style == "warning":
                tui.add_warning(text)
            else:
                tui.add_message(text)
        else:
            print(text)
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/keluar", "/exit", "/quit"):
        print("Daah!")
        return True
    elif cmd in ("/help", "/?"):
        print(SLASH_HELP)
        # Tampilkan plugin commands jika ada
        if plugin_mgr:
            plugin_commands = plugin_mgr.get_all_commands()
            if plugin_commands:
                print("\n\033[36mPlugin Commands:\033[0m")
                for name in sorted(plugin_commands.keys()):
                    print(f"  {name}")
    elif cmd == "/reset":
        del messages[1:]
        print("[riwayat dihapus]")
    elif cmd == "/config":
        need = PRESETS[cfg["backend"]]["needs_key"]
        print(f"  backend : {cfg['backend']}")
        print(f"  model   : {cfg['model']}")
        print(f"  mode    : {cfg.get('mode', DEFAULT_MODE)}")
        print(f"  base_url: {cfg['base_url']}")
        print(f"  api_key : {mask_key(cfg['api_key'])}" + ("" if need else "  (tidak diperlukan)"))
        # Tampilkan info plugins
        if plugin_mgr:
            print(f"  plugins : {len(plugin_mgr.plugins)} loaded")
    elif cmd == "/backend":
        if not arg:
            print("  Pakai: /backend <nama>. Pilihan: " + ", ".join(PRESETS))
        elif arg.lower() == "custom":
            setup_custom_provider(cfg)
        else:
            print("  " + apply_backend(cfg, arg))
    elif cmd == "/provider":
        setup_custom_provider(cfg)
    elif cmd in ("/providers", "/list"):
        choose_saved_provider(cfg)
    elif cmd == "/mode":
        if not arg:
            print("  Mode tersedia:")
            for name, info in MODES.items():
                tanda = " (aktif)" if name == cfg.get("mode") else ""
                print(f"    {name:<9} - {info['desc']}{tanda}")
            print("  Pakai: /mode <nama>")
        elif arg in MODES:
            cfg["mode"] = arg
            # Perbarui system prompt pada riwayat aktif.
            if messages:
                messages[0] = {"role": "system", "content": build_system_prompt(arg)}
            print(f"  Mode -> {arg} ({MODES[arg]['desc']})")
        else:
            print(f"  Mode tidak dikenal. Pilihan: {', '.join(MODES)}")
    elif cmd == "/models":
        if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
            print("  [info] atur API key dulu dengan /key")
        else:
            print("  \033[33mMengambil daftar model...\033[0m")
            ok, hasil = fetch_models(cfg["base_url"], cfg["api_key"])
            if not ok:
                print(f"  [error] {hasil}")
            else:
                if arg:
                    hasil = [m for m in hasil if arg.lower() in m.lower()] or hasil
                m = choose_model_interactive(cfg, hasil)
                if m:
                    cfg["model"] = m
                    print(f"  Model -> {m}")
    elif cmd == "/key":
        if arg:
            cfg["api_key"] = arg
            print(f"  API key diatur: {mask_key(arg)}")
        else:
            print("  Pakai: /key <api-key>")
    elif cmd == "/model":
        if arg:
            cfg["model"] = arg
            print(f"  Model -> {arg}")
        else:
            print("  Pakai: /model <nama>")
    elif cmd == "/url":
        if arg:
            cfg["base_url"] = arg.rstrip("/")
            print(f"  base_url -> {cfg['base_url']}")
        else:
            print("  Pakai: /url <base-url>")
    elif cmd == "/save":
        print("  " + save_config(cfg))
    elif cmd == "/tools":
        for s in tools.SCHEMAS:
            fn = s["function"]
            print(f"  {fn['name']:<12} {fn['description']}")
    elif cmd == "/sessions":
        # List semua sessions
        sessions = list_sessions()
        if not sessions:
            print("  Tidak ada session tersimpan.")
        else:
            print(f"\033[36mSessions ({len(sessions)}):\033[0m")
            for i, s in enumerate(sessions, 1):
                created = s.get('created', 'unknown')[:19]
                msgs = s.get('message_count', 0)
                print(f"  {i:>2}. {s['name']:<20} {created} ({msgs} msgs)")
            print("  Gunakan: /resume <nomor atau nama>")
    elif cmd == "/resume":
        # Resume session
        if not arg:
            print("  Pakai: /resume <nomor atau nama session>")
            print("  Lihat /sessions untuk daftar")
        else:
            sessions = list_sessions()
            # Coba sebagai nomor
            try:
                idx = int(arg) - 1
                if 0 <= idx < len(sessions):
                    session_file = sessions[idx]['file']
                    loaded_messages = load_session(session_file)
                    if loaded_messages:
                        # Clear current messages dan replace
                        messages.clear()
                        messages.extend(loaded_messages)
                        print(f"  \033[32mSession '{sessions[idx]['name']}' loaded ({len(loaded_messages)} msgs)\033[0m")
                        return False
            except ValueError:
                pass

            # Coba sebagai nama
            loaded_messages = load_session(arg)
            if loaded_messages:
                messages.clear()
                messages.extend(loaded_messages)
                print(f"  \033[32mSession '{arg}' loaded ({len(loaded_messages)} msgs)\033[0m")
            else:
                print(f"  \033[31mSession '{arg}' tidak ditemukan\033[0m")
    elif cmd == "/save-session":
        # Simpan session saat ini
        if not arg:
            arg = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file = save_session(messages, arg)
        print(f"  \033[32mSession saved: {arg}\033[0m")
        print(f"  File: {session_file}")
    elif cmd == "/delete-session":
        # Hapus session
        if not arg:
            print("  Pakai: /delete-session <nama session>")
        else:
            if delete_session(arg):
                print(f"  \033[32mSession '{arg}' deleted\033[0m")
            else:
                print(f"  \033[31mSession '{arg}' tidak ditemukan\033[0m")
    elif cmd == "/permissions":
        # Manage tool permissions
        if not arg:
            # List permissions
            print("\033[36mTool Permissions:\033[0m")
            print("  auto  = Execute tanpa tanya")
            print("  ask   = Tanya dulu sebelum execute")
            print("  deny  = Blokir total")
            print()
            for perm_type in ["auto", "ask", "deny"]:
                tools_list = [t for t, p in TOOL_PERMISSIONS.items() if p == perm_type]
                if tools_list:
                    color = "32" if perm_type == "auto" else ("33" if perm_type == "ask" else "31")
                    print(f"  \033[{color}m{perm_type}:\033[0m {', '.join(tools_list[:5])}")
                    if len(tools_list) > 5:
                        print(f"    ... and {len(tools_list) - 5} more")
            print()
            print("  Gunakan: /permissions <tool> <auto|ask|deny>")
        else:
            # Set permission
            parts = arg.split()
            if len(parts) != 2:
                print("  Pakai: /permissions <tool> <auto|ask|deny>")
            else:
                tool_name, perm = parts
                if perm not in ("auto", "ask", "deny"):
                    print("  Permission harus: auto, ask, atau deny")
                else:
                    update_tool_permission(tool_name, perm)
                    print(f"  \033[32mPermission '{tool_name}' -> {perm}\033[0m")
    elif cmd == "/plugins":
        # Tampilkan daftar plugin yang terinstall
        plugins = list_plugins()
        if not plugins:
            print("  Tidak ada plugin terinstall.")
        else:
            print(f"\033[36mPlugins ({len(plugins)}):\033[0m")
            for p in plugins:
                loc = "local" if p.get('location') == 'local' else "user"
                print(f"  {p['name']:<20} v{p.get('version', '?'):<8} [{loc}] {p.get('description', '')}")
    elif cmd == "/agent":
        # Sub-agent command
        if not arg:
            print("  Pakai: /agent <task>")
            print("         /agent --type <explore|code-reviewer|implementer> <task>")
            print("         /agent --bg <task>")
            print("  Contoh: /agent Buat function hello world di Python")
            print("  Contoh: /agent --type explore Cari semua file Python")
            print("  Contoh: /agent --bg Refactor kode di src/")
        elif arg.startswith("--type "):
            # Specialized agent
            parts = arg[7:].strip().split(maxsplit=1)
            if len(parts) < 2:
                print("  Pakai: /agent --type <explore|code-reviewer|implementer> <task>")
            else:
                agent_type, task = parts
                if agent_type not in AGENT_TYPES:
                    print(f"  Tipe tidak dikenal: {agent_type}")
                    print(f"  Tipe tersedia: {', '.join(AGENT_TYPES.keys())}")
                else:
                    print(f"  \033[33mMemulai {agent_type} agent...\033[0m")
                    agent = SpecializedAgent(task, cfg, os.getcwd(), agent_type=agent_type, hook_mgr=hook_mgr)
                    result = agent.run()
                    print(f"\n\033[36m{ASSISTANT_NAME}>\033[0m {result}")
        elif arg.startswith("--bg "):
            # Background agent
            task = arg[5:].strip()
            if not task:
                print("  Pakai: /agent --bg <task>")
            else:
                # Initialize background manager if needed
                if not hasattr(handle_slash, '_bg_manager'):
                    handle_slash._bg_manager = BackgroundAgentManager(cfg, os.getcwd(), hook_mgr)
                agent_id = handle_slash._bg_manager.spawn(task)
                print(f"  \033[32mBackground agent started: {agent_id}\033[0m")
                print(f"  Cek status: /agents")
        else:
            print(f"  \033[33mMemulai sub-agent...\033[0m")
            agent = SubAgent(arg, cfg, os.getcwd(), hook_mgr=hook_mgr)
            result = agent.run()
            print(f"\n\033[36m{ASSISTANT_NAME}>\033[0m {result}")
    elif cmd == "/agents":
        # List background agents
        if not hasattr(handle_slash, '_bg_manager'):
            print("  Tidak ada background agents.")
        else:
            agents_list = handle_slash._bg_manager.format_list()
            print(f"\033[36mBackground Agents:\033[0m")
            print(agents_list)
    elif cmd == "/plan":
        # Plan mode toggle
        if is_plan_mode():
            set_plan_mode(False)
            print("  \033[32mPlan mode OFF\033[0m — Sekarang bisa execute.")
            if get_plan_content():
                print(f"\n  Plan tersimpan:\n{get_plan_content()}")
        else:
            set_plan_mode(True)
            print("  \033[33mPlan mode ON\033[0m — Hanya eksplorasi, tidak execute.")
            print("  Gunakan tool read/search untuk eksplorasi kode.")
            print("  Ketik /plan lagi untuk keluar dan mulai implementasi.")
    elif cmd == "/tasks":
        # Task management
        task_mgr = get_task_manager()
        if not arg:
            # List tasks
            summary = task_mgr.format_summary()
            task_list = task_mgr.format_task_list()
            print(f"\033[36m{summary}\033[0m")
            print(task_list)
            print("\n  Pakai:")
            print("    /tasks create <deskripsi>  — buat task baru")
            print("    /tasks update <id> <status> — update status (pending|in_progress|completed)")
            print("    /tasks delete <id>  — hapus task")
        elif arg.startswith("create "):
            desc = arg[7:].strip()
            if desc:
                task = task_mgr.create(desc)
                print(f"  \033[32mTask #{task['id']} dibuat: {desc}\033[0m")
            else:
                print("  Pakai: /tasks create <deskripsi>")
        elif arg.startswith("update "):
            parts = arg[7:].strip().split(maxsplit=1)
            if len(parts) == 2:
                task_id, status = parts
                if status not in TaskManager.VALID_STATUSES:
                    print(f"  Status tidak valid: {status}")
                    print(f"  Status: {', '.join(TaskManager.VALID_STATUSES)}")
                else:
                    task = task_mgr.update(task_id, status=status)
                    if task:
                        print(f"  \033[32mTask #{task_id} -> {status}\033[0m")
                    else:
                        print(f"  Task #{task_id} tidak ditemukan")
            else:
                print("  Pakai: /tasks update <id> <pending|in_progress|completed>")
        elif arg.startswith("delete "):
            task_id = arg[7:].strip()
            if task_mgr.delete(task_id):
                print(f"  \033[33mTask #{task_id} dihapus\033[0m")
            else:
                print(f"  Task #{task_id} tidak ditemukan")
        else:
            print("  Pakai: /tasks [create|update|delete] ...")
    elif cmd == "/memory":
        # Memory management
        if not arg:
            # List memories
            memories = memory_mgr.list_all()
            if not memories:
                print("  Tidak ada memory tersimpan.")
            else:
                print(f"\033[36mMemory ({len(memories)}):\033[0m")
                for m in memories[:20]:
                    name = m.get('name', 'unknown')
                    mem_type = m.get('type', 'project')
                    desc = m.get('description', '')[:50]
                    print(f"  [{mem_type}] {name} — {desc}")
                print("\n  Pakai:")
                print("    /memory save <name> <content>  — simpan memory")
                print("    /memory get <name>  — lihat detail memory")
                print("    /memory search <query>  — cari memory")
                print("    /memory delete <name>  — hapus memory")
        elif arg.startswith("save "):
            parts = arg[5:].strip().split(maxsplit=1)
            if len(parts) == 2:
                name, content = parts
                try:
                    filepath = memory_mgr.save(name, content)
                    print(f"  \033[32mMemory '{name}' tersimpan\033[0m")
                except Exception as e:
                    print(f"  \033[31mError: {e}\033[0m")
            else:
                print("  Pakai: /memory save <name> <content>")
        elif arg.startswith("get "):
            name = arg[4:].strip()
            memory = memory_mgr.get(name)
            if memory:
                print(f"\033[36mMemory: {memory.get('name')}\033[0m")
                print(f"  Type: {memory.get('type', 'project')}")
                print(f"  Description: {memory.get('description', '-')}")
                print(f"\n{memory.get('content', '')}")
            else:
                print(f"  Memory '{name}' tidak ditemukan")
        elif arg.startswith("search "):
            query = arg[7:].strip()
            results = memory_mgr.search(query)
            if results:
                print(f"\033[36mSearch results for '{query}':\033[0m")
                for r in results:
                    name = r.get('name', 'unknown')
                    desc = r.get('description', '')[:50]
                    print(f"  [{r.get('type', 'project')}] {name} — {desc}")
            else:
                print(f"  Tidak ditemukan memory untuk: {query}")
        elif arg.startswith("delete "):
            name = arg[7:].strip()
            if memory_mgr.delete(name):
                print(f"  \033[32mMemory '{name}' dihapus\033[0m")
            else:
                print(f"  Memory '{name}' tidak ditemukan")
        else:
            print("  Pakai: /memory [save|get|search|delete] ...")
    elif cmd == "/skill":
        # Skill invocation
        if not arg:
            # List skills
            skills = skill_mgr.list_all()
            if not skills:
                print("  Tidak ada skills tersedia.")
            else:
                print(f"\033[36mSkills ({len(skills)}):\033[0m")
                for s in skills:
                    name = s.get('name', 'unknown')
                    desc = s.get('description', '')[:50]
                    source = s.get('source', 'custom')
                    print(f"  [{source}] {name} — {desc}")
                print("\n  Pakai: /skill <name> [args]")
                print("  Contoh: /skill review-code file=app.py")
        else:
            # Parse skill name and args
            parts = arg.split(maxsplit=1)
            skill_name = parts[0]
            skill_args = {}

            if len(parts) > 1:
                # Parse key=value pairs
                for pair in re.findall(r'(\w+)=(\S+)', parts[1]):
                    skill_args[pair[0]] = pair[1]

            # Invoke skill
            rendered = skill_mgr.invoke(skill_name, skill_args)
            if rendered:
                # Treat as user message
                messages.append({"role": "user", "content": rendered})
                print(f"  \033[32mSkill '{skill_name}' invoked\033[0m")
                # Will be processed in next loop iteration
            else:
                print(f"  Skill '{skill_name}' tidak ditemukan")
    elif cmd == "/schedule":
        # Scheduler management
        if not arg:
            # List scheduled tasks
            print(scheduler.format_list())
            print("\n  Pakai:")
            print("    /schedule add <cron> <prompt>  — tambah task")
            print("    /schedule remove <id>  — hapus task")
            print("    /schedule enable <id>  — aktifkan task")
            print("    /schedule disable <id>  — nonaktifkan task")
            print("\n  Cron shortcuts: @daily, @hourly, @every 5m, @every 2h")
            print("  Cron format: minute hour day month weekday")
            print("  Contoh: /schedule add @daily Cek status server")
        elif arg.startswith("add "):
            task_def = arg[4:].strip()
            # Parse: first word is cron, rest is prompt
            parts = task_def.split(maxsplit=1)
            if len(parts) == 2:
                cron_expr, prompt = parts
                try:
                    # Handle shortcuts
                    cron_expr = parse_cron_shortcut(cron_expr)
                    task = scheduler.add(cron_expr, prompt)
                    print(f"  \033[32mTask ditambahkan: {task.id}\033[0m")
                    print(f"  Cron: {cron_expr}")
                    print(f"  Prompt: {prompt}")
                except ValueError as e:
                    print(f"  \033[31mError: {e}\033[0m")
            else:
                print("  Pakai: /schedule add <cron> <prompt>")
        elif arg.startswith("remove "):
            task_id = arg[7:].strip()
            if scheduler.remove(task_id):
                print(f"  \033[32mTask {task_id} dihapus\033[0m")
            else:
                print(f"  Task {task_id} tidak ditemukan")
        elif arg.startswith("enable "):
            task_id = arg[7:].strip()
            if scheduler.enable(task_id):
                print(f"  \033[32mTask {task_id} diaktifkan\033[0m")
            else:
                print(f"  Task {task_id} tidak ditemukan")
        elif arg.startswith("disable "):
            task_id = arg[8:].strip()
            if scheduler.disable(task_id):
                print(f"  \033[32mTask {task_id} dinonaktifkan\033[0m")
            else:
                print(f"  Task {task_id} tidak ditemukan")
        else:
            print("  Pakai: /schedule [add|remove|enable|disable] ...")
    else:
        # Cek plugin commands
        if plugin_mgr:
            plugin_commands = plugin_mgr.get_all_commands()
            if cmd in plugin_commands:
                try:
                    result = plugin_commands[cmd](arg, cfg, messages)
                    if result:
                        print(f"  {result}")
                except Exception as e:
                    print(f"  \033[31mError: {e}\033[0m")
                return False

        print(f"  Perintah tidak dikenal: {cmd}. Ketik /help.")
    return False


def call_llm_streaming(cfg, messages, use_tools=True, timeout=180, hook_mgr=None):
    """Kirim permintaan ke LLM dengan streaming response.

    Return: (message, usage) di mana message adalah dict gabungan dari semua chunks.

    Args:
        hook_mgr: HookManager instance (optional) untuk lifecycle hooks
    """
    # before_llm hook
    if hook_mgr:
        hook_results = hook_mgr.emit('before_llm', messages=messages, cfg=cfg)
        for r in hook_results:
            if isinstance(r, list):
                messages = r

    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
        "stream": True  # Enable streaming
    }
    if use_tools:
        payload["tools"] = tools.SCHEMAS
        payload["tool_choice"] = "auto"

    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            # Collect streaming response
            full_content = ""
            tool_calls = []
            usage = {}
            current_tool_call = None

            # Read response
            response_data = resp.read().decode('utf-8')

            # Check if it's SSE format or regular JSON
            if response_data.strip().startswith('data: '):
                # SSE format - parse line by line
                for line in response_data.split('\n'):
                    line = line.strip()

                    # Skip empty lines
                    if not line or not line.startswith('data: '):
                        continue

                    # Check for end of stream
                    if line == 'data: [DONE]':
                        break

                    # Parse JSON chunk
                    try:
                        chunk = json.loads(line[6:])  # Remove 'data: ' prefix
                    except json.JSONDecodeError:
                        continue

                    # Extract choices
                    choices = chunk.get('choices', [])
                    if not choices:
                        # Check for usage in chunk
                        if 'usage' in chunk:
                            usage = chunk['usage']
                        continue

                    choice = choices[0]
                    delta = choice.get('delta', {})

                    # Handle content
                    if 'content' in delta and delta['content']:
                        content = delta['content']
                        full_content += content
                        # Print streaming token
                        sys.stdout.write(content)
                        sys.stdout.flush()

                    # Handle tool calls
                    if 'tool_calls' in delta:
                        for tc in delta['tool_calls']:
                            idx = tc.get('index', 0)

                            # Initialize or get current tool call
                            while len(tool_calls) <= idx:
                                tool_calls.append({
                                    'id': '',
                                    'type': 'function',
                                    'function': {'name': '', 'arguments': ''}
                                })

                            current = tool_calls[idx]

                            # Update tool call data
                            if 'id' in tc and tc['id']:
                                current['id'] = tc['id']

                            if 'function' in tc:
                                if 'name' in tc['function'] and tc['function']['name']:
                                    current['function']['name'] = tc['function']['name']
                                if 'arguments' in tc['function']:
                                    current['function']['arguments'] += tc['function']['arguments']

                    # Handle finish reason
                    if choice.get('finish_reason') == 'tool_calls':
                        # Reconstruct tool_calls format
                        pass
            else:
                # Regular JSON response - fallback to non-streaming
                try:
                    body = json.loads(response_data)
                    message = body.get("choices", [{}])[0].get("message", {})
                    usage = body.get("usage", {})

                    # Print content if available
                    if message.get("content"):
                        sys.stdout.write(message["content"])
                        sys.stdout.flush()

                    # after_llm hook
                    if hook_mgr:
                        hook_results = hook_mgr.emit('after_llm', response=message)
                        for r in hook_results:
                            if isinstance(r, dict):
                                message = r

                    return message, usage
                except Exception as e:
                    raise RuntimeError(f"Invalid response format: {e}")

            # Build message
            message = {"role": "assistant", "content": full_content}

            # Add tool calls if any
            valid_tool_calls = [tc for tc in tool_calls if tc.get('function', {}).get('name')]
            if valid_tool_calls:
                message['tool_calls'] = valid_tool_calls

            # after_llm hook
            if hook_mgr:
                hook_results = hook_mgr.emit('after_llm', response=message)
                for r in hook_results:
                    if isinstance(r, dict):
                        message = r

            return message, usage

    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        if use_tools and e.code in (400, 404, 422) and \
                ("tool" in detail.lower() or "function" in detail.lower()):
            print("\033[33m[info] endpoint menolak tools, mencoba ulang tanpa tools...\033[0m")
            return call_llm_streaming(cfg, messages, use_tools=False, timeout=timeout, hook_mgr=hook_mgr)
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    except Exception as e:
        raise RuntimeError(f"Streaming error: {e}")


def call_llm(cfg, messages, use_tools=True, timeout=180, hook_mgr=None, _retried=False):
    """Kirim permintaan ke endpoint chat completions (format OpenAI).

    Return: (message, usage) di mana:
    - message: dict balasan LLM
    - usage: dict token usage (prompt_tokens, completion_tokens, total_tokens)

    - Bila endpoint menolak parameter `tools` (HTTP 400/404/422, umum pada provider
      custom yang tidak mendukung function-calling), otomatis dicoba ulang tanpa tools.
    - Bila respons timeout (server lambat / cold-start, sering pada NVIDIA NIM),
      dicoba ulang sekali; bila masih gagal, dilempar sebagai RuntimeError agar
      ditangani anggun (program tidak crash).

    Args:
        hook_mgr: HookManager instance (optional) untuk lifecycle hooks
    """
    # before_llm hook
    if hook_mgr:
        hook_results = hook_mgr.emit('before_llm', messages=messages, cfg=cfg)
        # Jika hook mengembalikan messages baru, gunakan itu
        for r in hook_results:
            if isinstance(r, list):
                messages = r

    url = cfg["base_url"] + "/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
    }
    if use_tools:
        payload["tools"] = tools.SCHEMAS
        payload["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json"}
    if cfg["api_key"]:
        headers["Authorization"] = "Bearer " + cfg["api_key"]

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        usage = body.get("usage", {})

        # after_llm hook
        if hook_mgr:
            hook_results = hook_mgr.emit('after_llm', response=message)
            # Jika hook mengembalikan response baru, gunakan itu
            for r in hook_results:
                if isinstance(r, dict):
                    message = r

        return message, usage
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        # Banyak endpoint custom menolak parameter tools/function. Coba lagi tanpa tools.
        if use_tools and e.code in (400, 404, 422) and \
                ("tool" in detail.lower() or "function" in detail.lower()):
            print("\033[33m[info] endpoint menolak tools, mencoba ulang tanpa tools...\033[0m")
            return call_llm(cfg, messages, use_tools=False, timeout=timeout)
        raise RuntimeError(f"HTTP {e.code}: {detail}")
    except TimeoutError:
        # socket.timeout (alias TimeoutError) tidak terbungkus URLError -> tangani khusus.
        if not _retried:
            print("\033[33m[info] respons timeout, mencoba ulang sekali "
                  "(server mungkin cold-start)...\033[0m")
            return call_llm(cfg, messages, use_tools=use_tools,
                            timeout=timeout, _retried=True)
        raise RuntimeError(
            f"Timeout setelah {timeout} detik. Server lambat / cold-start "
            "(umum pada NVIDIA NIM). Coba lagi, atau pilih model yang lebih kecil/cepat."
        )
    except urllib.error.URLError as e:
        # URLError bisa membungkus timeout juga (mis. saat fase koneksi).
        if isinstance(getattr(e, "reason", None), TimeoutError) and not _retried:
            print("\033[33m[info] koneksi timeout, mencoba ulang sekali...\033[0m")
            return call_llm(cfg, messages, use_tools=use_tools,
                            timeout=timeout, _retried=True)
        raise RuntimeError(f"Koneksi gagal: {e.reason}")
    except (KeyError, IndexError, ValueError) as e:
        raise RuntimeError(f"Respons endpoint tidak sesuai format OpenAI: {e}")


def fetch_models(base_url, api_key):
    """Ambil daftar model yang tersedia dari endpoint /models (format OpenAI).

    Return (ok, hasil). Bila ok=True, hasil = list nama model.
    Bila ok=False, hasil = pesan error.
    """
    url = base_url.rstrip("/") + "/models"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, f"API key ditolak (HTTP {e.code}). Periksa key kamu."
        return False, f"HTTP {e.code}: endpoint menolak permintaan."
    except urllib.error.URLError as e:
        return False, f"Tidak bisa terhubung ke URL: {e.reason}"
    except Exception as e:
        return False, f"Gagal: {e}"

    # Format umum: {"data": [{"id": "..."}, ...]}  atau  {"models": [...]}
    items = body.get("data") or body.get("models") or []
    names = []
    for it in items:
        if isinstance(it, dict):
            names.append(it.get("id") or it.get("name") or "")
        elif isinstance(it, str):
            names.append(it)
    names = sorted(n for n in names if n)
    if not names:
        return False, "Endpoint merespons tetapi tidak ada daftar model."
    return True, names


def validate_endpoint(base_url, api_key):
    """Cek apakah URL + key valid dengan mencoba mengambil daftar model."""
    return fetch_models(base_url, api_key)


def check_tool_permission(tool_name, tool_args):
    """Check apakah tool boleh dieksekusi.

    Args:
        tool_name: Nama tool
        tool_args: Arguments tool

    Returns:
        bool: True jika boleh, False jika tidak
    """
    permission = TOOL_PERMISSIONS.get(tool_name, DEFAULT_TOOL_PERMISSION)

    if permission == "auto":
        return True
    elif permission == "deny":
        print(f"\033[31m  ⚠ Tool '{tool_name}' diblokir oleh permission system\033[0m")
        return False
    elif permission == "ask":
        # Format args untuk display
        args_display = ""
        if tool_args:
            if "path" in tool_args:
                args_display = f" ({tool_args['path']})"
            elif "command" in tool_args:
                args_display = f" ({tool_args['command'][:50]}...)"
            elif "url" in tool_args:
                args_display = f" ({tool_args['url'][:50]}...)"

        try:
            response = input(f"\033[33m  ⚠ Izinkan tool '{tool_name}'{args_display}? [Y/n]: \033[0m").strip().lower()
            return response in ("", "y", "yes", "ya")
        except (EOFError, KeyboardInterrupt):
            return False

    return True


def update_tool_permission(tool_name, permission):
    """Update permission untuk tool tertentu.

    Args:
        tool_name: Nama tool
        permission: "auto", "ask", atau "deny"
    """
    if permission in ("auto", "ask", "deny"):
        TOOL_PERMISSIONS[tool_name] = permission
        return True
    return False


def run_tool_calls(tool_calls, hook_mgr=None, tui=None):
    """Jalankan setiap tool yang diminta LLM, kembalikan pesan hasilnya.

    Args:
        tool_calls: List of tool call dicts dari LLM response
        hook_mgr: HookManager instance (optional) untuk lifecycle hooks
        tui: AizuTUI instance (optional) untuk display
    """
    results = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        fn = tools.REGISTRY.get(name)

        # Check permission sebelum execute
        if not check_tool_permission(name, args):
            results.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": f"Tool '{name}' diblokir oleh permission system.",
            })
            continue

        # before_tool hook
        if hook_mgr:
            hook_results = hook_mgr.emit('before_tool', tool_name=name, args=args)
            # Jika hook mengembalikan args baru, gunakan itu
            for r in hook_results:
                if isinstance(r, dict):
                    args = r

        # Tampilkan tool execution di TUI atau animasi lama
        if tui:
            tui.add_tool_execution(name, args)
        else:
            # Fallback ke animasi lama
            anim = show_tool_animation(name, args)
            time.sleep(0.3)

        if fn is None:
            if tui:
                tui.add_error(f"Tool '{name}' tidak ditemukan.")
            else:
                anim.stop(f"  \033[31m↳ ERROR: tool '{name}' tidak ditemukan.\033[0m")
            output = f"ERROR: tool '{name}' tidak ditemukan."
        else:
            try:
                output = fn(**args)
                # Tampilkan ringkasan hasil
                if tui:
                    # Format output for TUI
                    if name == "edit_file":
                        tui.add_success(f"File updated")
                    elif name == "write_file":
                        path = args.get("path", "")
                        tui.add_success(f"Wrote to {path}")
                    elif name == "read_file":
                        lines = str(output).count("\n") + 1
                        tui.add_success(f"Read {lines} lines")
                    elif name.startswith("git"):
                        tui.add_success(f"{name} completed")
                    elif name == "run_shell":
                        if output.startswith("✅"):
                            tui.add_success("Command completed")
                        elif output.startswith("❌"):
                            tui.add_error("Command failed")
                        else:
                            tui.add_success("Output received")
                    else:
                        tui.add_success(f"{name} completed")
                else:
                    # Animasi lama
                    if name == "edit_file":
                        anim.stop(f"  \033[32m↳ File updated ✓\033[0m")
                    elif name == "write_file":
                        path = args.get("path", "")
                        content = args.get("content", "")
                        lines = content.count("\n") + 1
                        anim.stop(f"  \033[32m↳ Wrote {lines} lines to {path} ✓\033[0m")
                    elif name == "read_file":
                        lines = str(output).count("\n") + 1
                        anim.stop(f"  \033[32m↳ Read {lines} lines ✓\033[0m")
                    elif name.startswith("git"):
                        anim.stop(f"  \033[32m↳ {name} ✓\033[0m")
                    elif name == "run_shell":
                        if output.startswith("✅"):
                            anim.stop(f"  \033[32m↳ Command completed ✓\033[0m")
                        elif output.startswith("❌"):
                            anim.stop(f"  \033[31m↳ Command failed ✗\033[0m")
                        else:
                            anim.stop(f"  \033[32m↳ Output received ✓\033[0m")
                    else:
                        result_preview = str(output)[:60]
                        if len(str(output)) > 60:
                            result_preview += "..."
                        anim.stop(f"  \033[32m↳ {result_preview}\033[0m")
            except Exception as e:
                if tui:
                    tui.add_error(f"Error: {e}")
                else:
                    anim.stop(f"  \033[31m↳ ERROR: {e}\033[0m")
                output = f"ERROR menjalankan {name}: {e}"

        # after_tool hook
        if hook_mgr:
            hook_results = hook_mgr.emit('after_tool', tool_name=name, args=args, result=output)
            # Jika hook mengembalikan result baru, gunakan itu
            for r in hook_results:
                if isinstance(r, str):
                    output = r

        results.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": str(output),
        })
    return results


def print_token_usage(usage, total_usage, context_info=None, model=None):
    """Tampilkan konsumsi token dan cost estimation."""
    total_tokens = usage.get("total_tokens", 0)
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)

    # Update total
    total_usage["total"] += total_tokens

    # Hitung cost
    pricing = PRICING.get(model, PRICING.get("default", {"input": 0.001, "output": 0.002}))
    cost_usd = (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1000
    cost_idr = cost_usd * USD_TO_IDR

    # Update total cost
    total_usage["cost_usd"] = total_usage.get("cost_usd", 0) + cost_usd
    total_usage["cost_idr"] = total_usage.get("cost_idr", 0) + cost_idr

    # Format cost display
    if cost_usd > 0:
        cost_display = f"${cost_usd:.4f} (Rp{cost_idr:,.0f})"
    else:
        cost_display = "Free"

    # Tampilkan
    if context_info and context_info.get("compressed"):
        print(f"\033[90m  ✻ {total_tokens} tokens | {cost_display} (cached)\033[0m")
    else:
        print(f"\033[90m  ✻ {total_tokens} tokens | {cost_display}\033[0m")


def chat_loop(cfg):
    mode = cfg.get("mode", DEFAULT_MODE)

    # Inisialisasi Plugin Manager dan Hook Manager
    plugin_mgr = PluginManager(cfg)
    hook_mgr = HookManager()

    # Load semua plugin
    plugin_mgr.load_all()

    # Register hooks dari plugin
    for plugin in plugin_mgr.plugins:
        hook_mgr.register_from_plugin(plugin)

    # Register tools, backends, modes dari plugin
    plugin_mgr.register_tools(tools.REGISTRY, tools.SCHEMAS)
    plugin_mgr.register_backends(PRESETS)
    plugin_mgr.register_modes(MODES)

    # Inisialisasi Memory Manager dan register memory tools
    memory_mgr = get_memory_manager()
    memory_tools = create_memory_tools(memory_mgr)
    for name, (func, schema) in memory_tools.items():
        if name not in tools.REGISTRY:
            tools.REGISTRY[name] = func
            tools.SCHEMAS.append(schema)

    # Inisialisasi Skill Manager
    skill_mgr = get_skill_manager()

    # Inisialisasi Scheduler
    scheduler = get_scheduler()

    # Startup hook
    hook_mgr.emit('on_startup')

    # Inisialisasi TUI
    tui = AizuTUI(
        workspace_path=os.getcwd(),
        backend=cfg['backend'],
        model=cfg.get('model', '')
    )

    try:
        # Setup TUI
        tui.setup()

        # Tampilkan info plugins
        if plugin_mgr.plugins:
            tui.add_info(f"Loaded {len(plugin_mgr.plugins)} plugins")

        # Tampilkan info mode
        tui.add_info(f"Mode: {mode} — {MODES.get(mode, MODES[DEFAULT_MODE])['desc']}")

        # Tampilkan warning jika API key belum diatur
        if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
            tui.add_error("API key belum diatur. Atur dengan: /key <api-key>")

        messages = [{"role": "system", "content": build_system_prompt(mode)}]
        total_usage = {"prompt": 0, "completion": 0, "total": 0}

        while True:
            try:
                # Get input from TUI
                user = tui.get_input().strip()
            except (EOFError, KeyboardInterrupt):
                tui.add_info("Daah!")
                # Auto-save session sebelum exit
                if len(messages) > 1:
                    session_name = datetime.now().strftime("%Y%m%d_%H%M%S")
                    save_session(messages, session_name)
                    tui.add_info(f"Session saved: {session_name}")
                hook_mgr.emit('on_shutdown')
                plugin_mgr.shutdown()
                break

            if not user:
                continue

            # on_message hook
            hook_mgr.emit('on_message', message=user)

            # Semua perintah diawali '/' ditangani sebagai pengaturan.
            if user.startswith("/"):
                if handle_slash(user, cfg, messages, plugin_mgr, hook_mgr, tui):
                    hook_mgr.emit('on_shutdown')
                    plugin_mgr.shutdown()
                    break
                continue

            # Pastikan key tersedia bila backend membutuhkannya.
            if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
                tui.add_error("API key belum diatur. Atur dengan: /key <api-key>")
                continue

            messages.append({"role": "user", "content": user})
            tui.add_user_message(user)

            # Memory auto-recall: inject relevant memories
            memory_context = memory_mgr.recall(user, limit=3)
            if memory_context:
                # Inject as system-level context before LLM call
                messages.insert(-1, {
                    "role": "system",
                    "content": memory_context
                })

        # Kompresi pesan untuk hemat token (prompt caching)
        if len(messages) > MAX_CONTEXT_MESSAGES:
            compressed = compress_messages(messages, cfg=cfg)
            # Tampilkan info kompresi
            old_count = len(messages)
            new_count = len(compressed)
            saved = old_count - new_count
            tui.add_info(f"Context compressed: {old_count} → {new_count} messages (saved {saved})")
        else:
            compressed = messages

        # Loop tool-calling: LLM bisa memanggil beberapa tool sebelum menjawab.
        tui.start_thinking("Thinking", "ctrl+o to expand")
        tool_call_count = 0
        MAX_TOOL_CALLS = 20  # Naikkan batas

        for _ in range(MAX_TOOL_CALLS):
            try:
                # Use streaming by default, fallback to non-streaming on error
                try:
                    msg, usage = call_llm_streaming(cfg, compressed, hook_mgr=hook_mgr)
                except RuntimeError as streaming_error:
                    # Fallback to non-streaming
                    tui.stop_thinking()
                    tui.add_info("Streaming tidak support, menggunakan non-streaming...")
                    tui.start_thinking("Thinking", "ctrl+o to expand")
                    msg, usage = call_llm(cfg, compressed, hook_mgr=hook_mgr)
                # Stop thinking
                tui.stop_thinking()
            except RuntimeError as e:
                hook_mgr.emit('on_error', error=e, context={'phase': 'llm_call'})
                tui.stop_thinking()
                tui.add_error(str(e))
                break

            # Simpan balasan asisten (termasuk permintaan tool bila ada).
            assistant_msg = {"role": "assistant", "content": msg.get("content") or ""}
            if msg.get("tool_calls"):
                assistant_msg["tool_calls"] = msg["tool_calls"]
            messages.append(assistant_msg)

            if msg.get("tool_calls"):
                tool_call_count += 1
                # Tampilkan token usage untuk tool call
                if usage:
                    is_compressed = len(messages) > MAX_CONTEXT_MESSAGES
                    print_token_usage(usage, total_usage, {"compressed": is_compressed}, model=cfg.get("model"))

                # Cek apakah tool call sudah terlalu banyak
                if tool_call_count >= MAX_TOOL_CALLS:
                    tui.add_info(f"{tool_call_count} tool calls dilakukan, memberikan jawaban final...")
                    # Minta LLM untuk memberikan jawaban final
                    messages.append({"role": "user", "content": "Berikan jawaban final sekarang, jangan panggil tool lagi."})
                    try:
                        final_msg, final_usage = call_llm(cfg, messages, hook_mgr=hook_mgr)
                        final_content = final_msg.get("content") or "(tidak ada jawaban)"
                        tui.add_assistant_message(final_content)
                        if final_usage:
                            print_token_usage(final_usage, total_usage, model=cfg.get("model"))
                    except:
                        pass
                    break

                tool_results = run_tool_calls(msg["tool_calls"], hook_mgr=hook_mgr, tui=tui)
                messages.extend(tool_results)

                # Kompresi lagi jika perlu
                if len(messages) > MAX_CONTEXT_MESSAGES:
                    compressed = compress_messages(messages, cfg=cfg)

                continue  # kirim hasil tool kembali ke LLM

            # Tidak ada tool call -> ini jawaban final.
            content = msg.get("content") or "(tidak ada jawaban)"
            tui.add_assistant_message(content)
            # Tampilkan token usage untuk response final
            if usage:
                is_compressed = len(messages) > MAX_CONTEXT_MESSAGES
                print_token_usage(usage, total_usage, {"compressed": is_compressed}, model=cfg.get("model"))
            break
        else:
            tui.add_info(f"Selesai setelah {MAX_TOOL_CALLS} tool calls")

    finally:
        # Cleanup TUI
        tui.cleanup()


def choose_model_interactive(cfg, models):
    """Pilih model dari daftar, dengan fitur pencarian agar tidak capek scroll."""
    current = models
    while True:
        print(f"\n\033[36mTersedia {len(current)} model.\033[0m")
        # Tampilkan maksimal 30 agar tidak membanjiri layar.
        tampil = current[:30]
        for i, m in enumerate(tampil, 1):
            print(f"  {i:>3}. {m}")
        if len(current) > 30:
            print(f"  ... dan {len(current) - 30} lagi (pakai pencarian untuk mempersempit)")

        print("\n  Ketik: nomor untuk pilih | /cari <kata> untuk filter | "
              "/all reset daftar | /ketik untuk isi manual")
        try:
            inp = input("Pilihan model: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None

        if not inp:
            continue
        if inp.startswith("/cari"):
            kata = inp[5:].strip().lower()
            hasil = [m for m in models if kata in m.lower()]
            if hasil:
                current = hasil
            else:
                print("  (tidak ada model cocok, daftar tidak diubah)")
            continue
        if inp == "/all":
            current = models
            continue
        if inp == "/ketik":
            try:
                manual = input("  Nama model manual: ").strip()
            except (EOFError, KeyboardInterrupt):
                manual = ""
            if manual:
                return manual
            continue
        # Coba sebagai nomor.
        try:
            idx = int(inp) - 1
            if 0 <= idx < len(tampil):
                return tampil[idx]
            print("  Nomor di luar rentang.")
        except ValueError:
            print("  Input tidak dikenali. Pakai nomor, /cari, /all, atau /ketik.")


def setup_custom_provider(cfg):
    """Setup provider custom: minta URL -> key -> validasi (ulang bila gagal) -> pilih model."""
    print("\033[36m--- Setup Provider Custom (kompatibel OpenAI) ---\033[0m")
    print("Contoh base URL: https://api.namaprovider.com/v1")

    while True:
        try:
            url = input("\nMasukkan base URL API (atau kosong untuk batal): ").strip()
        except (EOFError, KeyboardInterrupt):
            return False
        if not url:
            print("  Dibatalkan.")
            return False
        if not url.startswith("http"):
            print("  URL harus diawali http:// atau https://")
            continue
        url = url.rstrip("/")

        try:
            key = input("Masukkan API key (kosongkan bila tidak perlu): ").strip()
        except (EOFError, KeyboardInterrupt):
            return False

        print("  \033[33mMemeriksa endpoint...\033[0m")
        ok, hasil = validate_endpoint(url, key)
        if not ok:
            print(f"  \033[31mGAGAL: {hasil}\033[0m")
            print("  Silakan masukkan URL lagi.")
            continue

        # Valid — hasil = daftar model.
        print(f"  \033[32mVALID! Ditemukan {len(hasil)} model.\033[0m")
        cfg["backend"] = "custom"
        cfg["base_url"] = url
        cfg["api_key"] = key

        model = choose_model_interactive(cfg, hasil)
        if not model:
            # Tidak memilih model; pakai yang pertama sebagai default.
            model = hasil[0]
            print(f"  Tidak memilih, dipakai default: {model}")
        cfg["model"] = model
        idx = remember_provider(cfg, url, key, model)
        print(f"  \033[32mProvider custom siap | model: {model}\033[0m")
        print(f"  \033[32mTersimpan sebagai '{idx}' (API key ikut tersimpan). "
              f"Pilih lagi nanti lewat /providers.\033[0m")
        return True


def choose_backend_interactive(cfg):
    """Tampilkan menu pemilihan penyedia AI saat pertama dijalankan."""
    # Bila sudah ada provider custom tersimpan, tawarkan pilih langsung.
    if cfg.get("saved_providers"):
        print(f"\033[36mAda {len(cfg['saved_providers'])} provider custom tersimpan.\033[0m")
        try:
            pakai = input("Pakai salah satu provider tersimpan? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            pakai = ""
        if pakai in ("y", "ya", "yes") and choose_saved_provider(cfg):
            return cfg

    names = list(PRESETS.keys())
    print("\033[36m" + "=" * 52)
    print(" Pilih penyedia AI (provider):")
    print("=" * 52 + "\033[0m")
    for i, name in enumerate(names, 1):
        p = PRESETS[name]
        if name == "custom":
            note = "masukkan URL & key sendiri, model dicari otomatis"
            print(f"  {i}. {name:<11} — {note}")
        else:
            key_note = "butuh API key" if p["needs_key"] else "lokal/offline, tanpa key"
            print(f"  {i}. {name:<11} — {key_note} | default: {p['model']}")

    try:
        pilih = input("\nNomor pilihan [1-%d] (Enter = groq): " % len(names)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return cfg

    chosen = "groq"
    if pilih:
        try:
            idx = int(pilih) - 1
            if 0 <= idx < len(names):
                chosen = names[idx]
            else:
                print("[info] pilihan di luar rentang, dipakai groq.")
        except ValueError:
            print("[info] input bukan angka, dipakai groq.")

    if chosen == "custom":
        if not setup_custom_provider(cfg):
            # Batal -> kembali ke groq default.
            apply_backend(cfg, "groq")
    else:
        apply_backend(cfg, chosen)

        # Minta API key bila backend membutuhkannya dan belum ada.
        if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
            try:
                key = input(f"Masukkan API key untuk {cfg['backend']} "
                            f"(boleh kosong, isi nanti dengan /key): ").strip()
            except (EOFError, KeyboardInterrupt):
                key = ""
            if key:
                cfg["api_key"] = key

        # Tawarkan auto-cari model bila key tersedia.
        if cfg["api_key"] or not PRESETS[cfg["backend"]]["needs_key"]:
            try:
                cari = input("Cari & pilih model dari provider ini sekarang? [y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                cari = ""
            if cari in ("y", "ya", "yes"):
                ok, hasil = fetch_models(cfg["base_url"], cfg["api_key"])
                if ok:
                    m = choose_model_interactive(cfg, hasil)
                    if m:
                        cfg["model"] = m
                        print(f"  Model -> {m}")
                else:
                    print(f"  [info] gagal ambil model: {hasil} (pakai default {cfg['model']})")

    # Tawarkan simpan agar tidak perlu pilih lagi lain kali.
    try:
        simpan = input("Simpan pengaturan ini untuk seterusnya? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        simpan = ""
    if simpan in ("y", "ya", "yes"):
        print("  " + save_config(cfg))

    return cfg


if __name__ == "__main__":
    config = load_config()
    # Jalankan menu pemilihan hanya saat belum ada config & tidak dipaksa lewat env var.
    first_run = not os.path.exists(CONFIG_PATH) and "AGENT_BACKEND" not in os.environ
    if first_run and sys.stdin.isatty():
        config = choose_backend_interactive(config)
    chat_loop(config)
