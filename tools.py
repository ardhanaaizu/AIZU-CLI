"""
tools.py — Kumpulan tool yang bisa dipanggil oleh agent.

Setiap tool punya:
  - definisi skema (untuk dikirim ke LLM)
  - fungsi implementasi (dijalankan secara lokal di Termux)
"""

import os
import subprocess

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


# Peta nama tool -> fungsi
REGISTRY = {
    "read_file": read_file,
    "write_file": write_file,
    "list_dir": list_dir,
    "run_shell": run_shell,
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
]
