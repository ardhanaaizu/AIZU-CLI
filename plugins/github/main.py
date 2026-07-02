"""
GitHub Plugin untuk AIZU-CLI
=============================

Integrasi dengan GitHub API untuk:
- Repository management
- Issues dan Pull Requests
- File operations
- User information
"""

import os
import json
import urllib.request
import urllib.error
from plugins import Plugin


class GitHubPlugin(Plugin):
    """Plugin untuk GitHub API"""

    def __init__(self, config):
        super().__init__(config)
        self.token = config.get('github_token', os.environ.get('GITHUB_TOKEN', ''))

    def _request(self, url, method='GET', data=None):
        """Make GitHub API request"""
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'AIZU-CLI'
        }
        if self.token:
            headers['Authorization'] = f'token {self.token}'

        try:
            req_data = json.dumps(data).encode('utf-8') if data else None
            req = urllib.request.Request(url, data=req_data, headers=headers, method=method)

            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}"}
        except Exception as e:
            return {"error": str(e)}

    def get_tools(self):
        """Register GitHub tools"""
        tools = {}

        # 1. Get repository info
        def get_repo(owner, repo):
            """Dapatkan info repository"""
            result = self._request(f'https://api.github.com/repos/{owner}/{repo}')
            if 'error' in result:
                return result['error']

            return json.dumps({
                'name': result.get('name'),
                'full_name': result.get('full_name'),
                'description': result.get('description'),
                'stars': result.get('stargazers_count'),
                'forks': result.get('forks_count'),
                'language': result.get('language'),
                'url': result.get('html_url'),
                'created': result.get('created_at'),
                'updated': result.get('updated_at')
            }, indent=2)

        tools["github_get_repo"] = (get_repo, {
            "type": "function",
            "function": {
                "name": "github_get_repo",
                "description": "Dapatkan info repository GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Owner repository"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nama repository"
                        }
                    },
                    "required": ["owner", "repo"]
                }
            }
        })

        # 2. List issues
        def list_issues(owner, repo, state="open", per_page=10):
            """List issues di repository"""
            url = f'https://api.github.com/repos/{owner}/{repo}/issues?state={state}&per_page={per_page}'
            result = self._request(url)

            if isinstance(result, dict) and 'error' in result:
                return result['error']

            issues = []
            for issue in result[:per_page]:
                issues.append({
                    'number': issue.get('number'),
                    'title': issue.get('title'),
                    'state': issue.get('state'),
                    'user': issue.get('user', {}).get('login'),
                    'created': issue.get('created_at'),
                    'labels': [l.get('name') for l in issue.get('labels', [])]
                })

            return json.dumps(issues, indent=2)

        tools["github_list_issues"] = (list_issues, {
            "type": "function",
            "function": {
                "name": "github_list_issues",
                "description": "List issues di repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Owner repository"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nama repository"
                        },
                        "state": {
                            "type": "string",
                            "description": "State issues (open/closed/all)",
                            "default": "open"
                        },
                        "per_page": {
                            "type": "integer",
                            "description": "Jumlah issue per page",
                            "default": 10
                        }
                    },
                    "required": ["owner", "repo"]
                }
            }
        })

        # 3. Get issue
        def get_issue(owner, repo, issue_number):
            """Dapatkan detail issue"""
            result = self._request(f'https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}')

            if 'error' in result:
                return result['error']

            return json.dumps({
                'number': result.get('number'),
                'title': result.get('title'),
                'body': result.get('body'),
                'state': result.get('state'),
                'user': result.get('user', {}).get('login'),
                'assignees': [a.get('login') for a in result.get('assignees', [])],
                'labels': [l.get('name') for l in result.get('labels', [])],
                'comments': result.get('comments'),
                'created': result.get('created_at'),
                'updated': result.get('updated_at')
            }, indent=2)

        tools["github_get_issue"] = (get_issue, {
            "type": "function",
            "function": {
                "name": "github_get_issue",
                "description": "Dapatkan detail issue",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Owner repository"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nama repository"
                        },
                        "issue_number": {
                            "type": "integer",
                            "description": "Nomor issue"
                        }
                    },
                    "required": ["owner", "repo", "issue_number"]
                }
            }
        })

        # 4. List pull requests
        def list_pull_requests(owner, repo, state="open", per_page=10):
            """List pull requests"""
            url = f'https://api.github.com/repos/{owner}/{repo}/pulls?state={state}&per_page={per_page}'
            result = self._request(url)

            if isinstance(result, dict) and 'error' in result:
                return result['error']

            prs = []
            for pr in result[:per_page]:
                prs.append({
                    'number': pr.get('number'),
                    'title': pr.get('title'),
                    'state': pr.get('state'),
                    'user': pr.get('user', {}).get('login'),
                    'created': pr.get('created_at'),
                    'merged': pr.get('merged'),
                    'mergeable': pr.get('mergeable')
                })

            return json.dumps(prs, indent=2)

        tools["github_list_pull_requests"] = (list_pull_requests, {
            "type": "function",
            "function": {
                "name": "github_list_pull_requests",
                "description": "List pull requests",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Owner repository"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nama repository"
                        },
                        "state": {
                            "type": "string",
                            "description": "State PR (open/closed/all)",
                            "default": "open"
                        },
                        "per_page": {
                            "type": "integer",
                            "description": "Jumlah PR per page",
                            "default": 10
                        }
                    },
                    "required": ["owner", "repo"]
                }
            }
        })

        # 5. Search repositories
        def search_repositories(query, per_page=10):
            """Cari repositories"""
            import urllib.parse
            encoded_query = urllib.parse.quote(query)
            url = f'https://api.github.com/search/repositories?q={encoded_query}&per_page={per_page}'
            result = self._request(url)

            if 'error' in result:
                return result['error']

            repos = []
            for repo in result.get('items', [])[:per_page]:
                repos.append({
                    'name': repo.get('full_name'),
                    'description': repo.get('description'),
                    'stars': repo.get('stargazers_count'),
                    'language': repo.get('language'),
                    'url': repo.get('html_url')
                })

            return json.dumps(repos, indent=2)

        tools["github_search_repos"] = (search_repositories, {
            "type": "function",
            "function": {
                "name": "github_search_repos",
                "description": "Cari repositories di GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Query pencarian"
                        },
                        "per_page": {
                            "type": "integer",
                            "description": "Jumlah hasil per page",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            }
        })

        # 6. Get user info
        def get_user(username):
            """Dapatkan info user GitHub"""
            result = self._request(f'https://api.github.com/users/{username}')

            if 'error' in result:
                return result['error']

            return json.dumps({
                'login': result.get('login'),
                'name': result.get('name'),
                'bio': result.get('bio'),
                'public_repos': result.get('public_repos'),
                'followers': result.get('followers'),
                'following': result.get('following'),
                'created': result.get('created_at'),
                'url': result.get('html_url')
            }, indent=2)

        tools["github_get_user"] = (get_user, {
            "type": "function",
            "function": {
                "name": "github_get_user",
                "description": "Dapatkan info user GitHub",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "Username GitHub"
                        }
                    },
                    "required": ["username"]
                }
            }
        })

        # 7. List repository files
        def list_repo_files(owner, repo, path="", branch="main"):
            """List file di repository"""
            url = f'https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}'
            result = self._request(url)

            if isinstance(result, dict) and 'error' in result:
                return result['error']

            if not isinstance(result, list):
                return "Error: Invalid response"

            files = []
            for item in result:
                files.append({
                    'name': item.get('name'),
                    'type': item.get('type'),
                    'size': item.get('size'),
                    'path': item.get('path')
                })

            return json.dumps(files, indent=2)

        tools["github_list_repo_files"] = (list_repo_files, {
            "type": "function",
            "function": {
                "name": "github_list_repo_files",
                "description": "List file di repository",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "owner": {
                            "type": "string",
                            "description": "Owner repository"
                        },
                        "repo": {
                            "type": "string",
                            "description": "Nama repository"
                        },
                        "path": {
                            "type": "string",
                            "description": "Path di dalam repo",
                            "default": ""
                        },
                        "branch": {
                            "type": "string",
                            "description": "Branch name",
                            "default": "main"
                        }
                    },
                    "required": ["owner", "repo"]
                }
            }
        })

        return tools


def create(config):
    """Factory function untuk create plugin instance"""
    return GitHubPlugin(config)
