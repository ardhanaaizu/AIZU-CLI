"""
AIZU-CLI Modern TUI System (Claude Code Style)
===============================================

Text User Interface modern seperti Claude Code.
Layout:
┌─────────────────────────────────────────────────────────────┐
│ 📁 /path/to/project                        groq │ model    │  ← Header
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Thinking for 3s... (ctrl+o to expand)                       │  ← Thinking
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ℹ️  Loaded 9 plugins                                        │  ← Content
│ ✻ Running tool: read_file                                  │
│ ✅ File loaded                                              │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│ Phase 1: ✅ Buat plugins.py                                │  ← Tasks
│ Phase 2: ✅ Tambahkan HookManager                          │
│ Phase 3: ⏳ Integrasi ke agent.py                          │
│ Phase 4: □ Buat example plugins                            │
├─────────────────────────────────────────────────────────────┤
│ kamu> _                                                    │  ← Input
└─────────────────────────────────────────────────────────────┘
"""

import os
import sys
import time
import threading
from typing import List, Dict, Optional


# =============================================================================
# ANSI Colors
# =============================================================================
class Colors:
    """ANSI color codes"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Foreground
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    # Background
    BG_BLACK = "\033[40m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_MAGENTA = "\033[45m"
    BG_CYAN = "\033[46m"
    BG_WHITE = "\033[47m"


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
# TUI Components
# =============================================================================
class Header:
    """Header component - shows workspace info"""

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

        # Add plan mode indicator
        if self.plan_mode:
            right = f"📋 PLAN MODE | {right}"

        # Calculate padding
        padding = width - len(left) - len(right) - 4
        if padding < 0:
            padding = 0

        # Render
        Terminal.move_to(1, y)
        if self.plan_mode:
            sys.stdout.write(f"{Colors.BG_YELLOW}{Colors.BLACK}{Colors.BOLD}")
        else:
            sys.stdout.write(f"{Colors.BG_BLUE}{Colors.WHITE}{Colors.BOLD}")
        sys.stdout.write(f" {left}")
        sys.stdout.write(" " * padding)
        sys.stdout.write(f"{right} ")
        sys.stdout.write(f"{Colors.RESET}")

        # Fill rest of line
        if self.plan_mode:
            sys.stdout.write(f"{Colors.BG_YELLOW}{Colors.BLACK}")
        else:
            sys.stdout.write(f"{Colors.BG_BLUE}{Colors.WHITE}")
        sys.stdout.write(" " * (width - len(left) - len(right) - 2))
        sys.stdout.write(f"{Colors.RESET}")

        sys.stdout.flush()


class ThinkingIndicator:
    """Thinking indicator - shows thinking status"""

    def __init__(self):
        self.is_thinking = False
        self.thinking_text = ""
        self.thinking_start_time = 0
        self.note = ""
        self.width = Terminal.get_size()[0]
        self.animation_thread = None
        self.animation_running = False
        self.frames = ["✻", "✻.", "✻..", "✻..."]
        self.frame_index = 0

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
            time.sleep(0.3)

    def render(self, y: int):
        """Render thinking indicator at position y"""
        if not self.is_thinking:
            # Clear the line
            Terminal.move_to(1, y)
            sys.stdout.write("\033[K")
            sys.stdout.flush()
            return

        # Calculate elapsed time
        elapsed = int(time.time() - self.thinking_start_time)
        icon = self.frames[self.frame_index % len(self.frames)]

        # Build thinking text
        thinking_line = f"{icon} {self.thinking_text} for {elapsed}s..."
        if self.note:
            thinking_line += f" ({self.note})"

        # Truncate if too long
        if len(thinking_line) > self.width - 2:
            thinking_line = thinking_line[:self.width - 5] + "..."

        # Render
        Terminal.move_to(1, y)
        sys.stdout.write(f"{Colors.YELLOW}{Colors.BOLD}{thinking_line}{Colors.RESET}")
        sys.stdout.write("\033[K")  # Clear rest of line
        sys.stdout.flush()

    def update(self, y: int):
        """Update thinking indicator (call in loop)"""
        if self.is_thinking:
            self.render(y)


class ContentArea:
    """Content area component - shows tasks, animations, logs"""

    def __init__(self, max_lines: int = 10):
        self.max_lines = max_lines
        self.lines: List[Dict] = []
        self.width = Terminal.get_size()[0]

    def add_line(self, text: str, style: str = "normal", icon: str = ""):
        """Add a line to content area"""
        if len(self.lines) >= self.max_lines:
            self.lines.pop(0)

        self.lines.append({
            "text": text,
            "style": style,
            "icon": icon,
            "timestamp": time.time()
        })

    def clear(self):
        """Clear content area"""
        self.lines.clear()

    def render(self, y: int = 4, height: int = None):
        """Render content area at position y"""
        if height is None:
            height = self.max_lines

        width = self.width

        # Clear area
        for i in range(height):
            Terminal.move_to(1, y + i)
            sys.stdout.write("\033[K")

        # Render lines
        for i, line in enumerate(self.lines[-height:]):
            if i >= height:
                break

            Terminal.move_to(1, y + i)

            # Style mapping
            style_map = {
                "normal": Colors.WHITE,
                "success": Colors.GREEN,
                "warning": Colors.YELLOW,
                "error": Colors.RED,
                "info": Colors.CYAN,
                "dim": Colors.DIM,
                "thinking": Colors.YELLOW,
                "tool": Colors.MAGENTA,
                "user": Colors.GREEN,
                "assistant": Colors.CYAN,
                "diff-add": Colors.GREEN,
                "diff-remove": Colors.RED,
                "diff-info": Colors.CYAN,
            }

            color = style_map.get(line["style"], Colors.WHITE)
            icon = line["icon"]

            # Truncate text if too long
            text = line["text"]
            available_width = width - 4
            if icon:
                available_width -= 2
            if len(text) > available_width:
                text = text[:available_width - 3] + "..."

            # Render
            if icon:
                sys.stdout.write(f" {icon} {color}{text}{Colors.RESET}")
            else:
                sys.stdout.write(f"   {color}{text}{Colors.RESET}")

            # Fill rest of line
            current_len = len(text) + (2 if icon else 0)
            padding = width - current_len - 3
            if padding > 0:
                sys.stdout.write(" " * padding)

        # Fill empty lines
        for i in range(len(self.lines[-height:]), height):
            Terminal.move_to(1, y + i)
            sys.stdout.write(" " * width)

        sys.stdout.flush()


class TaskList:
    """Task list component - shows phases/tasks"""

    def __init__(self):
        self.tasks: List[Dict] = []
        self.width = Terminal.get_size()[0]

    def add_task(self, name: str, status: str = "pending"):
        """Add a task

        Status: pending, in_progress, completed, error
        """
        self.tasks.append({
            "name": name,
            "status": status,
            "timestamp": time.time()
        })

    def update_task(self, name: str, status: str):
        """Update task status"""
        for task in self.tasks:
            if task["name"] == name:
                task["status"] = status
                break

    def clear(self):
        """Clear tasks"""
        self.tasks.clear()

    def render(self, y: int):
        """Render task list at position y"""
        width = self.width

        # Clear area
        for i in range(len(self.tasks) + 1):
            Terminal.move_to(1, y + i)
            sys.stdout.write("\033[K")

        if not self.tasks:
            return

        # Render tasks
        for i, task in enumerate(self.tasks):
            Terminal.move_to(1, y + i)

            # Status icon
            status_icons = {
                "pending": f"{Colors.DIM}□{Colors.RESET}",
                "in_progress": f"{Colors.YELLOW}⏳{Colors.RESET}",
                "completed": f"{Colors.GREEN}✅{Colors.RESET}",
                "error": f"{Colors.RED}❌{Colors.RESET}",
            }

            icon = status_icons.get(task["status"], "□")
            name = task["name"]

            # Truncate if too long
            if len(name) > width - 6:
                name = name[:width - 9] + "..."

            # Render
            sys.stdout.write(f" {icon} {name}")

        sys.stdout.flush()


class InputArea:
    """Input area component - chat input"""

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

        # Render prompt
        sys.stdout.write(f"{Colors.GREEN}{Colors.BOLD}{self.prompt}{Colors.RESET}")

        # Render buffer
        sys.stdout.write(self.buffer)

        # Calculate cursor position
        cursor_x = len(self.prompt) + self.cursor_pos + 1
        Terminal.move_to(cursor_x, y)

        sys.stdout.flush()

    def get_input(self, input_y: int = None) -> str:
        """Get input from user (blocking)

        Args:
            input_y: Y position for input area (default: bottom of screen)
        """
        # Check if stdin is a TTY
        if not sys.stdin.isatty():
            # Not a TTY - use simple input()
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
                    # Tab - autocomplete
                    pass  # TODO: Implement autocomplete
                elif ch and ch.isprintable():
                    # Printable character
                    self.buffer = self.buffer[:self.cursor_pos] + ch + self.buffer[self.cursor_pos:]
                    self.cursor_pos += 1

                # Re-render after each keypress
                self.render(input_y)

        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# =============================================================================
# Main TUI Class
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
        self.content = ContentArea(max_lines=max(self.height - 12, 5))
        self.task_list = TaskList()
        self.input_area = InputArea()

        # State
        self.running = False

    def setup(self):
        """Setup TUI layout"""
        Terminal.clear()
        Terminal.hide_cursor()

        # Render header
        self.header.render(y=1)

        # Render separator
        Terminal.move_to(1, 2)
        sys.stdout.write("─" * self.width)
        sys.stdout.flush()

        # Render thinking indicator (y=3)
        self.thinking.render(y=3)

        # Render separator
        Terminal.move_to(1, 4)
        sys.stdout.write("─" * self.width)
        sys.stdout.flush()

        # Render content area (y=5)
        self.content.render(y=5)

        # Calculate task list position
        task_y = 5 + self.content.max_lines
        Terminal.move_to(1, task_y)
        sys.stdout.write("─" * self.width)
        sys.stdout.flush()

        # Render task list
        self.task_list.render(y=task_y + 1)

        # Render separator
        input_y = self.height - 1
        Terminal.move_to(1, input_y - 1)
        sys.stdout.write("─" * self.width)
        sys.stdout.flush()

        # Render input area
        self.input_area.render(input_y)

        sys.stdout.flush()

    def update_header(self, backend: str = None, model: str = None):
        """Update header info"""
        if backend:
            self.backend = backend
        if model:
            self.model = model

        self.header.backend = self.backend
        self.header.model = self.model
        self.header.render(y=1)

    def start_thinking(self, text: str = "Thinking", note: str = ""):
        """Start thinking animation"""
        self.thinking.start(text, note)
        # Start update thread
        threading.Thread(target=self._update_thinking, daemon=True).start()

    def _update_thinking(self):
        """Update thinking indicator in background"""
        while self.thinking.is_thinking:
            self.thinking.update(y=3)
            time.sleep(0.3)

    def stop_thinking(self):
        """Stop thinking animation"""
        self.thinking.stop()
        self.thinking.render(y=3)

    def add_message(self, text: str, style: str = "normal", icon: str = ""):
        """Add message to content area"""
        self.content.add_line(text, style=style, icon=icon)
        self.content.render(y=5)

    def add_user_message(self, text: str):
        """Add user message"""
        self.content.add_line(text, style="user", icon="👤")
        self.content.render(y=5)

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
                    self.content.add_line(line[:break_at], style="assistant", icon="🤖")
                    line = line[break_at:].lstrip()
                if line:
                    self.content.add_line(line, style="assistant", icon="🤖")
        self.content.render(y=5)

    def add_error(self, text: str):
        """Add error message"""
        self.content.add_line(text, style="error", icon="❌")
        self.content.render(y=5)

    def add_success(self, text: str):
        """Add success message"""
        self.content.add_line(text, style="success", icon="✅")
        self.content.render(y=5)

    def add_info(self, text: str):
        """Add info message"""
        self.content.add_line(text, style="info", icon="ℹ️")
        self.content.render(y=5)

    def add_tool_execution(self, tool_name: str, args: dict = None):
        """Add tool execution log"""
        args_str = ""
        if args:
            if "path" in args:
                args_str = f" ({args['path']})"
            elif "command" in args:
                args_str = f" ({args['command'][:30]}...)"

        self.content.add_line(f"Running {tool_name}{args_str}", style="tool", icon="🔧")
        self.content.render(y=5)

    def add_thinking(self, text: str):
        """Add thinking message"""
        self.content.add_line(text, style="thinking", icon="✻")
        self.content.render(y=5)

    def add_task(self, name: str, status: str = "pending"):
        """Add task to task list"""
        self.task_list.add_task(name, status)
        task_y = 5 + self.content.max_lines + 1
        self.task_list.render(y=task_y)

    def update_task(self, name: str, status: str):
        """Update task status"""
        self.task_list.update_task(name, status)
        task_y = 5 + self.content.max_lines + 1
        self.task_list.render(y=task_y)

    def add_warning(self, text: str):
        """Add warning message"""
        self.content.add_line(text, style="warning", icon="⚠️")
        self.content.render(y=5)

    def show_plan_mode(self, enabled: bool):
        """Show plan mode indicator in header."""
        if enabled:
            self.header.plan_mode = True
        else:
            self.header.plan_mode = False
        self.header.render(y=1)

    def show_task_summary(self, task_mgr):
        """Show task summary in the task list area."""
        if task_mgr:
            summary = task_mgr.get_summary()
            tasks = task_mgr.list_tasks()
            # Update internal task list
            self.task_list.tasks = []
            for task in tasks[:10]:  # Show max 10 tasks
                status_map = {
                    "pending": "pending",
                    "in_progress": "in_progress",
                    "completed": "completed"
                }
                self.task_list.add_task(
                    f"#{task['id']}: {task['subject'][:40]}",
                    status_map.get(task["status"], "pending")
                )
            task_y = 5 + self.content.max_lines + 1
            self.task_list.render(y=task_y)

    def show_agents_status(self, agents_text: str):
        """Show background agents status."""
        if agents_text and agents_text != "Tidak ada background agents.":
            self.add_info(f"Background agents:\n{agents_text}")

    def get_input(self) -> str:
        """Get user input"""
        input_y = self.height - 1
        return self.input_area.get_input(input_y)

    def cleanup(self):
        """Cleanup TUI"""
        Terminal.show_cursor()
        Terminal.move_to(1, self.height)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def print_response(self, text: str):
        """Print assistant response in content area"""
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

        # Add tasks
        tui.add_task("Phase 1: Setup", "completed")
        tui.add_task("Phase 2: Implement", "in_progress")
        tui.add_task("Phase 3: Test", "pending")

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
