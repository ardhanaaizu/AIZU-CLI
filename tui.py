"""
AIZU-CLI Responsive TUI (Claude Code Style)
============================================

Responsive TUI dengan 3 region tetap:
- TOP: Workspace & Progress (fixed)
- MIDDLE: Chat messages (scrollable)
- BOTTOM: Status bar & Input (fixed)
"""

import os
import sys
import time
import threading

# Platform detection
_IS_WINDOWS = sys.platform == "win32"

# Slash commands untuk autocomplete
COMMANDS = [
    ("/help", "tampilkan bantuan"),
    ("/config", "lihat pengaturan"),
    ("/backend", "ganti penyedia AI"),
    ("/provider", "setup provider custom"),
    ("/providers", "pilih provider tersimpan"),
    ("/key", "atur API key"),
    ("/model", "atur model"),
    ("/models", "cari model dari API"),
    ("/mode", "ganti mode kerja"),
    ("/url", "atur base URL"),
    ("/save", "simpan pengaturan"),
    ("/tools", "daftar tool"),
    ("/sessions", "lihat session"),
    ("/resume", "resume session"),
    ("/save-session", "simpan session"),
    ("/delete-session", "hapus session"),
    ("/permissions", "atur permission"),
    ("/plugins", "lihat plugin"),
    ("/agent", "jalankan sub-agent"),
    ("/agents", "lihat background agents"),
    ("/plan", "toggle plan mode"),
    ("/tasks", "kelola task list"),
    ("/memory", "kelola memory"),
    ("/skill", "invoke skill"),
    ("/schedule", "kelola scheduled tasks"),
    ("/data-user", "kelola data profil user"),
    ("/reset", "hapus riwayat"),
    ("/keluar", "keluar"),
]
MAX_SUGGEST = 6


# =============================================================================
# ANSI Colors & Escape Codes
# =============================================================================
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BG_BLUE = "\033[44m"
    BG_GRAY = "\033[100m"
    WHITE = "\033[97m"
    VIOLET = "\033[38;5;141m"
    BG_DARK_GRAY = "\033[48;5;236m"
    BG_LIGHT_GRAY = "\033[48;5;240m"


class ANSI:
    """ANSI escape code helpers"""
    # Cursor movement
    @staticmethod
    def cursor_to(row, col=1):
        """Move cursor to specific position"""
        return f"\033[{row};{col}H"

    @staticmethod
    def cursor_up(n=1):
        return f"\033[{n}A"

    @staticmethod
    def cursor_down(n=1):
        return f"\033[{n}B"

    @staticmethod
    def cursor_forward(n=1):
        return f"\033[{n}C"

    @staticmethod
    def cursor_backward(n=1):
        return f"\033[{n}D"

    # Screen control
    @staticmethod
    def clear_screen():
        return "\033[2J"

    @staticmethod
    def clear_line():
        return "\033[2K"

    @staticmethod
    def clear_to_end():
        return "\033[J"

    # Save/Restore cursor
    @staticmethod
    def save_cursor():
        return "\033[s"

    @staticmethod
    def restore_cursor():
        return "\033[u"

    # Scroll
    @staticmethod
    def scroll_up(n=1):
        return f"\033[{n}S"

    @staticmethod
    def scroll_down(n=1):
        return f"\033[{n}T"


