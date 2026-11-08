#!/usr/bin/env python3
"""Prepare WrenchClue's own directory, then enable its verified Caddy route."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import urllib.request
import uuid

ROOT = Path('/opt/seo-sites/wrenchclue')
CADDY = Path('/etc/caddy/Caddyfile')
FRAGMENT = Path('/etc/caddy/domains/wrenchclue.caddy')
IMPORT = 'import /etc/caddy/domains/wrenchclue.caddy'


def command(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def inventory():
    rows = command('docker', 'ps', '--format', '{{json .}}').splitlines()
    return [{k: row[k] for k in ('Names', 'ID', 'Ports')} for row in map(json.loads, rows)]


def prepare():
    rows = inventory()
    occupied = command('ss', '-H', '-ltn', 'sport = :5010').strip()
    own = next((r for r in rows if r['Names'] == 'seo-wrenchclue'), None)
    if occupied and (not own or '127.0.0.1:5010->3000/tcp' not in own['Ports']):
        raise RuntimeError('Port 5010 belongs to another service')
    if ROOT.is_symlink() or ROOT.resolve() != ROOT:
        raise RuntimeError('Unexpected deployment path')
    ROOT.mkdir(mode=0o755, exist_ok=True)
    user = pwd.getpwnam('deploy')
    os.chown(ROOT, user.pw_uid, user.pw_gid)
    baseline = ROOT / 'launch-baseline.json'
    if not baseline.exists():
        baseline.write_text(json.dumps({'containers': rows}, indent=2) + '\n')
    print(json.dumps({'prepared': str(ROOT), 'port': 5010, 'containers': rows}))


def publish(expected):
    if not re.fullmatch('[0-9a-f]{40}', expected or ''):
        raise RuntimeError('A full verified commit SHA is required')
    with urllib.request.urlopen('http://127.0.0.1:5010/api/health', timeout=5) as response:
        health = json.load(response)
    if (health.get('site'), health.get('articles'), health.get('commit')) != ('wrenchclue', 20, expected):
        raise RuntimeError('Production candidate does not match the expected release')
    source = Path(__file__).with_name('wrenchclue.caddy').read_bytes()
    required = b'wrenchclue.site {\n\tencode zstd gzip\n\treverse_proxy 127.0.0.1:5010\n}\n\nwww.wrenchclue.site {\n\tredir https://wrenchclue.site{uri} permanent\n}\n'
    if [line.strip() for line in source.decode().splitlines()] != [line.strip() for line in required.decode().splitlines()]:
        raise RuntimeError('Unexpected WrenchClue routing configuration')
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / 'provision-backups' / (stamp + '-' + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True, mode=0o700)
    os.chmod(backup.parent, 0o700)
    with open('/run/lock/seo-wrenchclue-caddy.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        original = CADDY.read_bytes()
        old_fragment = FRAGMENT.read_bytes() if FRAGMENT.exists() else None
        (backup / 'Caddyfile').write_bytes(original)
        if old_fragment is not None:
            (backup / 'wrenchclue.caddy').write_bytes(old_fragment)
        added = IMPORT not in original.decode().splitlines()
        try:
            FRAGMENT.write_bytes(source.replace(b'\r\n', b'\n'))
            os.chmod(FRAGMENT, 0o644)
            if added:
                # Append only our import, preserving every other site's configuration.
                with CADDY.open('ab') as config:
                    config.write(('\n' + IMPORT + '\n').encode())
                    config.flush()
                    os.fsync(config.fileno())
            command('caddy', 'validate', '--config', str(CADDY), '--adapter', 'caddyfile')
            command('systemctl', 'reload', 'caddy')
        except Exception:
            if old_fragment is None:
                FRAGMENT.unlink(missing_ok=True)
            else:
                FRAGMENT.write_bytes(old_fragment)
            if added:
                current = CADDY.read_text()
                CADDY.write_text(''.join(line for line in current.splitlines(keepends=True) if line.strip() != IMPORT))
            command('caddy', 'validate', '--config', str(CADDY), '--adapter', 'caddyfile')
            command('systemctl', 'reload', 'caddy')
            raise RuntimeError('WrenchClue routing failed and its previous route was restored') from None
    print(json.dumps({'route': 'https://wrenchclue.site', 'commit': expected, 'backup': str(backup)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'publish-route'])
    parser.add_argument('--expected-commit')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run provisioning as root; the website itself runs as an unprivileged user')
    if args.mode == 'prepare':
        prepare()
    else:
        publish(args.expected_commit)
