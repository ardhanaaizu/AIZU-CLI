"""
tools.py — Kumpulan tool yang bisa dipanggil oleh agent.

Setiap tool punya:
  - definisi skema (untuk dikirim ke LLM)
  - fungsi implementasi (dijalankan secara lokal di Termux)

Fitur:
  - File operations: read, write, edit, search
  - Directory: list
  - Shell: run commands
  - Web: search, fetch
  - Git: status, commit, push, pull, diff
"""

import os
import re
import subprocess
import urllib.request
import urllib.error
import json
import glob

# Batas keamanan sederhana untuk perintah shell.
DANGEROUS = ["rm -rf /", "mkfs", ":(){", "dd if=", "> /dev/sd"]


def read_file(path: str) -> str:
    """Baca isi file teks."""
    try:
        path = os.path.expanduser(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
        # Batasi output agar tidak membanjiri konteks.
        if len(data) > 20000:
            data = data[:20000] + "\n... (terpotong, file terlalu panjang)"
        return data
    except Exception as e:
        return f"ERROR membaca file: {e}"


def write_file(path: str, content: str) -> str:
    """Tulis (atau timpa) isi file teks."""
    try:
        path = os.path.expanduser(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"OK: {len(content)} karakter ditulis ke {path}"
    except Exception as e:
        return f"ERROR menulis file: {e}"


def list_dir(path: str = ".") -> str:
    """Tampilkan isi sebuah direktori."""
    try:
        path = os.path.expanduser(path)
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            tag = "DIR " if os.path.isdir(full) else "FILE"
            entries.append(f"[{tag}] {name}")
        return "\n".join(entries) if entries else "(direktori kosong)"
    except Exception as e:
        return f"ERROR membaca direktori: {e}"


def run_shell(command: str) -> str:
    """Jalankan perintah shell di Termux dan kembalikan output-nya."""
    low = command.lower()
    for bad in DANGEROUS:
        if bad in low:
            return f"DITOLAK: perintah berbahaya terdeteksi ('{bad}')."
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if len(out) > 10000:
            out = out[:10000] + "\n... (terpotong)"
        return out.strip() or f"(selesai, kode keluar {result.returncode})"
    except subprocess.TimeoutExpired:
        return "ERROR: perintah melebihi batas waktu 60 detik."
    except Exception as e:
        return f"ERROR menjalankan perintah: {e}"


# ---------------------------------------------------------------------------
# Web tools: search dan fetch
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5) -> str:
    """Cari di internet menggunakan DuckDuckGo (tanpa API key)."""
    try:
        # DuckDuckGo Instant Answer API
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
        req = urllib.request.Request(url, headers={"User-Agent": "AIZU-CLI/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        results = []

        # Abstract (jawaban langsung)
        if data.get("Abstract"):
            results.append(f"📖 **Ringkasan:** {data['Abstract']}")
            if data.get("AbstractURL"):
                results.append(f"   Sumber: {data['AbstractURL']}")

        # Related topics
        for topic in data.get("RelatedTopics", [])[:max_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                text = topic["Text"][:200]
                url = topic.get("FirstURL", "")
                results.append(f"• {text}")
                if url:
                    results.append(f"  {url}")

        if not results:
            return f"Tidak ditemukan hasil untuk: {query}"

        return "\n".join(results)
    except Exception as e:
        return f"ERROR web search: {e}"


def web_fetch(url: str, max_length: int = 5000) -> str:
    """Ambil konten dari URL dan konversi ke teks sederhana."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "AIZU-CLI/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Strip HTML tags sederhana
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()

        # Ambil title jika ada
        title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ""

        if len(content) > max_length:
            content = content[:max_length] + "\n... (terpotong)"

        result = ""
        if title:
            result += f"📄 **{title}**\n\n"
        result += content
        return result
    except Exception as e:
        return f"ERROR web fetch: {e}"


# ---------------------------------------------------------------------------
# File tools: edit dan search
# ---------------------------------------------------------------------------

def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Edit bagian tertentu dari file teks (replace text lama dengan baru)."""
    try:
        path = os.path.expanduser(path)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        if old_text not in content:
            return f"ERROR: teks '{old_text[:50]}...' tidak ditemukan di {path}"

        # Hitung berapa kali muncul
        count = content.count(old_text)
        new_content = content.replace(old_text, new_text, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        msg = f"OK: '{old_text[:30]}...' diganti di {path}"
        if count > 1:
            msg += f" (ada {count} kemunculan, yang pertama saja diganti)"
        return msg
    except Exception as e:
        return f"ERROR edit file: {e}"


def search_files(path: str = ".", pattern: str = "", content_search: str = "") -> str:
    """Cari file berdasarkan nama pattern ATAU konten.

    - pattern: glob pattern untuk nama file (mis. '*.py', '*.txt')
    - content_search: cari teks di dalam file
    """
    try:
        path = os.path.expanduser(path)
        results = []

        if pattern:
            # Search by filename
            search_pattern = os.path.join(path, "**", pattern)
            files = glob.glob(search_pattern, recursive=True)
            for f in sorted(files)[:50]:
                rel = os.path.relpath(f, path)
                size = os.path.getsize(f)
                results.append(f"  {rel} ({size} bytes)")

            if not results:
                return f"Tidak ditemukan file dengan pattern: {pattern}"
            return f"📂 File ditemukan ({len(results)}):\n" + "\n".join(results)

        elif content_search:
            # Search by content
            count = 0
            for root, dirs, files in os.walk(path):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for fname in files:
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if content_search.lower() in line.lower():
                                    rel = os.path.relpath(fpath, path)
                                    results.append(f"  {rel}:{i}: {line.strip()[:100]}")
                                    count += 1
                                    if count >= 30:
                                        return f"📂 Ditemukan {count}+ hasil (terbatas 30):\n" + "\n".join(results)
                    except (IOError, UnicodeDecodeError):
                        pass

            if not results:
                return f"Tidak ditemukan '{content_search}' di {path}"
            return f"📂 Ditemukan {len(results)} hasil:\n" + "\n".join(results)
        else:
            return "Penggunaan: search_files(path, pattern='*.py') ATAU search_files(path, content_search='teks')"
    except Exception as e:
        return f"ERROR search files: {e}"


# ---------------------------------------------------------------------------
# Git tools
# ---------------------------------------------------------------------------

def git_status() -> str:
    """Tampilkan status git repository."""
    return run_shell("git status --short")


def git_log(count: int = 10) -> str:
    """Tampilkan log git terakhir."""
    return run_shell(f"git log --oneline -{count}")


def git_diff(file: str = "") -> str:
    """Tampilkan perbedaan file (diff)."""
    if file:
        return run_shell(f"git diff {file}")
    return run_shell("git diff")


def git_add(files: str = ".") -> str:
    """Tambah file ke staging area."""
    return run_shell(f"git add {files}")


def git_commit(message: str) -> str:
    """Commit perubahan dengan pesan."""
    # Escape quotes
    safe_msg = message.replace('"', '\\"').replace("'", "\\'")
    return run_shell(f'git commit -m "{safe_msg}"')


def git_push() -> str:
    """Push ke remote repository."""
    return run_shell("git push")


def git_pull() -> str:
    """Pull dari remote repository."""
    return run_shell("git pull")


def git_branch(branch_name: str = "") -> str:
    """Lihat atau buat branch baru."""
    if branch_name:
        return run_shell(f"git checkout -b {branch_name}")
    return run_shell("git branch")


def git_checkout(branch: str) -> str:
    """Pindah ke branch lain."""
    return run_shell(f"git checkout {branch}")


# Peta nama tool -> fungsi
REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "run_shell": run_shell,
    "web_search": web_search,
    "web_fetch": web_fetch,
    "edit_file": edit_file,
    "search_files": search_files,
    "git_status": git_status,
    "git_log": git_log,
    "git_diff": git_diff,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_push": git_push,
    "git_pull": git_pull,
    "git_branch": git_branch,
    "git_checkout": git_checkout,
}

# Skema tool dalam format OpenAI function-calling.
SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Baca isi sebuah file teks dari sistem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang dibaca"}
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Tulis atau timpa isi sebuah file teks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file tujuan"},
                    "content": {"type": "string", "description": "Isi yang akan ditulis"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edit bagian tertentu dari file teks (ganti text lama dengan baru).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang diedit"},
                    "old_text": {"type": "string", "description": "Teks lama yang akan diganti"},
                    "new_text": {"type": "string", "description": "Teks baru pengganti"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Tampilkan daftar file dan folder dalam sebuah direktori.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path direktori (default '.')"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": "Cari file berdasarkan nama (pattern) atau konten teks di dalamnya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path direktori pencarian (default '.')"},
                    "pattern": {"type": "string", "description": "Pattern nama file (mis. '*.py', '*.txt')"},
                    "content_search": {"type": "string", "description": "Teks yang dicari di dalam file"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Jalankan perintah shell di Termux dan kembalikan output.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Perintah shell yang dijalankan"}
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Cari informasi di internet menggunakan DuckDuckGo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian"},
                    "max_results": {"type": "integer", "description": "Jumlah maksimal hasil (default 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": "Ambil konten dari sebuah URL website.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL yang akan diambil"},
                    "max_length": {"type": "integer", "description": "Panjang maksimal konten (default 5000)"},
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Tampilkan status git repository (file yang berubah).",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Tampilkan log commit git terakhir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "Jumlah commit yang ditampilkan (default 10)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": "Tampilkan perbedaan (diff) file yang belum di-commit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Nama file tertentu (opsional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_add",
            "description": "Tambah file ke staging area git.",
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {"type": "string", "description": "File atau pattern (default '.')"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": "Commit perubahan ke git dengan pesan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "Pesan commit"},
                },
                "required": ["message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_push",
            "description": "Push commit ke remote repository.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_pull",
            "description": "Pull dari remote repository.",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_branch",
            "description": "Lihat semua branch atau buat branch baru.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch_name": {"type": "string", "description": "Nama branch baru (opsional)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_checkout",
            "description": "Pindah ke branch lain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "branch": {"type": "string", "description": "Nama branch tujuan"},
                },
                "required": ["branch"],
            },
        },
    },
]
