"""
AIZU-CLI MCP Bridge
===================

Compatibility layer untuk menggunakan MCP (Model Context Protocol) servers
sebagai plugins di AIZU-CLI.

MCP Protocol: https://modelcontextprotocol.io/

Support:
- stdio transport (subprocess)
- SSE transport (Server-Sent Events)
- Tool discovery dan execution
- Auto-reconnect
"""

import os
import sys
import json
import time
import uuid
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional, Callable

# Import Plugin base class
from plugins import Plugin


# =============================================================================
# MCP Protocol Messages
# =============================================================================

class MCPMessage:
    """MCP JSON-RPC 2.0 message"""

    @staticmethod
    def initialize(capabilities=None):
        """Initialize request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": capabilities or {},
                "clientInfo": {
                    "name": "aizu-cli",
                    "version": "1.2.0"
                }
            }
        }

    @staticmethod
    def list_tools():
        """List tools request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {}
        }

    @staticmethod
    def call_tool(name, arguments):
        """Call tool request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments
            }
        }

    @staticmethod
    def list_resources():
        """List resources request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "resources/list",
            "params": {}
        }

    @staticmethod
    def read_resource(uri):
        """Read resource request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "resources/read",
            "params": {"uri": uri}
        }

    @staticmethod
    def list_prompts():
        """List prompts request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "prompts/list",
            "params": {}
        }

    @staticmethod
    def get_prompt(name, arguments=None):
        """Get prompt request"""
        return {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "prompts/get",
            "params": {
                "name": name,
                "arguments": arguments or {}
            }
        }


# =============================================================================
# MCP Transport (stdio)
# =============================================================================

class MCPStdioTransport:
    """Transport untuk MCP server via stdin/stdout (subprocess)

    Cross-platform: Support Windows, Linux, dan macOS.
    Windows tidak support select.select() pada pipes, jadi
    menggunakan threading untuk timeout.
    """

    def __init__(self, command, args=None, env=None, cwd=None):
        """
        Args:
            command: Command untuk menjalankan MCP server
            args: Arguments untuk command
            env: Environment variables
            cwd: Working directory
        """
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.process = None
        self._response_cache = {}
        self._lock = threading.Lock()
        self._is_windows = sys.platform == 'win32'

    def connect(self):
        """Start MCP server process"""
        try:
            # Merge env
            full_env = os.environ.copy()
            full_env.update(self.env)

            # Start process dengan platform-specific settings
            popen_kwargs = {
                'stdin': subprocess.PIPE,
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'env': full_env,
                'cwd': self.cwd,
                'text': True,
                'bufsize': 1,
            }

            # Windows-specific: hide console window
            if self._is_windows:
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                popen_kwargs['startupinfo'] = startupinfo

            self.process = subprocess.Popen(
                [self.command] + self.args,
                **popen_kwargs
            )

            # Send initialize
            response = self._send_and_receive(MCPMessage.initialize())
            if response and 'result' in response:
                return True
            return False

        except Exception as e:
            print(f"\033[31m[MCP] Gagal connect: {e}\033[0m")
            return False

    def disconnect(self):
        """Stop MCP server process"""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def send(self, message):
        """Send JSON-RPC message ke MCP server"""
        if not self.process or self.process.poll() is not None:
            raise ConnectionError("MCP server not connected")

        try:
            data = json.dumps(message) + "\n"
            self.process.stdin.write(data)
            self.process.stdin.flush()
        except Exception as e:
            raise ConnectionError(f"Failed to send: {e}")

    def receive(self, timeout=30):
        """Receive JSON-RPC response dari MCP server.

        Cross-platform implementation:
        - Unix: Gunakan select.select() untuk non-blocking read
        - Windows: Gunakan threading untuk timeout (select tidak support pipes)
        """
        if not self.process:
            raise ConnectionError("MCP server not connected")

        if self._is_windows:
            return self._receive_windows(timeout)
        else:
            return self._receive_unix(timeout)

    def _receive_unix(self, timeout=30):
        """Unix implementation menggunakan select.select()"""
        import select

        start_time = time.time()
        while time.time() - start_time < timeout:
            # Check if data available
            if self.process.stdout in select.select([self.process.stdout], [], [], 0.1)[0]:
                line = self.process.stdout.readline()
                if line:
                    try:
                        return json.loads(line.strip())
                    except json.JSONDecodeError:
                        continue

            # Check if process still running
            if self.process.poll() is not None:
                raise ConnectionError("MCP server process died")

        raise TimeoutError("MCP server response timeout")

    def _receive_windows(self, timeout=30):
        """Windows implementation menggunakan threading.

        select.select() tidak support pipes di Windows,
        jadi kita gunakan thread untuk membaca dengan timeout.
        """
        result = [None]
        error = [None]

        def read_line():
            try:
                line = self.process.stdout.readline()
                if line:
                    try:
                        result[0] = json.loads(line.strip())
                    except json.JSONDecodeError:
                        # Skip invalid JSON
                        pass
            except Exception as e:
                error[0] = e

        # Start reader thread
        reader = threading.Thread(target=read_line, daemon=True)
        reader.start()

        # Wait with timeout
        reader.join(timeout=timeout)

        if reader.is_alive():
            # Timeout - thread masih running
            raise TimeoutError("MCP server response timeout")

        if error[0]:
            raise error[0]

        if result[0] is None:
            # Check if process still running
            if self.process.poll() is not None:
                raise ConnectionError("MCP server process died")
            raise TimeoutError("No response from MCP server")

        return result[0]

    def _send_and_receive(self, message, timeout=30):
        """Send message dan tunggu response"""
        with self._lock:
            self.send(message)
            return self.receive(timeout)

    def is_connected(self):
        """Check apakah masih connected"""
        return self.process is not None and self.process.poll() is None


