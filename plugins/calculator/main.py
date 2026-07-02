"""
Calculator Plugin untuk AIZU-CLI
================================

Menambahkan tool kalkulator sederhana.
"""

from plugins import Plugin


class CalculatorPlugin(Plugin):
    """Plugin untuk kalkulator"""

    def get_tools(self):
        """Register calculator tool"""
        def calculate(expression):
            """
            Hitung ekspresi matematika sederhana.
            Support: +, -, *, /, **, %
            """
            try:
                # Hanya izinkan karakter yang aman
                allowed = set('0123456789+-*/.() ')
                if not all(c in allowed for c in expression):
                    return "Error: Ekspresi mengandung karakter yang tidak diizinkan"

                # Evaluasi ekspresi
                result = eval(expression)
                return str(result)
            except ZeroDivisionError:
                return "Error: Division by zero"
            except Exception as e:
                return f"Error: {e}"

        schema = {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "Hitung ekspresi matematika",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Ekspresi matematika (contoh: 2 + 3 * 4)"
                        }
                    },
                    "required": ["expression"]
                }
            }
        }

        return {"calculate": (calculate, schema)}


def create(config):
    """Factory function untuk create plugin instance"""
    return CalculatorPlugin(config)
