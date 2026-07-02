"""
AIZU-CLI Skills System
======================

Reusable prompt templates yang bisa di-invoke.
Mirip Claude Code's skill system.

Skills disimpan sebagai YAML-like files di ~/.aizu/skills/
"""

import os
import re
import json
from datetime import datetime


# =============================================================================
# Skill Manager
# =============================================================================

class SkillManager:
    """
    Manager untuk skill system.

    Skills adalah template prompt yang bisa di-invoke dengan /skill <name> [args]
    """

    def __init__(self, skills_dir=None):
        """
        Args:
            skills_dir: Directory untuk skill files (default: ~/.aizu/skills/)
        """
        self.skills_dir = skills_dir or os.path.expanduser("~/.aizu/skills")
        os.makedirs(self.skills_dir, exist_ok=True)

        # Built-in skills
        self._builtin_skills = self._get_builtin_skills()

    def _get_builtin_skills(self):
        """Built-in skills yang selalu tersedia."""
        return {
            "review-code": {
                "name": "review-code",
                "description": "Review kode untuk bug, security, dan best practices",
                "prompt": (
                    "Review kode berikut secara mendalam. Periksa:\n"
                    "1. Bug dan error potensial\n"
                    "2. Masalah keamanan (security)\n"
                    "3. Performance issues\n"
                    "4. Code style dan best practices\n"
                    "5. Edge cases yang belum ditangani\n\n"
                    "File yang akan di-review: {{file}}\n\n"
                    "Format output:\n"
                    "[SEVERITY] file:line — deskripsi\n\n"
                    "Severity: CRITICAL, HIGH, MEDIUM, LOW, INFO"
                ),
                "args": ["file"],
                "builtin": True,
            },
            "explain-code": {
                "name": "explain-code",
                "description": "Jelaskan kode secara detail",
                "prompt": (
                    "Jelaskan kode berikut secara detail:\n"
                    "1. Apa yang dilakukan kode ini\n"
                    "2. Alur eksekusi\n"
                    "3. Input/output\n"
                    "4. Edge cases\n"
                    "5. Saran perbaikan jika ada\n\n"
                    "File: {{file}}\n\n"
                    "Gunakan bahasa yang mudah dipahami."
                ),
                "args": ["file"],
                "builtin": True,
            },
            "write-tests": {
                "name": "write-tests",
                "description": "Buat unit tests untuk kode",
                "prompt": (
                    "Buat unit tests untuk kode berikut:\n\n"
                    "File: {{file}}\n"
                    "Framework: {{framework|unittest}}\n\n"
                    "Requirements:\n"
                    "1. Test semua fungsi publik\n"
                    "2. Test edge cases\n"
                    "3. Test error handling\n"
                    "4. Coverage minimal 80%\n\n"
                    "Output: File test yang lengkap dan bisa langsung dijalankan."
                ),
                "args": ["file", "framework"],
                "builtin": True,
            },
            "refactor": {
                "name": "refactor",
                "description": "Refactor kode untuk improve quality",
                "prompt": (
                    "Refactor kode berikut untuk meningkatkan kualitas:\n\n"
                    "File: {{file}}\n"
                    "Focus: {{focus|readability}}\n\n"
                    "Yang harus dilakukan:\n"
                    "1. Improve readability\n"
                    "2. Reduce complexity\n"
                    "3. Extract reusable functions\n"
                    "4. Add proper error handling\n"
                    "5. Follow naming conventions\n\n"
                    "Jangan mengubah behavior, hanya improve structure."
                ),
                "args": ["file", "focus"],
                "builtin": True,
            },
            "debug": {
                "name": "debug",
                "description": "Bantu debug error",
                "prompt": (
                    "Bantu debug error berikut:\n\n"
                    "Error: {{error}}\n"
                    "Context: {{context|}}\n\n"
                    "Langkah:\n"
                    "1. Analisis error message\n"
                    "2. Identifikasi root cause\n"
                    "3. Berikan solusi\n"
                    "4. Jelaskan cara mencegah di masa depan\n\n"
                    "Berikan fix yang langsung bisa diterapkan."
                ),
                "args": ["error", "context"],
                "builtin": True,
            },
            "commit": {
                "name": "commit",
                "description": "Buat commit message yang baik",
                "prompt": (
                    "Buatkan commit message untuk perubahan berikut:\n\n"
                    "Changes: {{changes|git diff}}\n\n"
                    "Format conventional commit:\n"
                    "<type>(<scope>): <subject>\n\n"
                    "Types: feat, fix, docs, style, refactor, test, chore\n\n"
                    "Rules:\n"
                    "- Subject max 50 chars\n"
                    "- Body max 72 chars per line\n"
                    "- Use imperative mood\n"
                    "- Explain WHY, not WHAT"
                ),
                "args": ["changes"],
                "builtin": True,
            },
            "docs": {
                "name": "docs",
                "description": "Buat dokumentasi untuk kode",
                "prompt": (
                    "Buat dokumentasi untuk kode berikut:\n\n"
                    "File: {{file}}\n"
                    "Format: {{format|markdown}}\n\n"
                    "Include:\n"
                    "1. Overview/purpose\n"
                    "2. Installation (jika perlu)\n"
                    "3. Usage examples\n"
                    "4. API reference\n"
                    "5. Configuration options\n\n"
                    "Gunakan format yang jelas dan terstruktur."
                ),
                "args": ["file", "format"],
                "builtin": True,
            },
        }

    def get(self, name):
        """
        Ambil skill berdasarkan name.

        Args:
            name: Skill name

        Returns:
            dict atau None: Skill data
        """
        # Check built-in first
        if name in self._builtin_skills:
            return self._builtin_skills[name]

        # Check custom skills
        filepath = os.path.join(self.skills_dir, f"{name}.json")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass

        return None

    def list_all(self):
        """
        List semua skills (built-in + custom).

        Returns:
            list: List of skill dicts
        """
        skills = []

        # Add built-in skills
        for skill in self._builtin_skills.values():
            skill_copy = skill.copy()
            skill_copy['source'] = 'builtin'
            skills.append(skill_copy)

        # Add custom skills
        if os.path.exists(self.skills_dir):
            for filename in os.listdir(self.skills_dir):
                if filename.endswith('.json'):
                    filepath = os.path.join(self.skills_dir, filename)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            skill = json.load(f)
                            skill['source'] = 'custom'
                            skills.append(skill)
                    except Exception:
                        pass

        return skills

    def save(self, name, prompt, description="", args=None):
        """
        Simpan custom skill.

        Args:
            name: Skill name
            prompt: Prompt template
            description: Skill description
            args: List of argument names

        Returns:
            str: Path ke file yang disimpan
        """
        skill = {
            "name": name,
            "description": description,
            "prompt": prompt,
            "args": args or [],
            "created": datetime.now().isoformat(),
        }

        filepath = os.path.join(self.skills_dir, f"{name}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(skill, f, indent=2, ensure_ascii=False)

        return filepath

    def delete(self, name):
        """
        Hapus custom skill.

        Args:
            name: Skill name

        Returns:
            bool: True jika berhasil
        """
        # Cannot delete built-in skills
        if name in self._builtin_skills:
            return False

        filepath = os.path.join(self.skills_dir, f"{name}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    def invoke(self, name, args=None):
        """
        Invoke skill: render prompt template dengan arguments.

        Args:
            name: Skill name
            args: Dict of arguments

        Returns:
            str: Rendered prompt
        """
        skill = self.get(name)
        if not skill:
            return None

        prompt = skill.get('prompt', '')
        args = args or {}

        # Get default values from args definition
        skill_args = skill.get('args', [])
        for arg_def in skill_args:
            if '|' in arg_def:
                arg_name, default = arg_def.split('|', 1)
                if arg_name not in args:
                    args[arg_name] = default

        # Replace {{placeholders}}
        def replace_placeholder(match):
            placeholder = match.group(1)
            if '|' in placeholder:
                # Has default value: {{arg|default}}
                parts = placeholder.split('|', 1)
                arg_name = parts[0].strip()
                default = parts[1].strip()
                return args.get(arg_name, default)
            else:
                # No default: {{arg}}
                arg_name = placeholder.strip()
                return args.get(arg_name, f'{{{arg_name}}}')

        rendered = re.sub(r'\{\{(.+?)\}\}', replace_placeholder, prompt)
        return rendered


# =============================================================================
# Singleton Instance
# =============================================================================

_global_skill_manager = None


def get_skill_manager(skills_dir=None):
    """Get atau buat global SkillManager instance."""
    global _global_skill_manager
    if _global_skill_manager is None:
        _global_skill_manager = SkillManager(skills_dir)
    return _global_skill_manager


def reset_skill_manager():
    """Reset global SkillManager (untuk testing)."""
    global _global_skill_manager
    _global_skill_manager = None