# =============================================================================
# MCP Transport (SSE)
# =============================================================================

class MCPSSETransport:
    """Transport untuk MCP server via SSE (Server-Sent Events)

    Features:
    - True SSE streaming support
    - Auto-reconnect on connection loss
    - Event parsing dari SSE stream
    """

    def __init__(self, url, headers=None, auto_reconnect=True, max_retries=3):
        """
        Args:
            url: URL MCP server SSE endpoint
            headers: HTTP headers
            auto_reconnect: Auto-reconnect on connection loss
            max_retries: Maximum reconnection attempts
        """
        self.url = url
        self.headers = headers or {}
        self._response_cache = {}
        self._lock = threading.Lock()
        self._connected = False
        self._auto_reconnect = auto_reconnect
        self._max_retries = max_retries
        self._retry_count = 0
        self._last_event_id = None

    def connect(self):
        """Connect ke SSE endpoint"""
        try:
            # Test connection
            response = self._send_and_receive(MCPMessage.initialize())
            if response and 'result' in response:
                self._connected = True
                self._retry_count = 0
                return True
            return False
        except Exception as e:
            print(f"\033[31m[MCP] Gagal connect SSE: {e}\033[0m")
            return False

    def disconnect(self):
        """Disconnect dari SSE endpoint"""
        self._connected = False
        self._retry_count = 0

    def send(self, message):
        """Send JSON-RPC message via HTTP POST dengan auto-reconnect"""
        for attempt in range(self._max_retries if self._auto_reconnect else 1):
            try:
                data = json.dumps(message).encode('utf-8')
                headers = {**self.headers, 'Content-Type': 'application/json'}

                # Add Last-Event-ID jika ada (untuk resume)
                if self._last_event_id:
                    headers['Last-Event-ID'] = self._last_event_id

                req = urllib.request.Request(
                    self.url,
                    data=data,
                    headers=headers,
                    method='POST'
                )

                with urllib.request.urlopen(req, timeout=30) as response:
                    content_type = response.headers.get('Content-Type', '')

                    # Check apakah response adalah SSE stream
                    if 'text/event-stream' in content_type:
                        return self._parse_sse_stream(response)
                    else:
                        # Regular JSON response
                        return json.loads(response.read().decode('utf-8'))

            except Exception as e:
                if not self._auto_reconnect or attempt == self._max_retries - 1:
                    raise ConnectionError(f"Failed to send: {e}")

                # Exponential backoff
                wait_time = min(2 ** attempt, 10)
                print(f"\033[33m[MCP] Reconnect attempt {attempt + 1} in {wait_time}s...\033[0m")
                time.sleep(wait_time)

        raise ConnectionError("Max retries exceeded")

    def _parse_sse_stream(self, response):
        """Parse SSE stream dari HTTP response.

        Format SSE:
        ```
        event: message
        id: 123
        data: {"jsonrpc": "2.0", ...}

        ```

        Returns:
            dict: Parsed JSON-RPC response
        """
        buffer = ""
        current_event = {}

        for chunk in iter(lambda: response.read1(4096), b''):
            buffer += chunk.decode('utf-8', errors='replace')

            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()

                if not line:
                    # Empty line = end of event
                    if current_event.get('data'):
                        try:
                            result = json.loads(current_event['data'])
                            # Save event ID untuk resume
                            if 'id' in current_event:
                                self._last_event_id = current_event['id']
                            return result
                        except json.JSONDecodeError:
                            pass
                    current_event = {}
                    continue

                if line.startswith('data: '):
                    current_event['data'] = line[6:]
                elif line.startswith('event: '):
                    current_event['event'] = line[7:]
                elif line.startswith('id: '):
                    current_event['id'] = line[4:]
                elif line.startswith('retry: '):
                    try:
                        current_event['retry'] = int(line[7:])
                    except ValueError:
                        pass

        # Process remaining buffer
        if current_event.get('data'):
            try:
                return json.loads(current_event['data'])
            except json.JSONDecodeError:
                pass

        return None

    def receive(self, timeout=30):
        """Receive response (sudah di-handle di send untuk HTTP)"""
        # Untuk HTTP transport, response sudah didapat di send()
        return None

    def _send_and_receive(self, message, timeout=30):
        """Send message dan tunggu response"""
        with self._lock:
            return self.send(message)

    def is_connected(self):
        """Check apakah masih connected"""
        return self._connected

    def reconnect(self):
        """Force reconnect ke SSE endpoint"""
        self.disconnect()
        return self.connect()


