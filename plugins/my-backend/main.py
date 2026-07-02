"""
My Backend Plugin untuk AIZU-CLI
================================

Menambahkan backend AI custom baru.
"""

from plugins import Plugin


class MyBackendPlugin(Plugin):
    """Plugin untuk custom backend"""

    def get_backends(self):
        """Register custom backend"""
        return {
            "my-llm": {
                "base_url": "https://api.example.com/v1",
                "model": "my-model",
                "needs_key": True
            }
        }


def create(config):
    """Factory function untuk create plugin instance"""
    return MyBackendPlugin(config)
