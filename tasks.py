"""
AIZU-CLI Task Management System
Structured task tracking dengan ID, status, dependencies.
Mirip Claude Code's TaskCreate/TaskUpdate/TaskList/TaskGet.
"""

import json
import os
import time
from datetime import datetime


TASKS_DIR = os.path.expanduser("~/.aizu")
TASKS_FILE = os.path.join(TASKS_DIR, "tasks.json")


class TaskManager:
    """Manages tasks with status tracking and dependencies."""

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_DELETED = "deleted"

    VALID_STATUSES = [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_DELETED]

    def __init__(self, session_id=None):
        self.session_id = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.tasks = {}
        self._next_id = 1
        self._load()

    def _load(self):
        """Load tasks from file."""
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Load tasks for current session or all sessions
                    if self.session_id in data.get("sessions", {}):
                        session_data = data["sessions"][self.session_id]
                        self.tasks = session_data.get("tasks", {})
                        self._next_id = session_data.get("next_id", 1)
                    else:
                        self.tasks = {}
                        self._next_id = 1
            except (json.JSONDecodeError, IOError):
                self.tasks = {}
                self._next_id = 1

    def _save(self):
        """Save tasks to file."""
        os.makedirs(TASKS_DIR, exist_ok=True)

        # Load existing data
        data = {"sessions": {}}
        if os.path.exists(TASKS_FILE):
            try:
                with open(TASKS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError):
                data = {"sessions": {}}

        # Update current session
        if "sessions" not in data:
            data["sessions"] = {}

        data["sessions"][self.session_id] = {
            "tasks": self.tasks,
            "next_id": self._next_id,
            "updated": datetime.now().isoformat()
        }

        with open(TASKS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def create(self, subject, description="", active_form="", metadata=None):
        """Create a new task.

        Args:
            subject: Brief title for the task
            description: Detailed requirements
            activeForm: Present continuous form shown when in_progress
            metadata: Optional dict of metadata

        Returns:
            dict: Created task with 'id' field
        """
        task_id = str(self._next_id)
        self._next_id += 1

        task = {
            "id": task_id,
            "subject": subject,
            "description": description,
            "active_form": active_form or subject,
            "status": self.STATUS_PENDING,
            "blocks": [],
            "blocked_by": [],
            "metadata": metadata or {},
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat()
        }

        self.tasks[task_id] = task
        self._save()
        return task

    def get(self, task_id):
        """Get a task by ID.

        Args:
            task_id: The task ID string

        Returns:
            dict or None: The task if found
        """
        return self.tasks.get(str(task_id))

    def update(self, task_id, **kwargs):
        """Update a task.

        Args:
            task_id: The task ID
            **kwargs: Fields to update (subject, description, active_form, status,
                      add_blocks, add_blocked_by, metadata)

        Returns:
            dict: Updated task or None if not found
        """
        task = self.tasks.get(str(task_id))
        if not task:
            return None

        if "subject" in kwargs:
            task["subject"] = kwargs["subject"]
        if "description" in kwargs:
            task["description"] = kwargs["description"]
        if "active_form" in kwargs:
            task["active_form"] = kwargs["active_form"]
        if "status" in kwargs:
            new_status = kwargs["status"]
            if new_status in self.VALID_STATUSES:
                task["status"] = new_status
        if "add_blocks" in kwargs:
            for block_id in kwargs["add_blocks"]:
                block_id = str(block_id)
                if block_id not in task["blocks"]:
                    task["blocks"].append(block_id)
        if "add_blocked_by" in kwargs:
            for blocker_id in kwargs["add_blocked_by"]:
                blocker_id = str(blocker_id)
                if blocker_id not in task["blocked_by"]:
                    task["blocked_by"].append(blocker_id)
        if "metadata" in kwargs:
            task["metadata"].update(kwargs["metadata"])

        task["updated"] = datetime.now().isoformat()
        self._save()
        return task

    def delete(self, task_id):
        """Mark a task as deleted.

        Args:
            task_id: The task ID

        Returns:
            bool: True if task was found and deleted
        """
        task = self.tasks.get(str(task_id))
        if not task:
            return False

        task["status"] = self.STATUS_DELETED
        task["updated"] = datetime.now().isoformat()
        self._save()
        return True

    def list_tasks(self, status=None, include_deleted=False):
        """List tasks with optional status filter.

        Args:
            status: Filter by status (None = all non-deleted)
            include_deleted: If True, include deleted tasks

        Returns:
            list: List of task dicts
        """
        result = []
        for task in self.tasks.values():
            if not include_deleted and task["status"] == self.STATUS_DELETED:
                continue
            if status and task["status"] != status:
                continue
            result.append(task)

        # Sort by ID
        result.sort(key=lambda t: int(t["id"]))
        return result

    def get_pending_tasks(self):
        """Get tasks that are not blocked and pending/in_progress."""
        result = []
        for task in self.list_tasks():
            if task["status"] in [self.STATUS_PENDING, self.STATUS_IN_PROGRESS]:
                # Check if blocked
                blocked = False
                for blocker_id in task.get("blocked_by", []):
                    blocker = self.get(blocker_id)
                    if blocker and blocker["status"] != self.STATUS_COMPLETED:
                        blocked = True
                        break
                if not blocked:
                    result.append(task)
        return result

    def get_blocked_tasks(self):
        """Get tasks that are blocked by incomplete dependencies."""
        result = []
        for task in self.list_tasks():
            if task["status"] in [self.STATUS_PENDING, self.STATUS_IN_PROGRESS]:
                for blocker_id in task.get("blocked_by", []):
                    blocker = self.get(blocker_id)
                    if blocker and blocker["status"] != self.STATUS_COMPLETED:
                        result.append(task)
                        break
        return result

    def get_summary(self):
        """Get a summary of task counts by status.

        Returns:
            dict: Counts by status
        """
        summary = {
            "total": 0,
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "blocked": 0
        }

        for task in self.list_tasks():
            summary["total"] += 1
            summary[task["status"]] += 1

        summary["blocked"] = len(self.get_blocked_tasks())
        return summary

    def format_task_list(self, tasks=None):
        """Format task list for display.

        Args:
            tasks: List of tasks to format (None = all)

        Returns:
            str: Formatted task list
        """
        if tasks is None:
            tasks = self.list_tasks()

        if not tasks:
            return "Tidak ada task."

        status_icons = {
            "pending": "⏳",
            "in_progress": "🔄",
            "completed": "✅",
            "deleted": "🗑️"
        }

        lines = []
        for task in tasks:
            icon = status_icons.get(task["status"], "❓")
            task_id = task["id"]
            subject = task["subject"]
            line = f"  {icon} #{task_id}: {subject}"

            # Add blocked info
            if task.get("blocked_by"):
                blockers = []
                for bid in task["blocked_by"]:
                    blocker = self.get(bid)
                    if blocker and blocker["status"] != self.STATUS_COMPLETED:
                        blockers.append(f"#{bid}")
                if blockers:
                    line += f" (blocked by: {', '.join(blockers)})"

            lines.append(line)

        return "\n".join(lines)

    def format_summary(self):
        """Format summary for display.

        Returns:
            str: Formatted summary
        """
        s = self.get_summary()
        parts = []
        if s["pending"] > 0:
            parts.append(f"⏳ {s['pending']} pending")
        if s["in_progress"] > 0:
            parts.append(f"🔄 {s['in_progress']} in progress")
        if s["completed"] > 0:
            parts.append(f"✅ {s['completed']} completed")
        if s["blocked"] > 0:
            parts.append(f"🔒 {s['blocked']} blocked")

        if not parts:
            return "Tidak ada task aktif."

        return f"Tasks: {' | '.join(parts)} (total: {s['total']})"


# Singleton instance for global use
_global_task_manager = None


def get_task_manager(session_id=None):
    """Get or create global TaskManager instance."""
    global _global_task_manager
    if _global_task_manager is None:
        _global_task_manager = TaskManager(session_id)
    return _global_task_manager


def reset_task_manager():
    """Reset global TaskManager (for testing)."""
    global _global_task_manager
    _global_task_manager = None
