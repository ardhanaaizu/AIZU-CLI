"""
Memory Plugin untuk AIZU-CLI
=============================

Sistem persistent memory untuk menyimpan dan mengingat informasi.
Menyimpan dalam format JSON di ~/.aizu/memory.json
"""

import os
import json
import time
from datetime import datetime
from plugins import Plugin


class MemoryPlugin(Plugin):
    """Plugin untuk persistent memory"""

    def __init__(self, config):
        super().__init__(config)
        self.memory_file = os.path.expanduser('~/.aizu/memory.json')
        self.memory = self._load_memory()

    def _load_memory(self):
        """Load memory dari file"""
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {"facts": [], "conversations": [], "preferences": {}}
        return {"facts": [], "conversations": [], "preferences": {}}

    def _save_memory(self):
        """Simpan memory ke file"""
        os.makedirs(os.path.dirname(self.memory_file), exist_ok=True)
        with open(self.memory_file, 'w', encoding='utf-8') as f:
            json.dump(self.memory, f, indent=2, ensure_ascii=False)

    def get_tools(self):
        """Register Memory tools"""
        tools = {}

        # 1. save_fact - Simpan fakta
        def save_fact(content, category="general", importance="normal"):
            """Simpan fakta atau informasi"""
            fact = {
                "id": len(self.memory["facts"]) + 1,
                "content": content,
                "category": category,
                "importance": importance,
                "created": datetime.now().isoformat(),
                "accessed": datetime.now().isoformat(),
                "access_count": 0
            }
            self.memory["facts"].append(fact)
            self._save_memory()

            return f"Fact saved (ID: {fact['id']})"

        tools["memory_save_fact"] = (save_fact, {
            "type": "function",
            "function": {
                "name": "memory_save_fact",
                "description": "Simpan fakta atau informasi",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Fakta yang akan disimpan"
                        },
                        "category": {
                            "type": "string",
                            "description": "Kategori (general, user, project, etc)",
                            "default": "general"
                        },
                        "importance": {
                            "type": "string",
                            "description": "Tingkat kepentingan (low, normal, high)",
                            "default": "normal"
                        }
                    },
                    "required": ["content"]
                }
            }
        })

        # 2. search_facts - Cari fakta
        def search_facts(query, category=None, limit=10):
            """Cari fakta dalam memory"""
            results = []
            query_lower = query.lower()

            for fact in self.memory["facts"]:
                # Filter by category
                if category and fact.get("category") != category:
                    continue

                # Search in content
                if query_lower in fact.get("content", "").lower():
                    # Update access
                    fact["accessed"] = datetime.now().isoformat()
                    fact["access_count"] = fact.get("access_count", 0) + 1

                    results.append(fact)

            # Sort by importance and access count
            importance_order = {"high": 0, "normal": 1, "low": 2}
            results.sort(key=lambda x: (
                importance_order.get(x.get("importance", "normal"), 1),
                -x.get("access_count", 0)
            ))

            self._save_memory()

            if not results:
                return "No facts found"

            formatted = []
            for fact in results[:limit]:
                formatted.append({
                    "id": fact.get("id"),
                    "content": fact.get("content"),
                    "category": fact.get("category"),
                    "importance": fact.get("importance"),
                    "created": fact.get("created")
                })

            return json.dumps(formatted, indent=2)

        tools["memory_search_facts"] = (search_facts, {
            "type": "function",
            "function": {
                "name": "memory_search_facts",
                "description": "Cari fakta dalam memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian"
                        },
                        "category": {
                            "type": "string",
                            "description": "Filter kategori (optional)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maksimal hasil",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        # 3. list_facts - List semua fakta
        def list_facts(category=None, limit=50):
            """List semua fakta dalam memory"""
            facts = self.memory["facts"]

            if category:
                facts = [f for f in facts if f.get("category") == category]

            # Sort by created
            facts.sort(key=lambda x: x.get("created", ""), reverse=True)

            if not facts:
                return "No facts stored"

            formatted = []
            for fact in facts[:limit]:
                formatted.append({
                    "id": fact.get("id"),
                    "content": fact.get("content")[:100] + "..." if len(fact.get("content", "")) > 100 else fact.get("content"),
                    "category": fact.get("category"),
                    "importance": fact.get("importance")
                })

            return json.dumps(formatted, indent=2)

        tools["memory_list_facts"] = (list_facts, {
            "type": "function",
            "function": {
                "name": "memory_list_facts",
                "description": "List semua fakta dalam memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": {
                            "type": "string",
                            "description": "Filter kategori (optional)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maksimal hasil",
                            "default": 50
                        }
                    },
                    "required": []
                }
            }
        })

        # 4. delete_fact - Hapus fakta
        def delete_fact(fact_id):
            """Hapus fakta dari memory"""
            original_count = len(self.memory["facts"])
            self.memory["facts"] = [f for f in self.memory["facts"] if f.get("id") != fact_id]

            if len(self.memory["facts"]) < original_count:
                self._save_memory()
                return f"Fact {fact_id} deleted"
            return f"Fact {fact_id} not found"

        tools["memory_delete_fact"] = (delete_fact, {
            "type": "function",
            "function": {
                "name": "memory_delete_fact",
                "description": "Hapus fakta dari memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fact_id": {
                            "type": "integer",
                            "description": "ID fakta yang akan dihapus"
                        }
                    },
                    "required": ["fact_id"]
                }
            }
        })

        # 5. save_preference - Simpan preferensi
        def save_preference(key, value):
            """Simpan preferensi user"""
            self.memory["preferences"][key] = {
                "value": value,
                "updated": datetime.now().isoformat()
            }
            self._save_memory()

            return f"Preference '{key}' saved"

        tools["memory_save_preference"] = (save_preference, {
            "type": "function",
            "function": {
                "name": "memory_save_preference",
                "description": "Simpan preferensi user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Nama preferensi"
                        },
                        "value": {
                            "type": "string",
                            "description": "Nilai preferensi"
                        }
                    },
                    "required": ["key", "value"]
                }
            }
        })

        # 6. get_preference - Ambil preferensi
        def get_preference(key):
            """Ambil preferensi user"""
            pref = self.memory["preferences"].get(key)
            if pref:
                return json.dumps({
                    "key": key,
                    "value": pref.get("value"),
                    "updated": pref.get("updated")
                }, indent=2)
            return f"Preference '{key}' not found"

        tools["memory_get_preference"] = (get_preference, {
            "type": "function",
            "function": {
                "name": "memory_get_preference",
                "description": "Ambil preferensi user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "key": {
                            "type": "string",
                            "description": "Nama preferensi"
                        }
                    },
                    "required": ["key"]
                }
            }
        })

        # 7. list_preferences - List semua preferensi
        def list_preferences():
            """List semua preferensi"""
            prefs = self.memory["preferences"]
            if not prefs:
                return "No preferences stored"

            formatted = []
            for key, pref in prefs.items():
                formatted.append({
                    "key": key,
                    "value": pref.get("value"),
                    "updated": pref.get("updated")
                })

            return json.dumps(formatted, indent=2)

        tools["memory_list_preferences"] = (list_preferences, {
            "type": "function",
            "function": {
                "name": "memory_list_preferences",
                "description": "List semua preferensi",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        # 8. save_conversation - Simpan ringkasan percakapan
        def save_conversation(summary, tags=None):
            """Simpan ringkasan percakapan"""
            conv = {
                "id": len(self.memory["conversations"]) + 1,
                "summary": summary,
                "tags": tags or [],
                "created": datetime.now().isoformat()
            }
            self.memory["conversations"].append(conv)
            self._save_memory()

            return f"Conversation saved (ID: {conv['id']})"

        tools["memory_save_conversation"] = (save_conversation, {
            "type": "function",
            "function": {
                "name": "memory_save_conversation",
                "description": "Simpan ringkasan percakapan",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "Ringkasan percakapan"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags untuk categorization"
                        }
                    },
                    "required": ["summary"]
                }
            }
        })

        # 9. search_conversations - Cari percakapan
        def search_conversations(query, limit=10):
            """Cari percakapan dalam memory"""
            results = []
            query_lower = query.lower()

            for conv in self.memory["conversations"]:
                if query_lower in conv.get("summary", "").lower():
                    results.append(conv)
                elif any(query_lower in tag.lower() for tag in conv.get("tags", [])):
                    results.append(conv)

            results.sort(key=lambda x: x.get("created", ""), reverse=True)

            if not results:
                return "No conversations found"

            formatted = []
            for conv in results[:limit]:
                formatted.append({
                    "id": conv.get("id"),
                    "summary": conv.get("summary")[:200],
                    "tags": conv.get("tags"),
                    "created": conv.get("created")
                })

            return json.dumps(formatted, indent=2)

        tools["memory_search_conversations"] = (search_conversations, {
            "type": "function",
            "function": {
                "name": "memory_search_conversations",
                "description": "Cari percakapan dalam memory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maksimal hasil",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        # 10. get_memory_stats - Statistik memory
        def get_memory_stats():
            """Dapatkan statistik memory"""
            return json.dumps({
                "total_facts": len(self.memory["facts"]),
                "total_conversations": len(self.memory["conversations"]),
                "total_preferences": len(self.memory["preferences"]),
                "categories": list(set(f.get("category", "general") for f in self.memory["facts"])),
                "memory_file": self.memory_file
            }, indent=2)

        tools["memory_get_stats"] = (get_memory_stats, {
            "type": "function",
            "function": {
                "name": "memory_get_stats",
                "description": "Dapatkan statistik memory",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        })

        return tools


def create(config):
    """Factory function untuk create plugin instance"""
    return MemoryPlugin(config)
