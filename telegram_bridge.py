#!/usr/bin/env python3
"""
telegram_bridge.py — Telegram Bot Bridge untuk AIZU-CLI.

Fitur:
- Kirim file PDF (surat lamaran) ke Telegram user
- Sistem linking kode: user akses bot → minta kode → masukkan di AIZU → linked
- Polling /getUpdates untuk menerima pesan
- Zero external dependencies (pakai urllib)

Usage:
    from telegram_bridge import get_telegram_bridge
    bridge = get_telegram_bridge()
    bridge.set_bot_token("123:ABC...")
    bridge.start_polling()
"""

import json
import os
import random
import string
import threading
import time
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
AIZU_DIR = os.path.join(os.path.expanduser("~"), ".aizu")
TELEGRAM_FILE = os.path.join(AIZU_DIR, "telegram.json")

API_BASE = "https://api.telegram.org/bot{token}/{method}"
CODE_LENGTH = 6
CODE_EXPIRY = 300  # 5 menit
POLL_INTERVAL = 2  # detik


# ---------------------------------------------------------------------------
# TelegramBridge
# ---------------------------------------------------------------------------
class TelegramBridge:
    """Telegram bot bridge untuk mengirim file ke user."""

    def __init__(self):
        self._data = self._load_data()
        self._polling = False
        self._poll_thread = None
        self._offset = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------
    def set_bot_token(self, token: str) -> dict:
        """Set Telegram bot token."""
        self._data["bot_token"] = token
        self._save_data()
        return {"success": True, "message": f"✅ Bot token berhasil disimpan"}

    def get_bot_token(self) -> str:
        """Ambil bot token."""
        return self._data.get("bot_token", "")

    def is_configured(self) -> bool:
        """Cek apakah bot sudah dikonfigurasi."""
        return bool(self._data.get("bot_token"))

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------
    def start_polling(self) -> dict:
        """Mulai polling Telegram updates di background thread."""
        if not self.is_configured():
            return {"success": False, "error": "Bot token belum di-set. Jalankan: /telegram start <token>"}

        if self._polling:
            return {"success": False, "error": "Polling sudah berjalan"}

        self._polling = True
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()
        return {"success": True, "message": "✅ Telegram bot polling dimulai"}

    def stop_polling(self) -> dict:
        """Stop polling."""
        if not self._polling:
            return {"success": False, "error": "Polling tidak berjalan"}

        self._polling = False
        if self._poll_thread:
            self._poll_thread.join(timeout=5)
            self._poll_thread = None
        return {"success": True, "message": "✅ Telegram bot polling dihentikan"}

    def is_polling(self) -> bool:
        """Cek apakah polling sedang berjalan."""
        return self._polling

    # ------------------------------------------------------------------
    # Linking
    # ------------------------------------------------------------------
    def generate_link_code(self) -> dict:
        """Generate kode linking unik 6 digit."""
        code = ''.join(random.choices(string.digits, k=CODE_LENGTH))

        with self._lock:
            self._data.setdefault("pending_codes", {})[code] = {
                "created_at": time.time()
            }
            self._save_data()

        return {
            "success": True,
            "code": code,
            "message": (
                f"✅ Kode linking: {code}\n\n"
                f"📋 Langkah:\n"
                f"   1. Buka Telegram, cari bot kamu\n"
                f"   2. Kirim /start ke bot\n"
                f"   3. Kirim /link ke bot\n"
                f"   4. Masukkan kode: {code}\n\n"
                f"⏰ Kode berlaku 5 menit"
            )
        }

    def verify_link_code(self, code: str, chat_id: int, username: str = "", first_name: str = "") -> dict:
        """Verifikasi kode linking dari Telegram."""
        with self._lock:
            pending = self._data.get("pending_codes", {})

            if code not in pending:
                return {"success": False, "error": "Kode tidak valid atau sudah expired"}

            # Cek expiry
            created = pending[code].get("created_at", 0)
            if time.time() - created > CODE_EXPIRY:
                del pending[code]
                self._save_data()
                return {"success": False, "error": "Kode sudah expired (5 menit). Minta kode baru di AIZU-CLI"}

            # Link berhasil
            del pending[code]

            linked = self._data.setdefault("linked_chats", {})
            linked[str(chat_id)] = {
                "username": username,
                "first_name": first_name,
                "linked_at": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._save_data()

        return {
            "success": True,
            "chat_id": chat_id,
            "message": f"✅ Telegram berhasil di-link! ({first_name or username or chat_id})"
        }

    def unlink(self, chat_id: int) -> dict:
        """Hapus linking Telegram."""
        with self._lock:
            linked = self._data.get("linked_chats", {})
            chat_str = str(chat_id)

            if chat_str not in linked:
                return {"success": False, "error": f"Chat ID {chat_id} tidak ditemukan di linked chats"}

            del linked[chat_str]
            self._save_data()

        return {"success": True, "message": f"✅ Chat ID {chat_id} berhasil di-unlink"}

    def get_linked_chats(self) -> dict:
        """Ambil daftar chat yang sudah linked."""
        return self._data.get("linked_chats", {})

    def has_linked_chats(self) -> bool:
        """Cek apakah ada chat yang linked."""
        return bool(self._data.get("linked_chats"))

    def get_primary_chat_id(self) -> int:
        """Ambil chat_id pertama (primary) untuk kirim file."""
        linked = self._data.get("linked_chats", {})
        if linked:
            return int(next(iter(linked)))
        return None

    # ------------------------------------------------------------------
    # Kirim Pesan & File
    # ------------------------------------------------------------------
    def send_message(self, chat_id: int, text: str) -> dict:
        """Kirim pesan teks ke Telegram."""
        result = self._api_call("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        })
        return result

    def send_document(self, chat_id: int, file_path: str, caption: str = "") -> dict:
        """Kirim file dokumen ke Telegram."""
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File tidak ditemukan: {file_path}"}

        token = self.get_bot_token()
        if not token:
            return {"success": False, "error": "Bot token belum di-set"}

        url = f"https://api.telegram.org/bot{token}/sendDocument"

        # Build multipart form data
        boundary = f"----AIZU{int(time.time())}"

        with open(file_path, "rb") as f:
            file_data = f.read()

        filename = os.path.basename(file_path)

        # Build body
        body = b""

        # chat_id field
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        body += f"{chat_id}\r\n".encode()

        # caption field
        if caption:
            body += f"--{boundary}\r\n".encode()
            body += b'Content-Disposition: form-data; name="caption"\r\n\r\n'
            body += f"{caption}\r\n".encode()

        # parse_mode field
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'
        body += b"HTML\r\n"

        # document field
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode()
        body += b"Content-Type: application/pdf\r\n\r\n"
        body += file_data
        body += b"\r\n"

        # Closing boundary
        body += f"--{boundary}--\r\n".encode()

        # Send request
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                if result.get("ok"):
                    return {"success": True, "message": f"✅ File berhasil dikirim ke Telegram"}
                else:
                    return {"success": False, "error": f"Telegram API error: {result.get('description', 'unknown')}"}
        except urllib.error.URLError as e:
            return {"success": False, "error": f"Gagal mengirim: {e}"}
        except Exception as e:
            return {"success": False, "error": f"Error: {e}"}

    # ------------------------------------------------------------------
    # Internal: Polling Loop
    # ------------------------------------------------------------------
    def _poll_loop(self):
        """Background polling loop untuk Telegram updates."""
        while self._polling:
            try:
                updates = self._get_updates()
                if updates and updates.get("ok"):
                    for update in updates.get("result", []):
                        self._handle_update(update)
                        self._offset = update["update_id"] + 1
            except Exception:
                pass  # Silent fail, lanjut polling

            time.sleep(POLL_INTERVAL)

    def _get_updates(self) -> dict:
        """Ambil updates dari Telegram."""
        return self._api_call("getUpdates", {
            "offset": self._offset,
            "timeout": 1
        })

    def _handle_update(self, update: dict):
        """Handle satu update dari Telegram."""
        message = update.get("message")
        if not message:
            return

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text", "").strip()
        username = chat.get("username", "")
        first_name = chat.get("first_name", "")

        if not chat_id or not text:
            return

        # Handle commands
        if text == "/start":
            self.send_message(chat_id,
                f"👋 Halo {first_name}!\n\n"
                f"Saya adalah bot AIZU-CLI. Untuk menghubungkan akun Telegram kamu "
                f"dengan AIZU-CLI, jalankan perintah:\n\n"
                f"📌 /link\n\n"
                f"Kemudian masukkan kode yang muncul di AIZU-CLI."
            )

        elif text == "/link":
            # Generate kode baru dan kirim ke user
            code = ''.join(random.choices(string.digits, k=CODE_LENGTH))
            with self._lock:
                self._data.setdefault("pending_codes", {})[code] = {
                    "created_at": time.time(),
                    "chat_id": chat_id,
                    "username": username,
                    "first_name": first_name
                }
                self._save_data()

            self.send_message(chat_id,
                f"🔑 Kode linking kamu:\n\n"
                f"╔═══════════════╗\n"
                f"║   {code}   ║\n"
                f"╚═══════════════╝\n\n"
                f"Masukkan kode ini di AIZU-CLI dengan menjalankan:\n"
                f"/telegram link {code}\n\n"
                f"⏰ Kode berlaku 5 menit"
            )

        elif text == "/status":
            linked = self._data.get("linked_chats", {})
            chat_str = str(chat_id)
            if chat_str in linked:
                info = linked[chat_str]
                self.send_message(chat_id,
                    f"✅ Status: Linked\n"
                    f"👤 {info.get('first_name', '')} (@{info.get('username', '')})\n"
                    f"📅 Linked sejak: {info.get('linked_at', '-')}"
                )
            else:
                self.send_message(chat_id,
                    f"❌ Status: Belum linked\n\n"
                    f"Kirim /link untuk mendapatkan kode linking"
                )

        elif text == "/unlink":
            with self._lock:
                linked = self._data.get("linked_chats", {})
                chat_str = str(chat_id)
                if chat_str in linked:
                    del linked[chat_str]
                    self._save_data()
                    self.send_message(chat_id, "✅ Akun Telegram kamu sudah di-unlink dari AIZU-CLI")
                else:
                    self.send_message(chat_id, "❌ Akun kamu belum ter-link")

        elif text == "/help":
            self.send_message(chat_id,
                f"📋 Perintah yang tersedia:\n\n"
                f"/start - Mulai bot\n"
                f"/link - Dapatkan kode linking\n"
                f"/status - Cek status linking\n"
                f"/unlink - Putuskan linking\n"
                f"/help - Tampilkan bantuan"
            )

    # ------------------------------------------------------------------
    # Internal: Telegram API
    # ------------------------------------------------------------------
    def _api_call(self, method: str, params: dict = None) -> dict:
        """Panggil Telegram Bot API."""
        token = self.get_bot_token()
        if not token:
            return {"success": False, "error": "Bot token belum di-set"}

        url = API_BASE.format(token=token, method=method)

        if params:
            data = json.dumps(params).encode("utf-8")
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
        else:
            req = urllib.request.Request(url)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            return {"ok": False, "error": f"HTTP {e.code}: {error_body}"}
        except urllib.error.URLError as e:
            return {"ok": False, "error": f"Connection error: {e}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ------------------------------------------------------------------
    # Internal: Data Persistence
    # ------------------------------------------------------------------
    def _load_data(self) -> dict:
        """Load data dari file."""
        os.makedirs(os.path.dirname(TELEGRAM_FILE), exist_ok=True)
        if os.path.exists(TELEGRAM_FILE):
            try:
                with open(TELEGRAM_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return {"bot_token": "", "linked_chats": {}, "pending_codes": {}}

    def _save_data(self):
        """Simpan data ke file."""
        os.makedirs(os.path.dirname(TELEGRAM_FILE), exist_ok=True)
        with open(TELEGRAM_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def cleanup_expired_codes(self):
        """Hapus kode yang sudah expired."""
        now = time.time()
        with self._lock:
            pending = self._data.get("pending_codes", {})
            expired = [code for code, info in pending.items()
                       if now - info.get("created_at", 0) > CODE_EXPIRY]
            for code in expired:
                del pending[code]
            if expired:
                self._save_data()
        return len(expired)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------
_bridge_instance = None


def get_telegram_bridge() -> TelegramBridge:
    """Dapatkan singleton TelegramBridge."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = TelegramBridge()
    return _bridge_instance


def reset_telegram_bridge():
    """Reset singleton (untuk testing)."""
    global _bridge_instance
    if _bridge_instance:
        _bridge_instance.stop_polling()
    _bridge_instance = None
