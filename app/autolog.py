"""Read only the configured Player.log, bounded in size; never modify the game log."""
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from .analyzer import analyze

MAX_BYTES = 10 * 1024 * 1024


def player_log_path():
    configured = os.getenv('RIMDOCTOR_PLAYER_LOG')
    if configured:
        return Path(configured)
    if os.name == 'nt':
        return Path.home() / 'AppData/LocalLow/Ludeon Studios/RimWorld by Ludeon Studios/Player.log'
    return Path('/rimworld-logs/Player.log')


def fingerprint(stat):
    # Windows stat/fstat disagree on ctime semantics; mtime and file identity agree.
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns,
            stat.st_ctime_ns if os.name != 'nt' else 0)


def read_player_log(known=''):
    path = player_log_path()
    try:
        before = path.stat()
        if before.st_size > MAX_BYTES:
            return {'state':'too_large', 'message':'Player.log가 10MB를 넘었습니다. 필요한 구간을 수동 입력해 주세요.'}
        revision = hashlib.sha256(repr(fingerprint(before)).encode()).hexdigest()
        source = {'name':'Player.log', 'bytes':before.st_size,
                  'modified_at':datetime.fromtimestamp(before.st_mtime, timezone.utc).isoformat()}
        if not before.st_size:
            return {'state':'empty', 'message':'Player.log가 비어 있습니다. 새 기록을 기다립니다.'}
        if known == revision:
            return {'state':'ready', 'changed':False, 'revision':revision, 'source':source}
        with path.open('rb') as f:
            data = f.read(MAX_BYTES + 1)
            after = os.fstat(f.fileno())
        if len(data) > MAX_BYTES:
            return {'state':'too_large', 'message':'Player.log가 10MB를 넘었습니다. 필요한 구간을 수동 입력해 주세요.'}
        if fingerprint(before) != fingerprint(after) or fingerprint(after) != fingerprint(path.stat()):
            return {'state':'changing', 'message':'게임이 로그를 기록 중입니다. 잠시 후 다시 확인합니다.'}
        try:
            text = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        except UnicodeError:
            return {'state':'invalid', 'message':'로그 인코딩을 읽을 수 없습니다. UTF-8 또는 BOM이 있는 UTF-16이 필요합니다.'}
        if not text.strip():
            return {'state':'empty', 'message':'Player.log에 분석할 내용이 없습니다. 새 기록을 기다립니다.'}
        if any(ord(c) < 32 and c not in '\r\n\t' for c in text):
            return {'state':'invalid', 'message':'Player.log가 텍스트 로그 형식이 아닙니다.'}
        return {'state':'ready', 'changed':True, 'revision':revision, 'source':source, 'result':analyze(text)}
    except FileNotFoundError:
        return {'state':'missing', 'message':'Player.log를 찾지 못했습니다. 림월드를 실행하면 다시 확인합니다.'}
    except OSError:
        return {'state':'unavailable', 'message':'Player.log를 읽을 수 없습니다. 파일 연결과 읽기 권한을 확인해 주세요.'}
