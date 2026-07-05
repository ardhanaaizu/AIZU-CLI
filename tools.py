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
import sys
import subprocess
import urllib.request
import urllib.error
import json
import glob
import time
import hashlib
import threading
import pathlib
from concurrent.futures import ThreadPoolExecutor, as_completed

# Batas keamanan sederhana untuk perintah shell.
DANGEROUS = ["rm -rf /", "mkfs", ":(){", "dd if=", "> /dev/sd"]


# =============================================================================
# Tool Result Cache
# =============================================================================
class ToolCache:
    """Cache tool results untuk menghindari pemanggilan berulang.

    Features:
    - TTL-based expiration (default 5 menit)
    - Max size limit (default 100 entries)
    - LRU eviction
    - Key berdasarkan tool name + args hash
    """

    def __init__(self, ttl=300, max_size=100):
        """
        Args:
            ttl: Time-to-live dalam detik (default 300 = 5 menit)
            max_size: Maximum cache entries (default 100)
        """
        self.cache = {}
        self.ttl = ttl
        self.max_size = max_size
        self.access_order = []  # For LRU

    def _make_key(self, tool_name, args):
        """Buat cache key dari tool name dan args."""
        args_str = json.dumps(args, sort_keys=True)
        args_hash = hashlib.md5(args_str.encode()).hexdigest()[:8]
        return f"{tool_name}:{args_hash}"

    def get(self, tool_name, args):
        """Ambil cached result jika ada dan belum expired.

        Returns:
            Cached result atau None jika tidak ada/expired
        """
        key = self._make_key(tool_name, args)

        if key not in self.cache:
            return None

        result, timestamp = self.cache[key]

        # Check TTL
        if time.time() - timestamp > self.ttl:
            del self.cache[key]
            if key in self.access_order:
                self.access_order.remove(key)
            return None

        # Update access order (LRU)
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

        return result

    def put(self, tool_name, args, result):
        """Simpan result ke cache.

        Args:
            tool_name: Nama tool
            args: Arguments dict
            result: Tool result untuk di-cache
        """
        # Evict jika penuh
        while len(self.cache) >= self.max_size:
            if self.access_order:
                oldest_key = self.access_order.pop(0)
                del self.cache[oldest_key]
            else:
                break

        key = self._make_key(tool_name, args)
        self.cache[key] = (result, time.time())
        self.access_order.append(key)

    def invalidate(self, tool_name, args):
        """Hapus specific cache entry."""
        key = self._make_key(tool_name, args)
        if key in self.cache:
            del self.cache[key]
        if key in self.access_order:
            self.access_order.remove(key)

    def clear(self):
        """Hapus semua cache."""
        self.cache.clear()
        self.access_order.clear()

    def stats(self):
        """Dapatkan cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "keys": list(self.cache.keys())
        }


# Global cache instance
_tool_cache = ToolCache()


def get_tool_cache():
    """Dapatkan global tool cache instance."""
    return _tool_cache


# =============================================================================
# Circuit Breaker (Error Handling)
# =============================================================================
class CircuitBreaker:
    """Circuit breaker pattern untuk external calls.

    Mencegah cascade failure dengan:
    - Failure counting
    - Automatic circuit opening
    - Timed recovery attempts

    States:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Too many failures, calls rejected
    - HALF_OPEN: Testing recovery, limited calls allowed
    """

    def __init__(self, failure_threshold=5, reset_timeout=60, half_open_max=3):
        """
        Args:
            failure_threshold: Jumlah failure sebelum circuit open
            reset_timeout: Detik sebelum mencoba half-open
            half_open_max: Max calls dalam half-open state
        """
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max = half_open_max

        self._state = "closed"
        self._failure_count = 0
        self._last_failure_time = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()

    @property
    def state(self):
        """Dapatkan current state."""
        with self._lock:
            self._check_state_transition()
            return self._state

    def _check_state_transition(self):
        """Check dan execute state transitions."""
        if self._state == "open":
            # Check apakah sudah waktunya half-open
            if time.time() - self._last_failure_time >= self.reset_timeout:
                self._state = "half_open"
                self._half_open_calls = 0

    def call(self, func, *args, **kwargs):
        """Execute function dengan circuit breaker protection.

        Args:
            func: Function yang akan dijalankan
            *args, **kwargs: Arguments untuk function

        Returns:
            Result dari function

        Raises:
            Exception: Jika circuit open atau function gagal
        """
        with self._lock:
            self._check_state_transition()

            if self._state == "open":
                raise Exception(f"Circuit breaker is OPEN. Retry in {self._retry_in()}s")

            if self._state == "half_open":
                if self._half_open_calls >= self.half_open_max:
                    raise Exception("Circuit breaker HALF_OPEN: max calls reached")
                self._half_open_calls += 1

        try:
            result = func(*args, **kwargs)

            # Success - reset failure count
            with self._lock:
                if self._state == "half_open":
                    self._state = "closed"
                self._failure_count = 0

            return result

        except Exception as e:
            with self._lock:
                self._failure_count += 1
                self._last_failure_time = time.time()

                if self._failure_count >= self.failure_threshold:
                    self._state = "open"
                    print(f"\033[33m[CircuitBreaker] Circuit OPENED after {self._failure_count} failures\033[0m")

            raise

    def _retry_in(self):
        """Hitung detik sampai retry berikutnya."""
        elapsed = time.time() - self._last_failure_time
        remaining = max(0, self.reset_timeout - elapsed)
        return int(remaining)

    def reset(self):
        """Reset circuit breaker ke closed state."""
        with self._lock:
            self._state = "closed"
            self._failure_count = 0
            self._half_open_calls = 0


# Global circuit breakers untuk external services
_circuit_breakers = {
    'llm': CircuitBreaker(failure_threshold=3, reset_timeout=30),
    'web': CircuitBreaker(failure_threshold=5, reset_timeout=60),
    'mcp': CircuitBreaker(failure_threshold=3, reset_timeout=45),
}


def get_circuit_breaker(name):
    """Dapatkan circuit breaker by name.

    Args:
        name: Circuit breaker name (llm, web, mcp)

    Returns:
        CircuitBreaker instance
    """
    return _circuit_breakers.get(name)


# =============================================================================
# Parallel Tool Execution
# =============================================================================
def run_tools_parallel(tool_calls, max_workers=3):
    """Execute multiple tool calls secara parallel.

    Args:
        tool_calls: List of (tool_name, args) tuples
        max_workers: Maximum concurrent workers (default 3)

    Returns:
        dict: {index: result} mapping
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit semua tasks
        future_to_idx = {}
        for idx, (tool_name, args) in enumerate(tool_calls):
            if tool_name in REGISTRY:
                func = REGISTRY[tool_name]
                future = executor.submit(func, **args)
                future_to_idx[future] = idx

        # Collect results
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result(timeout=120)
                results[idx] = result
            except Exception as e:
                results[idx] = f"ERROR: {e}"

    return results


