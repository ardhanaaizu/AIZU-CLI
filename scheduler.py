"""
AIZU-CLI Scheduler
==================

Cron-based task scheduling.
Schedule prompts untuk dijalankan secara periodik.

Constraint: Zero external dependencies (hanya Python stdlib)
"""

import os
import re
import json
import time
import threading
from datetime import datetime


# =============================================================================
# Cron Parser (Simple 5-field)
# =============================================================================

class CronExpression:
    """
    Simple cron expression parser.
    Format: minute hour day-of-month month day-of-week

    Supported:
    - * (any value)
    - */N (every N)
    - N (specific value)
    - N,M (list)
    - N-M (range)
    """

    def __init__(self, expression):
        """
        Args:
            expression: Cron expression string (5 fields)
        """
        self.expression = expression.strip()
        self.fields = self._parse(self.expression)

    def _parse(self, expr):
        """Parse cron expression."""
        parts = expr.split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression harus 5 field, dapat {len(parts)}: {expr}")

        field_names = ['minute', 'hour', 'day', 'month', 'weekday']
        result = {}

        for name, value in zip(field_names, parts):
            result[name] = self._parse_field(value, name)

        return result

    def _parse_field(self, value, field_name):
        """Parse satu cron field."""
        # Any value
        if value == '*':
            return None  # None means any

        # Every N
        match = re.match(r'\*/(\d+)', value)
        if match:
            return {'every': int(match.group(1))}

        # List
        if ',' in value:
            return {'list': [int(v) for v in value.split(',')]}

        # Range
        if '-' in value:
            start, end = value.split('-')
            return {'range': (int(start), int(end))}

        # Specific value
        try:
            return {'value': int(value)}
        except ValueError:
            raise ValueError(f"Invalid cron field '{value}' for {field_name}")

    def matches(self, dt=None):
        """
        Check apakah datetime match dengan cron expression.

        Args:
            dt: datetime object (default: now)

        Returns:
            bool: True jika match
        """
        if dt is None:
            dt = datetime.now()

        checks = [
            (self.fields['minute'], dt.minute),
            (self.fields['hour'], dt.hour),
            (self.fields['day'], dt.day),
            (self.fields['month'], dt.month),
            (self.fields['weekday'], dt.weekday()),
        ]

        for field, value in checks:
            if not self._field_matches(field, value):
                return False

        return True

    def _field_matches(self, field, value):
        """Check apakah value match dengan field definition."""
        if field is None:
            return True  # Any value

        if 'value' in field:
            return value == field['value']

        if 'every' in field:
            return value % field['every'] == 0

        if 'list' in field:
            return value in field['list']

        if 'range' in field:
            start, end = field['range']
            return start <= value <= end

        return False

    def __str__(self):
        return self.expression


# =============================================================================
# Scheduled Task
# =============================================================================

class ScheduledTask:
    """Represents a scheduled task."""

    def __init__(self, task_id, cron_expr, prompt, name="", enabled=True):
        """
        Args:
            task_id: Unique task ID
            cron_expr: Cron expression string
            prompt: Prompt to execute
            name: Human-readable name
            enabled: Whether task is enabled
        """
        self.id = task_id
        self.cron = CronExpression(cron_expr)
        self.cron_str = cron_expr
        self.prompt = prompt
        self.name = name or f"Task {task_id}"
        self.enabled = enabled
        self.last_run = None
        self.run_count = 0

    def should_run(self, dt=None):
        """Check apakah task harus dijalankan sekarang."""
        if not self.enabled:
            return False
        return self.cron.matches(dt)

    def mark_ran(self):
        """Mark bahwa task sudah dijalankan."""
        self.last_run = datetime.now().isoformat()
        self.run_count += 1

    def to_dict(self):
        """Convert ke dict untuk serialisasi."""
        return {
            "id": self.id,
            "cron": self.cron_str,
            "prompt": self.prompt,
            "name": self.name,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "run_count": self.run_count,
        }

    @classmethod
    def from_dict(cls, data):
        """Buat ScheduledTask dari dict."""
        task = cls(
            task_id=data['id'],
            cron_expr=data['cron'],
            prompt=data['prompt'],
            name=data.get('name', ''),
            enabled=data.get('enabled', True),
        )
        task.last_run = data.get('last_run')
        task.run_count = data.get('run_count', 0)
        return task


# =============================================================================
# Scheduler Manager
# =============================================================================

