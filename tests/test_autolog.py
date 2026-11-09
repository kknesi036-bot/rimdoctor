import os

import pytest
from fastapi.testclient import TestClient

from app import autolog
from app.main import app


@pytest.fixture
def log(tmp_path, monkeypatch):
    path = tmp_path / 'Player.log'
    monkeypatch.setenv('RIMDOCTOR_PLAYER_LOG', str(path))
    return path


def test_first_read_unchanged_append_truncate_and_rotation(log):
    log.write_text('Error: first\n', encoding='utf-8')
    original = log.read_bytes()
    first = autolog.read_player_log()
    assert first['result']['summary']['error_count'] == 1
    assert log.read_bytes() == original
    assert autolog.read_player_log(first['revision'])['changed'] is False
    with log.open('a', encoding='utf-8') as f:
        f.write('Error: second\n')
    second = autolog.read_player_log(first['revision'])
    assert second['changed'] and second['result']['summary']['error_count'] == 2
    log.write_bytes(b'')
    assert autolog.read_player_log(second['revision'])['state'] == 'empty'
    log.unlink()
    assert autolog.read_player_log()['state'] == 'missing'
    log.write_text('Game initialized\n', encoding='utf-8')
    assert autolog.read_player_log(second['revision'])['result']['summary']['error_count'] == 0


@pytest.mark.parametrize('encoding', ['utf-8', 'utf-8-sig', 'utf-16'])
def test_encoding(log, encoding):
    log.write_bytes('Error: 한글'.encode(encoding))
    assert autolog.read_player_log()['result']['groups'][0]['preview'] == 'Error: 한글'


@pytest.mark.parametrize('content,state', [(b'', 'empty'), (b' \n', 'empty'), (b'\x00', 'invalid'), (b'\xff', 'invalid')])
def test_unusable_content(log, content, state):
    log.write_bytes(content)
    result = autolog.read_player_log()
    assert result['state'] == state and 'result' not in result


def test_size_limit(log):
    with log.open('wb') as f:
        f.truncate(autolog.MAX_BYTES + 1)
    assert autolog.read_player_log()['state'] == 'too_large'


def test_same_size_rewrite(log):
    log.write_text('Error: one', encoding='utf-8')
    first = autolog.read_player_log()
    log.write_text('Error: two', encoding='utf-8')
    os.utime(log, ns=(log.stat().st_atime_ns, log.stat().st_mtime_ns + 1000000))
    assert autolog.read_player_log(first['revision'])['result']['groups'][0]['preview'] == 'Error: two'


def test_local_api_and_other_origins_rejected(log):
    log.write_text('Error: local', encoding='utf-8')
    with TestClient(app, base_url='http://localhost') as client:
        response = client.get('/api/autolog')
        assert response.status_code == 200
        assert response.json()['result']['summary']['error_count'] == 1
        revision = response.json()['revision']
        assert client.get('/api/autolog', params={'known':revision}).json()['changed'] is False
        assert client.get('/api/autolog', headers={'Origin':'http://other.example'}).status_code == 403
        assert client.get('/api/autolog', headers={'Host':'other.example'}).status_code == 403


def test_read_failure_has_no_private_path(log, monkeypatch):
    def denied(*args, **kwargs):
        raise PermissionError(str(log))
    monkeypatch.setattr(autolog.Path, 'stat', denied)
    response = autolog.read_player_log()
    assert response['state'] == 'unavailable'
    assert str(log) not in str(response)