# =============================================================================
# Cross-Platform Helpers
# =============================================================================
class PlatformHelper:
    """Helper untuk cross-platform compatibility.

    Deteksi platform dan provide platform-specific utilities.
    """

    @staticmethod
    def is_windows():
        """Check apakah running di Windows."""
        return sys.platform == 'win32'

    @staticmethod
    def is_wsl():
        """Check apakah running di WSL (Windows Subsystem for Linux)."""
        try:
            with open('/proc/version', 'r') as f:
                return 'microsoft' in f.read().lower()
        except Exception:
            return False

    @staticmethod
    def is_termux():
        """Check apakah running di Termux (Android)."""
        return 'TERMUX_VERSION' in os.environ

    @staticmethod
    def get_shell():
        """Dapatkan default shell untuk platform."""
        if PlatformHelper.is_windows():
            return os.environ.get('COMSPEC', 'cmd.exe')
        else:
            return os.environ.get('SHELL', '/bin/sh')

    @staticmethod
    def normalize_path(path):
        """Normalize path untuk platform saat ini.

        Args:
            path: Path string

        Returns:
            str: Normalized path
        """
        return str(pathlib.Path(path))

    @staticmethod
    def get_home_dir():
        """Dapatkan home directory."""
        return str(pathlib.Path.home())

    @staticmethod
    def get_temp_dir():
        """Dapatkan temp directory."""
        import tempfile
        return tempfile.gettempdir()

    @staticmethod
    def run_command(command, shell=None):
        """Run command dengan platform-specific settings.

        Args:
            command: Command string atau list
            shell: Shell to use (default: platform default)

        Returns:
            tuple: (returncode, stdout, stderr)
        """
        if shell is None:
            shell = PlatformHelper.get_shell()

        import subprocess

        kwargs = {
            'shell': True,
            'capture_output': True,
            'text': True,
        }

        # Windows-specific
        if PlatformHelper.is_windows():
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs['startupinfo'] = startupinfo

        try:
            result = subprocess.run(command, **kwargs)
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)


