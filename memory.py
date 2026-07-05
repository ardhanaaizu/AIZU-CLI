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
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
            'could', 'should', 'may', 'might', 'can', 'shall',
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

    # -------------------------------------------------------------------------
    # Smart Recall dengan TF-IDF Scoring
    # -------------------------------------------------------------------------
    def smart_recall(self, context, limit=5, boost_recent=True):
        """Recall memory yang relevan dengan TF-IDF scoring.

        Lebih cerdas dari search() biasa karena:
        1. TF-IDF weighting (term frequency * inverse document frequency)
        2. Recency boosting (memory baru dapat bonus)
        3. Type-based boosting (user/feedback > project > reference)
        4. Multi-keyword search dengan combinasi score

        Args:
            context: Current conversation context (user message)
            limit: Max memories to recall
            boost_recent: Jika True, berikan bonus untuk memory baru

        Returns:
            list: List of memory dicts yang relevan, sorted by score
        """
        keywords = self._extract_keywords(context)
        if not keywords:
            return []

        # Load semua memories
        all_memories = self.list_all()
        if not all_memories:
            return []

        # Build document frequency (DF) untuk IDF
        df = {}  # keyword -> jumlah memory yang mengandung keyword
        for mem in all_memories:
            content_lower = (mem.get('content', '') + ' ' + mem.get('description', '')).lower()
            for kw in keywords:
                if kw in content_lower:
                    df[kw] = df.get(kw, 0) + 1

        total_docs = len(all_memories)

        # Hitung score untuk setiap memory
        scored = []
        now = time.time()

        for mem in all_memories:
            score = 0.0
            content = mem.get('content', '')
            desc = mem.get('description', '')
            name = mem.get('name', '')
            mem_type = mem.get('type', 'project')
            updated = mem.get('updated', '')

            combined_text = f"{name} {desc} {content}".lower()

            # TF-IDF scoring untuk setiap keyword
            for kw in keywords:
                if kw not in combined_text:
                    continue

                # Term Frequency (TF)
                tf = combined_text.count(kw)
                if tf == 0:
                    continue

                # Inverse Document Frequency (IDF)
                df_count = df.get(kw, 0)
                if df_count == 0:
                    idf = 0
                else:
                    idf = 1.0 + (total_docs / df_count)  # Smoothed IDF

                # TF-IDF score
                score += tf * idf

            # Recency boost
            if boost_recent and updated:
                try:
                    updated_dt = datetime.strptime(updated[:10], "%Y-%m-%d")
                    days_old = (datetime.now() - updated_dt).days
                    if days_old < 7:
                        score *= 1.5  # 50% boost untuk memory < 1 minggu
                    elif days_old < 30:
                        score *= 1.2  # 20% boost untuk memory < 1 bulan
                except (ValueError, TypeError):
                    pass

            # Type boost
            type_boost = {
                'user': 1.3,
                'feedback': 1.2,
                'project': 1.0,
                'reference': 0.8
            }
            score *= type_boost.get(mem_type, 1.0)

            if score > 0:
                mem['score'] = score
                scored.append(mem)

        # Sort by score
        scored.sort(key=lambda x: x.get('score', 0), reverse=True)
        return scored[:limit]

    # -------------------------------------------------------------------------
    # Memory Deduplication
    # -------------------------------------------------------------------------
    def deduplicate(self, threshold=0.8, dry_run=False):
        """Detect dan merge duplicate memories.

        Menggunakan fuzzy string matching untuk mendeteksi memories
        yang mirip dan bisa di-merge.

        Args:
            threshold: Similarity threshold (0-1, default 0.8)
            dry_run: Jika True, hanya lapor tanpa menghapus

        Returns:
            dict: Report dengan duplicates_found, merged, details
        """
        all_memories = self.list_all()
        if len(all_memories) < 2:
            return {"duplicates_found": 0, "merged": 0, "details": []}

        duplicates = []
        checked = set()

        # Compare setiap pair of memories
        for i, mem1 in enumerate(all_memories):
            if mem1['name'] in checked:
                continue

            for j, mem2 in enumerate(all_memories[i+1:], i+1):
                if mem2['name'] in checked:
                    continue

                # Calculate similarity
                similarity = self._calculate_similarity(
                    mem1.get('content', ''),
                    mem2.get('content', '')
                )

                if similarity >= threshold:
                    duplicates.append({
                        'mem1': mem1['name'],
                        'mem2': mem2['name'],
                        'similarity': similarity,
                        'keep': mem1['name'],  # Keep yang lebih lama
                        'remove': mem2['name']
                    })
                    checked.add(mem2['name'])

        # Execute merges jika bukan dry_run
        merged = 0
        if not dry_run:
            for dup in duplicates:
                try:
                    self.delete(dup['remove'])
                    merged += 1
                except Exception:
                    pass

        return {
            "duplicates_found": len(duplicates),
            "merged": merged,
            "details": duplicates
        }

    def _calculate_similarity(self, text1, text2):
        """Hitung similarity antara dua text menggunakan Jaccard similarity.

        Args:
            text1: Text pertama
            text2: Text kedua

        Returns:
            float: Similarity score (0-1)
        """
        if not text1 or not text2:
            return 0.0

        # Tokenize ke words
        words1 = set(re.findall(r'\w+', text1.lower()))
        words2 = set(re.findall(r'\w+', text2.lower()))

        # Jaccard similarity
        intersection = words1 & words2
        union = words1 | words2

        if not union:
            return 0.0

        return len(intersection) / len(union)

    # -------------------------------------------------------------------------
    # Garbage Collection
    # -------------------------------------------------------------------------
    def garbage_collect(self, max_memories=100, max_age_days=90, min_access_count=0):
        """Clean old/unused memories.

        Hapus memories yang:
        1. Lebih tua dari max_age_days DAN tidak pernah diakses
        2. Melebihi max_memories limit (hapus yang paling lama)
        3. Punya access_count < min_access_count

        Args:
            max_memories: Maximum memories yang diizinkan (0 = unlimited)
            max_age_days: Maximum umur dalam hari (0 = unlimited)
            min_access_count: Minimum access count untuk retain

        Returns:
            dict: Report dengan checked, removed, retained
        """
        all_memories = self.list_all()
        if not all_memories:
            return {"checked": 0, "removed": 0, "retained": 0}

        to_remove = []
        now = datetime.now()

        for mem in all_memories:
            should_remove = False
            reason = ""

            # Check age
            if max_age_days > 0:
                created = mem.get('created', '')
                if created:
                    try:
                        created_dt = datetime.strptime(created[:10], "%Y-%m-%d")
                        age_days = (now - created_dt).days
                        if age_days > max_age_days:
                            # Hanya hapus jika access_count rendah
                            access_count = mem.get('access_count', 0)
                            if access_count < min_access_count + 1:
                                should_remove = True
                                reason = f"old ({age_days} days)"
                    except (ValueError, TypeError):
                        pass

            # Check access count
            if min_access_count > 0 and not should_remove:
                access_count = mem.get('access_count', 0)
                if access_count < min_access_count:
                    should_remove = True
                    reason = f"low access ({access_count})"

            if should_remove:
                to_remove.append({
                    'name': mem['name'],
                    'reason': reason
                })

        # Jika masih melebihi max_memories, hapus yang paling lama
        if max_memories > 0 and len(all_memories) - len(to_remove) > max_memories:
            # Sort by updated date
            remaining = [m for m in all_memories if m['name'] not in [r['name'] for r in to_remove]]
            remaining.sort(key=lambda x: x.get('updated', ''))

            # Remove excess
            excess_count = len(remaining) - max_memories
            for mem in remaining[:excess_count]:
                if mem['name'] not in [r['name'] for r in to_remove]:
                    to_remove.append({
                        'name': mem['name'],
                        'reason': 'excess'
                    })

        # Execute removals
        removed = 0
        for item in to_remove:
            try:
                self.delete(item['name'])
                removed += 1
            except Exception:
                pass

        return {
            "checked": len(all_memories),
            "removed": removed,
            "retained": len(all_memories) - removed,
            "details": to_remove
        }

    # -------------------------------------------------------------------------
    # Auto-Extract Memories from Conversation
    # -------------------------------------------------------------------------
    def auto_extract(self, messages, llm_func=None):
        """Otomatis extract fakta penting dari conversation.

        Mendeteksi:
        1. User preferences (suka X, lebih suka Y)
        2. Project decisions (kita putuskan untuk X)
        3. Important facts (X adalah Y)
        4. Technical info (file X ada di Y)

        Args:
            messages: List of conversation messages
            llm_func: Optional LLM function untuk extraction (unused for now)

        Returns:
            list: List of extracted memories (belum di-save)
        """
        extracted = []

        for msg in messages:
            if msg.get('role') != 'user':
                continue

            content = msg.get('content', '')
            content_lower = content.lower()

            # Detect preferences
            pref_patterns = [
                (r'(?:suka|suka banget|lebih suka|prefer|favorite)\s+(.+?)(?:\.|,|$)', 'preference'),
                (r'(?:tidak suka|ga suka|hate|benci)\s+(.+?)(?:\.|,|$)', 'dislike'),
                (r'(?:selalu|always)\s+(?:gunakan|pakai|use)\s+(.+?)(?:\.|,|$)', 'preference'),
            ]

            for pattern, pref_type in pref_patterns:
                matches = re.findall(pattern, content_lower)
                for match in matches:
                    extracted.append({
                        'type': 'user',
                        'content': f"User {pref_type}: {match.strip()}",
                        'source': 'auto_extract'
                    })

            # Detect decisions
            decision_patterns = [
                r'(?:kita|kami|let\'s)\s+(?:putuskan|decide|pilih|choose)\s+(?:untuk|to)?\s*(.+?)(?:\.|$)',
                r'(?:akan|will)\s+(?:menggunakan|pakai|use|implement)\s+(.+?)(?:\.|$)',
            ]

            for pattern in decision_patterns:
                matches = re.findall(pattern, content_lower)
                for match in matches:
                    extracted.append({
                        'type': 'project',
                        'content': f"Decision: {match.strip()}",
                        'source': 'auto_extract'
                    })

            # Detect facts
            fact_patterns = [
                r'(.+?)\s+(?:adalah|is|merupakan)\s+(.+?)(?:\.|$)',
                r'(?:file|folder|directory)\s+(.+?)\s+(?:ada di|terletak di|located at)\s+(.+?)(?:\.|$)',
            ]

            for pattern in fact_patterns:
                matches = re.findall(pattern, content_lower)
                for match in matches:
                    if len(match) == 2:
                        extracted.append({
                            'type': 'reference',
                            'content': f"{match[0].strip()} = {match[1].strip()}",
                            'source': 'auto_extract'
                        })

        return extracted


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
