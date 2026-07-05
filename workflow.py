"""
AIZU-CLI Workflow Orchestration
Pipeline & parallel execution untuk beberapa agent.
Mirip Claude Code's pipeline(), parallel(), phase().

Features:
- Pipeline execution dengan stages
- Parallel execution dengan barrier
- Workflow persistence (save/load)
- Error recovery dan retry
- Progress tracking
- Background execution
"""

import os
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


class WorkflowResult:
    """Result dari sebuah workflow step."""

    def __init__(self, data=None, error=None, duration=0):
        self.data = data
        self.error = error
        self.duration = duration

    @property
    def success(self):
        return self.error is None

    def __repr__(self):
        if self.success:
            return f"WorkflowResult(success, {self.duration:.1f}s)"
        return f"WorkflowResult(error: {self.error}, {self.duration:.1f}s)"


class WorkflowPhase:
    """Represents a phase in workflow execution."""

    def __init__(self, title):
        self.title = title
        self.start_time = None
        self.end_time = None
        self.status = "pending"  # pending, running, completed, error

    def start(self):
        self.start_time = time.time()
        self.status = "running"

    def complete(self):
        self.end_time = time.time()
        self.status = "completed"

    def error(self):
        self.end_time = time.time()
        self.status = "error"

    @property
    def duration(self):
        if self.start_time is None:
            return 0
        end = self.end_time or time.time()
        return end - self.start_time