# =============================================================================
# MCP Client
# =============================================================================

class MCPClient:
    """Client untuk koneksi ke MCP server"""

    def __init__(self, name, transport_type, transport_config):
        """
        Args:
            name: Nama MCP server
            transport_type: 'stdio' atau 'sse'
            transport_config: Config untuk transport
        """
        self.name = name
        self.transport_type = transport_type
        self.transport_config = transport_config
        self.transport = None
        self.tools = []
        self.resources = []
        self.prompts = []
        self.server_info = None

    def connect(self):
        """Connect ke MCP server"""
        try:
            if self.transport_type == 'stdio':
                self.transport = MCPStdioTransport(
                    command=self.transport_config.get('command', ''),
                    args=self.transport_config.get('args', []),
                    env=self.transport_config.get('env', {}),
                    cwd=self.transport_config.get('cwd')
                )
            elif self.transport_type == 'sse':
                self.transport = MCPSSETransport(
                    url=self.transport_config.get('url', ''),
                    headers=self.transport_config.get('headers', {})
                )
            else:
                raise ValueError(f"Unknown transport type: {self.transport_type}")

            # Connect
            if self.transport.connect():
                # Get server info
                self._load_capabilities()
                return True
            return False

        except Exception as e:
            print(f"\033[31m[MCP] Gagal connect ke {self.name}: {e}\033[0m")
            return False

    def disconnect(self):
        """Disconnect dari MCP server"""
        if self.transport:
            self.transport.disconnect()
            self.transport = None

    def _load_capabilities(self):
        """Load tools, resources, prompts dari server"""
        try:
            # List tools
            response = self._send(MCPMessage.list_tools())
            if response and 'result' in response:
                self.tools = response['result'].get('tools', [])

            # List resources (optional)
            try:
                response = self._send(MCPMessage.list_resources())
                if response and 'result' in response:
                    self.resources = response['result'].get('resources', [])
            except:
                pass

            # List prompts (optional)
            try:
                response = self._send(MCPMessage.list_prompts())
                if response and 'result' in response:
                    self.prompts = response['result'].get('prompts', [])
            except:
                pass

        except Exception as e:
            print(f"\033[33m[MCP] Gagal load capabilities: {e}\033[0m")

    def _send(self, message, timeout=30):
        """Send message ke server"""
        if not self.transport or not self.transport.is_connected():
            raise ConnectionError(f"MCP server {self.name} not connected")
        return self.transport._send_and_receive(message, timeout)

    def list_tools(self):
        """List semua tools yang tersedia"""
        return self.tools

    def call_tool(self, name, arguments):
        """Call tool di MCP server"""
        try:
            response = self._send(MCPMessage.call_tool(name, arguments))
            if response and 'result' in response:
                result = response['result']
                # MCP tool result bisa berupa content array
                if 'content' in result:
                    contents = result['content']
                    # Gabungkan semua text content
                    texts = []
                    for content in contents:
                        if content.get('type') == 'text':
                            texts.append(content.get('text', ''))
                    return '\n'.join(texts) if texts else str(result)
                return str(result)
            elif response and 'error' in response:
                return f"Error: {response['error'].get('message', 'Unknown error')}"
            return "Error: No response from MCP server"
        except Exception as e:
            return f"Error calling MCP tool: {e}"

    def is_connected(self):
        """Check apakah masih connected"""
        return self.transport is not None and self.transport.is_connected()


