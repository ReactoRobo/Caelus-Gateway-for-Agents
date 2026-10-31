#!/usr/bin/env python3
"""Caelus pairing and MCP client. Python standard library only; never asks for a password."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def endpoint(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path != '/mcp' or not parsed.hostname):
        raise ValueError('MCP 地址必须是 https://网关域名/mcp，不包含凭证或其他参数')
    if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('127.0.0.1', 'localhost', '::1')):
        raise ValueError('远程连接必须使用可信 HTTPS；仅本机回环允许 HTTP')
    if any(ord(c) <= 32 for c in value):
        raise ValueError('无效地址')
    parsed.port  # Validate malformed port without connecting.
    return value


def send(url, body, token=None):
    headers = {'Content-Type':'application/json', 'Accept':'application/json, text/event-stream'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    request = urllib.request.Request(url, json.dumps(body).encode(), headers)
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=35) as response:
            raw = response.read(2*1024*1024+1)
            if len(raw) > 2*1024*1024:
                raise ValueError('响应过大；请求不会自动重发')
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        # Never echo provider URLs, redirect headers, credentials or request bodies.
        if error.code in (401, 403):
            raise ValueError('未授权或授权已失效；请重新配对') from None
        raise ValueError(f'网关返回 HTTP {error.code}；请求不会自动重发') from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ValueError('连接失败或超时；控制结果未知，请勿用新 request_id 自动重发') from None


class Profile:
    def __init__(self, directory):
        if os.name != 'posix':
            raise ValueError('此版本需要 POSIX 私有凭证目录；Windows 请使用 WSL')
        self.directory = Path(directory).expanduser()
        if self.directory.is_symlink():
            raise ValueError('凭证目录不能是符号链接')
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if hasattr(os, 'getuid'):
            info = self.directory.stat()
            if info.st_uid != os.getuid():
                raise ValueError('凭证目录不属于当前用户')
            os.chmod(self.directory, 0o700)
        self.path = self.directory / 'connection.json'

    def read(self):
        fd = os.open(self.path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        with os.fdopen(fd) as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode) or (hasattr(os, 'getuid') and
                    (info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077)):
                raise ValueError('凭证文件权限不安全')
            value = json.loads(file.read(8192))
        endpoint(value['url'])
        return value

    def save(self, value):
        temp = self.directory / ('.connection-' + secrets.token_hex(8))
        try:
            with open(temp, 'x', opener=lambda p, f: os.open(p, f, 0o600)) as file:
                json.dump(value, file)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)


def rpc(profile, method, params):
    request_id = str(uuid.uuid4())
    value = send(profile['url'], dict(jsonrpc='2.0', id=request_id, method=method, params=params), profile['token'])
    if not isinstance(value, dict) or value.get('id') != request_id or value.get('error'):
        raise ValueError('MCP 请求失败；不自动重发')
    return value['result']


def run(args):
    profile = Profile(args.state_dir)
    if args.command == 'begin':
        url = endpoint(args.url)
        if profile.path.exists():
            raise ValueError('已有连接配置；请先查看 status，或在撤销旧授权后执行 forget')
        token = secrets.token_urlsafe(32)
        value = send(url + '/pair', {'token_hash':hashlib.sha256(token.encode()).hexdigest(), 'label':args.label})
        pair = value.get('pair_id', '')
        if len(pair) != 32 or any(c not in '0123456789abcdef' for c in pair):
            raise ValueError('网关不支持此配对流程')
        profile.save(dict(url=url, token=token, authorized=False))
        return dict(authorization_url=url[:-4] + '/mcp-authorize#' + pair,
                    verification_code=hashlib.sha256(token.encode()).hexdigest()[:8].upper(),
                    message='请本人打开授权页，核对域名和核对码，输入管理员密码后确认连接；不要把密码发到聊天。')
    if args.command == 'forget':
        profile.path.unlink(missing_ok=True)
        return {'forgotten':True, 'message':'已清除本机凭证；网关上的授权仍需在授权管理页面撤销。'}
    data = profile.read()
    if args.command == 'status':
        result = send(data['url']+'/pair/status', {}, data['token'])
        if result.get('authorized'):
            profile.save(dict(data, authorized=True, expires=result['expires']))
        return result
    if not data.get('authorized'):
        raise ValueError('请先完成授权，然后运行 status')
    if args.command == 'tools':
        info = rpc(data, 'initialize', {'protocolVersion':'2025-11-25', 'capabilities':{},
                                       'clientInfo':{'name':'caelus-skill', 'version':'0.1.0'}})
        return {'instructions':info.get('instructions'), **rpc(data, 'tools/list', {})}
    if args.command == 'call':
        arguments = json.load(sys.stdin)
        if not isinstance(arguments, dict):
            raise ValueError('标准输入必须是 JSON 对象')
        request = str(uuid.UUID(args.request_id))
        if 'request_id' in arguments:
            raise ValueError('request_id 应通过命令参数指定')
        return rpc(data, 'tools/call', {'name':args.tool, 'arguments':dict(arguments, request_id=request)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', default=str(Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'caelus-agent'))
    commands = parser.add_subparsers(dest='command', required=True)
    begin = commands.add_parser('begin')
    begin.add_argument('url')
    begin.add_argument('--label', default='Caelus Skill', help='显示给管理员的客户端名称')
    commands.add_parser('status')
    commands.add_parser('tools')
    commands.add_parser('forget')
    call = commands.add_parser('call')
    call.add_argument('tool')
    call.add_argument('--request-id', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False))
    except (ValueError, KeyError, OSError, TypeError):
        # Error text is deliberately generic: even hostile endpoints must not echo secrets.
        print(json.dumps({'error':'操作未完成。检查连接、授权、文件权限及参数；控制请求不会自动重发。'}, ensure_ascii=False))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
