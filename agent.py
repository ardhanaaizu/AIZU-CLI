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

try:
    import termios
    import tty
    _HAS_TTY = True
except ImportError:           # Windows / lingkungan tanpa termios
    _HAS_TTY = False

import tools


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
    "📁 File: read_file, write_file, edit_file, list_dir, search_files"
    "\n"
    "🌐 Web: web_search (cari internet), web_fetch (ambil dari URL)"
    "\n"
    "🔧 Git: git_status, git_log, git_diff, git_add, git_commit, git_push, git_pull, git_branch, git_checkout"
    "\n"
    "💻 Shell: run_shell (jalankan perintah terminal)"
    "\n\n"
    "ATURAN KERJA:"
    "\n"
    "1. Gunakan tool secara aktif untuk menyelesaikan tugas. Jangan hanya menjelaskan — LAKUKAN."
    "\n"
    "2. Untuk tugas kompleks, pecah menjadi langkah-langkah dan kerjakan satu per satu."
    "\n"
    "3. Selalu cek status dulu sebelum melakukan sesuatu (misal: git status sebelum commit)."
    "\n"
    "4. Untuk edit file, gunakan edit_file (bukan write_file) supaya lebih presisi."
    "\n"
    "5. Bila butuh informasi dari internet, gunakan web_search atau web_fetch."
    "\n"
    "6. Bila ditanya sesuatu yang butuh riset, cari dulu di internet."
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

# Context management settings
MAX_CONTEXT_MESSAGES = 20  # Maksimal pesan yang dikirim ke API
CACHE_SUMMARY_TOKENS = 100  # Estimasi token untuk summary percakapan lama


def compress_messages(messages, max_messages=MAX_CONTEXT_MESSAGES):
    """Kompresi pesan untuk hemat token.

    Strategi:
    - Simpan system prompt selalu
    - Simpan 5 pesan terakhir (recent context)
    - Pesan lama di-summary jadi satu
    """
    if len(messages) <= max_messages:
        return messages

    # Pisahkan system prompt
    system_msg = messages[0] if messages[0]["role"] == "system" else None
    other_msgs = messages[1:] if system_msg else messages

    # Simpan 5 pesan terakhir
    recent = other_msgs[-5:]
    old = other_msgs[:-5]

    # Buat summary dari pesan lama
    if old:
        summary_parts = []
        for msg in old:
            if msg["role"] == "user":
                content = msg.get("content", "")[:100]
                summary_parts.append(f"User: {content}")
            elif msg["role"] == "assistant" and not msg.get("tool_calls"):
                content = msg.get("content", "")[:100]
                summary_parts.append(f"Assistant: {content}")

        summary_content = "Ringkasan percakapan sebelumnya:\n" + "\n".join(summary_parts[-10:])
        summary_msg = {"role": "user", "content": summary_content}
        compressed = [summary_msg] + recent
    else:
        compressed = recent

    # Tambah system prompt di awal
    if system_msg:
        compressed = [system_msg] + compressed

    return compressed


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
  /keluar              keluar dari agent

