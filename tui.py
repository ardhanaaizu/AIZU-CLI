"""
AIZU-CLI Modern TUI System (Claude Code Style)
===============================================

Clean, minimal TUI seperti Claude Code.
Layout:
┌─────────────────────────────────────────────────────────────┐
│ 📁 /path/to/project                     groq | model        │  ← Header
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Thinking for 3s... (ctrl+o to expand)                       │  ← Thinking
│                                                             │
│ 👤 User message here...                                     │  ← Messages
│                                                             │
│ 🤖 Assistant response here...                               │
│                                                             │
│ 🔧 Running: read_file (path/to/file)                        │  ← Tool execution
│ ✅ File loaded (42 lines)                                   │
│                                                             │
│ kamu> _                                                     │  ← Input
└─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import time
import threading
from typing import List, Dict, Optional


# =============================================================================
# ANSI Colors (Minimalist)
# =============================================================================
class Colors:
    """ANSI color codes - Claude Code style"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Foreground (minimal palette)
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_BLUE = "\033[44m"
    BG_YELLOW = "\033[43m"


# =============================================================================
# Terminal Utilities
# =============================================================================
class Terminal:
    """Terminal manipulation utilities"""

    @staticmethod
    def get_size():
        """Get terminal size (width, height)"""
        try:
            import shutil
            size = shutil.get_terminal_size()
            return size.columns, size.lines
        except:
            return 80, 24

    @staticmethod
    def clear():
        """Clear terminal"""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

    @staticmethod
    def clear_line():
        """Clear current line"""
        sys.stdout.write("\r\033[K")
        sys.stdout.flush()

    @staticmethod
    def move_to(x, y):
        """Move cursor to position"""
        sys.stdout.write(f"\033[{y};{x}H")
        sys.stdout.flush()

    @staticmethod
    def hide_cursor():
        """Hide cursor"""
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()

    @staticmethod
    def show_cursor():
        """Show cursor"""
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


# =============================================================================
# TUI Components (Claude Code Style)
# =============================================================================
class Header:
    """Header component - clean, minimal"""

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model
        self.width = Terminal.get_size()[0]
        self.plan_mode = False

    def render(self, y: int = 1):
        """Render header at position y"""
        width = self.width

        # Truncate workspace path if too long
        display_path = self.workspace_path
        if len(display_path) > width - 30:
            display_path = "..." + display_path[-(width - 33):]

        # Build header content
        left = f"📁 {display_path}"
        right = f"{self.backend} | {self.model}"

        if self.plan_mode:
            right = f"📋 PLAN MODE | {right}"

        # Calculate padding
        padding = width - len(left) - len(right) - 4
        if padding < 0:
            padding = 0

        # Render - Claude Code style: simple colored background
        Terminal.move_to(1, y)
        if self.plan_mode:
            sys.stdout.write(f"{Colors.BG_YELLOW}{Colors.BOLD} ")
        else:
            sys.stdout.write(f"{Colors.BG_BLUE}{Colors.BOLD} ")
        sys.stdout.write(f"{left}")
        sys.stdout.write(" " * padding)
        sys.stdout.write(f"{right} ")
        sys.stdout.write(f"{Colors.RESET}")
        sys.stdout.flush()


