"""
Fetch Plugin untuk AIZU-CLI
============================

Ambil dan ekstrak konten dari URL.
Support HTML, JSON, dan plain text.
"""

import os
import re
import json
import urllib.request
import urllib.error
from html.parser import HTMLParser
from plugins import Plugin


class SimpleHTMLExtractor(HTMLParser):
    """Simple HTML content extractor"""

    def __init__(self):
        super().__init__()
        self.result = []
        self.current_tag = None
        self.skip_tags = {'script', 'style', 'noscript'}
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.skip_tags:
            self.skip_depth += 1
        self.current_tag = tag

    def handle_endtag(self, tag):
        if tag in self.skip_tags and self.skip_depth > 0:
            self.skip_depth -= 1

    def handle_data(self, data):
        if self.skip_depth == 0:
            text = data.strip()
            if text:
                self.result.append(text)

    def get_text(self):
        return '\n'.join(self.result)


class FetchPlugin(Plugin):
    """Plugin untuk fetch URL content"""

    def __init__(self, config):
        super().__init__(config)
        self.timeout = config.get('fetch_timeout', 30)

    def _fetch(self, url, headers=None, max_length=None):
        """Fetch URL content"""
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; AIZU-CLI/1.2)',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        }
        if headers:
            default_headers.update(headers)

        try:
            req = urllib.request.Request(url, headers=default_headers, method='GET')
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content_type = response.headers.get('Content-Type', '')
                raw_content = response.read()

                # Handle encoding
                if 'charset=' in content_type:
                    encoding = content_type.split('charset=')[-1].strip()
                else:
                    encoding = 'utf-8'

                try:
                    text = raw_content.decode(encoding)
                except:
                    text = raw_content.decode('utf-8', errors='replace')

                # Limit length
                if max_length and len(text) > max_length:
                    text = text[:max_length] + '\n... [truncated]'

                return {
                    'content': text,
                    'content_type': content_type,
                    'status': response.status,
                    'url': response.url
                }

        except urllib.error.HTTPError as e:
            return {'error': f"HTTP {e.code}: {e.reason}"}
        except urllib.error.URLError as e:
            return {'error': f"URL Error: {e.reason}"}
        except Exception as e:
            return {'error': str(e)}

    def _extract_text_from_html(self, html):
        """Extract text from HTML"""
        extractor = SimpleHTMLExtractor()
        try:
            extractor.feed(html)
            return extractor.get_text()
        except:
            # Fallback: regex
            text = re.sub(r'<[^>]+>', ' ', html)
            text = re.sub(r'\s+', ' ', text)
            return text.strip()

    def _extract_json(self, content):
        """Extract and format JSON"""
        try:
            data = json.loads(content)
            return json.dumps(data, indent=2)
        except:
            return content

    def get_tools(self):
        """Register Fetch tools"""
        tools = {}

        # 1. fetch_url - Fetch URL content
        def fetch_url(url, max_length=10000, extract_text=True):
            """Ambil konten dari URL"""
            result = self._fetch(url, max_length=max_length)

            if 'error' in result:
                return result['error']

            content = result['content']
            content_type = result['content_type']

            # Extract text from HTML
            if extract_text and 'html' in content_type:
                text = self._extract_text_from_html(content)
                return text[:max_length] if max_length else text

            # Format JSON
            elif 'json' in content_type:
                return self._extract_json(content)

            return content

        tools["fetch_url"] = (fetch_url, {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Ambil konten dari URL",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL yang akan di-fetch"
                        },
                        "max_length": {
                            "type": "integer",
                            "description": "Maksimal panjang konten",
                            "default": 10000
                        },
                        "extract_text": {
                            "type": "boolean",
                            "description": "Ekstrak text dari HTML",
                            "default": True
                        }
                    },
                    "required": ["url"]
                }
            }
        })

        # 2. fetch_json - Fetch JSON API
        def fetch_json(url, headers=None):
            """Fetch JSON dari API"""
            result = self._fetch(url, headers=headers)

            if 'error' in result:
                return result['error']

            return self._extract_json(result['content'])

        tools["fetch_json"] = (fetch_json, {
            "type": "function",
            "function": {
                "name": "fetch_json",
                "description": "Fetch JSON dari API",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL API"
                        },
                        "headers": {
                            "type": "object",
                            "description": "HTTP headers (optional)"
                        }
                    },
                    "required": ["url"]
                }
            }
        })

        # 3. fetch_raw - Fetch raw content
        def fetch_raw(url, max_length=50000):
            """Fetch raw content tanpa processing"""
            result = self._fetch(url, max_length=max_length, extract_text=False)

            if 'error' in result:
                return result['error']

            return result['content']

        tools["fetch_raw"] = (fetch_raw, {
            "type": "function",
            "function": {
                "name": "fetch_raw",
                "description": "Fetch raw content tanpa processing",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL yang akan di-fetch"
                        },
                        "max_length": {
                            "type": "integer",
                            "description": "Maksimal panjang konten",
                            "default": 50000
                        }
                    },
                    "required": ["url"]
                }
            }
        })

        # 4. fetch_headers - Fetch hanya headers
        def fetch_headers(url):
            """Fetch HTTP headers saja"""
            try:
                req = urllib.request.Request(url, method='HEAD', headers={
                    'User-Agent': 'AIZU-CLI/1.2'
                })
                with urllib.request.urlopen(req, timeout=10) as response:
                    headers = dict(response.headers)
                    return json.dumps({
                        'status': response.status,
                        'headers': headers
                    }, indent=2)
            except Exception as e:
                return f"Error: {e}"

        tools["fetch_headers"] = (fetch_headers, {
            "type": "function",
            "function": {
                "name": "fetch_headers",
                "description": "Fetch HTTP headers saja",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL"
                        }
                    },
                    "required": ["url"]
                }
            }
        })

        return tools


def create(config):
    """Factory function untuk create plugin instance"""
    return FetchPlugin(config)