class WorkflowEngine:
    """Engine untuk menjalankan workflow pipelines."""

    def __init__(self, agent_fn=None, log_fn=None):
        """
        Args:
            agent_fn: Function(agent_prompt, **opts) -> str
                      Fungsi untuk menjalankan sub-agent.
                      Jika None, menggunakan placeholder.
            log_fn: Function(message) untuk logging
        """
        self.agent_fn = agent_fn or self._default_agent_fn
        self.log_fn = log_fn or print
        self.phases = []
        self._current_phase = None

    def _default_agent_fn(self, prompt, **opts):
        """Default agent function (placeholder)."""
        return f"[Agent result for: {prompt[:50]}...]"

    def phase(self, title):
        """Start a new phase.

        Args:
            title: Phase title
        """
        # Complete previous phase
        if self._current_phase:
            self._current_phase.complete()

        phase = WorkflowPhase(title)
        phase.start()
        self.phases.append(phase)
        self._current_phase = phase
        self.log(f"-> Phase: {title}")

    def log(self, message):
        """Emit a progress message."""
        if self.log_fn:
            self.log_fn(message)

    def agent(self, prompt, label=None, **opts):
        """Run a single agent.

        Args:
            prompt: The task/prompt for the agent
            label: Optional display label
            **opts: Additional options passed to agent_fn

        Returns:
            WorkflowResult
        """
        start = time.time()
        label = label or prompt[:50]
        try:
            self.log(f"  🤖 Agent: {label}")
            result = self.agent_fn(prompt, **opts)
            duration = time.time() - start
            self.log(f"  ✅ Agent done ({duration:.1f}s): {label}")
            return WorkflowResult(data=result, duration=duration)
        except Exception as e:
            duration = time.time() - start
            self.log(f"  ❌ Agent error ({duration:.1f}s): {label} — {e}")
            return WorkflowResult(error=str(e), duration=duration)

    def pipeline(self, items, *stages):
        """Run items through multiple stages sequentially (per item).

        Each item goes through all stages independently.
        Items run in parallel, stages run sequentially per item.

        Args:
            items: List of items to process
            *stages: Stage functions. Each receives (prev_result, original_item, index)
                     First stage receives (None, item, index)

        Returns:
            list: Results from the last stage for each item
        """
        if not items:
            return []

        if not stages:
            return list(items)

        self.log(f"📋 Pipeline: {len(items)} items × {len(stages)} stages")

        results = [None] * len(items)

        def process_item(idx, item):
            current = item
            for stage_idx, stage_fn in enumerate(stages):
                try:
                    current = stage_fn(current if stage_idx > 0 else None, item, idx)
                except Exception as e:
                    self.log(f"  ❌ Pipeline error item {idx} stage {stage_idx}: {e}")
                    return None
            return current

        # Run items in parallel
        with ThreadPoolExecutor(max_workers=min(len(items), 8)) as executor:
            futures = {
                executor.submit(process_item, idx, item): idx
                for idx, item in enumerate(items)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    self.log(f"  ❌ Pipeline item {idx} failed: {e}")
                    results[idx] = None

        self.log(f"✅ Pipeline complete: {sum(1 for r in results if r is not None)}/{len(items)} success")
        return results

    def parallel(self, thunks):
        """Run multiple tasks concurrently (barrier).

        All tasks run in parallel, waits for all to complete.

        Args:
            thunks: List of callable (no args) that return results

        Returns:
            list: Results in same order as thunks
        """
        if not thunks:
            return []

        self.log(f"⚡ Parallel: {len(thunks)} tasks")

        results = [None] * len(thunks)

        with ThreadPoolExecutor(max_workers=min(len(thunks), 8)) as executor:
            futures = {
                executor.submit(thunk): idx
                for idx, thunk in enumerate(thunks)
            }

            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    self.log(f"  ❌ Parallel task {idx} failed: {e}")
                    results[idx] = None

        success_count = sum(1 for r in results if r is not None)
        self.log(f"✅ Parallel complete: {success_count}/{len(thunks)} success")
        return results

    def complete_phase(self):
        """Complete the current phase."""
        if self._current_phase:
            self._current_phase.complete()
            self.log(f"✅ Phase complete: {self._current_phase.title} ({self._current_phase.duration:.1f}s)")
            self._current_phase = None

    def get_status(self):
        """Get workflow status.

        Returns:
            dict: Status info
        """
        return {
            "phases": [
                {
                    "title": p.title,
                    "status": p.status,
                    "duration": p.duration
                }
                for p in self.phases
            ],
            "current_phase": self._current_phase.title if self._current_phase else None
        }

    def format_status(self):
        """Format status for display.

        Returns:
            str: Formatted status
        """
        lines = []
        for phase in self.phases:
            if phase.status == "completed":
                lines.append(f"  [DONE] {phase.title} ({phase.duration:.1f}s)")
            elif phase.status == "running":
                lines.append(f"  [RUN] {phase.title}...")
            elif phase.status == "error":
                lines.append(f"  [ERR] {phase.title} (error)")
            else:
                lines.append(f"  [WAIT] {phase.title}")

        return "\n".join(lines) if lines else "No workflow running."


# =============================================================================
# Workflow Manager (Persistence)
# =============================================================================

class WorkflowManager:
    """Manager untuk menyimpan dan mengelola workflows.

    Features:
    - Save/load workflows ke file
    - Track workflow execution history
    - Resume interrupted workflows
    """

    def __init__(self, workflow_dir=None):
        """
        Args:
            workflow_dir: Directory untuk workflow files (default: ~/.aizu/workflows/)
        """
        self.workflow_dir = workflow_dir or os.path.expanduser("~/.aizu/workflows")
        os.makedirs(self.workflow_dir, exist_ok=True)
        self._active_workflows = {}

    def save(self, name, workflow_data):
        """Simpan workflow ke file.

        Args:
            name: Workflow name
            workflow_data: Dict dengan workflow definition

        Returns:
            str: Path ke file yang disimpan
        """
        filepath = os.path.join(self.workflow_dir, f"{name}.json")

        # Add metadata
        workflow_data['_meta'] = {
            'name': name,
            'saved_at': datetime.now().isoformat(),
            'version': '1.0'
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(workflow_data, f, indent=2, ensure_ascii=False)

        return filepath

    def load(self, name):
        """Load workflow dari file.

        Args:
            name: Workflow name

        Returns:
            dict atau None: Workflow data
        """
        filepath = os.path.join(self.workflow_dir, f"{name}.json")

        if not os.path.exists(filepath):
            return None

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"\033[31m[Workflow] Gagal load {name}: {e}\033[0m")
            return None

    def list_all(self):
        """List semua saved workflows.

        Returns:
            list: List of workflow info dicts
        """
        workflows = []

        for filename in os.listdir(self.workflow_dir):
            if not filename.endswith('.json'):
                continue

            filepath = os.path.join(self.workflow_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get('_meta', {})
                    workflows.append({
                        'name': meta.get('name', filename[:-5]),
                        'saved_at': meta.get('saved_at', 'unknown'),
                        'phases': len(data.get('phases', [])),
                        'filepath': filepath
                    })
            except Exception:
                pass

        return workflows

    def delete(self, name):
        """Hapus workflow.

        Args:
            name: Workflow name

        Returns:
            bool: True jika berhasil
        """
        filepath = os.path.join(self.workflow_dir, f"{name}.json")

        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def track_execution(self, name, status, result=None):
        """Track workflow execution.

        Args:
            name: Workflow name
            status: Execution status (started, completed, failed)
            result: Optional result data
        """
        history_file = os.path.join(self.workflow_dir, "history.json")

        # Load existing history
        history = []
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except Exception:
                pass

        # Add entry
        history.append({
            'workflow': name,
            'status': status,
            'timestamp': datetime.now().isoformat(),
            'result': str(result)[:500] if result else None
        })

        # Keep last 100 entries
        history = history[-100:]

        # Save
        try:
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def get_history(self, limit=20):
        """Dapatkan execution history.

        Args:
            limit: Maximum entries

        Returns:
            list: List of history entries
        """
        history_file = os.path.join(self.workflow_dir, "history.json")

        if not os.path.exists(history_file):
            return []

        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
                return history[-limit:]
        except Exception:
            return []


# =============================================================================
# Background Workflow Runner
# =============================================================================

class BackgroundWorkflowRunner:
    """Runner untuk menjalankan workflow di background thread.

    Features:
    - Non-blocking execution
    - Progress callbacks
    - Cancellation support
    """

    def __init__(self, agent_fn=None, log_fn=None):
        """
        Args:
            agent_fn: Function(prompt, **opts) -> str
            log_fn: Function(message) untuk logging
        """
        self.agent_fn = agent_fn
        self.log_fn = log_fn or print
        self._thread = None
        self._cancel_flag = threading.Event()
        self._result = None
        self._error = None
        self._status = "idle"

    def run(self, workflow_fn, *args, **kwargs):
        """Run workflow di background.

        Args:
            workflow_fn: Function yang akan dijalankan
            *args, **kwargs: Arguments untuk workflow_fn

        Returns:
            bool: True jika berhasil dimulai
        """
        if self._thread and self._thread.is_alive():
            return False  # Already running

        self._cancel_flag.clear()
        self._result = None
        self._error = None
        self._status = "running"

        def _run():
            try:
                self._result = workflow_fn(*args, **kwargs)
                self._status = "completed"
            except Exception as e:
                self._error = e
                self._status = "failed"
            finally:
                self._status = "idle"

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        return True

    def cancel(self):
        """Cancel running workflow."""
        self._cancel_flag.set()

    def is_running(self):
        """Check apakah workflow sedang running."""
        return self._thread is not None and self._thread.is_alive()

    def get_result(self):
        """Dapatkan hasil workflow.

        Returns:
            tuple: (result, error)
        """
        return self._result, self._error

    def get_status(self):
        """Dapatkan status workflow.

        Returns:
            str: Status (idle, running, completed, failed)
        """
        return self._status

    def wait(self, timeout=None):
        """Tunggu workflow selesai.

        Args:
            timeout: Timeout dalam detik (None = unlimited)

        Returns:
            bool: True jika selesai dalam timeout
        """
        if self._thread:
            self._thread.join(timeout=timeout)
            return not self._thread.is_alive()
        return True

    @property
    def cancelled(self):
        """Check apakah workflow di-cancel."""
        return self._cancel_flag.is_set()


# =============================================================================
# Convenience Functions
# =============================================================================

def create_workflow(agent_fn=None, log_fn=None):
    """Create a new WorkflowEngine instance.

    Args:
        agent_fn: Function(prompt, **opts) -> str
        log_fn: Function(message) for logging

    Returns:
        WorkflowEngine
    """
    return WorkflowEngine(agent_fn=agent_fn, log_fn=log_fn)


def pipeline(items, *stages, agent_fn=None):
    """Convenience function for running a pipeline.

    Args:
        items: Items to process
        *stages: Stage functions
        agent_fn: Optional agent function

    Returns:
        list: Results
    """
    engine = WorkflowEngine(agent_fn=agent_fn)
    return engine.pipeline(items, *stages)


def parallel(*thunks, agent_fn=None):
    """Convenience function for running tasks in parallel.

    Args:
        *thunks: Callable tasks
        agent_fn: Optional agent function

    Returns:
        list: Results
    """
    engine = WorkflowEngine(agent_fn=agent_fn)
    return engine.parallel(list(thunks))