# Import pathlib untuk cross-platform paths
import pathlib


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
    """Jalankan perintah shell di Termux.

    Perintah install/download di-stream real-time (progress terlihat langsung).
    Tidak perlu manggil tool berulang kali.
    """
    low = command.lower()
    for bad in DANGEROUS:
        if bad in low:
            return f"DITOLAK: perintah berbahaya terdeteksi ('{bad}')."

    # Deteksi perintah yang perlu streaming
    streaming_patterns = [
        "apt ", "pkg ", "yum ", "dnf ",
        "npm ", "yarn ", "pnpm ",
        "pip ", "pip3 ",
        "brew ", "cargo ",
        "git clone", "git pull", "git fetch",
        "curl", "wget",
        "tar ", "unzip",
        "make", "cmake",
        "docker", "podman",
    ]
    need_streaming = any(pattern in low for pattern in streaming_patterns)

    if need_streaming:
        # Stream output real-time
        try:
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            output_lines = []
            line_count = 0

            for line in iter(process.stdout.readline, ''):
                if line:
                    output_lines.append(line.rstrip())
                    line_count += 1
                    # Tampilkan progress (limit biar gak spam)
                    if line_count <= 20 or line_count % 5 == 0:
                        clean = line.rstrip()[:70]
                        sys.stdout.write(f"\r\033[K  │ {clean}")
                        sys.stdout.flush()

            process.wait()

            total = len(output_lines)
            if total > 20:
                sys.stdout.write(f"\r\033[K  │ ... ({total} lines)\n")
                sys.stdout.flush()

            final = "\n".join(output_lines[-15:])
            if len(final) > 3000:
                final = final[:3000] + "\n..."

            if process.returncode != 0:
                return f"[ERR] Error (kode {process.returncode}):\n{final}"
            return f"[OK] Selesai ({total} lines):\n{final}"

        except Exception as e:
            return f"ERROR: {e}"

    # Perintah biasa - langsung jalankan
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120,
        )
        out = (result.stdout or "") + (result.stderr or "")
        if len(out) > 10000:
            out = out[:10000] + "\n... (terpotong)"
        return out.strip() or f"(selesai, kode {result.returncode})"
    except subprocess.TimeoutExpired:
        return f"[WAIT] Timeout. Jalankan langsung di terminal."
    except Exception as e:
        return f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Web tools: search dan fetch
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 5, backend: str = "auto") -> str:
    """Cari di internet dengan multiple backend support.

    Backends:
    - auto: Pilih yang tersedia (DuckDuckGo default)
    - duckduckgo: DuckDuckGo Instant Answer API (tanpa API key)
    - brave: Brave Search API (perlu API key)
    - google: Google Custom Search API (perlu API key + CX)

    Args:
        query: Search query
        max_results: Maximum results (default 5)
        backend: Search backend (auto, duckduckgo, brave, google)

    Returns:
        str: Formatted search results
    """
    # Auto-detect backend
    if backend == "auto":
        # Check for API keys di environment
        brave_key = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY")
        google_key = os.environ.get("GOOGLE_API_KEY")
        google_cx = os.environ.get("GOOGLE_CX") or os.environ.get("GOOGLE_SEARCH_CX")

        if brave_key:
            backend = "brave"
        elif google_key and google_cx:
            backend = "google"
        else:
            backend = "duckduckgo"

    # Execute search berdasarkan backend
    try:
        if backend == "brave":
            return _search_brave(query, max_results)
        elif backend == "google":
            return _search_google(query, max_results)
        else:
            return _search_duckduckgo(query, max_results)
    except Exception as e:
        # Fallback ke DuckDuckGo jika backend lain gagal
        if backend != "duckduckgo":
            try:
                return _search_duckduckgo(query, max_results)
            except Exception as e2:
                return f"ERROR web search: {e2}"
        return f"ERROR web search: {e}"