# =============================================================================
# TUI Class (Simple)
# =============================================================================
class AizuTUI:
    """Simple TUI for AIZU-CLI"""

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model
        self.plan_mode = False

        # Thinking state
        self.is_thinking = False
        self.thinking_start = 0
        self.thinking_text = "Thinking"
        self.anim_thread = None
        self.anim_running = False
        self.frame_idx = 0
        self.frames = ["*", "*", "*", "*", "*", "*", "*", "*", "*", "*"]

    # -------------------------------------------------------------------------
    # Setup & Cleanup
    # -------------------------------------------------------------------------
    def setup(self):
        """Initial setup - print header"""
        path = self.workspace_path
        if len(path) > 50:
            path = "..." + path[-47:]

        plan_indicator = " [PLAN] PLAN MODE" if self.plan_mode else ""

        print(f"\033[2J\033[H", end="")  # Clear screen
        print(f"{Colors.BG_BLUE}{Colors.BOLD} [DIR] {path}{plan_indicator}{' ' * 20}{self.backend} | {self.model} {Colors.RESET}")
        print(f"{Colors.DIM}{'-' * 60}{Colors.RESET}")
        print()

    def cleanup(self):
        """Cleanup on exit"""
        self._stop_animation()
        print()

    # -------------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------------
    def update_header(self, backend=None, model=None):
        if backend:
            self.backend = backend
        if model:
            self.model = model

    def show_plan_mode(self, enabled):
        self.plan_mode = enabled

    # -------------------------------------------------------------------------
    # Thinking Indicator
    # -------------------------------------------------------------------------
    def start_thinking(self, text="Thinking", note=""):
        self._stop_animation()
        self.is_thinking = True
        self.thinking_text = text
        self.thinking_start = time.time()
        self.frame_idx = 0
        self.anim_running = True
        self.anim_thread = threading.Thread(target=self._animate, daemon=True)
        self.anim_thread.start()

    def _animate(self):
        while self.anim_running:
            elapsed = int(time.time() - self.thinking_start)
            icon = self.frames[self.frame_idx % len(self.frames)]
            sys.stdout.write(f"\r{Colors.YELLOW}{icon} {self.thinking_text} for {elapsed}s...{Colors.RESET}  ")
            sys.stdout.flush()
            self.frame_idx += 1
            time.sleep(0.08)

    def _stop_animation(self):
        self.anim_running = False
        if self.anim_thread:
            self.anim_thread.join(timeout=0.3)
            self.anim_thread = None

    def stop_thinking(self):
        self._stop_animation()
        self.is_thinking = False
        sys.stdout.write(f"\r{' ' * 50}\r")  # Clear thinking line
        sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Messages (Simple Print)
    # -------------------------------------------------------------------------
    def add_message(self, text, role="system", icon=""):
        """Add a message - simple print"""
        if role == "user":
            color = Colors.GREEN
            if not icon:
                icon = "?"
        elif role == "assistant":
            color = Colors.CYAN
            if not icon:
                icon = "[AI]"
        elif role == "tool":
            color = Colors.MAGENTA
            if not icon:
                icon = "[WRENCH]"
        elif role == "error":
            color = Colors.RED
            if not icon:
                icon = "[ERR]"
        elif role == "success":
            color = Colors.GREEN
            if not icon:
                icon = "[OK]"
        elif role == "info":
            color = Colors.CYAN
            if not icon:
                icon = "[INFO]"
        elif role == "warning":
            color = Colors.YELLOW
            if not icon:
                icon = "?*"
        else:
            color = Colors.DIM
            if not icon:
                icon = "?"

        print(f" {icon} {color}{text}{Colors.RESET}")

    def add_user_message(self, text):
        """Print user message"""
        self.stop_thinking()
        print(f" ? {Colors.GREEN}{text}{Colors.RESET}")
        print()

    def add_assistant_message(self, text):
        """Print assistant message"""
        self.stop_thinking()
        # Print each line separately for better readability
        for line in text.split('\n'):
            if line.strip():
                print(f" [AI] {Colors.CYAN}{line}{Colors.RESET}")
        print()

    def add_tool_execution(self, tool_name, args=None):
        """Print tool execution"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"
        print(f" [WRENCH] {Colors.MAGENTA}Running: {tool_name}{args_str}{Colors.RESET}")

    def add_error(self, text):
        print(f" [ERR] {Colors.RED}{text}{Colors.RESET}")

    def add_success(self, text):
        print(f" [OK] {Colors.GREEN}{text}{Colors.RESET}")

    def add_info(self, text):
        print(f" [INFO]  {Colors.CYAN}{text}{Colors.RESET}")

    def add_warning(self, text):
        print(f" ?*  {Colors.YELLOW}{text}{Colors.RESET}")

    def add_thinking(self, text):
        print(f" ? {Colors.YELLOW}{text}{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    def get_input(self) -> str:
        """Get user input"""
        try:
            return input(f"{Colors.GREEN}{Colors.BOLD}kamu> {Colors.RESET}")
        except (EOFError, KeyboardInterrupt):
            raise


# =============================================================================
# Responsive TUI (New Design)
# =============================================================================
class ResponsiveTUI:
    """Responsive TUI dengan 3 region tetap untuk AIZU-CLI

    Layout:
    +---------------------------------------------+
    | TOP: Workspace & Progress (5 baris)         |
    +---------------------------------------------+
    | MIDDLE: Chat Messages (flexible)            |
    +---------------------------------------------+
    | BOTTOM: Status Bar + Input (3 baris)        |
    +---------------------------------------------+
    """

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model
        self.mode = "chat"

        # Terminal dimensions
        self.width = 80
        self.height = 24
        self._update_dimensions()

        # Region heights (fixed)
        self.TOP_HEIGHT = 5      # Workspace + Progress
        self.BOTTOM_HEIGHT = 3   # Status bar + Input
        # MIDDLE_HEIGHT = terminal_height - TOP - BOTTOM

        # Data
        self.progress_items = []  # List of {text, status}
        self.messages = []        # List of {role, text, icon}
        self.status_info = {
            "tokens": 0,
            "cost": "",
            "mode": "chat",
            "backend": "",
            "model": ""
        }

        # Thinking state
        self.is_thinking = False
        self.thinking_start = 0
        self.thinking_text = "Thinking"
        self.anim_thread = None
        self.anim_running = False
        self.frame_idx = 0
        self.frames = ["*", "*", "*", "*", "*", "*", "*", "*", "*", "*"]

        # Input state
        self.input_buffer = ""
        self.input_cursor = 0

        # Resize handler
        self._resize_callback_set = False
        self._setup_resize_handler()

    def _update_dimensions(self):
        """Update terminal dimensions"""
        try:
            size = os.get_terminal_size()
            self.width = size.columns
            self.height = size.lines
        except (OSError, ValueError):
            self.width = 80
            self.height = 24

    def _setup_resize_handler(self):
        """Setup terminal resize handler.

        Unix: SIGWINCH signal handler
        Windows: Periodic size check (no signal support)
        """
        if self._resize_callback_set:
            return

        try:
            import signal
            def handle_resize(signum, frame):
                old_width, old_height = self.width, self.height
                self._update_dimensions()
                if self.width != old_width or self.height != old_height:
                    self._on_resize()

            signal.signal(signal.SIGWINCH, handle_resize)
            self._resize_callback_set = True
        except (ImportError, AttributeError, OSError):
            # Windows atau environment tanpa SIGWINCH
            # Gunakan periodic check di _render_bottom
            self._resize_callback_set = False

    def _on_resize(self):
        """Handle terminal resize - re-render semua region"""
        # Clear dan re-render
        sys.stdout.write(ANSI.clear_screen())
        self._render_top()
        self._render_middle()
        self._render_bottom()
        self._move_to_input()
        sys.stdout.flush()

    def _middle_height(self):
        """Calculate middle region height"""
        return max(5, self.height - self.TOP_HEIGHT - self.BOTTOM_HEIGHT)

    # -------------------------------------------------------------------------
    # Setup & Cleanup
    # -------------------------------------------------------------------------
    def setup(self):
        """Initialize responsive layout"""
        self._update_dimensions()

        # Hide cursor dan clear screen
        sys.stdout.write("\033[?25l")  # Hide cursor
        sys.stdout.write(ANSI.clear_screen())
        sys.stdout.flush()

        # Render semua region
        self._render_top()
        self._render_middle()
        self._render_bottom()

        # Posisikan cursor di input
        self._move_to_input()
        sys.stdout.write("\033[?25h")  # Show cursor
        sys.stdout.flush()

    def cleanup(self):
        """Cleanup on exit"""
        self._stop_animation()
        sys.stdout.write("\033[?25h")  # Show cursor
        sys.stdout.write(ANSI.clear_screen())
        sys.stdout.write(ANSI.cursor_to(1, 1))
        sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Render Regions
    # -------------------------------------------------------------------------
    def _render_top(self):
        """Render TOP region: Workspace & Progress"""
        # Posisikan cursor di baris 1
        sys.stdout.write(ANSI.cursor_to(1, 1))

        # Header dengan background biru
        workspace = self.workspace_path
        if len(workspace) > self.width - 15:
            workspace = "..." + workspace[-(self.width - 18):]

        header = f" [DIR] {workspace}"
        header = header.ljust(self.width)
        sys.stdout.write(f"{Colors.BG_BLUE}{Colors.BOLD}{header}{Colors.RESET}")

        # Progress items (maksimal 3 baris)
        for i in range(min(3, len(self.progress_items))):
            item = self.progress_items[i]
            sys.stdout.write(ANSI.cursor_to(2 + i, 1))
            sys.stdout.write(ANSI.clear_line())

            if item["status"] == "done":
                icon = f"{Colors.GREEN}[OK]{Colors.RESET}"
            elif item["status"] == "running":
                icon = f"{Colors.YELLOW}[WAIT]{Colors.RESET}"
            elif item["status"] == "error":
                icon = f"{Colors.RED}[ERR]{Colors.RESET}"
            else:
                icon = f"{Colors.DIM}?{Colors.RESET}"

            text = item["text"][:self.width - 5]
            sys.stdout.write(f" {icon} {text}")

        # Jika kurang dari 3 progress items, kosongkan sisa baris
        for i in range(len(self.progress_items), 3):
            sys.stdout.write(ANSI.cursor_to(2 + i, 1))
            sys.stdout.write(ANSI.clear_line())

        # Separator
        sys.stdout.write(ANSI.cursor_to(self.TOP_HEIGHT, 1))
        sys.stdout.write(f"{Colors.DIM}{'-' * self.width}{Colors.RESET}")
        sys.stdout.flush()

    def _render_middle(self):
        """Render MIDDLE region: Chat Messages"""
        middle_start = self.TOP_HEIGHT + 1
        middle_height = self._middle_height()

        # Hitung berapa pesan yang bisa ditampilkan
        # Setiap pesan bisa 1+ baris tergantung panjang teks
        visible_messages = []
        lines_used = 0

        # Render dari pesan terbaru ke terlama
        for msg in reversed(self.messages):
            # Hitung baris yang dibutuhkan pesan ini
            text_lines = self._wrap_text(msg["text"], self.width - 4)
            msg_lines = len(text_lines)

            if lines_used + msg_lines > middle_height - 1:
                break

            visible_messages.insert(0, (msg, text_lines))
            lines_used += msg_lines

        # Clear middle region
        for i in range(middle_height):
            sys.stdout.write(ANSI.cursor_to(middle_start + i, 1))
            sys.stdout.write(ANSI.clear_line())

        # Render pesan
        current_row = middle_start
        for msg, text_lines in visible_messages:
            for line_idx, line in enumerate(text_lines):
                if current_row >= middle_start + middle_height:
                    break

                sys.stdout.write(ANSI.cursor_to(current_row, 1))

                # Icon hanya di baris pertama pesan
                if line_idx == 0:
                    icon = msg.get("icon", "?")
                    role = msg.get("role", "")
                    if role == "user":
                        color = Colors.GREEN
                    elif role == "assistant":
                        color = Colors.CYAN
                    elif role == "tool":
                        color = Colors.MAGENTA
                    elif role == "error":
                        color = Colors.RED
                    elif role == "info":
                        color = Colors.CYAN
                    else:
                        color = Colors.DIM

                    sys.stdout.write(f" {icon} {color}{line}{Colors.RESET}")
                else:
                    # Baris selanjutnya di-indent
                    sys.stdout.write(f"   {Colors.DIM}{line}{Colors.RESET}")

                current_row += 1

        # Separator
        sys.stdout.write(ANSI.cursor_to(self.TOP_HEIGHT + middle_height + 1, 1))
        sys.stdout.write(f"{Colors.DIM}{'-' * self.width}{Colors.RESET}")
        sys.stdout.flush()

    def _render_bottom(self):
        """Render BOTTOM region: Status Bar & Input"""
        bottom_start = self.height - self.BOTTOM_HEIGHT + 1

        # Status bar
        sys.stdout.write(ANSI.cursor_to(bottom_start, 1))
        sys.stdout.write(ANSI.clear_line())

        status_parts = []
        if self.status_info.get("backend"):
            status_parts.append(f"{self.status_info['backend']}")
        if self.status_info.get("model"):
            status_parts.append(f"{self.status_info['model']}")
        if self.status_info.get("tokens"):
            status_parts.append(f"{self.status_info['tokens']:,} tokens")
        if self.status_info.get("cost"):
            status_parts.append(self.status_info["cost"])
        if self.status_info.get("mode"):
            status_parts.append(f"mode: {self.status_info['mode']}")

        status_line = " | ".join(status_parts)
        if len(status_line) > self.width - 2:
            status_line = status_line[:self.width - 5] + "..."

        sys.stdout.write(f"{Colors.DIM} {status_line}{Colors.RESET}")

        # Input line
        sys.stdout.write(ANSI.cursor_to(bottom_start + 1, 1))
        sys.stdout.write(ANSI.clear_line())

        # Thinking indicator atau input prompt
        if self.is_thinking:
            elapsed = int(time.time() - self.thinking_start)
            icon = self.frames[self.frame_idx % len(self.frames)]
            sys.stdout.write(f" {Colors.YELLOW}{icon} {self.thinking_text} for {elapsed}s...{Colors.RESET}")
        else:
            prompt = f"{Colors.GREEN}{Colors.BOLD}kamu> {Colors.RESET}"
            sys.stdout.write(prompt)

        sys.stdout.flush()

    def _move_to_input(self):
        """Move cursor to input position"""
        bottom_start = self.height - self.BOTTOM_HEIGHT + 1
        if self.is_thinking:
            sys.stdout.write(ANSI.cursor_to(bottom_start + 1, 1))
        else:
            # Posisikan setelah prompt "kamu> "
            sys.stdout.write(ANSI.cursor_to(bottom_start + 1, 8))
        sys.stdout.flush()

    def _wrap_text(self, text, width):
        """Wrap text to fit within width.

        Mendukung ANSI escape codes - menghitung visible width, bukan termasuk escape codes.

        Args:
            text: Text to wrap
            width: Maximum visible width per line

        Returns:
            list: List of wrapped lines
        """
        import re

        if not text:
            return [""]

        def visible_length(s):
            """Hitung panjang visible dari string (tanpa ANSI codes)"""
            # Remove ANSI escape codes
            ansi_escape = re.compile(r'\033\[[0-9;]*m')
            return len(ansi_escape.sub('', s))

        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append("")
                continue

            words = paragraph.split()
            current_line = ""
            current_visible_len = 0

            for word in words:
                word_visible_len = visible_length(word)

                # Hitung panjang jika ditambahkan
                if current_visible_len + word_visible_len + (1 if current_line else 0) <= width:
                    if current_line:
                        current_line += " " + word
                        current_visible_len += word_visible_len + 1
                    else:
                        current_line = word
                        current_visible_len = word_visible_len
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                    current_visible_len = word_visible_len

            if current_line:
                lines.append(current_line)

        return lines if lines else [""]

    # -------------------------------------------------------------------------
    # Full Render
    # -------------------------------------------------------------------------
    def render(self):
        """Full render ulang semua region"""
        self._update_dimensions()

        sys.stdout.write(ANSI.save_cursor())
        sys.stdout.write("\033[?25l")

        self._render_top()
        self._render_middle()
        self._render_bottom()

        sys.stdout.write(ANSI.restore_cursor())
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()

    # -------------------------------------------------------------------------
    # TOP: Progress Region
    # -------------------------------------------------------------------------
    def add_progress(self, text, status="pending"):
        """Tambah item progress"""
        self.progress_items.append({"text": text, "status": status})
        self._render_top()
        self._move_to_input()

    def update_progress(self, index, status, text=None):
        """Update status progress item by index"""
        if 0 <= index < len(self.progress_items):
            self.progress_items[index]["status"] = status
            if text is not None:
                self.progress_items[index]["text"] = text
            self._render_top()
            self._move_to_input()

    def clear_progress(self):
        """Hapus semua progress"""
        self.progress_items.clear()
        self._render_top()
        self._move_to_input()

    def update_tokens(self, count):
        """Update token count di status bar"""
        self.status_info["tokens"] = count
        self._render_bottom()

    # -------------------------------------------------------------------------
    # MIDDLE: Chat Region
    # -------------------------------------------------------------------------
    def add_message(self, text, role="system", icon=""):
        """Tambah pesan ke chat area"""
        if not icon:
            if role == "user":
                icon = "?"
            elif role == "assistant":
                icon = "[AI]"
            elif role == "tool":
                icon = "[WRENCH]"
            elif role == "error":
                icon = "[ERR]"
            elif role == "success":
                icon = "[OK]"
            elif role == "info":
                icon = "[INFO]"
            elif role == "warning":
                icon = "?*"
            else:
                icon = "?"

        self.messages.append({"text": text, "role": role, "icon": icon})
        self._render_middle()
        self._move_to_input()

    def add_user_message(self, text):
        """Print user message"""
        self.stop_thinking()
        self.add_message(text, "user")

    def add_assistant_message(self, text):
        """Print assistant message"""
        self.stop_thinking()
        self.add_message(text, "assistant")

    def add_tool_execution(self, tool_name, args=None):
        """Print tool execution"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"
        self.add_message(f"Running: {tool_name}{args_str}", "tool")

    def add_error(self, text):
        self.add_message(text, "error")

    def add_success(self, text):
        self.add_message(text, "success")

    def add_info(self, text):
        self.add_message(text, "info")

    def add_warning(self, text):
        self.add_message(text, "warning")

    def add_thinking(self, text):
        self.add_message(text, "thinking", "?")

    # -------------------------------------------------------------------------
    # BOTTOM: Status Region
    # -------------------------------------------------------------------------
    def update_status(self, tokens=None, cost=None, mode=None, backend=None, model=None):
        """Update status bar"""
        if tokens is not None:
            self.status_info["tokens"] = tokens
        if cost is not None:
            self.status_info["cost"] = cost
        if mode is not None:
            self.status_info["mode"] = mode
        if backend is not None:
            self.status_info["backend"] = backend
        if model is not None:
            self.status_info["model"] = model

        self._render_bottom()
        self._move_to_input()

    def update_header(self, backend=None, model=None):
        """Update header info"""
        if backend:
            self.backend = backend
            self.status_info["backend"] = backend
        if model:
            self.model = model
            self.status_info["model"] = model
        self._render_bottom()
        self._move_to_input()

    # -------------------------------------------------------------------------
    # Thinking Animation
    # -------------------------------------------------------------------------
    def start_thinking(self, text="Thinking", note=""):
        """Start thinking animation"""
        self._stop_animation()
        self.is_thinking = True
        self.thinking_text = text
        self.thinking_start = time.time()
        self.frame_idx = 0
        self.anim_running = True
        self.anim_thread = threading.Thread(target=self._animate, daemon=True)
        self.anim_thread.start()

    def _animate(self):
        """Animation loop"""
        while self.anim_running:
            self.frame_idx += 1
            self._render_bottom()
            self._move_to_input()
            time.sleep(0.08)

    def _stop_animation(self):
        """Stop animation"""
        self.anim_running = False
        if self.anim_thread:
            self.anim_thread.join(timeout=0.3)
            self.anim_thread = None

    def stop_thinking(self):
        """Stop thinking indicator"""
        self._stop_animation()
        self.is_thinking = False
        self._render_bottom()
        self._move_to_input()

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    def get_input(self) -> str:
        """Get user input"""
        try:
            # Posisikan cursor di input
            self._move_to_input()

            # Baca input
            user_input = input()

            # Tambahkan ke messages
            if user_input.strip():
                self.add_user_message(user_input.strip())

            return user_input
        except (EOFError, KeyboardInterrupt):
            raise

    # -------------------------------------------------------------------------
    # Plan Mode
    # -------------------------------------------------------------------------
    def show_plan_mode(self, enabled):
        """Toggle plan mode indicator"""
        self.plan_mode = enabled
        self._render_top()
        self._move_to_input()


