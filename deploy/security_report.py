#!/usr/bin/env python3
"""晚风安全巡检：累积更新黑名单 + 正常访问报告"""
import gzip, glob, re, subprocess
from collections import defaultdict
from datetime import datetime

CONF = '/etc/nginx/conf.d/block-scanners.conf'
EXCLUDE = {'120.77.9.218', '127.0.0.1'}  # 服务器自己、本机回环

SENS = re.compile(r'(\.env|\.git|\.vscode|\.svn|wp-|phpmyadmin|\.htaccess|\.DS_Store|actuator|\.aws|\.ssh|/config|/admin|php://|allow_url_include|/bin/sh|/cgi-bin|sftp|\.bak|\.backup|\.sql|\.yml|\.yaml)', re.I)
BADUA = re.compile(r'(curl|wget|python|Go-http|nikto|sqlmap|nmap|masscan|zgrab|scanner|libredtail|l9tcpid|Exposure|Rota|MSIE [678]|libwww|Java/|okhttp|crawler|spider|facebookexternalhit|BLEXBot|Ahrefs|Semrush|DotBot|PetalBot|Bytespider|bot)', re.I)


def load_lines():
    lines = []
    for f in ['/var/log/nginx/access.log', '/var/log/nginx/access.log.1']:
        try:
            with open(f) as fh:
                lines.extend(fh.readlines())
        except FileNotFoundError:
            pass
    for f in sorted(glob.glob('/var/log/nginx/access.log.*.gz')):
        try:
            with gzip.open(f, 'rt') as fh:
                lines.extend(fh.readlines())
        except Exception:
            pass
    return lines


def parse(line):
    m = re.match(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([^"]*)" \d+ \d+ "[^"]*" "([^"]*)"', line)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3), m.group(4)  # ip, ts, req, ua


def to_ts(ts):
    try:
        return datetime.strptime(ts.split()[0], '%d/%b/%Y:%H:%M:%S').timestamp()
    except Exception:
        return None


def device(ua):
    if 'iPhone' in ua or 'CFNetwork' in ua:
        return 'iPhone'
    if 'NetworkingExtension' in ua:
        return 'iOS系统服务'
    if 'Macintosh' in ua:
        return 'Mac'
    if 'Windows' in ua:
        return 'Windows'
    if 'Linux' in ua or 'X11' in ua:
        return 'Linux'
    if not ua or ua == '-':
        return '(空UA)'
    return ua[:32]


def read_existing():
    rules = set()
    try:
        for line in open(CONF):
            line = line.strip()
            if line.startswith('deny '):
                rules.add(line.split()[1].rstrip(';'))
    except FileNotFoundError:
        pass
    return rules


def main():
    lines = load_lines()
    stats = defaultdict(lambda: {'n': 0, 'first': None, 'last': None, 't0': None, 't1': None,
                                  'ua': set(), 'sens': 0, 'badua': 0, 'real_iphone': False})
    for line in lines:
        p = parse(line)
        if not p:
            continue
        ip, ts, req, ua = p
        d = stats[ip]
        d['n'] += 1
        d['first'] = ts if d['first'] is None or ts < d['first'] else d['first']
        d['last'] = ts if d['last'] is None or ts > d['last'] else d['last']
        t = to_ts(ts)
        if t:
            d['t0'] = t if d['t0'] is None else min(d['t0'], t)
            d['t1'] = t if d['t1'] is None else max(d['t1'], t)
        if len(d['ua']) < 4:
            d['ua'].add(ua)
        if 'iPhone' in ua:
            d['real_iphone'] = True
        if SENS.search(req):
            d['sens'] += 1
        if BADUA.search(ua):
            d['badua'] += 1

    # 识别扫描器（三重规则，优先级递减）
    # 1) 敏感路径探测 = 铁证（扫描器伪装 iPhone UA 也会扫 .env/.git 等）
    # 2) 高频突发 = 攻击特征
    # 3) 异常 UA 且无真实 iPhone 访问（避免测试 curl 混入用户出口 IP 造成误伤）
    new_scanners = set()
    for ip, d in stats.items():
        if ip in EXCLUDE:
            continue
        if d['sens'] > 0:
            new_scanners.add(ip)
            continue
        # 高频突发
        if d['t0'] and d['t1'] and d['n'] >= 100 and (d['t1'] - d['t0']) <= 600:
            new_scanners.add(ip)
            continue
        if d['badua'] > 0 and not d['real_iphone']:
            new_scanners.add(ip)

    # 合并 /24 段
    seg_count = defaultdict(int)
    for ip in new_scanners:
        seg_count['.'.join(ip.split('.')[:3]) + '.0/24'] += 1
    new_rules = set()
    for ip in new_scanners:
        seg = '.'.join(ip.split('.')[:3]) + '.0/24'
        new_rules.add(seg if seg_count[seg] >= 2 else ip)

    existing = read_existing()
    added = new_rules - existing
    removed = existing - new_rules
    final = sorted(new_rules)

    header = ['# 拦截恶意扫描器/爬虫 IP（全量重算，每次基于最新日志）',
              '# 规则：敏感路径 / 异常UA / 高频突发；已排除服务器自身与真实 iPhone 用户', '']
    with open(CONF, 'w') as f:
        f.write('\n'.join(header) + '\n'.join(f'deny {r};' for r in final) + '\n')

    reload_ok = True
    t = subprocess.run(['nginx', '-t'], capture_output=True, text=True)
    if t.returncode != 0:
        reload_msg = 'nginx -t 失败: ' + t.stderr[-150:]
        reload_ok = False
    else:
        r = subprocess.run(['systemctl', 'reload', 'nginx'], capture_output=True, text=True)
        reload_msg = 'OK' if r.returncode == 0 else 'reload 失败: ' + r.stderr[-150:]

    # 正常 IP：非扫描器、非排除、访问>=2次（去掉一次性噪音）
    normal = [(ip, d) for ip, d in stats.items()
              if ip not in EXCLUDE and ip not in new_scanners and d['n'] >= 2]
    normal.sort(key=lambda x: -x[1]['n'])

    all_ts = [d['first'] for d in stats.values() if d['first']]
    ts_range = f"{min(all_ts)[:17]} ~ {max(all_ts)[:17]}" if all_ts else 'N/A'

    print('🌙 晚风 · 安全巡检报告')
    print(f"📅 分析周期：{ts_range}")
    print()
    print('━━━ 🛡 黑名单更新 ━━━')
    print(f"上期规则：{len(existing)} 条")
    print(f"本期新增：{len(added)} 条")
    print(f"本期移除：{len(removed)} 条")
    print(f"当前规则：{len(final)} 条")
    print(f"重载状态：{reload_msg}")
    print()
    print(f'━━━ 👥 正常访问 IP（共 {len(normal)} 个，已过滤一次性噪音）━━━')
    for ip, d in normal[:40]:
        uas = list(d['ua'])
        ua0 = uas[0] if uas else ''
        dev = device(ua0)
        tag = {'iPhone': '📱', 'iOS系统服务': '🔄', 'Mac': '💻', 'Windows': '💻', 'Linux': '💻'}.get(dev, '❓')
        print(f"{tag} {ip:18s} {d['n']:4d}次  {d['first'][:17]} ~ {d['last'][:17]}  {dev}")
    if len(normal) > 40:
        print(f"  … 其余 {len(normal) - 40} 个 IP（访问量较低）已省略")


if __name__ == '__main__':
    main()