def _search_duckduckgo(query: str, max_results: int = 5) -> str:
    """Search menggunakan DuckDuckGo Instant Answer API (tanpa API key)."""
    url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": "AIZU-CLI/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as ssl_err:
        # Fallback to DNS-over-HTTPS (DoH) via Cloudflare
        try:
            import ssl
            doh_url = "https://cloudflare-dns.com/dns-query?name=api.duckduckgo.com&type=A"
            doh_req = urllib.request.Request(doh_url, headers={"Accept": "application/dns-json"})
            with urllib.request.urlopen(doh_req, timeout=10) as doh_resp:
                doh_data = json.loads(doh_resp.read().decode("utf-8"))
                
            real_ips = []
            for answer in doh_data.get("Answer", []):
                if answer.get("type") == 1: # A record
                    real_ips.append(answer.get("data"))
            
            # CNAME resolution fallback if type 1 wasn't in main Answer list
            if not real_ips:
                doh_url2 = "https://cloudflare-dns.com/dns-query?name=duckduckgo.com&type=A"
                doh_req2 = urllib.request.Request(doh_url2, headers={"Accept": "application/dns-json"})
                with urllib.request.urlopen(doh_req2, timeout=10) as doh_resp2:
                    doh_data2 = json.loads(doh_resp2.read().decode("utf-8"))
                for answer in doh_data2.get("Answer", []):
                    if answer.get("type") == 1:
                        real_ips.append(answer.get("data"))
            
            if not real_ips:
                raise RuntimeError("Gagal mendapatkan IP asli via DoH")
                
            real_ip = real_ips[0]
            ctx = ssl._create_unverified_context()
            ip_url = f"https://{real_ip}/?q={urllib.parse.quote(query)}&format=json&no_html=1&skip_disambig=1"
            ip_req = urllib.request.Request(ip_url, headers={
                "User-Agent": "AIZU-CLI/1.0",
                "Host": "api.duckduckgo.com"
            })
            with urllib.request.urlopen(ip_req, timeout=15, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as doh_err:
            raise RuntimeError(f"Bypass sensor DNS gagal ({doh_err}). Original error: {ssl_err}")

    results = []

    # Abstract (jawaban langsung)
    if data.get("Abstract"):
        results.append(f"[INFO] **Ringkasan:** {data['Abstract']}")
        if data.get("AbstractURL"):
            results.append(f"   Sumber: {data['AbstractURL']}")

    # Answer box
    if data.get("Answer"):
        results.append(f"[ANSWER] **Jawaban:** {data['Answer']}")
        if data.get("AnswerType"):
            results.append(f"   Tipe: {data['AnswerType']}")

    # Infobox
    if data.get("Infobox"):
        infobox = data["Infobox"]
        if infobox.get("content"):
            for item in infobox["content"][:2]:
                if item.get("label") and item.get("value"):
                    results.append(f"[INFO] {item['label']}: {item['value']}")

    # Related topics
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and topic.get("Text"):
            text = topic["Text"][:200]
            topic_url = topic.get("FirstURL", "")
            results.append(f"• {text}")
            if topic_url:
                results.append(f"  {topic_url}")

    # AbstractText (jika ada)
    if not results and data.get("AbstractText"):
        results.append(f"[INFO] {data['AbstractText'][:300]}")

    if not results:
        return f"Tidak ditemukan hasil untuk: {query}"

    return "\n".join(results)


def _search_brave(query: str, max_results: int = 5) -> str:
    """Search menggunakan Brave Search API (perlu API key)."""
    api_key = os.environ.get("BRAVE_API_KEY") or os.environ.get("BRAVE_SEARCH_API_KEY")
    if not api_key:
        raise ValueError("BRAVE_API_KEY tidak ditemukan di environment")

    url = f"https://api.search.brave.com/res/v1/web/search?q={urllib.parse.quote(query)}&count={max_results}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key
    })

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    web_results = data.get("web", {}).get("results", [])

    if not web_results:
        return f"Tidak ditemukan hasil untuk: {query}"

    for item in web_results[:max_results]:
        title = item.get("title", "")
        description = item.get("description", "")
        result_url = item.get("url", "")

        results.append(f"[LINK] **{title}**")
        if description:
            results.append(f"   {description[:200]}")
        if result_url:
            results.append(f"   -> {result_url}")
        results.append("")

    return "\n".join(results)


