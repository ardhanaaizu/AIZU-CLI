"""
Filesystem Plugin untuk AIZU-CLI
=================================

Menambahkan operasi filesystem yang aman dan lengkap.
Mirip dengan MCP Filesystem server tapi native Python.
"""

import os
import json
import glob
import shutil
from pathlib import Path
from plugins import Plugin


class FilesystemPlugin(Plugin):
    """Plugin untuk operasi filesystem"""

    def get_tools(self):
        """Register filesystem tools"""
        tools = {}

        # 1. read_file - Baca file dengan encoding handling
        def read_file(path, encoding="utf-8"):
            """Baca isi file dengan aman"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: File tidak ditemukan: {path}"
                if not os.path.isfile(path):
                    return f"Error: Bukan file: {path}"

                with open(path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()
                return content
            except Exception as e:
                return f"Error reading file: {e}"

        tools["fs_read_file"] = (read_file, {
            "type": "function",
            "function": {
                "name": "fs_read_file",
                "description": "Baca isi file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path ke file"
                        },
                        "encoding": {
                            "type": "string",
                            "description": "Encoding file (default: utf-8)",
                            "default": "utf-8"
                        }
                    },
                    "required": ["path"]
                }
            }
        })

        # 2. write_file - Tulis file dengan backup
        def write_file(path, content, backup=True):
            """Tulis file dengan optional backup"""
            try:
                path = os.path.expanduser(path)

                # Buat backup jika file exists
                if backup and os.path.exists(path):
                    backup_path = f"{path}.bak"
                    shutil.copy2(path, backup_path)

                # Buat direktori jika belum ada
                os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)

                return f"File written: {path}"
            except Exception as e:
                return f"Error writing file: {e}"

        tools["fs_write_file"] = (write_file, {
            "type": "function",
            "function": {
                "name": "fs_write_file",
                "description": "Tulis konten ke file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path ke file"
                        },
                        "content": {
                            "type": "string",
                            "description": "Konten yang akan ditulis"
                        },
                        "backup": {
                            "type": "boolean",
                            "description": "Buat backup sebelum write (default: true)",
                            "default": True
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        })

        # 3. edit_file - Edit file dengan find/replace
        def edit_file(path, old_text, new_text, count=0):
            """Edit file dengan find and replace"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: File tidak ditemukan: {path}"

                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()

                if old_text not in content:
                    return f"Error: Text tidak ditemukan di {path}"

                # Backup
                backup_path = f"{path}.bak"
                shutil.copy2(path, backup_path)

                # Replace
                if count > 0:
                    new_content = content.replace(old_text, new_text, count)
                else:
                    new_content = content.replace(old_text, new_text)

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                return f"File edited: {path}"
            except Exception as e:
                return f"Error editing file: {e}"

        tools["fs_edit_file"] = (edit_file, {
            "type": "function",
            "function": {
                "name": "fs_edit_file",
                "description": "Edit file dengan find and replace",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path ke file"
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Text yang akan diganti"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Text pengganti"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Jumlah replacement (0 = all)",
                            "default": 0
                        }
                    },
                    "required": ["path", "old_text", "new_text"]
                }
            }
        })

        # 4. list_directory - List isi direktori
        def list_directory(path=".", pattern="*", show_hidden=False, recursive=False):
            """List isi direktori"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: Directory tidak ditemukan: {path}"
                if not os.path.isdir(path):
                    return f"Error: Bukan directory: {path}"

                items = []

                if recursive:
                    for root, dirs, files in os.walk(path):
                        for name in files + dirs:
                            full_path = os.path.join(root, name)
                            rel_path = os.path.relpath(full_path, path)
                            if not show_hidden and name.startswith('.'):
                                continue
                            if glob.fnmatch.fnmatch(name, pattern):
                                items.append(rel_path)
                else:
                    for name in os.listdir(path):
                        if not show_hidden and name.startswith('.'):
                            continue
                        if glob.fnmatch.fnmatch(name, pattern):
                            items.append(name)

                items.sort()

                # Format output
                result = []
                for item in items[:100]:  # Limit 100 items
                    full_path = os.path.join(path, item)
                    if os.path.isdir(full_path):
                        result.append(f"📁 {item}/")
                    else:
                        size = os.path.getsize(full_path)
                        result.append(f"📄 {item} ({size} bytes)")

                if len(items) > 100:
                    result.append(f"\n... and {len(items) - 100} more items")

                return '\n'.join(result) if result else "Empty directory"
            except Exception as e:
                return f"Error listing directory: {e}"

        tools["fs_list_directory"] = (list_directory, {
            "type": "function",
            "function": {
                "name": "fs_list_directory",
                "description": "List isi direktori",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path direktori (default: current)",
                            "default": "."
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern untuk filter",
                            "default": "*"
                        },
                        "show_hidden": {
                            "type": "boolean",
                            "description": "Tampilkan file hidden",
                            "default": False
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "List recursive",
                            "default": False
                        }
                    },
                    "required": []
                }
            }
        })

        # 5. search_files - Cari file berdasarkan nama/konten
        def search_files(path=".", pattern="*", content_search=None, max_results=50):
            """Cari file berdasarkan nama atau konten"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: Path tidak ditemukan: {path}"

                results = []
                count = 0

                for root, dirs, files in os.walk(path):
                    # Skip hidden dirs
                    dirs[:] = [d for d in dirs if not d.startswith('.')]

                    for name in files:
                        if count >= max_results:
                            break

                        full_path = os.path.join(root, name)

                        # Check filename pattern
                        if glob.fnmatch.fnmatch(name, pattern):
                            if content_search:
                                # Search in content
                                try:
                                    with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read()
                                    if content_search.lower() in content.lower():
                                        results.append(full_path)
                                        count += 1
                                except:
                                    pass
                            else:
                                results.append(full_path)
                                count += 1

                    if count >= max_results:
                        break

                if results:
                    return '\n'.join(results)
                return "No files found"
            except Exception as e:
                return f"Error searching files: {e}"

        tools["fs_search_files"] = (search_files, {
            "type": "function",
            "function": {
                "name": "fs_search_files",
                "description": "Cari file berdasarkan nama atau konten",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path untuk search",
                            "default": "."
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Glob pattern untuk filename",
                            "default": "*"
                        },
                        "content_search": {
                            "type": "string",
                            "description": "Text yang dicari di dalam file"
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maksimal hasil",
                            "default": 50
                        }
                    },
                    "required": []
                }
            }
        })

        # 6. get_file_info - Info detail file
        def get_file_info(path):
            """Dapatkan info detail file/direktori"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: Path tidak ditemukan: {path}"

                stat = os.stat(path)
                info = {
                    "path": path,
                    "name": os.path.basename(path),
                    "type": "directory" if os.path.isdir(path) else "file",
                    "size": stat.st_size,
                    "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                    "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_ctime)),
                    "permissions": oct(stat.st_mode)[-3:]
                }

                if os.path.isfile(path):
                    # Get line count
                    try:
                        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = sum(1 for _ in f)
                        info["lines"] = lines
                    except:
                        pass

                return json.dumps(info, indent=2)
            except Exception as e:
                return f"Error getting file info: {e}"

        tools["fs_get_file_info"] = (get_file_info, {
            "type": "function",
            "function": {
                "name": "fs_get_file_info",
                "description": "Dapatkan info detail file/direktori",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path ke file/direktori"
                        }
                    },
                    "required": ["path"]
                }
            }
        })

        # 7. copy_file - Copy file/direktori
        def copy_file(source, destination, overwrite=False):
            """Copy file atau direktori"""
            try:
                source = os.path.expanduser(source)
                destination = os.path.expanduser(destination)

                if not os.path.exists(source):
                    return f"Error: Source tidak ditemukan: {source}"

                if os.path.exists(destination) and not overwrite:
                    return f"Error: Destination sudah ada: {destination} (gunakan overwrite=True)"

                if os.path.isdir(source):
                    shutil.copytree(source, destination)
                else:
                    os.makedirs(os.path.dirname(destination) if os.path.dirname(destination) else '.', exist_ok=True)
                    shutil.copy2(source, destination)

                return f"Copied: {source} -> {destination}"
            except Exception as e:
                return f"Error copying: {e}"

        tools["fs_copy_file"] = (copy_file, {
            "type": "function",
            "function": {
                "name": "fs_copy_file",
                "description": "Copy file atau direktori",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "Path source"
                        },
                        "destination": {
                            "type": "string",
                            "description": "Path destination"
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "Overwrite jika sudah ada",
                            "default": False
                        }
                    },
                    "required": ["source", "destination"]
                }
            }
        })

        # 8. move_file - Move/rename file
        def move_file(source, destination):
            """Move atau rename file"""
            try:
                source = os.path.expanduser(source)
                destination = os.path.expanduser(destination)

                if not os.path.exists(source):
                    return f"Error: Source tidak ditemukan: {source}"

                os.makedirs(os.path.dirname(destination) if os.path.dirname(destination) else '.', exist_ok=True)
                shutil.move(source, destination)

                return f"Moved: {source} -> {destination}"
            except Exception as e:
                return f"Error moving: {e}"

        tools["fs_move_file"] = (move_file, {
            "type": "function",
            "function": {
                "name": "fs_move_file",
                "description": "Move atau rename file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "source": {
                            "type": "string",
                            "description": "Path source"
                        },
                        "destination": {
                            "type": "string",
                            "description": "Path destination"
                        }
                    },
                    "required": ["source", "destination"]
                }
            }
        })

        # 9. delete_file - Hapus file/direktori
        def delete_file(path, recursive=False):
            """Hapus file atau direktori"""
            try:
                path = os.path.expanduser(path)
                if not os.path.exists(path):
                    return f"Error: Path tidak ditemukan: {path}"

                if os.path.isdir(path):
                    if recursive:
                        shutil.rmtree(path)
                    else:
                        os.rmdir(path)
                else:
                    os.remove(path)

                return f"Deleted: {path}"
            except Exception as e:
                return f"Error deleting: {e}"

        tools["fs_delete_file"] = (delete_file, {
            "type": "function",
            "function": {
                "name": "fs_delete_file",
                "description": "Hapus file atau direktori",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path yang akan dihapus"
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "Hapus recursive (untuk direktori)",
                            "default": False
                        }
                    },
                    "required": ["path"]
                }
            }
        })

        # 10. create_directory - Buat direktori
        def create_directory(path, parents=True):
            """Buat direktori baru"""
            try:
                path = os.path.expanduser(path)
                os.makedirs(path, exist_ok=parents)
                return f"Directory created: {path}"
            except Exception as e:
                return f"Error creating directory: {e}"

        tools["fs_create_directory"] = (create_directory, {
            "type": "function",
            "function": {
                "name": "fs_create_directory",
                "description": "Buat direktori baru",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path direktori baru"
                        },
                        "parents": {
                            "type": "boolean",
                            "description": "Buat parent directories juga",
                            "default": True
                        }
                    },
                    "required": ["path"]
                }
            }
        })

        return tools


def create(config):
    """Factory function untuk create plugin instance"""
    return FilesystemPlugin(config)