# =============================================================================
# Streaming TUI
# =============================================================================
class StreamingTUI:
    """Streaming wrapper untuk ClaudeStyleTUI.

    Delegates streaming display ke ClaudeStyleTUI.start_streaming() /
    stream_token() / stop_streaming() untuk incremental display.
    """

    def __init__(self, tui):
        """
        Args:
            tui: ClaudeStyleTUI instance
        """
        self.tui = tui
        self.buffer = ""

        # Jika tui punya start_streaming, pakai itu
        self._use_native = hasattr(tui, 'start_streaming')

        if self._use_native:
            tui.start_streaming()

        # Get terminal width untuk word wrap fallback
        try:
            size = os.get_terminal_size()
            self.line_width = size.columns - 10
        except (OSError, ValueError):
            self.line_width = 70

    def on_token(self, token: str):
        """Process satu token dari streaming response."""
        self.buffer += token

        if self._use_native:
            self.tui.stream_token(token)
        else:
            # Fallback: direct write
            sys.stdout.write(token)
            sys.stdout.flush()

    def on_complete(self):
        """Dipanggil saat streaming selesai."""
        if self._use_native:
            self.tui.stop_streaming()
        else:
            # Fallback: add as message
            if self.buffer.strip() and hasattr(self.tui, 'add_assistant_message'):
                self.tui.add_assistant_message(self.buffer)

        self.buffer = ""

    def get_content(self):
        """Dapatkan full content yang sudah di-stream."""
        return self.buffer