class Scheduler:
    """
    Cron-based scheduler untuk AIZU-CLI.

    Menjalankan prompt secara periodik berdasarkan cron expression.
    """

    def __init__(self, config_path=None):
        """
        Args:
            config_path: Path ke config file (default: ~/.aizu/scheduled.json)
        """
        self.config_path = config_path or os.path.expanduser("~/.aizu/scheduled.json")
        self.tasks = {}
        self._running = False
        self._thread = None
        self._callback = None  # Callback function untuk execute prompt
        self._load()

    def _load(self):
        """Load tasks dari file."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for task_data in data.get('tasks', []):
                        task = ScheduledTask.from_dict(task_data)
                        self.tasks[task.id] = task
            except Exception as e:
                print(f"[Scheduler] Error loading: {e}")

    def _save(self):
        """Simpan tasks ke file."""
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        data = {
            "tasks": [t.to_dict() for t in self.tasks.values()]
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def add(self, cron_expr, prompt, name=""):
        """
        Tambah scheduled task baru.

        Args:
            cron_expr: Cron expression (5 field)
            prompt: Prompt yang akan dijalankan
            name: Nama task (opsional)

        Returns:
            ScheduledTask: Task yang dibuat
        """
        # Validate cron expression
        try:
            CronExpression(cron_expr)
        except ValueError as e:
            raise ValueError(f"Invalid cron expression: {e}")

        # Generate ID
        task_id = f"task-{int(time.time())}"

        # Create task
        task = ScheduledTask(task_id, cron_expr, prompt, name)
        self.tasks[task_id] = task
        self._save()

        return task

    def remove(self, task_id):
        """
        Hapus scheduled task.

        Args:
            task_id: Task ID

        Returns:
            bool: True jika berhasil
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save()
            return True
        return False

    def enable(self, task_id):
        """Enable task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = True
            self._save()
            return True
        return False

    def disable(self, task_id):
        """Disable task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = False
            self._save()
            return True
        return False

    def list_tasks(self):
        """
        List semua scheduled tasks.

        Returns:
            list: List of ScheduledTask
        """
        return list(self.tasks.values())

    def get(self, task_id):
        """Get task by ID."""
        return self.tasks.get(task_id)

    def start(self, callback, check_interval=60):
        """
        Start scheduler background thread.

        Args:
            callback: Function(prompt) yang dipanggil saat task waktunya jalan
            check_interval: Interval pengecekan dalam detik (default: 60)
        """
        if self._running:
            return

        self._callback = callback
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(check_interval,),
            daemon=True
        )
        self._thread.start()

    def stop(self):
        """Stop scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

    def _run_loop(self, check_interval):
        """Main scheduler loop."""
        last_check_minute = -1

        while self._running:
            now = datetime.now()

            # Only check once per minute
            if now.minute != last_check_minute:
                last_check_minute = now.minute

                for task in self.tasks.values():
                    if task.should_run(now):
                        # Check if already ran this minute
                        if task.last_run:
                            last_run_dt = datetime.fromisoformat(task.last_run)
                            if last_run_dt.minute == now.minute and last_run_dt.hour == now.hour:
                                continue

                        # Execute task
                        try:
                            if self._callback:
                                self._callback(task.prompt)
                            task.mark_ran()
                        except Exception as e:
                            print(f"[Scheduler] Error executing {task.name}: {e}")

                # Save after checking
                self._save()

            time.sleep(check_interval)

    def format_list(self):
        """Format task list untuk display."""
        tasks = self.list_tasks()
        if not tasks:
            return "Tidak ada scheduled tasks."

        lines = ["⏰ Scheduled Tasks:"]
        for task in tasks:
            status = "✅" if task.enabled else "⏸️"
            name = task.name or task.prompt[:30]
            cron = task.cron_str
            runs = task.run_count
            last = task.last_run[:16] if task.last_run else "never"

            lines.append(f"  {status} [{task.id}] {name}")
            lines.append(f"     Cron: {cron} | Runs: {runs} | Last: {last}")

        return "\n".join(lines)


# =============================================================================
# Cron Expression Helpers
# =============================================================================

def parse_cron_shortcut(text):
    """
    Parse cron shortcut ke full expression.

    Supported shortcuts:
    - @yearly atau @annually → 0 0 1 1 *
    - @monthly → 0 0 1 * *
    - @weekly → 0 0 * * 0
    - @daily atau @midnight → 0 0 * * *
    - @hourly → 0 * * * *
    - @every Nm → */N * * * * (every N minutes)
    - @every Nh → * */N * * * (every N hours)
    """
    shortcuts = {
        '@yearly': '0 0 1 1 *',
        '@annually': '0 0 1 1 *',
        '@monthly': '0 0 1 * *',
        '@weekly': '0 0 * * 0',
        '@daily': '0 0 * * *',
        '@midnight': '0 0 * * *',
        '@hourly': '0 * * * *',
    }

    text = text.strip().lower()

    if text in shortcuts:
        return shortcuts[text]

    # @every Nm or @every Nh
    match = re.match(r'@every (\d+)(m|h)', text)
    if match:
        num = int(match.group(1))
        unit = match.group(2)
        if unit == 'm':
            return f'*/{num} * * * *'
        elif unit == 'h':
            return f'0 */{num} * * *'

    # Return as-is (assume it's a cron expression)
    return text


# =============================================================================
# Singleton Instance
# =============================================================================

_global_scheduler = None


def get_scheduler(config_path=None):
    """Get atau buat global Scheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = Scheduler(config_path)
    return _global_scheduler


def reset_scheduler():
    """Reset global Scheduler (untuk testing)."""
    global _global_scheduler
    _global_scheduler = None