# =============================================================================
# MCP Plugin (AIZU-CLI Plugin wrapper)
# =============================================================================

class MCPPlugin(Plugin):
    """Plugin wrapper untuk MCP server"""

    def __init__(self, config, mcp_client):
        """
        Args:
            config: AIZU-CLI config
            mcp_client: MCPClient instance
        """
        super().__init__(config)
        self.mcp_client = mcp_client
        self.name = mcp_client.name

    def get_tools(self):
        """Convert MCP tools ke AIZU-CLI format"""
        tools = {}

        for mcp_tool in self.mcp_client.tools:
            tool_name = mcp_tool.get('name', 'unknown')
            description = mcp_tool.get('description', '')
            input_schema = mcp_tool.get('inputSchema', {})

            # Buat wrapper function
            def make_wrapper(t_name):
                def wrapper(**kwargs):
                    return self.mcp_client.call_tool(t_name, kwargs)
                wrapper.__name__ = t_name
                wrapper.__doc__ = description
                return wrapper

            # Convert ke OpenAI function format
            schema = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": input_schema if input_schema else {
                        "type": "object",
                        "properties": {}
                    }
                }
            }

            # Prefixed name untuk avoid collision
            prefixed_name = f"mcp_{self.name}_{tool_name}"
            tools[prefixed_name] = (make_wrapper(tool_name), schema)

        return tools

    def on_startup(self):
        """Connect ke MCP server saat startup"""
        if not self.mcp_client.is_connected():
            self.mcp_client.connect()

    def on_shutdown(self):
        """Disconnect dari MCP server saat shutdown"""
        self.mcp_client.disconnect()


# =============================================================================
# MCP Manager
# =============================================================================

class MCPManager:
    """Manager untuk MCP servers"""

    def __init__(self, config):
        """
        Args:
            config: AIZU-CLI config
        """
        self.config = config
        self.clients = {}
        self.plugins = []

    def load_from_config(self, mcp_config=None):
        """
        Load MCP servers dari config.

        Config format:
        {
            "mcpServers": {
                "server-name": {
                    "command": "node",
                    "args": ["path/to/server.js"],
                    "env": {"KEY": "value"},
                    "cwd": "/path/to/dir"
                }
            }
        }

        Atau untuk SSE:
        {
            "mcpServers": {
                "server-name": {
                    "url": "http://localhost:3000/sse",
                    "headers": {"Authorization": "Bearer xxx"}
                }
            }
        }
        """
        if mcp_config is None:
            # Coba load dari config file
            mcp_config = self._load_mcp_config()

        if not mcp_config:
            return

        servers = mcp_config.get('mcpServers', {})
        for name, server_config in servers.items():
            self._add_server(name, server_config)

    def _load_mcp_config(self):
        """Load MCP config dari file"""
        # Cek beberapa lokasi
        config_paths = [
            os.path.expanduser('~/.aizu/mcp.json'),
            os.path.join(os.path.dirname(__file__), 'mcp.json'),
            os.path.expanduser('~/.config/claude/claude_desktop_config.json'),
        ]

        for path in config_paths:
            if os.path.exists(path):
                try:
                    with open(path, 'r') as f:
                        return json.load(f)
                except:
                    continue

        return None

    def _add_server(self, name, server_config):
        """Tambah MCP server"""
        try:
            # Tentukan transport type
            if 'url' in server_config:
                transport_type = 'sse'
                transport_config = {
                    'url': server_config['url'],
                    'headers': server_config.get('headers', {})
                }
            elif 'command' in server_config:
                transport_type = 'stdio'
                transport_config = {
                    'command': server_config['command'],
                    'args': server_config.get('args', []),
                    'env': server_config.get('env', {}),
                    'cwd': server_config.get('cwd')
                }
            else:
                print(f"\033[33m[MCP] Server {name}: invalid config\033[0m")
                return

            # Buat client
            client = MCPClient(name, transport_type, transport_config)
            if client.connect():
                self.clients[name] = client

                # Buat plugin wrapper
                plugin = MCPPlugin(self.config, client)
                self.plugins.append(plugin)

                print(f"\033[32m[MCP] Connected ke {name} ({len(client.tools)} tools)\033[0m")
            else:
                print(f"\033[33m[MCP] Gagal connect ke {name}\033[0m")

        except Exception as e:
            print(f"\033[31m[MCP] Error adding {name}: {e}\033[0m")

    def add_server(self, name, command=None, args=None, url=None, headers=None, env=None, cwd=None):
        """
        Tambah MCP server secara manual.

        Args:
            name: Nama server
            command: Command untuk stdio transport
            args: Arguments untuk stdio
            url: URL untuk SSE transport
            headers: Headers untuk SSE
            env: Environment variables
            cwd: Working directory
        """
        if url:
            server_config = {
                'url': url,
                'headers': headers or {}
            }
        elif command:
            server_config = {
                'command': command,
                'args': args or [],
                'env': env or {},
                'cwd': cwd
            }
        else:
            raise ValueError("Either command or url must be provided")

        self._add_server(name, server_config)

    def get_plugins(self):
        """Get semua MCP plugins"""
        return self.plugins

    def get_client(self, name):
        """Get MCP client by name"""
        return self.clients.get(name)

    def disconnect_all(self):
        """Disconnect semua servers"""
        for client in self.clients.values():
            client.disconnect()
        self.clients.clear()
        self.plugins.clear()