class StreamingProgressDisplay:
    """Progress display untuk streaming yang menunjukkan status real-time.

    Menampilkan:
    - Token count real-time
    - Streaming speed (tokens/detik)
    - Estimated time remaining
    """

    def __init__(self):
        self.start_time = 0
        self.token_count = 0
        self.last_update = 0
        self.update_interval = 0.5  # Update setiap 0.5 detik

    def start(self):
        """Mulai tracking progress"""
        self.start_time = time.time()
        self.token_count = 0
        self.last_update = self.start_time

    def on_token(self, token: str):
        """Track token untuk statistics

        Args:
            token: Token yang diterima
        """
        self.token_count += len(token)
        now = time.time()

        # Update display secara periodik (bukan setiap token)
        if now - self.last_update >= self.update_interval:
            self._update_display()
            self.last_update = now

    def _update_display(self):
        """Update progress display"""
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return

        # Hitung tokens per second
        tps = self.token_count / elapsed

        # Format display
        if tps >= 1000:
            speed_str = f"{tps/1000:.1f}k t/s"
        else:
            speed_str = f"{tps:.0f} t/s"

        # Tulis ke status line (akan di-overwrite)
        status = f"\r\033[K  [FAST] {self.token_count} tokens | {speed_str}"
        sys.stdout.write(status)
        sys.stdout.flush()

    def finish(self):
        """Selesai streaming, tampilkan summary"""
        elapsed = time.time() - self.start_time
        if elapsed <= 0:
            return

        tps = self.token_count / elapsed

        # Clear status line
        sys.stdout.write(f"\r\033[K")
        sys.stdout.flush()


# =============================================================================
# Test
# =============================================================================
if __name__ == "__main__":
    # Menggunakan ClaudeStyleTUI yang baru
    tui = ClaudeStyleTUI(
        workspace_path=os.getcwd(),
        backend="groq",
        model="llama-3.3-70b"
    )
    try:
        # Memanggil banner sebelum setup agar langsung ter-render
        tui.show_banner()
        tui.setup()

        tui.add_info("AIZU-CLI started")
        tui.start_thinking("Thinking")
        time.sleep(2)
        tui.stop_thinking()
        tui.add_tool_execution("read_file", {"path": "test.py"})
        tui.add_success("File loaded")
        tui.add_user_message("Hello!")
        tui.add_assistant_message("Hi! How can I help?")

        while True:
            try:
                user = tui.get_input()
                if user.lower() in ("/quit", "/exit", "/keluar"):
                    break
                tui.add_user_message(user)
                tui.start_thinking("Thinking")
                time.sleep(1)
                tui.stop_thinking()
                tui.add_assistant_message(f"You said: {user}")
            except (KeyboardInterrupt, EOFError):
                break
    finally:
        tui.cleanup()


