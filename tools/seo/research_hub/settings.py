"""Explicit project/provider bindings; credentials never travel through MCP."""
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

package = Path(__file__).resolve().parent
ROOT = package.parents[2] if package.parent.name == 'seo' and package.parent.parent.name == 'tools' else Path.cwd()
DEFAULT_HOME = Path(os.environ.get('SEO_RESEARCH_HOME', ROOT / 'artifacts' / 'seo-research'))


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', value):
        raise ValueError('Use a short lowercase project identifier')
    return value


def web_url(value):
    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError('Invalid URL')
    parsed = urlsplit(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError('Use an HTTP(S) URL without credentials or fragment')
    if parsed.port not in (None, 80, 443) or any(ord(c) < 33 for c in value):
        raise ValueError('Invalid URL port or characters')
    return parsed


def property_contains(prop, url):
    page = web_url(url)
    if prop.startswith('sc-domain:'):
        host = prop.removeprefix('sc-domain:')
        return page.hostname == host or page.hostname.endswith('.' + host)
    base = web_url(prop)
    return (page.scheme, page.netloc) == (base.scheme, base.netloc) and page.path.startswith(base.path)


class Settings:
    def __init__(self, home=DEFAULT_HOME):
        self.home = Path(home).resolve()
        self.path = self.home / 'config.private.json'
        self.data = json.loads(self.path.read_text(encoding='utf-8-sig'))
        if self.data.get('schemaVersion') != 1:
            raise ValueError('Unsupported research configuration version')
        self.projects = self.data.get('projects', {})
        for name, project in self.projects.items():
            identifier(name)
            if not project.get('hosts') or any(not re.fullmatch(r'[a-z0-9.-]+', h) for h in project['hosts']):
                raise ValueError('Project needs an explicit hostname allowlist')
            if project.get('minimumPosition') is not None and not 1 <= project['minimumPosition'] <= 1000:
                raise ValueError('Invalid project ranking policy')
            for engine in ('google', 'bing'):
                provider = project.get(engine)
                if not provider:
                    continue
                prop = provider['property']
                if prop.startswith('sc-domain:'):
                    if engine != 'google' or prop[10:] not in project['hosts']:
                        raise ValueError('Property does not belong to project')
                elif web_url(prop).hostname not in project['hosts']:
                    raise ValueError('Property does not belong to project')
                if engine == 'google' and not provider.get('account'):
                    raise ValueError('Google requires an explicit expected account')

    def project(self, name):
        identifier(name)
        if name not in self.projects:
            raise ValueError('Unknown project; configure it locally first')
        return self.projects[name]

    def check_url(self, project, url):
        if web_url(url).hostname not in self.project(project)['hosts']:
            raise ValueError('URL is outside the selected project')
        return url

    def credential(self, project, engine):
        config = self.project(project).get(engine)
        if not config or not config.get('enabled'):
            raise ValueError('Provider is not enabled for this project')
        path = Path(config.get('credentialFile', ''))
        if not path.is_absolute() or not path.is_file():
            raise ValueError('Provider credential file is not configured')
        return config, path

    def public_projects(self):
        return [dict(id=name, name=p.get('name', name), hosts=p['hosts'], languages=p.get('languages', []),
                     minimumPosition=p.get('minimumPosition'), providers={engine: dict(
                         configured=bool(p.get(engine)), enabled=bool(p.get(engine, {}).get('enabled')))
                         for engine in ('google', 'bing')}) for name, p in self.projects.items()]