class ThinkingIndicator:
    """Thinking indicator - Claude Code style (simple, clean)"""

    def __init__(self):
        self.is_thinking = False
        self.thinking_text = ""
        self.thinking_start_time = 0
        self.note = ""
        self.width = Terminal.get_size()[0]
        self.animation_thread = None
        self.animation_running = False
        self.frame_index = 0
        # Claude Code style: simple dots animation
        self.frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def start(self, text: str = "Thinking", note: str = ""):
        """Start thinking animation"""
        self.is_thinking = True
        self.thinking_text = text
        self.thinking_start_time = time.time()
        self.note = note
        self.animation_running = True
        self.animation_thread = threading.Thread(target=self._animate, daemon=True)
        self.animation_thread.start()

    def stop(self):
        """Stop thinking animation"""
        self.animation_running = False
        self.is_thinking = False
        if self.animation_thread:
            self.animation_thread.join(timeout=0.5)
        self.note = ""

    def _animate(self):
        """Animation thread"""
        while self.animation_running:
            self.frame_index = (self.frame_index + 1) % len(self.frames)
            time.sleep(0.08)

    def render(self, y: int):
        """Render thinking indicator at position y"""
        if not self.is_thinking:
            Terminal.move_to(1, y)
            sys.stdout.write("\033[K")
            sys.stdout.flush()
            return

        # Calculate elapsed time
        elapsed = int(time.time() - self.thinking_start_time)
        icon = self.frames[self.frame_index % len(self.frames)]

        # Claude Code style: simple "Thinking for Xs..."
        thinking_line = f"{Colors.YELLOW}{icon} {self.thinking_text} for {elapsed}s...{Colors.RESET}"
        if self.note:
            thinking_line += f" {Colors.DIM}({self.note}){Colors.RESET}"

        # Truncate if too long
        if len(thinking_line) > self.width - 2:
            thinking_line = thinking_line[:self.width - 5] + "..."

        # Render
        Terminal.move_to(1, y)
        sys.stdout.write(thinking_line)
        sys.stdout.write("\033[K")
        sys.stdout.flush()

    def update(self, y: int):
        """Update thinking indicator (call in loop)"""
        if self.is_thinking:
            self.render(y)


class MessageArea:
    """Message area - Claude Code style (inline messages)"""

    def __init__(self, max_lines: int = 100):
        self.max_lines = max_lines
        self.messages: List[Dict] = []
        self.width = Terminal.get_size()[0]

    def add_message(self, text: str, role: str = "system", icon: str = ""):
        """Add a message"""
        self.messages.append({
            "text": text,
            "role": role,
            "icon": icon,
            "timestamp": time.time()
        })

        # Keep only last N messages
        if len(self.messages) > self.max_lines:
            self.messages = self.messages[-self.max_lines:]

    def clear(self):
        """Clear messages"""
        self.messages.clear()

    def render(self, y: int, height: int = None):
        """Render messages at position y"""
        if height is None:
            height = self.max_lines

        width = self.width

        # Clear area
        for i in range(height):
            Terminal.move_to(1, y + i)
            sys.stdout.write("\033[K")

        # Render messages (last N)
        visible = self.messages[-height:]
        for i, msg in enumerate(visible):
            if i >= height:
                break

            Terminal.move_to(1, y + i)

            text = msg["text"]
            role = msg["role"]
            icon = msg["icon"]

            # Claude Code style: simple colored text with optional icon
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
                color = Colors.WHITE
                if not icon:
                    icon = "•"

            # Format line
            if icon:
                line = f" {icon} {color}{text}{Colors.RESET}"
            else:
                line = f"   {color}{text}{Colors.RESET}"

            # Truncate if too long
            max_width = width - 2
            if len(line) > max_width:
                line = line[:max_width - 3] + "..."

            sys.stdout.write(line)

        # Fill empty lines
        for i in range(len(visible), height):
            Terminal.move_to(1, y + i)
            sys.stdout.write(" " * width)

        sys.stdout.flush()


