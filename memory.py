"""
AIZU-CLI Memory System
======================

Persistent memory system seperti Claude Code.
Menyimpan fakta, preferensi, dan context secara persisten.

Fitur:
- Memory types: user, feedback, project, reference
- Cross-linking dengan [[name]] syntax
- MEMORY.md index file
- Auto-recall berdasarkan relevance
- Full-text search

Constraint: Zero external dependencies (hanya Python stdlib)
"""

import os
import re
import json
import time
from datetime import datetime
from pathlib import Path


# =============================================================================
# Memory Types
# =============================================================================

MEMORY_TYPES = {
    "user": "Siapa user (role, expertise, preferences)",
    "feedback": "Guidance dari user tentang cara kerja",
    "project": "Ongoing work, goals, constraints",
    "reference": "Pointer ke external resources (URLs, docs)",
}


# =============================================================================
# Memory Manager
# =============================================================================

class MemoryManager:
    """
    Manager untuk persistent memory system.

    Memory disimpan sebagai file individual di ~/.aizu/memory/
    dengan frontmatter (YAML-like) dan body content.
    """

    def __init__(self, memory_dir=None):
        """
        Args:
            memory_dir: Directory untuk memory files (default: ~/.aizu/memory/)
        """
        self.memory_dir = memory_dir or os.path.expanduser("~/.aizu/memory")
        self.index_file = os.path.join(self.memory_dir, "MEMORY.md")
        os.makedirs(self.memory_dir, exist_ok=True)

    def save(self, name, content, memory_type="project", description=""):
        """
        Simpan atau update memory.

        Args:
            name: Slug name (short-kebab-case)
            content: Memory content (bisa multi-line)
            memory_type: Tipe memory (user, feedback, project, reference)
            description: One-line summary untuk index

        Returns:
            str: Path ke file yang disimpan
        """
        # Validate name
        name = self._sanitize_name(name)
        if not name:
            raise ValueError("Name tidak boleh kosong")

        # Validate type
        if memory_type not in MEMORY_TYPES:
            memory_type = "project"

        # Build file path
        filepath = os.path.join(self.memory_dir, f"{name}.md")

        # Build content with frontmatter
        now = datetime.now().strftime("%Y-%m-%d")
        frontmatter = f"""---
name: {name}
description: {description or content[:80]}
metadata:
  type: {memory_type}
  created: {now}
  updated: {now}
---

{content}
"""

        # Write file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(frontmatter)

        # Update index
        self._update_index()

        return filepath

    def get(self, name):
        """
        Ambil memory berdasarkan name.

        Args:
            name: Memory name slug

        Returns:
            dict atau None: Memory data dengan frontmatter dan content
        """
        name = self._sanitize_name(name)
        filepath = os.path.join(self.memory_dir, f"{name}.md")

        if not os.path.exists(filepath):
            return None

        return self._read_memory_file(filepath)

    def search(self, query, limit=5):
        """
        Cari memory berdasarkan query (full-text search).

        Args:
            query: Search query
            limit: Max results

        Returns:
            list: List of memory dicts yang match
        """
        query_lower = query.lower()
        results = []

        for filename in os.listdir(self.memory_dir):
            if not filename.endswith('.md') or filename == 'MEMORY.md':
                continue

            filepath = os.path.join(self.memory_dir, filename)
            memory = self._read_memory_file(filepath)
            if not memory:
                continue

            # Calculate relevance score
            score = 0
            name = memory.get('name', '')
            desc = memory.get('description', '')
            content = memory.get('content', '')

            # Name match (highest weight)
            if query_lower in name.lower():
                score += 10

            # Description match
            if query_lower in desc.lower():
                score += 5

            # Content match
            if query_lower in content.lower():
                score += 3

            # Type match
            if query_lower in memory.get('type', '').lower():
                score += 2

            if score > 0:
                memory['score'] = score
                results.append(memory)

        # Sort by score
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return results[:limit]

    def list_all(self, memory_type=None):
        """
        List semua memories.

        Args:
            memory_type: Filter by type (None = all)

        Returns:
            list: List of memory dicts
        """
        memories = []

        for filename in os.listdir(self.memory_dir):
            if not filename.endswith('.md') or filename == 'MEMORY.md':
                continue

            filepath = os.path.join(self.memory_dir, filename)
            memory = self._read_memory_file(filepath)
            if not memory:
                continue

            if memory_type and memory.get('type') != memory_type:
                continue

            memories.append(memory)

        # Sort by updated date
        memories.sort(key=lambda x: x.get('updated', ''), reverse=True)
        return memories

    def delete(self, name):
        """
        Hapus memory.

        Args:
            name: Memory name slug

        Returns:
            bool: True jika berhasil dihapus
        """
        name = self._sanitize_name(name)
        filepath = os.path.join(self.memory_dir, f"{name}.md")

        if os.path.exists(filepath):
            os.remove(filepath)
            self._update_index()
            return True
        return False

    def get_related(self, name, limit=3):
        """
        Cari memory yang ter-link dengan memory tertentu.

        Args:
            name: Memory name
            limit: Max results

        Returns:
            list: List of related memory dicts
        """
        memory = self.get(name)
        if not memory:
            return []

        content = memory.get('content', '')
        # Find [[links]]
        links = re.findall(r'\[\[(\S+)\]\]', content)

        related = []
        for link_name in links[:limit]:
            related_memory = self.get(link_name)
            if related_memory:
                related.append(related_memory)

        return related

    def recall(self, context, limit=3):
        """
        Auto-recall: Cari memory yang relevan dengan context.

        Dipanggil sebelum LLM call untuk inject relevant memories.

        Args:
            context: Current conversation context (user message)
            limit: Max memories to recall

        Returns:
            str: Formatted memory context untuk inject ke system prompt
        """
        # Extract keywords from context
        keywords = self._extract_keywords(context)
        if not keywords:
            return ""

        # Search for each keyword
        found = {}
        for keyword in keywords:
            results = self.search(keyword, limit=2)
            for r in results:
                name = r.get('name', '')
                if name not in found or r.get('score', 0) > found[name].get('score', 0):
                    found[name] = r

        # Sort by score and take top N
        sorted_memories = sorted(found.values(), key=lambda x: x.get('score', 0), reverse=True)[:limit]

        if not sorted_memories:
            return ""

        # Format for injection
        parts = ["## Relevant Memories"]
        for mem in sorted_memories:
            name = mem.get('name', 'unknown')
            mem_type = mem.get('type', 'project')
            desc = mem.get('description', '')
            content = mem.get('content', '')[:200]  # Truncate

            parts.append(f"\n### [{mem_type}] {name}")
            if desc:
                parts.append(f"Description: {desc}")
            parts.append(content)

        return "\n".join(parts)

    def _read_memory_file(self, filepath):
        """Baca memory file dan parse frontmatter."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse frontmatter
            if content.startswith('---'):
                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = parts[1].strip()
                    body = parts[2].strip()

                    # Parse YAML-like frontmatter
                    data = self._parse_frontmatter(frontmatter)

                    # Extract metadata sub-keys to top level
                    metadata = data.get('metadata', {})
                    if isinstance(metadata, dict):
                        data['type'] = metadata.get('type', 'project')
                        data['created'] = metadata.get('created', '')
                        data['updated'] = metadata.get('updated', '')

                    data['content'] = body
                    data['filepath'] = filepath
                    return data

            # No frontmatter - treat whole content as body
            return {
                'name': os.path.basename(filepath).replace('.md', ''),
                'content': content,
                'filepath': filepath,
                'type': 'project',
            }
        except Exception as e:
            print(f"[Memory] Error reading {filepath}: {e}")
            return None

    def _parse_frontmatter(self, text):
        """Parse YAML-like frontmatter (simple key-value with nested support)."""
        data = {}
        current_key = None
        current_value = []
        nested_key = None
        nested_data = {}

        for line in text.split('\n'):
            line = line.rstrip()

            # Check for nested key (2-space indent)
            nested_match = re.match(r'^  (\w+):\s*(.*)', line)
            if nested_match and current_key:
                # This is a nested key under current_key
                if nested_key and nested_data is not None:
                    nested_data[nested_key] = '\n'.join(current_value).strip() if current_value else ''
                nested_key = nested_match.group(1)
                current_value = [nested_match.group(2)] if nested_match.group(2) else []
                if not isinstance(nested_data, dict):
                    nested_data = {}
                continue

            # Check for top-level key: value
            match = re.match(r'^(\w+):\s*(.*)', line)
            if match:
                # Save previous key (with nested data if any)
                if current_key:
                    if nested_key and nested_data is not None:
                        nested_data[nested_key] = '\n'.join(current_value).strip() if current_value else ''
                        data[current_key] = nested_data
                    elif current_value:
                        data[current_key] = current_value[0] if len(current_value) == 1 else '\n'.join(current_value).strip()
                    else:
                        data[current_key] = ''
                    nested_key = None
                    nested_data = {}

                current_key = match.group(1)
                current_value = [match.group(2)] if match.group(2) else []
            elif current_key and not nested_key and line.startswith('  '):
                # Continuation of previous value (indented but not nested)
                current_value.append(line.strip())

        # Save last key
        if current_key:
            if nested_key and isinstance(nested_data, dict):
                nested_data[nested_key] = '\n'.join(current_value).strip() if current_value else ''
                data[current_key] = nested_data
            elif current_value:
                data[current_key] = current_value[0] if len(current_value) == 1 else '\n'.join(current_value).strip()
            else:
                data[current_key] = ''

        return data

    def _update_index(self):
        """Update MEMORY.md index file."""
        memories = self.list_all()

        lines = ["# AIZU Memory Index", ""]
        lines.append(f"_Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
        lines.append("")

        # Group by type
        by_type = {}
        for mem in memories:
            mem_type = mem.get('type', 'project')
            if mem_type not in by_type:
                by_type[mem_type] = []
            by_type[mem_type].append(mem)

        # Write each type section
        for mem_type in ['user', 'feedback', 'project', 'reference']:
            if mem_type not in by_type:
                continue

            type_label = MEMORY_TYPES.get(mem_type, mem_type)
            lines.append(f"## {mem_type.title()}")
            lines.append(f"_{type_label}_")
            lines.append("")

            for mem in by_type[mem_type]:
                name = mem.get('name', 'unknown')
                desc = mem.get('description', '')[:60]
                lines.append(f"- [{name}]({name}.md) — {desc}")

            lines.append("")

        # Write to file
        with open(self.index_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

    def _sanitize_name(self, name):
        """Sanitize memory name ke kebab-case."""
        if not name:
            return ""
        # Convert to lowercase, replace spaces and special chars with hyphens
        name = re.sub(r'[^a-z0-9\-_]', '-', name.lower())
        # Remove multiple hyphens
        name = re.sub(r'-+', '-', name)
        # Remove leading/trailing hyphens
        name = name.strip('-')
        return name[:64]  # Max 64 chars

    def _extract_keywords(self, text):
        """Extract keywords dari text untuk search."""
        # Simple keyword extraction
        # Remove common words, keep significant ones
        stop_words = {
            'yang', 'dan', 'di', 'ke', 'dari', 'ini', 'itu', 'untuk',
            'dengan', 'pada', 'adalah', 'akan', 'oleh', 'juga', 'sudah',
            'ada', 'bisa', 'tidak', 'belum', 'lebih', 'sangat', 'seperti',
            'the', 'is', 'at', 'which', 'on', 'and', 'a', 'an', 'it',
            'to', 'for', 'of', 'in', 'with', 'that', 'this', 'be',
        }

        # Tokenize
        words = re.findall(r'\w+', text.lower())

        # Filter stop words and short words
        keywords = [w for w in words if w not in stop_words and len(w) > 2]

        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        return unique[:10]  # Max 10 keywords


# =============================================================================
# Memory Tools (untuk registrasi ke AIZU-CLI)
# =============================================================================

def create_memory_tools(memory_mgr):
    """
    Buat tool functions untuk memory system.

    Args:
        memory_mgr: MemoryManager instance

    Returns:
        dict: {tool_name: (function, schema)}
    """
    tools = {}

    # memory_save
    def memory_save(name, content, memory_type="project", description=""):
        """Simpan fakta/preferensi ke persistent memory."""
        try:
            filepath = memory_mgr.save(name, content, memory_type, description)
            return f"✅ Memory '{name}' tersimpan di {filepath}"
        except Exception as e:
            return f"❌ Error: {e}"

    tools["memory_save"] = (memory_save, {
        "type": "function",
        "function": {
            "name": "memory_save",
            "description": "Simpan fakta, preferensi, atau context ke persistent memory. "
                           "Memory types: user (siapa user), feedback (guidance), "
                           "project (ongoing work), reference (external resources).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nama memory (kebab-case, contoh: 'python-preference')"
                    },
                    "content": {
                        "type": "string",
                        "description": "Isi memory (bisa multi-line)"
                    },
                    "memory_type": {
                        "type": "string",
                        "description": "Tipe memory: user, feedback, project, reference",
                        "enum": ["user", "feedback", "project", "reference"]
                    },
                    "description": {
                        "type": "string",
                        "description": "Satu baris summary untuk index"
                    }
                },
                "required": ["name", "content"]
            }
        }
    })

    # memory_search
    def memory_search(query, limit=5):
        """Cari memory berdasarkan query."""
        results = memory_mgr.search(query, limit)
        if not results:
            return f"Tidak ditemukan memory untuk: {query}"

        lines = [f"🔍 Ditemukan {len(results)} memory:"]
        for r in results:
            name = r.get('name', 'unknown')
            mem_type = r.get('type', 'project')
            desc = r.get('description', '')[:60]
            content = r.get('content', '')[:100]
            lines.append(f"\n  [{mem_type}] {name}")
            if desc:
                lines.append(f"  {desc}")
            lines.append(f"  {content}...")
        return "\n".join(lines)

    tools["memory_search"] = (memory_search, {
        "type": "function",
        "function": {
            "name": "memory_search",
            "description": "Cari memory berdasarkan keyword. Berguna untuk recall fakta/preferensi sebelumnya.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Kata kunci pencarian"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Jumlah maksimal hasil (default 5)"
                    }
                },
                "required": ["query"]
            }
        }
    })

    # memory_list
    def memory_list(memory_type=None):
        """List semua memory tersimpan."""
        memories = memory_mgr.list_all(memory_type)
        if not memories:
            return "Tidak ada memory tersimpan."

        lines = [f"📚 Memory ({len(memories)}):"]
        for m in memories:
            name = m.get('name', 'unknown')
            mem_type = m.get('type', 'project')
            desc = m.get('description', '')[:50]
            updated = m.get('updated', '')[:10]
            lines.append(f"  [{mem_type}] {name} — {desc} ({updated})")
        return "\n".join(lines)

    tools["memory_list"] = (memory_list, {
        "type": "function",
        "function": {
            "name": "memory_list",
            "description": "List semua memory yang tersimpan. Bisa filter berdasarkan tipe.",
            "parameters": {
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "description": "Filter by type (opsional): user, feedback, project, reference"
                    }
                }
            }
        }
    })

    # memory_get
    def memory_get(name):
        """Ambil detail memory berdasarkan name."""
        memory = memory_mgr.get(name)
        if not memory:
            return f"Memory '{name}' tidak ditemukan."

        lines = [
            f"📝 Memory: {memory.get('name', 'unknown')}",
            f"Type: {memory.get('type', 'project')}",
            f"Description: {memory.get('description', '-')}",
            f"Updated: {memory.get('updated', '-')}",
            "",
            memory.get('content', '(empty)')
        ]
        return "\n".join(lines)

    tools["memory_get"] = (memory_get, {
        "type": "function",
        "function": {
            "name": "memory_get",
            "description": "Ambil detail memory berdasarkan nama.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nama memory"
                    }
                },
                "required": ["name"]
            }
        }
    })

    # memory_delete
    def memory_delete(name):
        """Hapus memory."""
        if memory_mgr.delete(name):
            return f"✅ Memory '{name}' dihapus"
        return f"❌ Memory '{name}' tidak ditemukan"

    tools["memory_delete"] = (memory_delete, {
        "type": "function",
        "function": {
            "name": "memory_delete",
            "description": "Hapus memory yang tersimpan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Nama memory yang akan dihapus"
                    }
                },
                "required": ["name"]
            }
        }
    })

    return tools


# =============================================================================
# Singleton Instance
# =============================================================================

_global_memory_manager = None


def get_memory_manager(memory_dir=None):
    """Get atau buat global MemoryManager instance."""
    global _global_memory_manager
    if _global_memory_manager is None:
        _global_memory_manager = MemoryManager(memory_dir)
    return _global_memory_manager


def reset_memory_manager():
    """Reset global MemoryManager (untuk testing)."""
    global _global_memory_manager
    _global_memory_manager = None