Tool yang tersedia:
  File    : read_file, write_file, edit_file, list_dir, search_files
  Web     : web_search, web_fetch
  Git     : git_status, git_log, git_diff, git_add, git_commit, git_push, git_pull, git_branch, git_checkout
  Shell   : run_shell"""


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


def handle_slash(line, cfg, messages):
    """Tangani perintah slash. Return True jika program harus berhenti."""
    parts = line.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("/keluar", "/exit", "/quit"):
        print("Daah!")
        return True
    elif cmd in ("/help", "/?"):
        print(SLASH_HELP)
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
    else:
        print(f"  Perintah tidak dikenal: {cmd}. Ketik /help.")
    return False


def call_llm(cfg, messages, use_tools=True, timeout=180, _retried=False):
    """Kirim permintaan ke endpoint chat completions (format OpenAI).

    Return: (message, usage) di mana:
    - message: dict balasan LLM
    - usage: dict token usage (prompt_tokens, completion_tokens, total_tokens)

    - Bila endpoint menolak parameter `tools` (HTTP 400/404/422, umum pada provider
      custom yang tidak mendukung function-calling), otomatis dicoba ulang tanpa tools.
    - Bila respons timeout (server lambat / cold-start, sering pada NVIDIA NIM),
      dicoba ulang sekali; bila masih gagal, dilempar sebagai RuntimeError agar
      ditangani anggun (program tidak crash).
    """
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


def run_tool_calls(tool_calls):
    """Jalankan setiap tool yang diminta LLM, kembalikan pesan hasilnya."""
    results = []
    for tc in tool_calls:
        name = tc["function"]["name"]
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        fn = tools.REGISTRY.get(name)

        # Tampilkan animasi loading
        anim = show_tool_animation(name, args)
        time.sleep(0.3)  # Biar animasi terlihat

        if fn is None:
            anim.stop(f"  \033[31m↳ ERROR: tool '{name}' tidak ditemukan.\033[0m")
            output = f"ERROR: tool '{name}' tidak ditemukan."
        else:
            try:
                output = fn(**args)
                # Tampilkan ringkasan hasil sesuai tool
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
                elif name == "list_dir":
                    items = str(output).count("\n") + 1
                    anim.stop(f"  \033[32m↳ {items} items ✓\033[0m")
                elif name.startswith("git"):
                    anim.stop(f"  \033[32m↳ {name} ✓\033[0m")
                elif name == "run_shell":
                    if output.startswith("✅"):
                        anim.stop(f"  \033[32m↳ Command completed ✓\033[0m")
                    elif output.startswith("❌"):
                        anim.stop(f"  \033[31m↳ Command failed ✗\033[0m")
                    else:
                        anim.stop(f"  \033[32m↳ Output received ✓\033[0m")
                elif name in ("web_search", "web_fetch"):
                    anim.stop(f"  \033[32m↳ Data fetched ✓\033[0m")
                elif name == "search_files":
                    count = str(output).count("\n") + 1
                    anim.stop(f"  \033[32m↳ Found {count} results ✓\033[0m")
                else:
                    result_preview = str(output)[:60]
                    if len(str(output)) > 60:
                        result_preview += "..."
                    anim.stop(f"  \033[32m↳ {result_preview}\033[0m")
            except Exception as e:
                anim.stop(f"  \033[31m↳ ERROR: {e}\033[0m")
                output = f"ERROR menjalankan {name}: {e}"

        results.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": str(output),
        })
    return results


def print_token_usage(usage, total_usage, context_info=None):
    """Tampilkan konsumsi token secara simple."""
    total_tokens = usage.get("total_tokens", 0)

    # Update total
    total_usage["total"] += total_tokens

    # Tampilkan simple
    if context_info and context_info.get("compressed"):
        print(f"\033[90m  ✻ {total_tokens} tokens (cached)\033[0m")
    else:
        print(f"\033[90m  ✻ {total_tokens} tokens\033[0m")


def chat_loop(cfg):
    mode = cfg.get("mode", DEFAULT_MODE)
    # Clear screen sebelum tampilkan banner
    print("\033[2J\033[H", end="")
    print("\033[36m" + BANNER + "\033[0m")
    print("\033[36m" + "=" * 54 + "\033[0m")
    print(f"  Provider : \033[32m{cfg['backend']}\033[0m")
    print(f"  Model    : \033[32m{cfg['model'] or '(belum dipilih)'}\033[0m")
    print(f"  Mode     : \033[32m{mode}\033[0m — {MODES.get(mode, MODES[DEFAULT_MODE])['desc']}")
    print(f"  Endpoint : {cfg['base_url'] or '(belum diatur)'}")
    print("\033[36m" + "=" * 54 + "\033[0m")
    print(" Ketik /help untuk daftar perintah, /keluar untuk berhenti.")

    if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
        print("\033[33m[info] API key belum diatur. Atur dengan: /key <api-key>\033[0m")

    messages = [{"role": "system", "content": build_system_prompt(mode)}]
    total_usage = {"prompt": 0, "completion": 0, "total": 0}

    while True:
        print()
        try:
            user = prompt_with_completion("\033[32mkamu>\033[0m ", 6).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nDaah!")
            break

        if not user:
            continue

        # Semua perintah diawali '/' ditangani sebagai pengaturan.
        if user.startswith("/"):
            if handle_slash(user, cfg, messages):
                break
            continue

        # Pastikan key tersedia bila backend membutuhkannya.
        if PRESETS[cfg["backend"]]["needs_key"] and not cfg["api_key"]:
            print("\033[33m[info] Belum ada API key. Atur dulu dengan: /key <api-key>\033[0m")
            continue

        messages.append({"role": "user", "content": user})

        # Kompresi pesan untuk hemat token (prompt caching)
        if len(messages) > MAX_CONTEXT_MESSAGES:
            compressed = compress_messages(messages)
            # Tampilkan info kompresi
            old_count = len(messages)
            new_count = len(compressed)
            saved = old_count - new_count
            print(f"\033[90m  ✻ Context compressed: {old_count} → {new_count} messages (saved {saved})\033[0m")
        else:
            compressed = messages

        # Loop tool-calling: LLM bisa memanggil beberapa tool sebelum menjawab.
        thinking_anim = LoadingAnimation(THINKING_FRAMES, delay=0.2)
        thinking_anim.start()
        time.sleep(0.5)  # Biar user lihat animasi awal
        tool_call_count = 0
        MAX_TOOL_CALLS = 20  # Naikkan batas

        for _ in range(MAX_TOOL_CALLS):
            try:
                msg, usage = call_llm(cfg, compressed)
            except RuntimeError as e:
                thinking_anim.stop()
                print(f"\033[31m[error] {e}\033[0m")
                break

            # Simpan balasan asisten (termasuk permintaan tool bila ada).
            assistant_msg = {"role": "assistant", "content": msg.get("content") or ""}
            if msg.get("tool_calls"):
                assistant_msg["tool_calls"] = msg["tool_calls"]
            messages.append(assistant_msg)

            if msg.get("tool_calls"):
                tool_call_count += 1
                thinking_anim.stop()
                # Tampilkan token usage untuk tool call
                if usage:
                    is_compressed = len(messages) > MAX_CONTEXT_MESSAGES
                    print_token_usage(usage, total_usage, {"compressed": is_compressed})

                # Cek apakah tool call sudah terlalu banyak
                if tool_call_count >= MAX_TOOL_CALLS:
                    print(f"\033[33m[info] {tool_call_count} tool calls dilakukan, memberikan jawaban final...\033[0m")
                    # Minta LLM untuk memberikan jawaban final
                    messages.append({"role": "user", "content": "Berikan jawaban final sekarang, jangan panggil tool lagi."})
                    try:
                        final_msg, final_usage = call_llm(cfg, messages)
                        final_content = final_msg.get("content") or "(tidak ada jawaban)"
                        print(f"\n\033[36m{ASSISTANT_NAME}>\033[0m {final_content}")
                        if final_usage:
                            print_token_usage(final_usage, total_usage)
                    except:
                        pass
                    break

                tool_results = run_tool_calls(msg["tool_calls"])
                messages.extend(tool_results)

                # Kompresi lagi jika perlu
                if len(messages) > MAX_CONTEXT_MESSAGES:
                    compressed = compress_messages(messages)

                # Mulai animasi thinking lagi untuk response berikutnya
                thinking_anim = LoadingAnimation(THINKING_FRAMES)
                thinking_anim.start()
                continue  # kirim hasil tool kembali ke LLM

            # Tidak ada tool call -> ini jawaban final.
            thinking_anim.stop()
            content = msg.get("content") or "(tidak ada jawaban)"
            print(f"\n\033[36m{ASSISTANT_NAME}>\033[0m {content}")
            # Tampilkan token usage untuk response final
            if usage:
                is_compressed = len(messages) > MAX_CONTEXT_MESSAGES
                print_token_usage(usage, total_usage, {"compressed": is_compressed})
            break
        else:
            thinking_anim.stop()
            print(f"\033[33m[info] Selesai setelah {MAX_TOOL_CALLS} tool calls\033[0m")


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
