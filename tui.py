"""
AIZU-CLI Simple TUI (Claude Code Style)
========================================

Clean, simple TUI tanpa complex cursor positioning.
Messages ditampilkan secara linear seperti chat biasa.
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
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    # -------------------------------------------------------------------------
    # Setup & Cleanup
    # -------------------------------------------------------------------------
    def setup(self):
        """Initial setup - print header"""
        path = self.workspace_path
        if len(path) > 50:
            path = "..." + path[-47:]

        plan_indicator = " 📋 PLAN MODE" if self.plan_mode else ""

        print(f"\033[2J\033[H", end="")  # Clear screen
        print(f"{Colors.BG_BLUE}{Colors.BOLD} 📁 {path}{plan_indicator}{' ' * 20}{self.backend} | {self.model} {Colors.RESET}")
        print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
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

        print(f" {icon} {color}{text}{Colors.RESET}")

    def add_user_message(self, text):
        """Print user message"""
        self.stop_thinking()
        print(f" 👤 {Colors.GREEN}{text}{Colors.RESET}")
        print()

    def add_assistant_message(self, text):
        """Print assistant message"""
        self.stop_thinking()
        # Print each line separately for better readability
        for line in text.split('\n'):
            if line.strip():
                print(f" 🤖 {Colors.CYAN}{line}{Colors.RESET}")
        print()

    def add_tool_execution(self, tool_name, args=None):
        """Print tool execution"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"
        print(f" 🔧 {Colors.MAGENTA}Running: {tool_name}{args_str}{Colors.RESET}")

    def add_error(self, text):
        print(f" ❌ {Colors.RED}{text}{Colors.RESET}")

    def add_success(self, text):
        print(f" ✅ {Colors.GREEN}{text}{Colors.RESET}")

    def add_info(self, text):
        print(f" ℹ️  {Colors.CYAN}{text}{Colors.RESET}")

    def add_warning(self, text):
        print(f" ⚠️  {Colors.YELLOW}{text}{Colors.RESET}")

    def add_thinking(self, text):
        print(f" ✻ {Colors.YELLOW}{text}{Colors.RESET}")

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
