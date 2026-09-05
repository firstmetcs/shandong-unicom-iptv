#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找 epg.xml 中无 programme 的频道，按 display-name 在 sggc.xml 中找到
对应频道，把其节目复制补充到 epg.xml 对应频道下（改写 channel 属性指向
epg 频道 id）。

作为模块使用:
    from fill_epg import fill_epg
    result = fill_epg('epg.xml')                      # 默认从 GitHub 下载 sggc
    result = fill_epg('epg.xml', 'sggc.xml')          # 本地文件作为来源
    result = fill_epg('epg.xml', log=lambda m: None)  # 静默模式
    # result: {'channels', 'empty', 'filled', 'unmatched', 'added', 'output'}

命令行用法:
    python fill_epg.py [epg.xml] [sggc来源] [-o 输出文件] [--no-backup]

sggc来源 默认为 GitHub 上的 sggc.xml.gz 在线地址（自动下载并解压），
也可传本地 xml 文件路径。默认原地更新 epg.xml（首次运行生成 epg.xml.bak
备份）。脚本可重复执行：已有节目的频道不会被再次处理，天然幂等。
"""
import argparse
import copy
import gzip
import os
import re
import shutil
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict

SGGC_URL = 'https://gh-proxy.com/https://github.com/sggc/SD-EPG/raw/refs/heads/main/EPG/sggc.xml.gz'

# 归一化时尝试去掉的频道名后缀，用于消除 "-标清"/"-高清"/"HD" 等写法差异
STRIP_SUFFIXES = ('-标清', '-高清', '标清', '高清', '-hd', 'hd')


def norm(name):
    """去空白、统一小写。"""
    return re.sub(r'\s+', '', name or '').lower()


def name_keys(name):
    """生成一个频道名的多级归一化候选键，按优先级排列：
    原名 > 去清晰度后缀 > 去连字符（含再去后缀）。"""
    n = norm(name)
    keys = [n]
    for suf in STRIP_SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            keys.append(n[:-len(suf)])
    no_dash = n.replace('-', '').replace('－', '')
    if no_dash != n:
        keys.append(no_dash)
        for suf in STRIP_SUFFIXES:
            if no_dash.endswith(suf) and len(no_dash) > len(suf):
                keys.append(no_dash[:-len(suf)])
    out, seen = [], set()
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def load_sggc(source, log=print):
    """来源为 http(s) URL 时下载并解压（.gz），否则按本地 xml 文件解析。"""
    if source.startswith(('http://', 'https://')):
        log(f'[0] 下载 {source}')
        req = urllib.request.Request(source, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
        if source.endswith('.gz'):
            data = gzip.decompress(data)
        log(f'[0] 下载完成，解压后 {len(data) / 1048576:.1f} MB')
        return ET.fromstring(data)
    return ET.parse(source).getroot()


def build_alias_table(sggc_root):
    """sggc 的 display-name（含别名）归一化键 -> sggc channel id。"""
    alias = {}
    for ch in sggc_root.findall('channel'):
        cid = ch.get('id')
        for dn in ch.findall('display-name'):
            if dn.text:
                for k in name_keys(dn.text):
                    alias.setdefault(k, cid)
    return alias


def date_range_of(root):
    """返回已有 programme 的日期范围 (min, max)，格式 YYYYMMDD。"""
    days = [p.get('start', '')[:8] for p in root.findall('programme') if p.get('start')]
    if not days:
        return None, None
    return min(days), max(days)


def reindent_programme(prog):
    """sggc 的 programme 缩进比 epg 深 2 格，复制后调整对齐。"""
    if len(prog):
        if prog.text is None or prog.text.strip() == '':
            prog.text = '\n  '
        for i, child in enumerate(prog):
            if child.tail is None or child.tail.strip() == '':
                child.tail = '\n' if i == len(prog) - 1 else '\n  '
    prog.tail = '\n'


def fill_epg(epg_path, sggc_source=SGGC_URL, output=None, backup=True, log=print):
    """补充 epg 文件中无 programme 的频道。

    参数:
        epg_path:   待补充的 epg xml 文件
        sggc_source: 节目来源，http(s) URL（.gz 自动解压）或本地 xml 路径
        output:     输出文件，默认原地覆盖 epg_path
        backup:     原地覆盖时是否生成一次性的 <epg>.bak 备份
        log:        日志回调，默认 print，传 lambda m: None 可静默

    返回摘要 dict:
        {'channels': 频道总数, 'empty': [(cid, name)],
         'filled': [(cid, name, sggc_id, 补充条数)], 'unmatched': [(cid, name)],
         'added': 补充总条数, 'output': 输出文件路径}
    """
    log("=" * 60)
    log("补充 epg 文件中无 programme 的频道")
    log("=" * 60)
    epg_tree = ET.parse(epg_path)
    epg_root = epg_tree.getroot()
    sggc_root = load_sggc(sggc_source, log=log)

    # 1. 统计 epg 各频道节目数，找出无 programme 的频道
    prog_count = defaultdict(int)
    for p in epg_root.findall('programme'):
        prog_count[p.get('channel')] += 1
    empty_channels = []
    for ch in epg_root.findall('channel'):
        if prog_count.get(ch.get('id'), 0) == 0:
            dn = ch.find('display-name')
            empty_channels.append((ch.get('id'), dn.text if dn is not None else ''))
    total_channels = len(epg_root.findall('channel'))
    log(f'[1] {epg_path}: 频道 {total_channels} 个，其中无节目 {len(empty_channels)} 个')

    result = {'channels': total_channels, 'empty': empty_channels,
              'filled': [], 'unmatched': [], 'added': 0, 'output': None}
    if not empty_channels:
        log('所有频道均有节目，无需处理。')
        return result

    # 2. 建 sggc 别名表并匹配
    alias = build_alias_table(sggc_root)
    sggc_progs = defaultdict(list)
    for p in sggc_root.findall('programme'):
        sggc_progs[p.get('channel')].append(p)

    matched = []
    for cid, name in empty_channels:
        hit = next((alias[k] for k in name_keys(name) if k in alias), None)
        if hit:
            matched.append((cid, name, hit))
        else:
            result['unmatched'].append((cid, name))

    # 3. 按 epg 已有节目日期范围过滤后复制
    dmin, dmax = date_range_of(epg_root)
    total_added = 0
    for cid, name, sid in matched:
        progs = [p for p in sggc_progs.get(sid, [])
                 if dmin is None or dmin <= p.get('start', '')[:8] <= dmax]
        progs.sort(key=lambda p: p.get('start', ''))
        for p in progs:
            np = copy.deepcopy(p)
            np.set('channel', cid)
            reindent_programme(np)
            epg_root.append(np)
        total_added += len(progs)
        result['filled'].append((cid, name, sid, len(progs)))
        mark = '' if progs else '  (sggc 中该频道无日期范围内的节目)'
        log(f'    {name} -> sggc[{sid}]: +{len(progs)} 条{mark}')

    log(f'[2] 匹配成功 {len(matched)} 个频道，共补充 {total_added} 条节目')
    if result['unmatched']:
        log(f"[3] 未匹配 {len(result['unmatched'])} 个（sggc 中无对应频道，保持原样）:")
        for _, name in result['unmatched']:
            log(f'    {name}')
    else:
        log('[3] 全部匹配')
    result['added'] = total_added

    # 4. 写出
    out_path = output or epg_path
    if out_path == epg_path and backup:
        bak = epg_path + '.bak'
        if not os.path.exists(bak):
            shutil.copy2(epg_path, bak)
            log(f'[4] 已备份原文件 -> {bak}')
    epg_tree.write(out_path, encoding='UTF-8', xml_declaration=True)
    log(f'[4] 已写入 {out_path}')
    result['output'] = out_path
    return result


def main():
    ap = argparse.ArgumentParser(description='按 display-name 从 sggc.xml 补充 epg.xml 缺失节目')
    ap.add_argument('epg', nargs='?', default='epg.xml', help='待补充的 epg 文件 (默认 epg.xml)')
    ap.add_argument('sggc', nargs='?', default=SGGC_URL,
                    help='节目来源：URL 或本地 xml 文件 (默认 GitHub sggc.xml.gz)')
    ap.add_argument('-o', '--output', default=None, help='输出文件，默认原地覆盖 epg 文件')
    ap.add_argument('--no-backup', action='store_true', help='原地覆盖时不生成 .bak 备份')
    args = ap.parse_args()
    fill_epg(args.epg, sggc_source=args.sggc, output=args.output,
             backup=not args.no_backup)


if __name__ == '__main__':
    main()