def _search_google(query: str, max_results: int = 5) -> str:
    """Search menggunakan Google Custom Search API (perlu API key + CX)."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    cx = os.environ.get("GOOGLE_CX") or os.environ.get("GOOGLE_SEARCH_CX")

    if not api_key or not cx:
        raise ValueError("GOOGLE_API_KEY dan GOOGLE_CX harus di-set di environment")

    url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={urllib.parse.quote(query)}&num={max_results}"
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "AIZU-CLI/1.0")

    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    results = []
    items = data.get("items", [])

    if not items:
        return f"Tidak ditemukan hasil untuk: {query}"

    for item in items[:max_results]:
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")

        results.append(f"[LINK] **{title}**")
        if snippet:
            results.append(f"   {snippet[:200]}")
        if link:
            results.append(f"   -> {link}")
        results.append("")

    return "\n".join(results)


def web_fetch(url: str, max_length: int = 5000) -> str:
    """Ambil konten dari URL dan konversi ke teks sederhana."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "AIZU-CLI/1.0",
            "Accept": "text/html,application/xhtml+xml,text/plain"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        # Ambil title SEBELUM strip HTML tags
        title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        title = title_match.group(1).strip() if title_match else ""

        # Strip HTML tags sederhana
        content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()

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
            return f"[DIR] File ditemukan ({len(results)}):\n" + "\n".join(results)

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
                                        return f"[DIR] Ditemukan {count}+ hasil (terbatas 30):\n" + "\n".join(results)
                    except (IOError, UnicodeDecodeError):
                        pass

            if not results:
                return f"Tidak ditemukan '{content_search}' di {path}"
            return f"[DIR] Ditemukan {len(results)} hasil:\n" + "\n".join(results)
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
    import shlex
    safe_msg = shlex.quote(message)
    return run_shell(f'git commit -m {safe_msg}')


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


# ---------------------------------------------------------------------------
# Enhanced tools (Claude Code style)
# ---------------------------------------------------------------------------

def glob_files(pattern: str, path: str = ".", sort_by: str = "name") -> str:
    """Cari file berdasarkan glob pattern (recursive).

    Mirip dengan Glob tool di Claude Code.
    Contoh: '*.py', 'src/**/*.js', '**/*.txt'

    Args:
        pattern: Glob pattern
        path: Base directory untuk search
        sort_by: Sort order (name, modified, size)

    Returns:
        str: Formatted list of matching files
    """
    try:
        import fnmatch

        path = os.path.expanduser(path)

        # Normalize pattern
        if not pattern.startswith('**') and not os.path.isabs(pattern):
            pattern = os.path.join(path, pattern)

        # Use glob with recursive support
        if '**' in pattern:
            files = glob.glob(pattern, recursive=True)
        else:
            # Also search recursively for non-** patterns
            files = glob.glob(os.path.join(path, '**', pattern), recursive=True)
            if not files:
                files = glob.glob(pattern, recursive=True)

        if not files:
            return f"Tidak ditemukan file dengan pattern: {pattern}"

        # Filter hanya file (bukan directory)
        files = [f for f in files if os.path.isfile(f)]

        # Sort
        if sort_by == "modified":
            files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        elif sort_by == "size":
            files.sort(key=lambda x: os.path.getsize(x), reverse=True)
        else:
            files.sort()

        # Format output
        result_lines = []
        for f in files[:100]:  # Limit 100 results
            rel = os.path.relpath(f, path)
            size = os.path.getsize(f)
            mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f)))

            # Format size
            if size < 1024:
                size_str = f"{size}B"
            elif size < 1024 * 1024:
                size_str = f"{size/1024:.1f}KB"
            else:
                size_str = f"{size/(1024*1024):.1f}MB"

            result_lines.append(f"  {rel}  ({size_str}, {mtime})")

        count = len(files)
        header = f"[DIR] Ditemukan {count} file" + (f" (menampilkan 100)" if count > 100 else "")
        return header + ":\n" + "\n".join(result_lines)
    except Exception as e:
        return f"ERROR glob: {e}"


