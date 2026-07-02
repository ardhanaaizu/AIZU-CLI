"""
Brave Search Plugin untuk AIZU-CLI
====================================

Pencarian web menggunakan Brave Search API.
Lebih privat dan akurat dibanding search engine lain.
"""

import os
import json
import urllib.request
import urllib.error
import urllib.parse
from plugins import Plugin


class BraveSearchPlugin(Plugin):
    """Plugin untuk Brave Search API"""

    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.get('brave_api_key', os.environ.get('BRAVE_API_KEY', ''))

    def _search(self, query, count=10, country=None, search_lang=None):
        """Make Brave Search API request"""
        if not self.api_key:
            return {"error": "Brave API key not configured. Set BRAVE_API_KEY environment variable."}

        params = {
            'q': query,
            'count': min(count, 20)
        }
        if country:
            params['country'] = country
        if search_lang:
            params['search_lang'] = search_lang

        url = f"https://api.search.brave.com/res/v1/web/search?{urllib.parse.urlencode(params)}"

        headers = {
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip',
            'X-Subscription-Token': self.api_key
        }

        try:
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode('utf-8'))
                return data
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def get_tools(self):
        """Register Brave Search tools"""
        tools = {}

        # 1. Web Search
        def web_search(query, count=10, country=None, search_lang=None):
            """Cari di web menggunakan Brave Search"""
            result = self._search(query, count, country, search_lang)

            if 'error' in result:
                return result['error']

            web_results = result.get('web', {}).get('results', [])

            formatted = []
            for r in web_results[:count]:
                formatted.append({
                    'title': r.get('title'),
                    'url': r.get('url'),
                    'description': r.get('description'),
                    'age': r.get('age')
                })

            return json.dumps(formatted, indent=2)

        tools["brave_web_search"] = (web_search, {
            "type": "function",
            "function": {
                "name": "brave_web_search",
                "description": "Cari di web menggunakan Brave Search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Jumlah hasil (max 20)",
                            "default": 10
                        },
                        "country": {
                            "type": "string",
                            "description": "Kode negara (misal: ID, US)"
                        },
                        "search_lang": {
                            "type": "string",
                            "description": "Bahasa pencarian (misal: id, en)"
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        # 2. News Search
        def news_search(query, count=10, country=None):
            """Cari berita menggunakan Brave Search"""
            if not self.api_key:
                return "Brave API key not configured"

            params = {
                'q': query,
                'count': min(count, 20)
            }
            if country:
                params['country'] = country

            url = f"https://api.search.brave.com/res/v1/news/search?{urllib.parse.urlencode(params)}"

            headers = {
                'Accept': 'application/json',
                'X-Subscription-Token': self.api_key
            }

            try:
                req = urllib.request.Request(url, headers=headers, method='GET')
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode('utf-8'))

                results = data.get('results', [])

                formatted = []
                for r in results[:count]:
                    formatted.append({
                        'title': r.get('title'),
                        'url': r.get('url'),
                        'description': r.get('description'),
                        'source': r.get('source'),
                        'age': r.get('age')
                    })

                return json.dumps(formatted, indent=2)

            except Exception as e:
                return f"Error: {e}"

        tools["brave_news_search"] = (news_search, {
            "type": "function",
            "function": {
                "name": "brave_news_search",
                "description": "Cari berita menggunakan Brave Search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian berita"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Jumlah hasil",
                            "default": 10
                        },
                        "country": {
                            "type": "string",
                            "description": "Kode negara"
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        # 3. Image Search
        def image_search(query, count=10):
            """Cari gambar menggunakan Brave Search"""
            if not self.api_key:
                return "Brave API key not configured"

            params = {
                'q': query,
                'count': min(count, 20)
            }

            url = f"https://api.search.brave.com/res/v1/images/search?{urllib.parse.urlencode(params)}"

            headers = {
                'Accept': 'application/json',
                'X-Subscription-Token': self.api_key
            }

            try:
                req = urllib.request.Request(url, headers=headers, method='GET')
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = json.loads(response.read().decode('utf-8'))

                results = data.get('results', [])

                formatted = []
                for r in results[:count]:
                    formatted.append({
                        'title': r.get('title'),
                        'url': r.get('properties', {}).get('url'),
                        'thumbnail': r.get('thumbnail', {}).get('src'),
                        'source': r.get('source')
                    })

                return json.dumps(formatted, indent=2)

            except Exception as e:
                return f"Error: {e}"

        tools["brave_image_search"] = (image_search, {
            "type": "function",
            "function": {
                "name": "brave_image_search",
                "description": "Cari gambar menggunakan Brave Search",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian gambar"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Jumlah hasil",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        return tools


def create(config):
    """Factory function untuk create plugin instance"""
    return BraveSearchPlugin(config)
