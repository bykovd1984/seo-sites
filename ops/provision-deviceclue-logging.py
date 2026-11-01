#!/usr/bin/env python3
"""Run as root on the existing VPS. Never outputs or copies credentials off-host."""
import base64
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

STREAM = 'logs-deviceclue-prod'
VIEW = 'deviceclue-logs'

def provision():
    assert os.geteuid() == 0, 'Run as root on the VPS'
    site = json.loads(subprocess.check_output(['docker', 'inspect', 'gt-site']))[0]
    env = dict(value.split('=', 1) for value in site['Config']['Env'] if '=' in value)
    admin = 'Basic ' + base64.b64encode((env['ElasticConfiguration__Login'] + ':' + env['ElasticConfiguration__Password']).encode()).decode()

    def request(method, path, body=None, authorization=admin, kibana=False):
        data = None if body is None else json.dumps(body).encode()
        headers = {'Authorization': authorization, 'Content-Type': 'application/json', 'kbn-xsrf': 'deviceclue-logging'}
        url = ('http://127.0.0.1:5601' if kibana else 'http://127.0.0.1:9200') + path
        with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=headers), timeout=20) as response:
            return json.load(response)

    keyword = {'type': 'keyword'}
    mappings = {'dynamic': 'strict', 'properties': {
        '@timestamp': {'type': 'date'}, 'message': {'type': 'text'},
        'service': {'properties': {key: keyword for key in ['name', 'environment', 'version']}},
        'log': {'properties': {'level': keyword}},
        'event': {'properties': {'action': keyword, 'duration': {'type': 'long'}}},
        'http': {'properties': {'request': {'properties': {'method': keyword}}, 'response': {'properties': {'status_code': {'type': 'integer'}}}}},
        'url': {'properties': {'path': keyword}},
        'error': {'properties': {'type': keyword, 'stack_trace': {'type': 'text'}}},
    }}
    request('PUT', '/_index_template/deviceclue-logs', {
        'index_patterns': [STREAM], 'priority': 501, 'data_stream': {},
        'template': {'settings': {'number_of_shards': 1, 'number_of_replicas': 0}, 'mappings': mappings,
                     'lifecycle': {'data_retention': '30d'}},
        '_meta': {'owner': 'deviceclue', 'description': 'Operational logs without request identifiers or search content'},
    })
    try:
        request('GET', '/_data_stream/' + STREAM)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        request('PUT', '/_data_stream/' + STREAM)
    request('PUT', '/_data_stream/' + STREAM + '/_lifecycle', {'data_retention': '30d'})

    secrets = Path('/opt/seo-sites/deviceclue/secrets')
    secrets.mkdir(mode=0o750, exist_ok=True)
    os.chown(secrets, 0, 10001)
    os.chmod(secrets, 0o750)
    key_path = secrets / 'elasticsearch-api-key'
    if not key_path.exists():
        result = request('POST', '/_security/api_key', {
            'name': 'deviceclue-log-writer',
            'role_descriptors': {'deviceclue-writer': {'cluster': [], 'indices': [{'names': [STREAM], 'privileges': ['create_doc']}] }},
            'metadata': {'service': 'deviceclue', 'purpose': 'write operational logs only'},
        })
        # O_EXCL prevents an accidental overwrite; umask prevents a world-readable window.
        descriptor = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        with os.fdopen(descriptor, 'w') as output:
            output.write(result['encoded'])
        id_path = secrets / 'elasticsearch-api-key-id'
        descriptor = os.open(id_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, 'w') as output:
            output.write(result['id'])
    os.chown(key_path, 0, 10001)
    os.chmod(key_path, 0o640)
    writer = 'ApiKey ' + key_path.read_text().strip()
    privileges = request('POST', '/_security/user/_has_privileges', {
        'cluster': ['manage_security'],
        'index': [
            {'names': [STREAM], 'privileges': ['create_doc', 'read', 'delete', 'manage']},
            {'names': ['logs-gt-site-prod', 'logs-gt-prod', 'logs-gt-test'], 'privileges': ['create_doc', 'read']},
        ],
    }, authorization=writer)
    assert privileges['cluster']['manage_security'] is False
    assert privileges['index'][STREAM]['create_doc'] is True
    assert all(not allowed for name, permissions in privileges['index'].items() for privilege, allowed in permissions.items() if name != STREAM or privilege != 'create_doc')

    network = 'deviceclue-logs'
    exists = subprocess.run(['docker', 'network', 'inspect', network], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if not exists:
        subprocess.run(['docker', 'network', 'create', '--internal', network], check=True, stdout=subprocess.DEVNULL)
    elastic = json.loads(subprocess.check_output(['docker', 'inspect', 'gt-elasticsearch']))[0]
    if network not in elastic['NetworkSettings']['Networks']:
        subprocess.run(['docker', 'network', 'connect', '--alias', 'deviceclue-elasticsearch', network, 'gt-elasticsearch'], check=True)

    try:
        view = request('GET', '/api/data_views/data_view/' + VIEW, kibana=True)
        assert view['data_view']['title'] == STREAM
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        request('POST', '/api/data_views/data_view', {'data_view': {'id': VIEW, 'name': 'DeviceClue — server logs', 'title': STREAM, 'timeFieldName': '@timestamp'}}, kibana=True)
    print(json.dumps({'stream': STREAM, 'dataView': VIEW, 'keyStoredOnServer': True, 'restrictedPrivilegesVerified': True, 'retentionPolicy': '30d', 'network': network}))

if __name__ == '__main__':
    try:
        provision()
    except urllib.error.HTTPError as error:
        print('Logging setup HTTP error:', error.code, '(response and credentials omitted)')
        raise SystemExit(1)
