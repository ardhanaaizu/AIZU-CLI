"""
My Mode Plugin untuk AIZU-CLI
==============================

Menambahkan mode kerja baru.
"""

from plugins import Plugin


class MyModePlugin(Plugin):
    """Plugin untuk custom mode"""

    def get_modes(self):
        """Register custom mode"""
        return {
            "belajar": {
                "desc": "Mode belajar dengan penjelasan detail",
                "extra": " Mode belajar: berikan penjelasan lengkap dengan contoh, "
                         "langkah-langkah, dan tips. Cocok untuk pemula."
            }
        }


def create(config):
    """Factory function untuk create plugin instance"""
    return MyModePlugin(config)