# =============================================================================
# Helper Functions
# =============================================================================

def load_mcp_config():
    """Load MCP config dari berbagai lokasi"""
    config_paths = [
        os.path.expanduser('~/.aizu/mcp.json'),
        os.path.join(os.path.dirname(__file__), 'mcp.json'),
        os.path.expanduser('~/.config/claude/claude_desktop_config.json'),
    ]

    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except:
                continue

    return None


def create_mcp_config_template():
    """Buat template MCP config"""
    template = {
        "mcpServers": {
            "example-stdio": {
                "command": "node",
                "args": ["path/to/server.js"],
                "env": {
                    "API_KEY": "your-api-key"
                }
            },
            "example-sse": {
                "url": "http://localhost:3000/sse",
                "headers": {
                    "Authorization": "Bearer your-token"
                }
            }
        }
    }
    return template


def save_mcp_config(config, path=None):
    """Simpan MCP config"""
    if path is None:
        path = os.path.expanduser('~/.aizu/mcp.json')

    os.makedirs(os.path.dirname(path), exist_ok=True)

    with open(path, 'w') as f:
        json.dump(config, f, indent=2)

    return path


# =============================================================================
# Popular MCP Servers (pre-configured)
# =============================================================================

POPULAR_MCP_SERVERS = {
    "filesystem": {
        "description": "Baca/tulis file dengan aman",
        "npm": "@modelcontextprotocol/server-filesystem",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem"]
    },
    "github": {
        "description": "Akses GitHub API",
        "npm": "@modelcontextprotocol/server-github",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_TOKEN": ""}
    },
    "brave-search": {
        "description": "Pencarian web via Brave",
        "npm": "@modelcontextprotocol/server-brave-search",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-brave-search"],
        "env": {"BRAVE_API_KEY": ""}
    },
    "fetch": {
        "description": "Ambil konten dari URL",
        "npm": "@modelcontextprotocol/server-fetch",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-fetch"]
    },
    "memory": {
        "description": "Persistent memory",
        "npm": "@modelcontextprotocol/server-memory",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-memory"]
    },
    "sequential-thinking": {
        "description": "Reasoning step-by-step",
        "npm": "@modelcontextprotocol/server-sequential-thinking",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"]
    }
}


def get_popular_server(name):
    """Get popular MCP server config"""
    return POPULAR_MCP_SERVERS.get(name)


def list_popular_servers():
    """List semua popular MCP servers"""
    return list(POPULAR_MCP_SERVERS.keys())