def grep_content(pattern: str, path: str = ".", include: str = "",
                 max_results: int = 50, context: int = 0,
                 ignore_case: bool = True, output_mode: str = "content",
                 head_limit: int = 0) -> str:
    """Cari pattern (regex) di dalam file dengan fitur ripgrep-like.

    Mirip dengan Grep tool di Claude Code.

    Args:
        pattern: Regex pattern yang dicari
        path: Direktori pencarian
        include: Filter file (mis. '*.py', '*.js')
        max_results: Jumlah maksimal hasil (default 50)
        context: Jumlah baris context sebelum/sesudah (default 0)
        ignore_case: Case insensitive search (default True)
        output_mode: Output format (content, files_with_matches, count)
        head_limit: Limit total output lines (0 = unlimited)

    Returns:
        str: Formatted search results
    """
    import fnmatch

    try:
        path = os.path.expanduser(path)
        results = []
        file_matches = {}  # For files_with_matches mode
        match_count = 0

        # Compile regex
        flags = re.IGNORECASE if ignore_case else 0
        try:
            compiled = re.compile(pattern, flags)
        except re.error as e:
            return f"ERROR: Invalid regex pattern: {e}"

        for root, dirs, files in os.walk(path):
            # Skip hidden dirs dan common non-source dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in [
                'node_modules', '__pycache__', '.git', 'venv', 'env', '.venv'
            ]]

            for fname in files:
                # Filter by include pattern
                if include:
                    if not fnmatch.fnmatch(fname, include):
                        continue

                fpath = os.path.join(root, fname)
                try:
                    # Skip binary files
                    with open(fpath, 'rb') as f:
                        chunk = f.read(8192)
                        if b'\x00' in chunk:
                            continue

                    # Read file lines untuk context support
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()

                    rel = os.path.relpath(fpath, path)
                    file_has_match = False

                    for i, line in enumerate(lines):
                        if compiled.search(line):
                            file_has_match = True
                            match_count += 1

                            if output_mode == "files_with_matches":
                                if rel not in file_matches:
                                    file_matches[rel] = 0
                                file_matches[rel] += 1
                                continue

                            if output_mode == "count":
                                if rel not in file_matches:
                                    file_matches[rel] = 0
                                file_matches[rel] += 1
                                continue

                            # content mode
                            if context > 0:
                                # Tambahkan context lines
                                start = max(0, i - context)
                                end = min(len(lines), i + context + 1)

                                # Separator jika bukan match pertama di file
                                if results and results[-1] != "--":
                                    results.append("--")

                                for ctx_idx in range(start, end):
                                    ctx_line = lines[ctx_idx].rstrip()
                                    if ctx_idx == i:
                                        # Match line
                                        results.append(f"  {rel}:{ctx_idx+1}: {ctx_line[:120]}")
                                    else:
                                        # Context line
                                        results.append(f"  {rel}:{ctx_idx+1}- {ctx_line[:120]}")
                            else:
                                # No context - langsung
                                results.append(f"  {rel}:{i+1}: {line.strip()[:120]}")

                            if len(results) >= max_results:
                                break

                    if len(results) >= max_results:
                        break

                except (IOError, UnicodeDecodeError):
                    pass

            if len(results) >= max_results:
                break

        # Format output berdasarkan mode
        if output_mode == "files_with_matches":
            if not file_matches:
                return f"Tidak ditemukan file yang mengandung: {pattern}"
            files_list = sorted(file_matches.keys())
            return f"[DIR] {len(files_list)} file mengandung '{pattern}':\n" + "\n".join(f"  {f}" for f in files_list)

        elif output_mode == "count":
            if not file_matches:
                return f"Tidak ditemukan match untuk: {pattern}"
            total = sum(file_matches.values())
            lines = [f"📊 Match count untuk '{pattern}':"]
            for f, count in sorted(file_matches.items()):
                lines.append(f"  {f}: {count}")
            lines.append(f"  Total: {total}")
            return "\n".join(lines)

        else:
            # content mode
            if not results:
                return f"Tidak ditemukan '{pattern}' di {path}"

            # Apply head_limit jika diatur
            if head_limit > 0:
                results = results[:head_limit]

            header = f"[SEARCH] Ditemukan {match_count} match" + (f" (menampilkan {len(results)} baris)" if len(results) < match_count else "")
            return header + ":\n" + "\n".join(results)

    except Exception as e:
        return f"ERROR grep: {e}"


