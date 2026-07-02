"""
AIZU-CLI Workflow Orchestration
Pipeline & parallel execution untuk beberapa agent.
Mirip Claude Code's pipeline(), parallel(), phase().
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


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
        self.log(f"▶ Phase: {title}")

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
                lines.append(f"  ✅ {phase.title} ({phase.duration:.1f}s)")
            elif phase.status == "running":
                lines.append(f"  ⏳ {phase.title}...")
            elif phase.status == "error":
                lines.append(f"  ❌ {phase.title} (error)")
            else:
                lines(f"  ⏸ {phase.title}")

        return "\n".join(lines) if lines else "No workflow running."


# Convenience functions

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
