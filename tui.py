"""
AIZU-CLI Modern TUI System (Claude Code Style)
===============================================

Clean, minimal TUI seperti Claude Code.
Single-screen layout dengan cursor positioning yang benar.

Layout (Claude Code style):
┌─────────────────────────────────────────────────────────────┐
│ 📁 /path/to/project                     groq | model        │  ← Header (line 1)
├─────────────────────────────────────────────────────────────┤  ← Separator (line 2)
│ ⠋ Thinking for 3s... (ctrl+o to expand)                    │  ← Thinking (line 3)
├─────────────────────────────────────────────────────────────┤  ← Separator (line 4)
│                                                             │
│ 👤 User message                                             │  ← Messages area
│                                                             │
│ 🤖 Assistant response                                       │
│                                                             │
│ 🔧 Running: read_file (file.py)                            │
│ ✅ File loaded                                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤  ← Separator
│ kamu> _                                                     │  ← Input (bottom)
└─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import time
import threading


# =============================================================================
# ANSI Colors
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
    BG_YELLOW = "\033[43m"


# =============================================================================
# TUI Class
# =============================================================================
class AizuTUI:
    """Claude Code-style TUI for AIZU-CLI"""

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model
        self.plan_mode = False

        # Terminal size
        self.width, self.height = self._get_terminal_size()

        # Layout positions (fixed)
        self.HEADER_Y = 1
        self.SEP1_Y = 2
        self.THINKING_Y = 3
        self.SEP2_Y = 4
        self.MSG_START_Y = 5
        self.INPUT_Y = self.height - 1
        self.MSG_MAX_LINES = self.INPUT_Y - self.MSG_START_Y - 1

        # State
        self.is_thinking = False
        self.thinking_start = 0
        self.thinking_text = "Thinking"
        self.thinking_note = ""
        self.anim_thread = None
        self.anim_running = False
        self.frame_idx = 0
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

        # Messages buffer (simple list of (icon, color, text))
        self.messages = []

    def _get_terminal_size(self):
        try:
            import shutil
            s = shutil.get_terminal_size()
            return s.columns, s.lines
        except:
            return 80, 24

    # -------------------------------------------------------------------------
    # Cursor & Screen Control
    # -------------------------------------------------------------------------
    def _move(self, x, y):
        sys.stdout.write(f"\033[{y};{x}H")

    def _clear_line(self):
        sys.stdout.write("\033[K")

    def _clear_screen(self):
        sys.stdout.write("\033[2J\033[H")

    def _flush(self):
        sys.stdout.flush()

    # -------------------------------------------------------------------------
    # Setup & Cleanup
    # -------------------------------------------------------------------------
    def setup(self):
        """Initial screen setup"""
        self._clear_screen()
        self._render_header()
        self._render_separator(self.SEP1_Y)
        self._render_thinking_line()
        self._render_separator(self.SEP2_Y)
        self._clear_messages_area()
        self._render_separator(self.INPUT_Y - 1)
        self._render_input()
        self._flush()

    def cleanup(self):
        """Cleanup on exit"""
        self._stop_animation()
        sys.stdout.write("\033[?25h")  # Show cursor
        self._move(1, self.height)
        sys.stdout.write("\n")
        self._flush()

    # -------------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------------
    def _render_header(self):
        """Render top header bar"""
        path = self.workspace_path
        max_path = self.width - len(self.backend) - len(self.model) - 15
        if len(path) > max_path:
            path = "..." + path[-(max_path-3):]

        left = f" 📁 {path}"
        right = f"{self.backend} | {self.model} "

        if self.plan_mode:
            right = f"📋 PLAN | {right}"

        padding = self.width - len(left) - len(right)
        if padding < 0:
            padding = 0

        self._move(1, self.HEADER_Y)
        bg = Colors.BG_YELLOW if self.plan_mode else Colors.BG_BLUE
        sys.stdout.write(f"{bg}{Colors.BOLD}{left}{' ' * padding}{right}{Colors.RESET}")

    def update_header(self, backend=None, model=None):
        if backend:
            self.backend = backend
        if model:
            self.model = model
        self._render_header()
        self._flush()

    # -------------------------------------------------------------------------
    # Separators
    # -------------------------------------------------------------------------
    def _render_separator(self, y):
        self._move(1, y)
        sys.stdout.write(f"{Colors.DIM}{'─' * self.width}{Colors.RESET}")

    # -------------------------------------------------------------------------
    # Thinking Indicator
    # -------------------------------------------------------------------------
    def _render_thinking_line(self):
        """Render thinking indicator at fixed position"""
        self._move(1, self.THINKING_Y)
        self._clear_line()

        if not self.is_thinking:
            sys.stdout.write(" ")  # Empty line
            return

        elapsed = int(time.time() - self.thinking_start)
        icon = self.frames[self.frame_idx % len(self.frames)]
        note = f" ({self.thinking_note})" if self.thinking_note else ""
        line = f"{Colors.YELLOW}{icon} {self.thinking_text} for {elapsed}s...{Colors.RESET}{Colors.DIM}{note}{Colors.RESET}"

        # Truncate if too long
        if len(line) > self.width + 20:  # +20 for ANSI codes
            line = line[:self.width + 17] + "..."

        sys.stdout.write(line)

    def start_thinking(self, text="Thinking", note=""):
        self._stop_animation()
        self.is_thinking = True
        self.thinking_text = text
        self.thinking_note = note
        self.thinking_start = time.time()
        self.frame_idx = 0
        self.anim_running = True
        self.anim_thread = threading.Thread(target=self._animate, daemon=True)
        self.anim_thread.start()

    def _animate(self):
        while self.anim_running:
            self.frame_idx = (self.frame_idx + 1) % len(self.frames)
            self._render_thinking_line()
            self._flush()
            time.sleep(0.08)

    def _stop_animation(self):
        self.anim_running = False
        if self.anim_thread:
            self.anim_thread.join(timeout=0.3)
            self.anim_thread = None

    def stop_thinking(self):
        self._stop_animation()
        self.is_thinking = False
        self._render_thinking_line()
        self._flush()

    # -------------------------------------------------------------------------
    # Messages Area
    # -------------------------------------------------------------------------
    def _clear_messages_area(self):
        """Clear the messages area"""
        for y in range(self.MSG_START_Y, self.MSG_START_Y + self.MSG_MAX_LINES):
            self._move(1, y)
            self._clear_line()

    def _render_messages(self):
        """Render all messages in the messages area"""
        self._clear_messages_area()

        # Show last N messages that fit
        visible = self.messages[-self.MSG_MAX_LINES:]
        for i, (icon, color, text) in enumerate(visible):
            y = self.MSG_START_Y + i
            if y >= self.MSG_START_Y + self.MSG_MAX_LINES:
                break

            self._move(1, y)

            # Format: icon + space + colored text
            if icon:
                line = f" {icon} {color}{text}{Colors.RESET}"
            else:
                line = f"   {color}{text}{Colors.RESET}"

            # Truncate to terminal width
            # Note: ANSI codes don't take visual space, so we need to be careful
            # Simple approach: just write and let terminal handle wrapping
            sys.stdout.write(line[:self.width + 30])  # Extra room for ANSI

    def add_message(self, text, role="system", icon=""):
        """Add a message to the display"""
        # Set color and default icon based on role
        if role == "user":
            color = Colors.GREEN
            if not icon:
                icon = "👤"
        elif role == "assistant":
            color = Colors.CYAN
            if not icon:
                icon = "🤖"
        elif role == "tool":
            color = Colors.MAGENTA
            if not icon:
                icon = "🔧"
        elif role == "error":
            color = Colors.RED
            if not icon:
                icon = "❌"
        elif role == "success":
            color = Colors.GREEN
            if not icon:
                icon = "✅"
        elif role == "info":
            color = Colors.CYAN
            if not icon:
                icon = "ℹ️"
        elif role == "warning":
            color = Colors.YELLOW
            if not icon:
                icon = "⚠️"
        else:
            color = Colors.DIM
            if not icon:
                icon = "•"

        self.messages.append((icon, color, text))
        self._render_messages()
        self._flush()

    def add_user_message(self, text):
        # Wrap long lines
        for line in text.split('\n'):
            line = line.strip()
            if line:
                while len(line) > 70:
                    break_at = line[:70].rfind(' ')
                    if break_at <= 0:
                        break_at = 70
                    self.add_message(line[:break_at], role="user")
                    line = line[break_at:].strip()
                if line:
                    self.add_message(line, role="user")

    def add_assistant_message(self, text):
        for line in text.split('\n'):
            line = line.strip()
            if line:
                while len(line) > 70:
                    break_at = line[:70].rfind(' ')
                    if break_at <= 0:
                        break_at = 70
                    self.add_message(line[:break_at], role="assistant")
                    line = line[break_at:].strip()
                if line:
                    self.add_message(line, role="assistant")

    def add_tool_execution(self, tool_name, args=None):
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"
        self.add_message(f"Running: {tool_name}{args_str}", role="tool")

    def add_error(self, text):
        self.add_message(text, role="error")

    def add_success(self, text):
        self.add_message(text, role="success")

    def add_info(self, text):
        self.add_message(text, role="info")

    def add_warning(self, text):
        self.add_message(text, role="warning")

    def add_thinking(self, text):
        self.add_message(text, role="info", icon="✻")

    def show_plan_mode(self, enabled):
        self.plan_mode = enabled
        self._render_header()
        self._flush()

    # -------------------------------------------------------------------------
    # Input
    # -------------------------------------------------------------------------
    def _render_input(self):
        """Render input prompt at bottom"""
        self._move(1, self.INPUT_Y)
        self._clear_line()
        sys.stdout.write(f"{Colors.GREEN}{Colors.BOLD}kamu> {Colors.RESET}")

    def get_input(self) -> str:
        """Get user input (blocking)"""
        if not sys.stdin.isatty():
            try:
                return input("kamu> ")
            except (EOFError, KeyboardInterrupt):
                raise

        import tty
        import termios

        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        buf = ""
        cursor = 0
        history = []
        hist_idx = -1

        try:
            tty.setcbreak(fd)
            self._render_input()
            self._flush()

            while True:
                ch = sys.stdin.read(1)

                if ch in ("\r", "\n"):
                    if buf:
                        history.append(buf)
                    self._move(1, self.INPUT_Y)
                    self._clear_line()
                    sys.stdout.write(f"{Colors.GREEN}{Colors.BOLD}kamu> {Colors.RESET}{buf}")
                    sys.stdout.write("\n")
                    self._flush()
                    return buf

                elif ch == "\x03":  # Ctrl+C
                    raise KeyboardInterrupt

                elif ch == "\x04":  # Ctrl+D
                    if not buf:
                        raise EOFError

                elif ch in ("\x7f", "\x08"):  # Backspace
                    if cursor > 0:
                        buf = buf[:cursor-1] + buf[cursor:]
                        cursor -= 1

                elif ch == "\x1b":  # Escape sequence
                    seq = sys.stdin.read(2)
                    if seq == "[A":  # Up
                        if history and hist_idx < len(history) - 1:
                            hist_idx += 1
                            buf = history[-(hist_idx + 1)]
                            cursor = len(buf)
                    elif seq == "[B":  # Down
                        if hist_idx > 0:
                            hist_idx -= 1
                            buf = history[-(hist_idx + 1)]
                            cursor = len(buf)
                        elif hist_idx == 0:
                            hist_idx = -1
                            buf = ""
                            cursor = 0
                    elif seq == "[C":  # Right
                        if cursor < len(buf):
                            cursor += 1
                    elif seq == "[D":  # Left
                        if cursor > 0:
                            cursor -= 1

                elif ch == "\t":
                    pass  # TODO: autocomplete

                elif ch and ch.isprintable():
                    buf = buf[:cursor] + ch + buf[cursor:]
                    cursor += 1

                # Re-render input line
                self._move(1, self.INPUT_Y)
                self._clear_line()
                sys.stdout.write(f"{Colors.GREEN}{Colors.BOLD}kamu> {Colors.RESET}{buf}")
                # Move cursor to correct position
                self._move(6 + cursor, self.INPUT_Y)
                self._flush()

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


# =============================================================================
# Streaming TUI
# =============================================================================
class StreamingTUI:
    """Simple streaming wrapper"""

    def __init__(self, tui: AizuTUI):
        self.tui = tui
        self.buffer = ""

    def on_token(self, token: str):
        self.buffer += token
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_complete(self):
        if self.buffer.strip():
            self.tui.add_assistant_message(self.buffer)
        self.buffer = ""


# =============================================================================
# Test
# =============================================================================
if __name__ == "__main__":
    tui = AizuTUI(
        workspace_path=os.getcwd(),
        backend="groq",
        model="llama-3.3-70b"
    )
    try:
        tui.setup()
        tui.add_info("AIZU-CLI started")
        tui.start_thinking("Thinking")
        time.sleep(2)
        tui.stop_thinking()
        tui.add_tool_execution("read_file", {"path": "test.py"})
        tui.add_success("File loaded")
        tui.add_user_message("Hello, can you help me?")
        tui.add_assistant_message("Sure! What do you need help with?")

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