def read_file_lines(path: str, offset: int = 0, limit: int = 50) -> str:
    """Baca file dengan offset dan limit (berdasarkan baris).

    Mirip dengan Read tool di Claude Code yang support offset/limit.
    - path: file yang dibaca
    - offset: baris mulai (0-based)
    - limit: jumlah baris yang dibaca
    """
    try:
        path = os.path.expanduser(path)
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        total = len(lines)
        if offset >= total:
            return f"ERROR: offset {offset} melebihi jumlah baris ({total})"

        end = min(offset + limit, total)
        selected = lines[offset:end]

        # Format with line numbers (1-based)
        result_lines = []
        for i, line in enumerate(selected, start=offset + 1):
            result_lines.append(f"{i:4d}\t{line.rstrip()}")

        header = f"📄 {path} (baris {offset+1}-{end} dari {total})"
        return header + "\n" + "\n".join(result_lines)
    except Exception as e:
        return f"ERROR membaca file: {e}"


def edit_file_improved(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Edit file dengan exact string replacement (lebih presisi).

    Mirip dengan Edit tool di Claude Code.
    - old_string: teks yang dicari (harus match persis termasuk indentasi)
    - new_string: teks pengganti
    - replace_all: jika True, ganti semua kemunculan; jika False, hanya yang pertama
    """
    try:
        path = os.path.expanduser(path)
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()

        if old_string not in content:
            return f"ERROR: string tidak ditemukan di {path}.\nPastikan string match persis termasuk indentasi dan newline."

        count = content.count(old_string)

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            if count > 1:
                return f"ERROR: ditemukan {count} kemunculan. Gunakan replace_all=True untuk ganti semua, atau buat string lebih spesifik."
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return f"OK: {replaced} kemunculan diganti di {path}"
    except Exception as e:
        return f"ERROR edit: {e}"


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
    "glob_files": glob_files,
    "grep_content": grep_content,
    "read_file_lines": read_file_lines,
    "edit_file_improved": edit_file_improved,
    # Utility functions
    "get_tool_cache": lambda: json.dumps(get_tool_cache().stats()),
    "clear_tool_cache": lambda: (get_tool_cache().clear(), "Cache cleared")[1],
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
            "description": "Jalankan perintah shell. Install/download di-stream real-time.",
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
            "description": "Cari informasi di internet. Support multiple backends: DuckDuckGo (default, no API key), Brave Search (perlu BRAVE_API_KEY), Google Custom Search (perlu GOOGLE_API_KEY + GOOGLE_CX).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Kata kunci pencarian"},
                    "max_results": {"type": "integer", "description": "Jumlah maksimal hasil (default 5)"},
                    "backend": {"type": "string", "description": "Search backend: auto, duckduckgo, brave, google (default auto)"},
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
    {
        "type": "function",
        "function": {
            "name": "glob_files",
            "description": "Cari file berdasarkan glob pattern (recursive). Contoh: '*.py', 'src/**/*.js'. Results sorted by modification time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern untuk mencari file"},
                    "path": {"type": "string", "description": "Direktori pencarian (default '.')"},
                    "sort_by": {"type": "string", "description": "Sort order: name, modified, size (default name)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_content",
            "description": "Cari pattern (regex) di dalam file dengan fitur ripgrep-like. Support context lines, case sensitivity, dan multiple output modes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern yang dicari"},
                    "path": {"type": "string", "description": "Direktori pencarian (default '.')"},
                    "include": {"type": "string", "description": "Filter file (mis. '*.py', '*.js')"},
                    "max_results": {"type": "integer", "description": "Jumlah maksimal hasil (default 50)"},
                    "context": {"type": "integer", "description": "Jumlah baris context sebelum/sesudah (default 0)"},
                    "ignore_case": {"type": "boolean", "description": "Case insensitive search (default true)"},
                    "output_mode": {"type": "string", "description": "Output format: content, files_with_matches, count (default content)"},
                    "head_limit": {"type": "integer", "description": "Limit total output lines (0 = unlimited)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_lines",
            "description": "Baca file dengan offset dan limit baris. Berguna untuk file besar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang dibaca"},
                    "offset": {"type": "integer", "description": "Baris mulai (0-based, default 0)"},
                    "limit": {"type": "integer", "description": "Jumlah baris (default 50)"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file_improved",
            "description": "Edit file dengan exact string replacement. Lebih presisi dari edit_file biasa.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path file yang diedit"},
                    "old_string": {"type": "string", "description": "String yang dicari (harus match persis)"},
                    "new_string": {"type": "string", "description": "String pengganti"},
                    "replace_all": {"type": "boolean", "description": "Ganti semua kemunculan (default false)"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
]
