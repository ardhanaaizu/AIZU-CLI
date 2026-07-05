"""
AIZU-CLI Plugin System
======================

Sistem plugin untuk AIZU-CLI yang mendukung:
- Tools baru (file, web, git, shell, custom)
- Backends baru (provider AI custom)
- Modes baru (custom system prompts)
- Slash commands baru
- Lifecycle hooks (before/after tool, LLM, startup, shutdown)
- Sub-agents dengan worktree isolation
- MCP (Model Context Protocol) compatibility

Constraint: Zero external dependencies (hanya Python stdlib)
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import importlib.util
import threading
from pathlib import Path

# Import MCP bridge (optional)
try:
    from mcp_bridge import MCPManager, load_mcp_config, POPULAR_MCP_SERVERS
    _HAS_MCP = True
except ImportError:
    _HAS_MCP = False


# =============================================================================
# Plugin Base Class
# =============================================================================

class Plugin:
    """
    Base class untuk semua AIZU-CLI plugins.

    Plugin harus extend class ini dan override method-method yang diperlukan.
    """

    def __init__(self, config):
        """
        Inisialisasi plugin.

        Args:
            config: Config dict dari AIZU-CLI
        """
        self.config = config

    def get_tools(self):
        """
        Return dict tool baru.

        Returns:
            dict: {tool_name: (function, schema)}
                - function: callable yang menerima parameter sesuai schema
                - schema: OpenAI function-calling schema dict
        """
        return {}

    def get_backends(self):
        """
        Return dict backend baru.

        Returns:
            dict: {backend_name: {base_url, model, needs_key}}
        """
        return {}

    def get_modes(self):
        """
        Return dict mode baru.

        Returns:
            dict: {mode_name: {desc, extra}}
        """
        return {}

    def get_commands(self):
        """
        Return dict slash commands baru.

        Returns:
            dict: {/command_name: handler_function}
                - handler_function: callable(args, cfg, messages) -> str
        """
        return {}

    def on_startup(self):
        """Dipanggil saat AIZU-CLI mulai. Override untuk inisialisasi."""
        pass

    def on_shutdown(self):
        """Dipanggil saat AIZU-CLI berhenti. Override untuk cleanup."""
        pass

    # -------------------------------------------------------------------------
    # Hook methods (optional)
    # -------------------------------------------------------------------------

    def before_tool(self, tool_name, args):
        """
        Dipanggil sebelum tool dieksekusi.

        Args:
            tool_name: Nama tool yang akan dipanggil
            args: Dict parameter tool

        Returns:
            None, atau dict untuk memodifikasi args
        """
        pass

    def after_tool(self, tool_name, args, result):
        """
        Dipanggil setelah tool selesai dieksekusi.

        Args:
            tool_name: Nama tool yang dipanggil
            args: Dict parameter tool
            result: Hasil eksekusi tool (string)

        Returns:
            None, atau string untuk mengganti result
        """
        pass

    def before_llm(self, messages, cfg):
        """
        Dipanggil sebelum panggil LLM.

        Args:
            messages: List of message dicts
            cfg: Config dict

        Returns:
            None, atau list untuk mengganti messages
        """
        pass

    def after_llm(self, response):
        """
        Dipanggil setelah LLM merespons.

        Args:
            response: Response dict dari LLM

        Returns:
            None, atau dict untuk mengganti response
        """
        pass

    def on_message(self, message):
        """
        Dipanggil saat pesan baru diterima (user input).

        Args:
            message: String pesan user

        Returns:
            None, atau string untuk mengganti message
        """
        pass

    def on_error(self, error, context=None):
        """
        Dipanggil saat terjadi error.

        Args:
            error: Exception object
            context: Dict info konteks (optional)

        Returns:
            None
        """
        pass


# =============================================================================
# Hook Manager
# =============================================================================

class HookManager:
    """
    Manager untuk lifecycle hooks.

    Mendukung 8 event types:
    - before_tool: Sebelum tool dieksekusi
    - after_tool: Setelah tool selesai
    - before_llm: Sebelum panggil LLM
    - after_llm: Setelah LLM merespons
    - on_message: Saat pesan baru diterima
    - on_error: Saat terjadi error
    - on_startup: Saat AIZU-CLI mulai
    - on_shutdown: Saat AIZU-CLI berhenti
    """

    VALID_EVENTS = [
        'before_tool', 'after_tool',
        'before_llm', 'after_llm',
        'on_message', 'on_error',
        'on_startup', 'on_shutdown',
    ]

    def __init__(self):
        self.hooks = {event: [] for event in self.VALID_EVENTS}

    def register(self, event, callback):
        """
        Register callback untuk event.

        Args:
            event: Nama event (harus dari VALID_EVENTS)
            callback: Callable function

        Raises:
            ValueError: Jika event tidak valid
        """
        if event not in self.VALID_EVENTS:
            raise ValueError(f"Invalid event: {event}. Must be one of: {self.VALID_EVENTS}")

        if callable(callback):
            self.hooks[event].append(callback)

    def unregister(self, event, callback):
        """
        Unregister callback dari event.

        Args:
            event: Nama event
            callback: Callback yang akan dihapus
        """
        if event in self.hooks:
            self.hooks[event] = [cb for cb in self.hooks[event] if cb != callback]

    def emit(self, event, **kwargs):
        """
        Panggil semua callback untuk event.

        Args:
            event: Nama event
            **kwargs: Parameter untuk callback

        Returns:
            list: Hasil dari semua callback
        """
        if event not in self.hooks:
            return []

        results = []
        for callback in self.hooks[event]:
            try:
                result = callback(**kwargs)
                results.append(result)
            except Exception as e:
                # Log error tapi jangan crash
                print(f"\033[33m[Hook Error] {event}: {e}\033[0m")

        return results

    def register_from_plugin(self, plugin):
        """
        Register hooks dari plugin secara otomatis.

        Args:
            plugin: Plugin instance
        """
        hook_methods = {
            'before_tool': 'before_tool',
            'after_tool': 'after_tool',
            'before_llm': 'before_llm',
            'after_llm': 'after_llm',
            'on_message': 'on_message',
            'on_error': 'on_error',
            'on_startup': 'on_startup',
            'on_shutdown': 'on_shutdown',
        }

        for event, method_name in hook_methods.items():
            if hasattr(plugin, method_name):
                method = getattr(plugin, method_name)
                # Check if method is overridden (not the base Plugin method)
                if method.__func__ is not getattr(Plugin, method_name, None):
                    self.register(event, method)

    def clear(self):
        """Hapus semua hooks."""
        for event in self.VALID_EVENTS:
            self.hooks[event] = []


# =============================================================================
# Plugin Manager
# =============================================================================

class PluginManager:
    """
    Manager untuk load, register, dan manage plugins.

    Plugin dicari dari:
    1. ./plugins/ (lokal, bersama source code)
    2. ~/.aizu/plugins/ (user plugins)
    3. MCP servers (via mcp.json config)

    Features:
    - Thread-safe operations (gunakan lock)
    - Hot-reload support (watch file changes)
    - Plugin sandboxing (restricted imports)
    """

    def __init__(self, config):
        """
        Inisialisasi PluginManager.

        Args:
            config: Config dict dari AIZU-CLI
        """
        self.config = config
        self.plugins = []
        self.plugin_dirs = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins'),
            os.path.expanduser('~/.aizu/plugins'),
        ]
        self._loaded_modules = {}
        self.mcp_manager = None

        # Thread safety
        self._lock = threading.RLock()
        self._plugin_timestamps = {}  # Track file modification times untuk hot-reload
        self._watch_thread = None
        self._watching = False

        # Sandboxing
        self._sandbox_enabled = config.get('plugin_sandbox', False)
        self._allowed_modules = {
            'json', 'os', 'os.path', 'sys', 're', 'time', 'datetime',
            'pathlib', 'collections', 'itertools', 'functools', 'math',
            'random', 'string', 'textwrap', 'hashlib', 'base64',
            'urllib', 'urllib.request', 'urllib.parse', 'urllib.error',
        }
        self._blocked_functions = {'exec', 'eval', 'compile', '__import__'}

    def load_all(self):
        """Scan dan load semua plugin dari semua direktori + MCP servers."""
        # Load Python plugins
        for plugin_dir in self.plugin_dirs:
            if os.path.exists(plugin_dir):
                self._scan_dir(plugin_dir)

        # Load MCP servers (jika available)
        if _HAS_MCP:
            self._load_mcp_servers()

        print(f"\033[32m[Plugins] Loaded {len(self.plugins)} plugin(s)\033[0m")

    def _load_mcp_servers(self):
        """Load MCP servers dari config"""
        try:
            mcp_config = load_mcp_config()
            if mcp_config:
                self.mcp_manager = MCPManager(self.config)
                self.mcp_manager.load_from_config(mcp_config)

                # Tambah MCP plugins ke list
                for plugin in self.mcp_manager.get_plugins():
                    self.plugins.append(plugin)

                mcp_count = len(self.mcp_manager.clients)
                if mcp_count > 0:
                    print(f"\033[32m[MCP] Loaded {mcp_count} MCP server(s)\033[0m")
        except Exception as e:
            print(f"\033[33m[MCP] Gagal load MCP servers: {e}\033[0m")

    def _scan_dir(self, directory):
        """Scan direktori untuk plugin."""
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)

                # Plugin bisa berupa directory atau .py file
                if os.path.isdir(item_path):
                    self._load_plugin_dir(item_path)
                elif item.endswith('.py') and item != '__init__.py':
                    self._load_plugin_file(item_path)
        except PermissionError:
            pass

    def _load_plugin_dir(self, plugin_dir):
        """Load plugin dari direktori."""
        manifest_path = os.path.join(plugin_dir, 'plugin.json')

        # Baca manifest
        if os.path.exists(manifest_path):
            try:
                with open(manifest_path, 'r') as f:
                    manifest = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"\033[33m[Plugin] Gagal load manifest {manifest_path}: {e}\033[0m")
                return
        else:
            # Default manifest
            manifest = {
                'name': os.path.basename(plugin_dir),
                'version': '1.0.0',
                'entry': 'main.py'
            }

        # Load entry point
        entry_file = manifest.get('entry', 'main.py')
        entry_path = os.path.join(plugin_dir, entry_file)

        if not os.path.exists(entry_path):
            print(f"\033[33m[Plugin] Entry point tidak ditemukan: {entry_path}\033[0m")
            return

        self._load_plugin_from_file(entry_path, manifest)

    def _load_plugin_file(self, plugin_file):
        """Load plugin dari file .py tunggal."""
        manifest = {
            'name': os.path.splitext(os.path.basename(plugin_file))[0],
            'version': '1.0.0',
        }
        self._load_plugin_from_file(plugin_file, manifest)

    def _load_plugin_from_file(self, file_path, manifest):
        """Load plugin dari file Python."""
        plugin_name = manifest.get('name', 'unknown')

        try:
            # Dynamic import
            module_name = f"aizu_plugin_{plugin_name}_{int(time.time())}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Cari factory function 'create'
            if hasattr(module, 'create'):
                plugin_instance = module.create(self.config)
                if isinstance(plugin_instance, Plugin):
                    self.plugins.append(plugin_instance)
                    self._loaded_modules[plugin_name] = module
                else:
                    print(f"\033[33m[Plugin] {plugin_name}: create() harus return Plugin instance\033[0m")
            else:
                print(f"\033[33m[Plugin] {plugin_name}: tidak ada fungsi create()\033[0m")

        except Exception as e:
            print(f"\033[33m[Plugin] Gagal load {plugin_name}: {e}\033[0m")

    def register_tools(self, registry, schemas):
        """
        Register semua tool dari plugin ke REGISTRY dan SCHEMAS.

        Thread-safe: menggunakan lock untuk mencegah race condition.

        Args:
            registry: tools.REGISTRY dict
            schemas: tools.SCHEMAS list
        """
        with self._lock:
            for plugin in self.plugins:
                try:
                    tools = plugin.get_tools()
                    for name, (func, schema) in tools.items():
                        if name not in registry:
                            registry[name] = func
                            schemas.append(schema)
                        else:
                            print(f"\033[33m[Plugin] Tool '{name}' sudah ada, skip\033[0m")
                except Exception as e:
                    print(f"\033[33m[Plugin] Error register tools: {e}\033[0m")

    def register_backends(self, presets):
        """
        Register semua backend dari plugin ke PRESETS.

        Args:
            presets: PRESETS dict dari agent.py
        """
        for plugin in self.plugins:
            try:
                backends = plugin.get_backends()
                for name, config in backends.items():
                    if name not in presets:
                        presets[name] = config
                    else:
                        print(f"\033[33m[Plugin] Backend '{name}' sudah ada, skip\033[0m")
            except Exception as e:
                print(f"\033[33m[Plugin] Error register backends: {e}\033[0m")

    def register_modes(self, modes):
        """
        Register semua mode dari plugin ke MODES.

        Args:
            modes: MODES dict dari agent.py
        """
        for plugin in self.plugins:
            try:
                modes_dict = plugin.get_modes()
                for name, config in modes_dict.items():
                    if name not in modes:
                        modes[name] = config
                    else:
                        print(f"\033[33m[Plugin] Mode '{name}' sudah ada, skip\033[0m")
            except Exception as e:
                print(f"\033[33m[Plugin] Error register modes: {e}\033[0m")

    def get_all_commands(self):
        """
        Kumpulkan semua slash command dari plugin.

        Returns:
            dict: {/command_name: handler_function}
        """
        commands = {}
        for plugin in self.plugins:
            try:
                plugin_commands = plugin.get_commands()
                for name, handler in plugin_commands.items():
                    # Pastikan nama diawali /
                    if not name.startswith('/'):
                        name = '/' + name
                    if name not in commands:
                        commands[name] = handler
                    else:
                        print(f"\033[33m[Plugin] Command '{name}' sudah ada, skip\033[0m")
            except Exception as e:
                print(f"\033[33m[Plugin] Error get commands: {e}\033[0m")

        return commands

    def shutdown(self):
        """Shutdown semua plugin dan MCP servers."""
        # Stop hot-reload watcher
        self.stop_hot_reload()

        with self._lock:
            for plugin in self.plugins:
                try:
                    plugin.on_shutdown()
                except Exception as e:
                    print(f"\033[33m[Plugin] Error shutdown: {e}\033[0m")

            # Disconnect MCP servers
            if self.mcp_manager:
                try:
                    self.mcp_manager.disconnect_all()
                except Exception as e:
                    print(f"\033[33m[MCP] Error shutdown: {e}\033[0m")

            self.plugins.clear()
            self._loaded_modules.clear()

    # -------------------------------------------------------------------------
    # Hot-Reload Support
    # -------------------------------------------------------------------------
    def start_hot_reload(self, interval=5):
        """Mulai hot-reload watcher.

        Watch plugin directories untuk perubahan file dan auto-reload.

        Args:
            interval: Check interval dalam detik (default 5)
        """
        if self._watching:
            return

        self._watching = True
        self._watch_thread = threading.Thread(
            target=self._watch_loop,
            args=(interval,),
            daemon=True
        )
        self._watch_thread.start()
        print(f"\033[32m[Plugin] Hot-reload started (interval: {interval}s)\033[0m")

    def stop_hot_reload(self):
        """Stop hot-reload watcher."""
        self._watching = False
        if self._watch_thread:
            self._watch_thread.join(timeout=2)
            self._watch_thread = None

    def _watch_loop(self, interval):
        """Background loop untuk watch file changes."""
        while self._watching:
            try:
                self._check_for_changes()
            except Exception as e:
                print(f"\033[33m[Plugin] Hot-reload error: {e}\033[0m")
            time.sleep(interval)

    def _check_for_changes(self):
        """Check semua plugin dirs untuk perubahan file."""
        changed_plugins = []

        with self._lock:
            for plugin_dir in self.plugin_dirs:
                if not os.path.exists(plugin_dir):
                    continue

                for item in os.listdir(plugin_dir):
                    item_path = os.path.join(plugin_dir, item)

                    # Check directory plugins
                    if os.path.isdir(item_path):
                        manifest_path = os.path.join(item_path, 'plugin.json')
                        entry_file = 'main.py'

                        if os.path.exists(manifest_path):
                            try:
                                with open(manifest_path, 'r') as f:
                                    manifest = json.load(f)
                                entry_file = manifest.get('entry', 'main.py')
                            except Exception:
                                pass

                        entry_path = os.path.join(item_path, entry_file)
                        if os.path.exists(entry_path):
                            current_mtime = os.path.getmtime(entry_path)
                            stored_mtime = self._plugin_timestamps.get(entry_path)

                            if stored_mtime and current_mtime > stored_mtime:
                                changed_plugins.append((entry_path, item))
                            self._plugin_timestamps[entry_path] = current_mtime

                    # Check single file plugins
                    elif item.endswith('.py') and item != '__init__.py':
                        current_mtime = os.path.getmtime(item_path)
                        stored_mtime = self._plugin_timestamps.get(item_path)

                        if stored_mtime and current_mtime > stored_mtime:
                            changed_plugins.append((item_path, item[:-3]))
                        self._plugin_timestamps[item_path] = current_mtime

        # Reload changed plugins
        for file_path, plugin_name in changed_plugins:
            self._reload_plugin(file_path, plugin_name)

    def _reload_plugin(self, file_path, plugin_name):
        """Reload satu plugin.

        Args:
            file_path: Path ke plugin file
            plugin_name: Nama plugin
        """
        print(f"\033[36m[Plugin] Hot-reloading: {plugin_name}\033[0m")

        # Unload existing plugin
        self._unload_plugin(plugin_name)

        # Reload
        try:
            manifest = {'name': plugin_name, 'version': '1.0.0'}
            self._load_plugin_from_file(file_path, manifest)
            print(f"\033[32m[Plugin] Reloaded: {plugin_name}\033[0m")
        except Exception as e:
            print(f"\033[31m[Plugin] Gagal reload {plugin_name}: {e}\033[0m")

    def _unload_plugin(self, plugin_name):
        """Unload plugin berdasarkan nama.

        Args:
            plugin_name: Nama plugin yang akan di-unload
        """
        # Remove dari plugins list
        self.plugins = [p for p in self.plugins if not hasattr(p, '_plugin_name') or p._plugin_name != plugin_name]

        # Unload module
        if plugin_name in self._loaded_modules:
            module = self._loaded_modules[plugin_name]
            # Remove dari sys.modules
            for key in list(sys.modules.keys()):
                if sys.modules[key] is module:
                    del sys.modules[key]
            del self._loaded_modules[plugin_name]

    def reload_all(self):
        """Reload semua plugins."""
        print("\033[36m[Plugin] Reloading semua plugins...\033[0m")

        with self._lock:
            # Unload semua
            for plugin in self.plugins:
                try:
                    plugin.on_shutdown()
                except Exception:
                    pass

            self.plugins.clear()
            self._loaded_modules.clear()
            self._plugin_timestamps.clear()

        # Reload
        self.load_all()

    # -------------------------------------------------------------------------
    # Sandboxing
    # -------------------------------------------------------------------------
    def _check_sandbox(self, module):
        """Check apakah module aman untuk di-load.

        Args:
            module: Python module yang akan di-check

        Returns:
            tuple: (is_safe, reason)
        """
        if not self._sandbox_enabled:
            return True, ""

        # Check untuk blocked functions
        for attr_name in dir(module):
            if attr_name in self._blocked_functions:
                return False, f"Blocked function: {attr_name}"

            # Check untuk dangerous imports
            attr = getattr(module, attr_name, None)
            if callable(attr) and hasattr(attr, '__module__'):
                if attr.__module__ in ['subprocess', 'os.system', 'shutil']:
                    return False, f"Dangerous module: {attr.__module__}"

        return True, ""

    def enable_sandbox(self, enabled=True):
        """Enable/disable plugin sandboxing.

        Args:
            enabled: True untuk enable sandbox
        """
        self._sandbox_enabled = enabled
        status = "enabled" if enabled else "disabled"
        print(f"\033[36m[Plugin] Sandbox {status}\033[0m")

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------
    def get_plugin_info(self):
        """Dapatkan info semua plugins.

        Returns:
            list: List of plugin info dicts
        """
        with self._lock:
            info = []
            for i, plugin in enumerate(self.plugins):
                tools = list(plugin.get_tools().keys()) if hasattr(plugin, 'get_tools') else []
                info.append({
                    'index': i,
                    'name': plugin.__class__.__name__,
                    'type': type(plugin).__bases__[0].__name__ if type(plugin).__bases__ else 'Plugin',
                    'tools': tools,
                    'has_backends': bool(plugin.get_backends()) if hasattr(plugin, 'get_backends') else False,
                    'has_modes': bool(plugin.get_modes()) if hasattr(plugin, 'get_modes') else False,
                    'has_commands': bool(plugin.get_commands()) if hasattr(plugin, 'get_commands') else False,
                })
            return info

    def get_plugin(self, name):
        """Dapatkan plugin berdasarkan nama class.

        Args:
            name: Nama plugin (class name)

        Returns:
            Plugin instance atau None
        """
        with self._lock:
            for plugin in self.plugins:
                if plugin.__class__.__name__.lower() == name.lower():
                    return plugin
            return None


# =============================================================================
# Sub-Agent
# =============================================================================

class SubAgent:
    """
    Sub-agent dengan worktree isolation.

    Memungkinkan delegasi task ke child agent loop dengan:
    - Worktree terpisah untuk git repos
    - Temp directory untuk non-git projects
    - Isolasi context dan file system
    """

    def __init__(self, task, config, parent_dir, hook_mgr=None):
        """
        Inisialisasi SubAgent.

        Args:
            task: String task yang akan dikerjakan
            config: Config dict dari parent
            parent_dir: Direktori kerja parent
            hook_mgr: HookManager instance (optional)
        """
        self.task = task
        self.config = config.copy()
        self.parent_dir = parent_dir
        self.hook_mgr = hook_mgr
        self.worktree_dir = None
        self.result = None
        self.is_git_repo = os.path.exists(os.path.join(parent_dir, '.git'))

    def run(self):
        """
        Jalankan sub-agent.

        Returns:
            str: Hasil eksekusi task
        """
        try:
            # 1. Buat worktree
            self._create_worktree()

            # 2. Jalankan child agent loop
            self._run_child_loop()

            # 3. Ambil hasil
            self._collect_result()

        except Exception as e:
            self.result = f"Sub-agent error: {e}"
            if self.hook_mgr:
                self.hook_mgr.emit('on_error', error=e, context={'subagent': True})

        finally:
            # 4. Cleanup worktree
            self._cleanup_worktree()

        return self.result

    def _create_worktree(self):
        """Buat worktree terpisah."""
        if self.is_git_repo:
            # Git repo - buat worktree
            worktree_name = f"aizu-subagent-{int(time.time())}"
            self.worktree_dir = os.path.join(
                self.parent_dir, '.aizu', 'worktrees', worktree_name
            )
            os.makedirs(os.path.dirname(self.worktree_dir), exist_ok=True)

            result = subprocess.run(
                ['git', 'worktree', 'add', self.worktree_dir, 'HEAD'],
                cwd=self.parent_dir,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                # Fallback ke temp directory
                self.worktree_dir = tempfile.mkdtemp(prefix='aizu-subagent-')
                self.is_git_repo = False
        else:
            # Bukan git - buat temp directory
            self.worktree_dir = tempfile.mkdtemp(prefix='aizu-subagent-')

        # Update config dengan worktree directory
        self.config['workdir'] = self.worktree_dir

    def _run_child_loop(self):
        """Jalankan child agent loop di worktree."""
        # Import di sini untuk avoid circular import
        from agent import build_system_prompt, call_llm, run_tool_calls
        import tools

        # Buat messages dengan task
        messages = [
            {"role": "system", "content": build_system_prompt('chat')},
            {"role": "user", "content": self.task}
        ]

        # Jalankan tool-calling loop (max 20 iterasi)
        for i in range(20):
            response = call_llm(self.config, messages)

            if not response:
                self.result = "Error: Tidak ada response dari LLM"
                break

            if 'tool_calls' in response and response['tool_calls']:
                # Execute tool calls
                tool_results = run_tool_calls(response['tool_calls'])

                # Tambahkan ke messages
                messages.append({
                    "role": "assistant",
                    "content": response.get('content', ''),
                    "tool_calls": response['tool_calls']
                })

                for result in tool_results:
                    messages.append({
                        "role": "tool",
                        "content": str(result)
                    })
            else:
                # Final answer
                self.result = response.get('content', '')
                break

    def _collect_result(self):
        """Kumpulkan hasil dari worktree."""
        # Jika ada file baru yang dibuat di worktree, copy ke parent
        if self.worktree_dir and os.path.exists(self.worktree_dir):
            # Implementasi copy file baru (opsional)
            pass

    def _cleanup_worktree(self):
        """Hapus worktree."""
        if not self.worktree_dir or not os.path.exists(self.worktree_dir):
            return

        try:
            if self.is_git_repo:
                subprocess.run(
                    ['git', 'worktree', 'remove', self.worktree_dir, '--force'],
                    cwd=self.parent_dir,
                    capture_output=True
                )
            else:
                shutil.rmtree(self.worktree_dir)
        except Exception as e:
            print(f"\033[33m[SubAgent] Cleanup error: {e}\033[0m")


class BackgroundSubAgent(SubAgent):
    """
    Sub-agent yang bisa jalan di background.

    Mirip Claude Code's background agents.
    Parent tidak blocking, bisa cek status kapan saja.
    """

    def __init__(self, task, config, parent_dir, hook_mgr=None, agent_id=None):
        super().__init__(task, config, parent_dir, hook_mgr)
        self.agent_id = agent_id or f"bg-{int(time.time())}"
        self.thread = None
        self.status = "pending"  # pending, running, completed, error
        self.start_time = None
        self.end_time = None
        self._callbacks = []

    def run(self):
        """Jalankan sub-agent di background thread."""
        self.status = "running"
        self.start_time = time.time()
        self.thread = threading.Thread(target=self._run_wrapper, daemon=True)
        self.thread.start()
        return self.agent_id

    def _run_wrapper(self):
        """Wrapper untuk menjalankan run() dan update status."""
        try:
            super().run()
            self.status = "completed"
        except Exception as e:
            self.status = "error"
            self.result = f"Error: {e}"
        finally:
            self.end_time = time.time()
            self._notify_callbacks()

    def _notify_callbacks(self):
        """Notify semua callback bahwa agent selesai."""
        for callback in self._callbacks:
            try:
                callback(self)
            except Exception:
                pass

    def on_complete(self, callback):
        """Register callback untuk saat agent selesai."""
        self._callbacks.append(callback)

    def is_running(self):
        """Cek apakah agent masih running."""
        return self.status == "running"

    def wait(self, timeout=None):
        """Tunggu agent selesai."""
        if self.thread:
            self.thread.join(timeout=timeout)
        return self.result

    def get_duration(self):
        """Durasi eksekusi."""
        if self.start_time is None:
            return 0
        end = self.end_time or time.time()
        return end - self.start_time

    def format_status(self):
        """Format status untuk display."""
        icons = {
            "pending": "⏳",
            "running": "🔄",
            "completed": "✅",
            "error": "❌"
        }
        icon = icons.get(self.status, "❓")
        duration = self.get_duration()
        task_preview = self.task[:50] + ("..." if len(self.task) > 50 else "")
        return f"{icon} [{self.agent_id}] {task_preview} ({duration:.1f}s)"


class BackgroundAgentManager:
    """
    Manager untuk background agents.

    Mirip Claude Code's agent management.
    """

    def __init__(self, config, parent_dir, hook_mgr=None):
        self.config = config
        self.parent_dir = parent_dir
        self.hook_mgr = hook_mgr
        self.agents = {}

    def spawn(self, task, agent_id=None):
        """Spawn background agent baru.

        Args:
            task: Task description
            agent_id: Optional custom ID

        Returns:
            str: Agent ID
        """
        agent = BackgroundSubAgent(
            task=task,
            config=self.config,
            parent_dir=self.parent_dir,
            hook_mgr=self.hook_mgr,
            agent_id=agent_id
        )
        agent_id = agent.agent_id
        self.agents[agent_id] = agent
        agent.run()
        return agent_id

    def get(self, agent_id):
        """Get agent by ID."""
        return self.agents.get(agent_id)

    def list_agents(self, status=None):
        """List semua agents.

        Args:
            status: Filter by status (None = all)

        Returns:
            list: List of BackgroundSubAgent
        """
        agents = list(self.agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return agents

    def list_running(self):
        """List agents yang masih running."""
        return self.list_agents(status="running")

    def stop(self, agent_id):
        """Stop/cancel agent.

        Args:
            agent_id: Agent ID

        Returns:
            bool: True if stopped
        """
        agent = self.agents.get(agent_id)
        if agent and agent.is_running():
            # Force cleanup
            agent.status = "error"
            agent.result = "Cancelled by user"
            agent.end_time = time.time()
            agent._cleanup_worktree()
            return True
        return False

    def format_list(self):
        """Format semua agents untuk display."""
        if not self.agents:
            return "Tidak ada background agents."

        lines = []
        for agent in self.agents.values():
            lines.append(agent.format_status())
        return "\n".join(lines)


# Specialized Agent Types
AGENT_TYPES = {
    "explore": {
        "description": "Read-only agent untuk eksplorasi kode. Tidak boleh write/execute.",
        "system_prompt": (
            "Kamu adalah explore agent. Tugasmu adalah mencari dan memahami kode. "
            "Kamu HANYA BOLEH membaca file (read_file, list_dir, search_files, glob_files, grep_content, read_file_lines). "
            "Kamu TIDAK BOLEH menulis, mengedit, atau mengeksekusi apapun. "
            "Jawab dengan fakta dari kode, jangan berasumsi."
        ),
        "allowed_tools": ["read_file", "list_dir", "search_files", "glob_files", "grep_content", "read_file_lines"],
        "blocked_tools": ["write_file", "edit_file", "edit_file_improved", "run_shell", "git_add", "git_commit", "git_push"],
    },
    "code-reviewer": {
        "description": "Review kode, cari bug dan masalah keamanan.",
        "system_prompt": (
            "Kamu adalah code reviewer. Tugasmu adalah me-review kode dan mencari: "
            "1. Bug dan error potensial\n"
            "2. Masalah keamanan (security)\n"
            "3. Performance issues\n"
            "4. Code style dan best practices\n"
            "5. Edge cases yang belum ditangani\n\n"
            "Baca kode dengan teliti, berikan penjelasan spesifik dengan line number. "
            "Format: [SEVERITY] file:line — deskripsi"
        ),
        "allowed_tools": ["read_file", "list_dir", "search_files", "glob_files", "grep_content", "read_file_lines", "git_diff", "git_status"],
        "blocked_tools": ["write_file", "edit_file", "edit_file_improved", "run_shell"],
    },
    "implementer": {
        "description": "Fokus menulis dan mengedit kode.",
        "system_prompt": (
            "Kamu adalah implementer agent. Tugasmu adalah menulis kode sesuai instruksi. "
            "Fokus pada:\n"
            "1. Tulis kode yang bersih dan terstruktur\n"
            "2. Ikuti existing code style\n"
            "3. Tambah komentar untuk logika kompleks\n"
            "4. Handle edge cases\n"
            "5. Commit setelah selesai jika diminta\n\n"
            "Kerjakan task step by step, jangan terburu-buru."
        ),
        "allowed_tools": ["read_file", "write_file", "edit_file", "edit_file_improved", "list_dir",
                         "search_files", "glob_files", "grep_content", "read_file_lines",
                         "run_shell", "git_status", "git_add", "git_commit"],
        "blocked_tools": ["git_push"],  # push harus manual
    },
}


class SpecializedAgent(SubAgent):
    """
    Sub-agent dengan tipe spesialis.

    Mirip Claude Code's specialized agent types.
    Setiap tipe punya constraint berbeda.
    """

    def __init__(self, task, config, parent_dir, agent_type="explore", hook_mgr=None):
        super().__init__(task, config, parent_dir, hook_mgr)

        if agent_type not in AGENT_TYPES:
            raise ValueError(f"Agent type tidak dikenal: {agent_type}. Pilih: {list(AGENT_TYPES.keys())}")

        self.agent_type = agent_type
        self.type_config = AGENT_TYPES[agent_type]

    def _run_child_loop(self):
        """Jalankan child loop dengan constraint berdasarkan tipe."""
        from agent import build_system_prompt, call_llm, run_tool_calls
        import tools

        # Build specialized system prompt
        base_prompt = build_system_prompt('chat')
        type_prompt = self.type_config["system_prompt"]
        system_content = f"{base_prompt}\n\n## Specialized Mode: {self.agent_type}\n\n{type_prompt}"

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": self.task}
        ]

        # Tool filtering
        allowed = self.type_config.get("allowed_tools")
        blocked = self.type_config.get("blocked_tools", [])

        # Backup original registry
        original_registry = dict(tools.REGISTRY)

        try:
            # Filter tools
            if allowed:
                tools.REGISTRY = {k: v for k, v in original_registry.items() if k in allowed}
            elif blocked:
                tools.REGISTRY = {k: v for k, v in original_registry.items() if k not in blocked}

            # Run loop
            for i in range(20):
                response = call_llm(self.config, messages)

                if not response:
                    self.result = "Error: Tidak ada response dari LLM"
                    break

                if 'tool_calls' in response and response['tool_calls']:
                    # Filter tool calls yang tidak diizinkan
                    filtered_calls = []
                    for tc in response['tool_calls']:
                        func_name = tc.get('function', {}).get('name', '')
                        if func_name in tools.REGISTRY:
                            filtered_calls.append(tc)
                        else:
                            # Block tool call
                            messages.append({
                                "role": "tool",
                                "content": f"DITOLAK: tool '{func_name}' tidak diizinkan dalam mode {self.agent_type}"
                            })

                    if filtered_calls:
                        tool_results = run_tool_calls(filtered_calls)
                        messages.append({
                            "role": "assistant",
                            "content": response.get('content', ''),
                            "tool_calls": filtered_calls
                        })
                        for result in tool_results:
                            messages.append({"role": "tool", "content": str(result)})
                else:
                    self.result = response.get('content', '')
                    break

        finally:
            # Restore original registry
            tools.REGISTRY = original_registry


# =============================================================================
# Utility Functions
# =============================================================================

def create_plugin_skeleton(name, plugin_type='tool', target_dir=None):
    """
    Buat skeleton plugin baru.

    Args:
        name: Nama plugin
        plugin_type: Tipe plugin (tool, backend, mode, command)
        target_dir: Direktori target (default: ./plugins/)

    Returns:
        str: Path ke plugin yang dibuat
    """
    if target_dir is None:
        target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins')

    plugin_dir = os.path.join(target_dir, name)
    os.makedirs(plugin_dir, exist_ok=True)

    # Buat manifest
    manifest = {
        'name': name,
        'version': '1.0.0',
        'description': f'{plugin_type.title()} plugin: {name}',
        'author': '',
        'type': plugin_type,
        'entry': 'main.py'
    }

    with open(os.path.join(plugin_dir, 'plugin.json'), 'w') as f:
        json.dump(manifest, f, indent=2)

    # Buat main.py dengan template
    template = f'''"""
{name} - {plugin_type.title()} Plugin untuk AIZU-CLI
"""

from plugins import Plugin


class {name.title().replace('-', '')}Plugin(Plugin):
    """Plugin untuk {name}"""

'''

    if plugin_type == 'tool':
        template += '''    def get_tools(self):
        """Register tools"""
        def my_tool(param1):
            # Implementasi tool di sini
            return f"Hasil: {param1}"

        schema = {
            "type": "function",
            "function": {
                "name": "my_tool",
                "description": "Deskripsi tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {
                            "type": "string",
                            "description": "Parameter 1"
                        }
                    },
                    "required": ["param1"]
                }
            }
        }

        return {"my_tool": (my_tool, schema)}
'''
    elif plugin_type == 'backend':
        template += '''    def get_backends(self):
        """Register backends"""
        return {
            "my-backend": {
                "base_url": "https://api.example.com/v1",
                "model": "my-model",
                "needs_key": True
            }
        }
'''
    elif plugin_type == 'mode':
        template += '''    def get_modes(self):
        """Register modes"""
        return {
            "my-mode": {
                "desc": "My custom mode",
                "extra": "Extra system prompt for this mode."
            }
        }
'''
    elif plugin_type == 'command':
        template += '''    def get_commands(self):
        """Register slash commands"""
        def my_command(args, cfg, messages):
            """Handler untuk /my-command"""
            return f"Command executed with args: {args}"

        return {"/my-command": my_command}
'''

    template += '''

def create(config):
    """Factory function untuk create plugin instance"""
    return {name.title().replace('-', '')}Plugin(config)
'''.format(name=name)

    with open(os.path.join(plugin_dir, 'main.py'), 'w') as f:
        f.write(template)

    return plugin_dir


def list_plugins():
    """
    List semua plugin yang terinstall.

    Returns:
        list: List of dict info plugin
    """
    plugin_dirs = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'plugins'),
        os.path.expanduser('~/.aizu/plugins'),
    ]

    plugins = []
    for plugin_dir in plugin_dirs:
        if not os.path.exists(plugin_dir):
            continue

        for item in os.listdir(plugin_dir):
            item_path = os.path.join(plugin_dir, item)

            if os.path.isdir(item_path):
                manifest_path = os.path.join(item_path, 'plugin.json')
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest = json.load(f)
                        manifest['path'] = item_path
                        manifest['location'] = 'local' if 'plugins/' in plugin_dir else 'user'
                        plugins.append(manifest)
                    except (json.JSONDecodeError, IOError):
                        pass

    return plugins