class InputArea:
    """Input area - Claude Code style (simple prompt)"""

    def __init__(self, prompt: str = "kamu> "):
        self.prompt = prompt
        self.buffer = ""
        self.cursor_pos = 0
        self.width = Terminal.get_size()[0]
        self.history: List[str] = []
        self.history_index = -1

    def render(self, y: int):
        """Render input area at position y"""
        width = self.width

        # Clear line
        Terminal.move_to(1, y)
        sys.stdout.write("\033[K")

        # Claude Code style: simple green prompt
        sys.stdout.write(f"{Colors.GREEN}{Colors.BOLD}{self.prompt}{Colors.RESET}")

        # Render buffer
        sys.stdout.write(self.buffer)

        # Calculate cursor position
        cursor_x = len(self.prompt) + self.cursor_pos + 1
        Terminal.move_to(cursor_x, y)

        sys.stdout.flush()

    def get_input(self, input_y: int = None) -> str:
        """Get input from user (blocking)"""
        # Check if stdin is a TTY
        if not sys.stdin.isatty():
            try:
                return input(f"{self.prompt}")
            except (EOFError, KeyboardInterrupt):
                raise

        import tty
        import termios

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        # Get terminal size
        width, height = Terminal.get_size()
        if input_y is None:
            input_y = height - 1

        try:
            tty.setcbreak(fd)
            self.buffer = ""
            self.cursor_pos = 0

            # Initial render
            self.render(input_y)

            while True:
                ch = sys.stdin.read(1)

                if ch in ("\r", "\n"):
                    # Enter - add to history and return
                    if self.buffer:
                        self.history.append(self.buffer)
                    return self.buffer
                elif ch == "\x03":
                    # Ctrl+C
                    raise KeyboardInterrupt
                elif ch == "\x04":
                    # Ctrl+D
                    if not self.buffer:
                        raise EOFError
                elif ch in ("\x7f", "\x08"):
                    # Backspace
                    if self.cursor_pos > 0:
                        self.buffer = self.buffer[:self.cursor_pos - 1] + self.buffer[self.cursor_pos:]
                        self.cursor_pos -= 1
                elif ch == "\x1b":
                    # Escape sequence
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        # Up arrow - history
                        if self.history and self.history_index < len(self.history) - 1:
                            self.history_index += 1
                            self.buffer = self.history[-(self.history_index + 1)]
                            self.cursor_pos = len(self.buffer)
                    elif seq == "[B":
                        # Down arrow - history
                        if self.history_index > 0:
                            self.history_index -= 1
                            self.buffer = self.history[-(self.history_index + 1)]
                            self.cursor_pos = len(self.buffer)
                        elif self.history_index == 0:
                            self.history_index = -1
                            self.buffer = ""
                            self.cursor_pos = 0
                    elif seq == "[C":
                        # Right arrow
                        if self.cursor_pos < len(self.buffer):
                            self.cursor_pos += 1
                    elif seq == "[D":
                        # Left arrow
                        if self.cursor_pos > 0:
                            self.cursor_pos -= 1
                elif ch == "\t":
                    # Tab - autocomplete (TODO)
                    pass
                elif ch and ch.isprintable():
                    # Printable character
                    self.buffer = self.buffer[:self.cursor_pos] + ch + self.buffer[self.cursor_pos:]
                    self.cursor_pos += 1

                # Re-render after each keypress
                self.render(input_y)

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# =============================================================================
# Main TUI Class (Claude Code Style)
# =============================================================================
class AizuTUI:
    """Modern TUI for AIZU-CLI (Claude Code Style)"""

    def __init__(self, workspace_path: str, backend: str = "", model: str = ""):
        self.workspace_path = workspace_path
        self.backend = backend
        self.model = model

        # Calculate layout dimensions
        self.width, self.height = Terminal.get_size()

        # Components
        self.header = Header(workspace_path, backend, model)
        self.thinking = ThinkingIndicator()
        self.messages = MessageArea(max_lines=max(self.height - 6, 10))
        self.input_area = InputArea()

        # State
        self.running = False

        # Calculate layout positions
        self.header_y = 1
        self.separator_y = 2
        self.thinking_y = 3
        self.messages_y = 4
        self.input_y = self.height - 1

    def setup(self):
        """Setup TUI layout"""
        Terminal.clear()

        # Render header
        self.header.render(y=self.header_y)

        # Render separator
        Terminal.move_to(1, self.separator_y)
        sys.stdout.write("─" * self.width)
        sys.stdout.flush()

        # Render thinking indicator
        self.thinking.render(y=self.thinking_y)

        # Render messages area
        self.messages.render(y=self.messages_y, height=self.input_y - self.messages_y - 1)

        # Render input area
        self.input_area.render(y=self.input_y)

        sys.stdout.flush()

    def update_header(self, backend: str = None, model: str = None):
        """Update header info"""
        if backend:
            self.backend = backend
        if model:
            self.model = model

        self.header.backend = self.backend
        self.header.model = self.model
        self.header.render(y=self.header_y)

    def start_thinking(self, text: str = "Thinking", note: str = ""):
        """Start thinking animation"""
        self.thinking.start(text, note)
        # Start update thread
        threading.Thread(target=self._update_thinking, daemon=True).start()

    def _update_thinking(self):
        """Update thinking indicator in background"""
        while self.thinking.is_thinking:
            self.thinking.update(y=self.thinking_y)
            time.sleep(0.1)

    def stop_thinking(self):
        """Stop thinking animation"""
        self.thinking.stop()
        self.thinking.render(y=self.thinking_y)

    def add_message(self, text: str, role: str = "system", icon: str = ""):
        """Add message to message area"""
        self.messages.add_message(text, role=role, icon=icon)
        self._render_messages()

    def _render_messages(self):
        """Render messages area"""
        available_height = self.input_y - self.messages_y - 1
        self.messages.render(y=self.messages_y, height=available_height)

    def add_user_message(self, text: str):
        """Add user message"""
        # Split into multiple lines if too long
        lines = text.split('\n')
        for line in lines:
            if line.strip():
                # Wrap long lines
                while len(line) > 70:
                    break_at = line[:70].rfind(' ')
                    if break_at == -1:
                        break_at = 70
                    self.add_message(line[:break_at], role="user")
                    line = line[break_at:].lstrip()
                if line:
                    self.add_message(line, role="user")

    def add_assistant_message(self, text: str):
        """Add assistant message"""
        # Split into multiple lines if too long
        lines = text.split('\n')
        for line in lines:
            if line.strip():
                # Wrap long lines
                while len(line) > 70:
                    break_at = line[:70].rfind(' ')
                    if break_at == -1:
                        break_at = 70
                    self.add_message(line[:break_at], role="assistant")
                    line = line[break_at:].lstrip()
                if line:
                    self.add_message(line, role="assistant")

    def add_error(self, text: str):
        """Add error message"""
        self.add_message(text, role="error")

    def add_success(self, text: str):
        """Add success message"""
        self.add_message(text, role="success")

    def add_info(self, text: str):
        """Add info message"""
        self.add_message(text, role="info")

    def add_warning(self, text: str):
        """Add warning message"""
        self.add_message(text, role="warning")

    def add_tool_execution(self, tool_name: str, args: dict = None):
        """Add tool execution log"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"

        self.add_message(f"Running: {tool_name}{args_str}", role="tool")

    def add_thinking(self, text: str):
        """Add thinking message"""
        self.add_message(text, role="info", icon="✻")

    def show_plan_mode(self, enabled: bool):
        """Show plan mode indicator in header."""
        self.header.plan_mode = enabled
        self.header.render(y=self.header_y)

    def get_input(self) -> str:
        """Get user input"""
        return self.input_area.get_input(self.input_y)

    def cleanup(self):
        """Cleanup TUI"""
        Terminal.show_cursor()
        Terminal.move_to(1, self.height)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def print_response(self, text: str):
        """Print assistant response"""
        self.add_assistant_message(text)


# =============================================================================
# Streaming TUI
# =============================================================================
class StreamingTUI:
    """TUI for streaming responses"""

    def __init__(self, tui: AizuTUI):
        self.tui = tui
        self.buffer = ""

    def on_token(self, token: str):
        """Called for each streaming token"""
        self.buffer += token
        sys.stdout.write(token)
        sys.stdout.flush()

    def on_complete(self):
        """Called when streaming is complete"""
        if self.buffer.strip():
            self.tui.add_assistant_message(self.buffer)
        self.buffer = ""


# =============================================================================
# Example Usage
# =============================================================================
def example_tui():
    """Example usage of TUI"""
    import os

    # Create TUI
    tui = AizuTUI(
        workspace_path=os.getcwd(),
        backend="groq",
        model="llama-3.3-70b-versatile"
    )

    try:
        # Setup
        tui.setup()

        # Add some messages
        tui.add_info("AIZU-CLI started")
        tui.start_thinking("Processing", "ctrl+o to expand")
        time.sleep(2)
        tui.stop_thinking()
        tui.add_tool_execution("read_file", {"path": "test.py"})
        tui.add_success("File loaded")

        # Get input
        while True:
            try:
                user_input = tui.get_input()
                if user_input.lower() in ("/quit", "/exit", "/keluar"):
                    break

                # Add user message
                tui.add_user_message(user_input)

                # Simulate response
                tui.start_thinking("Generating", "ctrl+o to expand")
                time.sleep(1)
                tui.stop_thinking()
                tui.add_assistant_message(f"Response to: {user_input}")

            except KeyboardInterrupt:
                break
            except EOFError:
                break

    finally:
        tui.cleanup()


if __name__ == "__main__":
    example_tui()