# =============================================================================
# Claude Code Style TUI (New Implementation)
# =============================================================================
class ClaudeStyleTUI:
    """TUI dengan style Claude Code untuk AIZU-CLI.

    Layout:
    +================================================================+
    | [DIR] workspace_path                     backend | model       |
    +================================================================+
    |                                                                  |
    |  > Hello, bisa bantu saya?                                       |
    |                                                                  |
    |  [AI] Tentu! Saya siap membantu. Apa yang bisa saya lakukan?    |
    |                                                                  |
    |  [TOOL] Running: read_file (config.json)                         |
    |  [OK] File loaded                                                |
    |                                                                  |
    +------------------------------------------------------------------+
    |  kamu> _                                                         |
    +------------------------------------------------------------------+
    |  Tokens: 1,234 | Cost: $0.00 | Mode: chat                       |
    +------------------------------------------------------------------+

    Features:
    - Clean layout dengan borders
    - Color-coded messages per role
    - Progress indicators untuk tool execution
    - Streaming token display
    - Status bar dengan token count dan cost
    """

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model
        self.mode = "chat"
        self.plan_mode = False

        # Thread lock untuk stdout
        self._lock = threading.Lock()

        # Terminal dimensions
        self.width = 80
        self.height = 24
        self._last_width = self.width
        self._last_height = self.height
        self._update_dimensions()

        # Region heights
        self.HEADER_HEIGHT = 0      # Header dicetak sekali (scroll)
        self.INPUT_HEIGHT = 2       # Separator + input prompt
        self.STATUS_HEIGHT = 1      # Status bar
        self._sug_lines_drawn = 0   # Track jumlah baris suggestion yang sedang digambar

        # Data
        self.messages = []          # List of {role, text, icon, timestamp}
        self.progress_items = []    # List of {text, status}
        self.status_info = {
            "tokens": 0,
            "cost": "",
            "mode": "chat",
            "backend": "",
            "model": ""
        }

        # Thinking state
        self.is_thinking = False
        self.thinking_start = 0
        self.thinking_text = "Thinking"
        self.anim_thread = None
        self.anim_running = False
        self.frame_idx = 0
        self.frames = ["*", ".", "*", ".", "*", ".", "*", ".", "*", "."]

        # Streaming state (incremental display)
        self._streaming = False
        self._stream_buffer = ""
        self._stream_row = 0
        self._stream_col = 0

        # Resize handler
        self._setup_resize_handler()

    def _update_dimensions(self):
        """Update terminal dimensions"""
        try:
            size = os.get_terminal_size()
            self.width = size.columns
            self.height = size.lines
        except (OSError, ValueError):
            self.width = 80
            self.height = 24
        self.HEADER_HEIGHT = 0  # Header tidak statis di atas lagi, melainkan scroll

    def _setup_resize_handler(self):
        """Setup terminal resize handler.

        Unix: SIGWINCH signal handler
        Windows: Fallback to periodic check in get_input()/stop_thinking()
        """
        try:
            import signal
            def handle_resize(signum, frame):
                old_width, old_height = self.width, self.height
                self._update_dimensions()
                if self.width != old_width or self.height != old_height:
                    self._on_resize()
            signal.signal(signal.SIGWINCH, handle_resize)
        except (ImportError, AttributeError, OSError):
            pass  # Windows: use _check_resize() fallback

    def _check_resize(self):
        """Check if terminal size changed (Windows fallback)."""
        old_w, old_h = self._last_width, self._last_height
        self._update_dimensions()
        if self.width != old_w or self.height != old_h:
            self._last_width = self.width
            self._last_height = self.height
            self._on_resize()

    def _input_row(self):
        """Row index of the input prompt line"""
        return self.height - self.INPUT_HEIGHT - self.STATUS_HEIGHT + 1

    def _on_resize(self):
        """No-op in sequential mode"""
        pass

    def _chat_height(self):
        """Calculate chat area height"""
        return max(5, self.height - self.HEADER_HEIGHT - self.INPUT_HEIGHT - self.STATUS_HEIGHT)

    # -------------------------------------------------------------------------
    # Setup & Cleanup
    # -------------------------------------------------------------------------
    def show_banner(self):
        """Tampilkan banner/header premium di chat area agar bisa scroll up."""
        left_width = 35
        right_width = self.width - left_width - 3
        if right_width < 10:
            right_width = 10
        
        # Borders
        title_str = "─ Aizu CLI v2.1.201 "
        top_left = title_str + "─" * (left_width - len(title_str))
        top_right = "─" * right_width
        
        border_top = f"┌{top_left}┬{top_right}┐"
        border_bottom = f"└{'─' * left_width}┴{'─' * right_width}┘"
        
        # Invader ASCII
        invader = [
            "  █     █  ",
            "  ███████  ",
            " ██ █ █ ██ ",
            " █████████ ",
            "   █   █   "
        ]
        
        workspace = self.workspace_path
        if len(workspace) > left_width - 4:
            workspace = "..." + workspace[-(left_width - 7):]
            
        model_billing = f"{self.model} · API Billing"
        if len(model_billing) > left_width - 4:
            model_billing = model_billing[:left_width - 7] + "..."

        left_rows = [
            "Selamat datang kembali!".center(left_width),
            invader[0].center(left_width),
            invader[1].center(left_width),
            invader[2].center(left_width),
            invader[3].center(left_width),
            invader[4].center(left_width),
            model_billing.center(left_width),
            workspace.center(left_width)
        ]
        
        right_rows = [
            "Yang baru",
            "Sesi Aizu Pro kini mendukung peralatan canggih.",
            "Memperbaiki NameError saat memanggil /skill dan /schedule.",
            "Melompati pemblokiran DNS ISP menggunakan secure DoH.",
            "/release-notes untuk info lebih lanjut",
            "",
            "",
            ""
        ]
        
        def add_and_print(text):
            self.messages.append({"role": "header", "text": text, "timestamp": time.time()})
            print(text)

        # Spacing kosong di awal
        add_and_print("")
        
        # Append top border
        add_and_print(f"{Colors.VIOLET}{border_top}{Colors.RESET}")
        
        # Append rows
        for i in range(8):
            l_val = left_rows[i]
            r_val = right_rows[i]
            
            l_color = Colors.WHITE
            if "Selamat" in l_val:
                l_color = Colors.BOLD + Colors.WHITE
            elif any(x in l_val for x in ["█", "██"]):
                l_color = Colors.VIOLET
            else:
                l_color = Colors.DIM + Colors.WHITE
                
            r_color = Colors.WHITE
            if "Yang baru" in r_val:
                r_color = Colors.BOLD + Colors.VIOLET
            elif "/release" in r_val:
                r_color = Colors.DIM + Colors.WHITE
            
            l_part = l_val[:left_width].ljust(left_width)
            r_part = r_val[:right_width].ljust(right_width)
            
            row_str = (
                f"{Colors.VIOLET}│{Colors.RESET}"
                f"{l_color}{l_part}{Colors.RESET}"
                f"{Colors.VIOLET}│{Colors.RESET}"
                f"{r_color}{r_part}{Colors.RESET}"
                f"{Colors.VIOLET}│{Colors.RESET}"
            )
            add_and_print(row_str)
            
        # Append bottom border
        add_and_print(f"{Colors.VIOLET}{border_bottom}{Colors.RESET}")
        
        # Spacing kosong di akhir
        add_and_print("")
        sys.stdout.flush()

    def setup(self):
        """Initialize TUI layout"""
        self._update_dimensions()
        self._last_width = self.width
        self._last_height = self.height

        with self._lock:
            import os
            if _IS_WINDOWS:
                os.system('cls')
            else:
                sys.stdout.write("\033[2J\033[3J\033[H")
            sys.stdout.flush()

    def cleanup(self):
        """Cleanup on exit"""
        self._stop_animation()
        with self._lock:
            sys.stdout.flush()

    def _full_render(self):
        """No-op in sequential mode"""
        pass

    # -------------------------------------------------------------------------
    # Header Region
    # -------------------------------------------------------------------------
    def _render_header(self):
        """Render header (No-op karena header bersifat scrolling)"""
        pass
        sys.stdout.flush()

    def get_last_chat_lines(self, count):
        """Dapatkan count baris chat terakhir yang terformat (untuk memulihkan chat ter-overwrite)."""
        lines = []
        for msg in reversed(self.messages):
            role = msg.get("role", "")
            if role == "header":
                lines.insert(0, msg["text"])
            elif role == "user":
                text_lines = self._wrap_text(msg["text"], self.width)
                for idx, l in enumerate(text_lines):
                    prefix = "> " if idx == 0 else "  "
                    lines.insert(0, f"{Colors.GREEN}{prefix}{l}{Colors.RESET}")
            elif role == "assistant":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.WHITE
                for l in text_lines:
                    lines.insert(0, f"{color}{l}{Colors.RESET}")
            elif role == "thought" or role == "churned":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.DIM + Colors.WHITE
                for l in text_lines:
                    lines.insert(0, f"{color}{l}{Colors.RESET}")
            elif role == "tool":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.YELLOW
                for l in text_lines:
                    lines.insert(0, f"{color}🔧 {l}{Colors.RESET}")
            elif role == "tool_done":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.GREEN
                for l in text_lines:
                    lines.insert(0, f"{color}✻ {l}{Colors.RESET}")
            elif role == "error":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.RED
                for l in text_lines:
                    lines.insert(0, f"{color}❌ {l}{Colors.RESET}")
            elif role == "info":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.BLUE
                for l in text_lines:
                    lines.insert(0, f"{color}ℹ️ {l}{Colors.RESET}")
            elif role == "success":
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.GREEN
                for l in text_lines:
                    lines.insert(0, f"{color}✅ {l}{Colors.RESET}")
            else:
                text_lines = self._wrap_text(msg["text"], self.width)
                color = Colors.DIM
                for l in text_lines:
                    lines.insert(0, f"{color}{l}{Colors.RESET}")
                        
            if len(lines) >= count:
                break
        return lines[-count:] if len(lines) >= count else ([""] * (count - len(lines)) + lines)

    # -------------------------------------------------------------------------
    # Chat Region
    # -------------------------------------------------------------------------
    def _render_chat(self):
        """No-op in sequential mode"""
        pass

    # -------------------------------------------------------------------------
    # Input Region
    # -------------------------------------------------------------------------
    def _render_input(self):
        """No-op in sequential mode"""
        pass

    # -------------------------------------------------------------------------
    # Status Region
    # -------------------------------------------------------------------------
    def _render_status(self):
        """No-op in sequential mode"""
        pass

    # -------------------------------------------------------------------------
    # Message Methods
    # -------------------------------------------------------------------------
    def add_message(self, text, role="system", icon=""):
        """Add message ke chat area secara sequential"""
        self.messages.append({
            "role": role,
            "text": text,
            "icon": icon,
            "timestamp": time.time()
        })
        text_lines = self._wrap_text(text, self.width)
        with self._lock:
            if role == "header":
                for line in text_lines:
                    print(line)
            elif role == "user":
                for line in text_lines:
                    print(f"{Colors.GREEN}> {line}{Colors.RESET}")
            elif role == "assistant":
                color = Colors.WHITE
                for line in text_lines:
                    print(f"{color}{line}{Colors.RESET}")
            elif role == "thought":
                color = Colors.DIM + Colors.WHITE
                for line in text_lines:
                    print(f"{color}{line}{Colors.RESET}")
            elif role == "churned":
                color = Colors.DIM + Colors.WHITE
                for line in text_lines:
                    print(f"{color}{line}{Colors.RESET}")
            elif role == "tool":
                color = Colors.YELLOW
                for line in text_lines:
                    print(f"{color}🔧 {line}{Colors.RESET}")
            elif role == "tool_done":
                color = Colors.GREEN
                for line in text_lines:
                    print(f"{color}✻ {line}{Colors.RESET}")
            elif role == "error":
                color = Colors.RED
                for line in text_lines:
                    print(f"{color}❌ {line}{Colors.RESET}")
            elif role == "info":
                color = Colors.BLUE
                for line in text_lines:
                    print(f"{color}ℹ️ {line}{Colors.RESET}")
            elif role == "success":
                color = Colors.GREEN
                for line in text_lines:
                    print(f"{color}✅ {line}{Colors.RESET}")
            else:
                color = Colors.DIM
                for line in text_lines:
                    print(f"{color}{line}{Colors.RESET}")
            sys.stdout.flush()

    def add_user_message(self, text):
        """Add user message ke riwayat tanpa mencetak ulang (karena sudah dicetak saat Enter)"""
        self.stop_thinking()
        self.messages.append({
            "role": "user",
            "text": text,
            "timestamp": time.time()
        })

    def add_assistant_message(self, text):
        """Add assistant message (menghindari duplikasi jika sudah di-stream)"""
        self.stop_thinking()
        is_duplicate = False
        if self.messages:
            last = self.messages[-1]
            if last.get("role") == "assistant" and last.get("text") == text:
                is_duplicate = True
        if not is_duplicate:
            self.add_message(text, "assistant", "●")

    def add_thought_duration(self, seconds, usage=None, model=None, total_usage=None):
        """Add thought duration message sebaris dengan token info di akhir hasil.
        Juga akumulasi total_usage untuk session tracking."""
        text = f"✻ Berpikir {seconds}s"

        if usage:
            total_tokens = usage.get("total_tokens", 0)
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            # Caching detection
            cached_tokens = 0
            if "prompt_tokens_details" in usage and isinstance(usage["prompt_tokens_details"], dict):
                cached_tokens = usage["prompt_tokens_details"].get("cached_tokens", 0)
            if not cached_tokens:
                cached_tokens = usage.get("prompt_cache_hit_tokens", 0)

            cache_status = f"Aktif ({cached_tokens} token)" if cached_tokens > 0 else "Tidak aktif"

            # Cost calculation
            PRICING = {
                "llama-3.3-70b-versatile": {"input": 0.0, "output": 0.0},
                "llama-3.1-8b-instant": {"input": 0.0, "output": 0.0},
                "gemma2-9b-it": {"input": 0.0, "output": 0.0},
                "gpt-4o": {"input": 0.0025, "output": 0.01},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-4-turbo": {"input": 0.01, "output": 0.03},
                "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
                "gemini-2.0-flash": {"input": 0.0, "output": 0.0},
                "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
                "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
                "meta-llama/llama-3.3-70b-instruct": {"input": 0.00059, "output": 0.00079},
                "anthropic/claude-3-haiku": {"input": 0.00025, "output": 0.00125},
                "anthropic/claude-3-sonnet": {"input": 0.003, "output": 0.015},
                "default": {"input": 0.001, "output": 0.002}
            }
            USD_TO_IDR = 15800

            pricing = PRICING.get(model, PRICING.get("default", {"input": 0.001, "output": 0.002}))
            cost_usd = (prompt_tokens * pricing["input"] + completion_tokens * pricing["output"]) / 1000
            cost_idr = cost_usd * USD_TO_IDR

            cost_str = f"${cost_usd:.4f} (Rp{cost_idr:,.0f})" if cost_usd > 0 else "Gratis"
            text += f" · {total_tokens} token · {cost_str} · Caching: {cache_status}"

            # Akumulasi session total
            if total_usage is not None:
                total_usage["prompt"] = total_usage.get("prompt", 0) + prompt_tokens
                total_usage["completion"] = total_usage.get("completion", 0) + completion_tokens
                total_usage["total"] = total_usage.get("total", 0) + total_tokens
                total_usage["cost_usd"] = total_usage.get("cost_usd", 0) + cost_usd
                total_usage["cost_idr"] = total_usage.get("cost_idr", 0) + cost_idr

        thought_msg = {
            "role": "thought",
            "text": text,
            "icon": "",
            "timestamp": time.time()
        }

        has_recent = False
        for msg in reversed(self.messages[-3:]):
            if msg.get("role") == "thought":
                has_recent = True
                break

        if not has_recent:
            self.messages.append(thought_msg)
            text_lines = self._wrap_text(thought_msg["text"], self.width)
            color = Colors.DIM + Colors.WHITE
            with self._lock:
                for line in text_lines:
                    print(f"{color}{line}{Colors.RESET}")
                sys.stdout.flush()

    def add_churned_duration(self, seconds, total_usage=None):
        """Add churned duration message at the end, dengan session total"""
        text = f"✻ Selesai dalam {seconds}s"
        if total_usage and total_usage.get("total", 0) > 0:
            total_tokens = total_usage["total"]
            total_cost_usd = total_usage.get("cost_usd", 0)
            total_cost_idr = total_usage.get("cost_idr", 0)
            if total_cost_usd > 0:
                cost_str = f"${total_cost_usd:.4f} (Rp{total_cost_idr:,.0f})"
            else:
                cost_str = "Gratis"
            text += f" · Total sesi: {total_tokens} token · {cost_str}"
        churned_msg = {
            "role": "churned",
            "text": text,
            "icon": "",
            "timestamp": time.time()
        }
        self.messages.append(churned_msg)
        text_lines = self._wrap_text(churned_msg["text"], self.width)
        color = Colors.DIM + Colors.WHITE
        with self._lock:
            for line in text_lines:
                print(f"{color}{line}{Colors.RESET}")
            sys.stdout.flush()

    def add_tool_execution(self, tool_name, args=None):
        """Add tool execution message"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"
        text = f"Menjalankan: {tool_name}{args_str}"
        self.add_message(text, "tool", "[TOOL]")

    def add_tool_done(self, tool_name, result=""):
        """Add tool done message"""
        text = f"{tool_name} selesai"
        if result:
            text += f": {result[:50]}"
        self.add_message(text, "tool_done", "[OK]")

    def add_error(self, text):
        """Add error message"""
        self.add_message(text, "error", "[ERR]")

    def add_success(self, text):
        """Add success message"""
        self.add_message(text, "success", "[OK]")

    def add_info(self, text):
        """Add info message"""
        self.add_message(text, "info", "[INFO]")

    def add_warning(self, text):
        """Add warning message"""
        self.add_message(text, "warning", "[WARN]")

    # -------------------------------------------------------------------------
    # Thinking Animation
    # -------------------------------------------------------------------------
    def start_thinking(self, text="Berpikir", note=""):
        """Start thinking animation"""
        self._stop_animation()
        self.is_thinking = True
        self.thinking_text = text
        self.thinking_start = time.time()
        self.frame_idx = 0
        self._stop_event = threading.Event()
        self.anim_thread = threading.Thread(target=self._animate, args=(self._stop_event,), daemon=True)
        self.anim_thread.start()

    def _animate(self, stop_event):
        """Thinking animation thread (thread-safe dengan Event)"""
        while not stop_event.is_set():
            elapsed = int(time.time() - self.thinking_start)
            icon = self.frames[self.frame_idx % len(self.frames)]

            with self._lock:
                sys.stdout.write(f"\r{Colors.YELLOW} {icon} {self.thinking_text} ({elapsed}s)...{Colors.RESET}  ")
                sys.stdout.flush()

            self.frame_idx += 1
            stop_event.wait(0.15)

    def stop_thinking(self):
        """Stop thinking animation"""
        self._stop_animation()
        self.is_thinking = False
        with self._lock:
            sys.stdout.write(f"\r{' ' * 60}\r")  # Clear thinking line
            sys.stdout.flush()

    def _stop_animation(self):
        """Stop animation thread"""
        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()
        if hasattr(self, 'anim_thread') and self.anim_thread:
            self.anim_thread.join(timeout=0.3)
            self.anim_thread = None

    # -------------------------------------------------------------------------
    # Streaming Methods (Incremental Display)
    # -------------------------------------------------------------------------
    def start_streaming(self):
        """Start streaming mode — incremental token display."""
        self._streaming = True
        self._stream_buffer = ""

        # JANGAN stop thinking di sini — biarkan sampai token pertama tiba
        # Thinking di-stop otomatis di stream_token() saat token pertama

        self.messages.append({
            "role": "assistant",
            "text": "",
            "timestamp": time.time()
        })

        with self._lock:
            sys.stdout.write(Colors.WHITE)
            sys.stdout.flush()

    def stream_token(self, token):
        """Add token secara incremental ke stdout."""
        if not self._streaming:
            return

        # Stop thinking animation saat token pertama tiba
        if not self._stream_buffer and self.is_thinking:
            self.stop_thinking()
            # Baris baru sebelum output assistant
            with self._lock:
                sys.stdout.write("\n")
                sys.stdout.flush()

        self._stream_buffer += token

        with self._lock:
            sys.stdout.write(token)
            sys.stdout.flush()

        if self.messages:
            self.messages[-1]["text"] = self._stream_buffer

    def stop_streaming(self):
        """Stop streaming mode dan final render."""
        self._streaming = False
        if self.messages:
            self.messages[-1]["text"] = self._stream_buffer
        self._stream_buffer = ""
        with self._lock:
            print() # Print newline to finish assistant block
            sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Progress Methods
    # -------------------------------------------------------------------------
    def add_progress(self, text, status="pending"):
        """Add progress item dan re-render"""
        self.progress_items.append({"text": text, "status": status})
        with self._lock:
            self._render_chat()
            self._render_input()

    def update_progress(self, index_or_text, new_status=None, text=None):
        """Update progress item status.

        Mendukung 2 signature:
        - update_progress(index, status, text=None)  — by index
        - update_progress(text, new_status)           — by text match
        """
        if isinstance(index_or_text, int):
            idx = index_or_text
            if 0 <= idx < len(self.progress_items):
                if new_status is not None:
                    self.progress_items[idx]["status"] = new_status
                if text is not None:
                    self.progress_items[idx]["text"] = text
        else:
            for item in self.progress_items:
                if item["text"] == index_or_text:
                    item["status"] = new_status
                    break

        with self._lock:
            self._render_chat()
            self._render_input()

    def clear_progress(self):
        """Clear all progress items dan re-render"""
        self.progress_items.clear()
        with self._lock:
            self._render_chat()
            self._render_input()

    # -------------------------------------------------------------------------
    # Status Methods
    # -------------------------------------------------------------------------
    def update_status(self, tokens=None, cost=None, mode=None, backend=None, model=None):
        """Update status bar info"""
        if tokens is not None:
            self.status_info["tokens"] = tokens
        if cost is not None:
            self.status_info["cost"] = cost
        if mode is not None:
            self.status_info["mode"] = mode
            self.mode = mode
        if backend is not None:
            self.status_info["backend"] = backend
            self.backend = backend
        if model is not None:
            self.status_info["model"] = model
            self.model = model
        with self._lock:
            self._render_status()
            sys.stdout.flush()

    def update_tokens(self, count):
        """Update token count"""
        self.status_info["tokens"] = count
        with self._lock:
            self._render_status()
            sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Header Methods
    # -------------------------------------------------------------------------
    def update_header(self, backend=None, model=None):
        """Update header info"""
        if backend:
            self.backend = backend
            self.status_info["backend"] = backend
        if model:
            self.model = model
            self.status_info["model"] = model
        with self._lock:
            self._render_header()
            sys.stdout.flush()

    def show_plan_mode(self, enabled):
        """Toggle plan mode indicator di header"""
        self.plan_mode = enabled
        with self._lock:
            self._render_header()
            sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    def get_input(self) -> str:
        """Get user input dengan slash command suggestions.

        Menampilkan rekomendasi slash command secara real-time saat user
        mengetik diawali '/'. Mendukung Windows (msvcrt) dan Unix (termios).
        """
        self._check_resize()

        if _IS_WINDOWS:
            return self._input_windows()
        else:
            return self._input_unix()

    def _input_windows(self):
        """Input dengan suggestions di Windows pakai msvcrt secara sequential."""
        with self._lock:
            # Tampilkan top divider secara mengalir (scroll)
            sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
            sys.stdout.flush()

        # Fallback kalau bukan TTY (piped stdin)
        if not sys.stdin.isatty():
            return input()

        import msvcrt

        buf = ""
        sel = -1
        self._sug_lines_drawn = 0

        def render_all():
            sug = self._match_commands(buf)
            prompt_len = 2 + len(buf)
            prompt_rows = prompt_len // self.width + 1

            with self._lock:
                # 1. Hapus suggestions lama dan pulihkan chat history baris lama
                K = self._sug_lines_drawn
                if K > 0:
                    sys.stdout.write(ANSI.cursor_up(K + prompt_rows))
                    chat_lines = self.get_last_chat_lines(K)
                    for line in chat_lines:
                        sys.stdout.write(ANSI.clear_line())
                        sys.stdout.write(line + "\n")
                    # Tulis ulang top divider
                    sys.stdout.write(ANSI.clear_line())
                    sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                    self._sug_lines_drawn = 0
                else:
                    if prompt_rows > 1:
                        sys.stdout.write(ANSI.cursor_up(prompt_rows - 1))

                # Sekarang kursor berada di baris pertama prompt. Hapus semuanya ke bawah!
                sys.stdout.write("\r" + ANSI.clear_to_end())

                # 2. Gambar suggestions baru jika ada
                if sug:
                    sys.stdout.write(ANSI.cursor_up(len(sug) + 1))
                    for i, (cmd, desc) in enumerate(sug):
                        sys.stdout.write(ANSI.clear_line())
                        if i == sel:
                            sys.stdout.write(f"  {Colors.BG_LIGHT_GRAY}{Colors.WHITE} {cmd}  {desc} {Colors.RESET}\n")
                        else:
                            sys.stdout.write(f"  {Colors.VIOLET}{cmd}{Colors.RESET}  {Colors.DIM}{desc}{Colors.RESET}\n")
                    # Tulis ulang top divider
                    sys.stdout.write(ANSI.clear_line())
                    sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                    self._sug_lines_drawn = len(sug)

                # 3. Tulis ulang prompt line + clear to end untuk bottom divider & status help
                sys.stdout.write(f"{Colors.GREEN}> {Colors.WHITE}{buf}")
                sys.stdout.write(f"\n{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                sys.stdout.write(f"  {Colors.DIM}{Colors.WHITE}? untuk pintasan · ← untuk agen{Colors.RESET}")

                # 4. Posisikan kursor kembali ke prompt line typing position
                move_up_count = 2 + (prompt_rows - 1)
                sys.stdout.write(ANSI.cursor_up(move_up_count))
                cursor_col = prompt_len % self.width + 1
                sys.stdout.write("\r")
                if cursor_col > 1:
                    sys.stdout.write(f"\033[{cursor_col - 1}C")
                sys.stdout.flush()

        # Render pertama kali
        render_all()

        while True:
            if msvcrt.kbhit():
                ch = msvcrt.getwch()

                if ch in ('\r', '\n'):
                    # Enter
                    sug = self._match_commands(buf)
                    if sug and 0 <= sel < len(sug):
                        buf = sug[sel][0]
                    # Hapus dan pulihkan layar sebelum keluar
                    with self._lock:
                        prompt_len = 2 + len(buf)
                        prompt_rows = prompt_len // self.width + 1
                        K = self._sug_lines_drawn
                        if K > 0:
                            sys.stdout.write(ANSI.cursor_up(K + prompt_rows))
                            chat_lines = self.get_last_chat_lines(K)
                            for line in chat_lines:
                                sys.stdout.write(ANSI.clear_line())
                                sys.stdout.write(line + "\n")
                            self._sug_lines_drawn = 0
                        else:
                            sys.stdout.write(ANSI.cursor_up(prompt_rows))
                        # Hapus area input (top divider, prompt line, bottom divider, status help)
                        sys.stdout.write("\r" + ANSI.clear_to_end())
                        # Cetak pesan user secara bersih sebagai chat history
                        print(f"{Colors.GREEN}> {buf}{Colors.RESET}")
                        sys.stdout.flush()
                    return buf

                elif ch == '\x03':
                    raise KeyboardInterrupt

                elif ch == '\x08':
                    # Backspace
                    buf = buf[:-1]
                    sel = -1
                    render_all()

                elif ch == '\t':
                    # Tab — autocomplete
                    sug = self._match_commands(buf)
                    if sug:
                        if 0 <= sel < len(sug):
                            buf = sug[sel][0] + " "
                        else:
                            buf = sug[0][0] + " "
                        sel = -1
                        render_all()

                elif ch == '\xe0':
                    # Arrow keys (special key prefix on Windows)
                    ch2 = msvcrt.getwch()
                    sug = self._match_commands(buf)
                    if ch2 == 'H':  # Up
                        if sug:
                            sel = max(0, sel - 1) if sel >= 0 else 0
                            render_all()
                    elif ch2 == 'P':  # Down
                        if sug:
                            sel = min(len(sug) - 1, sel + 1) if sel >= 0 else 0
                            render_all()

                elif ch >= ' ':
                    buf += ch
                    sel = -1
                    render_all()

            else:
                time.sleep(0.02)

    def _input_unix(self):
        """Input dengan suggestions di Unix pakai termios secara sequential."""
        import termios
        import tty

        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            # Fallback ke input() biasa
            with self._lock:
                sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                sys.stdout.flush()
            return input()

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        buf = ""
        sel = -1
        self._sug_lines_drawn = 0

        def render_all():
            sug = self._match_commands(buf)
            prompt_len = 2 + len(buf)
            prompt_rows = prompt_len // self.width + 1

            with self._lock:
                # 1. Hapus suggestions lama dan pulihkan chat history baris lama
                K = self._sug_lines_drawn
                if K > 0:
                    sys.stdout.write(ANSI.cursor_up(K + prompt_rows))
                    chat_lines = self.get_last_chat_lines(K)
                    for line in chat_lines:
                        sys.stdout.write(ANSI.clear_line())
                        sys.stdout.write(line + "\n")
                    # Tulis ulang top divider
                    sys.stdout.write(ANSI.clear_line())
                    sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                    self._sug_lines_drawn = 0
                else:
                    if prompt_rows > 1:
                        sys.stdout.write(ANSI.cursor_up(prompt_rows - 1))

                # Sekarang kursor berada di baris pertama prompt. Hapus semuanya ke bawah!
                sys.stdout.write("\r" + ANSI.clear_to_end())

                # 2. Gambar suggestions baru jika ada
                if sug:
                    sys.stdout.write(ANSI.cursor_up(len(sug) + 1))
                    for i, (cmd, desc) in enumerate(sug):
                        sys.stdout.write(ANSI.clear_line())
                        if i == sel:
                            sys.stdout.write(f"  {Colors.BG_LIGHT_GRAY}{Colors.WHITE} {cmd}  {desc} {Colors.RESET}\n")
                        else:
                            sys.stdout.write(f"  {Colors.VIOLET}{cmd}{Colors.RESET}  {Colors.DIM}{desc}{Colors.RESET}\n")
                    # Tulis ulang top divider
                    sys.stdout.write(ANSI.clear_line())
                    sys.stdout.write(f"{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                    self._sug_lines_drawn = len(sug)

                # 3. Tulis ulang prompt line + clear to end untuk bottom divider & status help
                sys.stdout.write(f"{Colors.GREEN}> {Colors.WHITE}{buf}")
                sys.stdout.write(f"\n{Colors.VIOLET}{'-' * self.width}{Colors.RESET}\n")
                sys.stdout.write(f"  {Colors.DIM}{Colors.WHITE}? untuk pintasan · ← untuk agen{Colors.RESET}")

                # 4. Posisikan kursor kembali ke prompt line typing position
                move_up_count = 2 + (prompt_rows - 1)
                sys.stdout.write(ANSI.cursor_up(move_up_count))
                cursor_col = prompt_len % self.width + 1
                sys.stdout.write("\r")
                if cursor_col > 1:
                    sys.stdout.write(f"\033[{cursor_col - 1}C")
                sys.stdout.flush()

        try:
            tty.setcbreak(fd)
            render_all()
            while True:
                ch = sys.stdin.read(1)
                if ch in ('\r', '\n'):
                    sug = self._match_commands(buf)
                    if sug and 0 <= sel < len(sug):
                        buf = sug[sel][0]
                    # Hapus dan pulihkan layar sebelum keluar
                    with self._lock:
                        prompt_len = 2 + len(buf)
                        prompt_rows = prompt_len // self.width + 1
                        K = self._sug_lines_drawn
                        if K > 0:
                            sys.stdout.write(ANSI.cursor_up(K + prompt_rows))
                            chat_lines = self.get_last_chat_lines(K)
                            for line in chat_lines:
                                sys.stdout.write(ANSI.clear_line())
                                sys.stdout.write(line + "\n")
                            self._sug_lines_drawn = 0
                        else:
                            sys.stdout.write(ANSI.cursor_up(prompt_rows))
                        # Hapus area input (top divider, prompt line, bottom divider, status help)
                        sys.stdout.write("\r" + ANSI.clear_to_end())
                        # Cetak pesan user secara bersih sebagai chat history
                        print(f"{Colors.GREEN}> {buf}{Colors.RESET}")
                        sys.stdout.flush()
                    return buf
                elif ch == '\x03':
                    raise KeyboardInterrupt
                elif ch == '\x04':
                    if not buf:
                        raise EOFError
                elif ch in ('\x7f', '\x08'):
                    buf = buf[:-1]
                    sel = -1
                    render_all()
                elif ch == '\t':
                    sug = self._match_commands(buf)
                    if sug:
                        if 0 <= sel < len(sug):
                            buf = sug[sel][0] + " "
                        else:
                            buf = sug[0][0] + " "
                        sel = -1
                    render_all()
                elif ch == '\x1b':
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        sug = self._match_commands(buf)
                        if ch3 == 'A':  # Up
                            if sug:
                                sel = max(0, sel - 1) if sel >= 0 else 0
                        elif ch3 == 'B':  # Down
                            if sug:
                                sel = min(len(sug) - 1, sel + 1) if sel >= 0 else 0
                        render_all()
                elif ch >= ' ':
                    buf += ch
                    sel = -1
                    render_all()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    @staticmethod
    def _match_commands(buf):
        """Cari command yang cocok dengan teks yang sedang diketik."""
        if not buf.startswith('/'):
            return []
        low = buf.lower()
        return [(c, h) for c, h in COMMANDS if c.startswith(low)][:MAX_SUGGEST]

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    def _wrap_text(self, text, width):
        """Wrap text untuk fit dalam width"""
        import re

        if not text:
            return [""]

        def visible_length(s):
            ansi_escape = re.compile(r'\033\[[0-9;]*m')
            return len(ansi_escape.sub('', s))

        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append("")
                continue

            words = paragraph.split()
            current_line = ""
            current_visible_len = 0

            for word in words:
                word_visible_len = visible_length(word)

                if current_visible_len + word_visible_len + (1 if current_line else 0) <= width:
                    if current_line:
                        current_line += " " + word
                        current_visible_len += word_visible_len + 1
                    else:
                        current_line = word
                        current_visible_len = word_visible_len
                else:
                    if current_line:
                        lines.append(current_line)
                    current_line = word
                    current_visible_len = word_visible_len

            if current_line:
                lines.append(current_line)

        return lines if lines else [""]
