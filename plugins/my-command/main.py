"""
My Command Plugin untuk AIZU-CLI
=================================

Menambahkan slash command baru.
"""

from plugins import Plugin


class MyCommandPlugin(Plugin):
    """Plugin untuk custom commands"""

    def get_commands(self):
        """Register custom commands"""
        def hello_handler(args, cfg, messages):
            """Handler untuk /hello command"""
            name = args if args else "World"
            return f"Hello, {name}! 👋"

        def info_handler(args, cfg, messages):
            """Handler untuk /info command"""
            return (f"Backend: {cfg.get('backend', 'unknown')}\n"
                    f"Model: {cfg.get('model', 'unknown')}\n"
                    f"Mode: {cfg.get('mode', 'unknown')}")

        def weather_handler(args, cfg, messages):
            """Handler untuk /weather command"""
            city = args if args else "Jakarta"
            # Contoh sederhana - dalam implementasi nyata bisa pakai API
            return f"Weather di {city}: Cerah ☀️ (contoh saja)"

        return {
            "/hello": hello_handler,
            "/info": info_handler,
            "/weather": weather_handler,
        }


def create(config):
    """Factory function untuk create plugin instance"""
    return MyCommandPlugin(config)
