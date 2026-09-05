#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查找 epg.xml 中无 programme 的频道，按 display-name 在 sggc.xml 中找到
对应频道，把其节目复制补充到 epg.xml 对应频道下（改写 channel 属性指向
epg 频道 id）。同时检查各频道节目时间是否连续，不连续时从 sggc 取缺失
时间段补充（边界处裁剪对齐，epg 已有内容优先、不覆盖）。
处理前先删除同一频道下起止时间完全相同的重复节目（epg 与 sggc 来源
均去重，各保留第一条）。

作为模块使用:
    from fill_epg import fill_epg
    result = fill_epg('epg.xml')                      # 默认从 GitHub 下载 sggc
    result = fill_epg('epg.xml', 'sggc.xml')          # 本地文件作为来源
    result = fill_epg('epg.xml', log=lambda m: None)  # 静默模式
    # result: {'channels', 'empty', 'filled', 'unmatched', 'added',
    #          'deduped', 'sggc_deduped', 'gap_filled', 'gap_inserted',
    #          'gap_no_source', 'output'}

命令行用法:
    python fill_epg.py [epg.xml] [sggc来源] [-o 输出文件] [--no-backup]

sggc来源 默认为 GitHub 上的 sggc.xml.gz 在线地址（自动下载并解压），
也可传本地 xml 文件路径。默认原地更新 epg.xml（首次运行生成 epg.xml.bak
备份）。脚本可重复执行：已补充的频道/缺口不会被再次处理，天然幂等。
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
from datetime import datetime, timedelta

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


TZ_RE = re.compile(r'\s*([+-]\d{4})$')


def parse_ts(s):
    """'20260831000000 +0800' -> 归一化到 UTC 的 datetime，非法返回 None。"""
    if not s or len(s) < 14 or not s[:14].isdigit():
        return None
    try:
        dt = datetime.strptime(s[:14], '%Y%m%d%H%M%S')
    except ValueError:
        return None
    m = TZ_RE.search(s)
    if m:
        o = m.group(1)
        delta = timedelta(hours=int(o[1:3]), minutes=int(o[3:5]))
        dt -= delta if o[0] == '+' else -delta
    return dt


def ts_offset(s):
    m = TZ_RE.search(s or '')
    return m.group(1) if m else '+0800'


def fmt_ts(dt, off='+0800'):
    delta = timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))
    dt = dt + (delta if off[0] == '+' else -delta)
    return dt.strftime('%Y%m%d%H%M%S') + ' ' + off


def fill_gap_from(sggc_list, lo, hi):
    """取覆盖缺口时间段 (lo, hi) 的 sggc 节目，克隆并裁剪到缺口范围内。

    sggc 自身可能存在重叠（长节目压着细排片），这里按开始时间贪心选取
    互不重叠的子集（同时刻优先短节目，保留更细的排片），避免插入重叠。
    """
    cands = []
    for p in sggc_list:
        s, e = parse_ts(p.get('start')), parse_ts(p.get('stop'))
        if s is None or e is None or e <= s or e <= lo or s >= hi:
            continue
        cands.append((s, e, p))
    cands.sort(key=lambda t: (t[0], t[1]))
    out, last_end = [], None
    for s, e, p in cands:
        if last_end is not None and s < last_end:
            continue
        np = copy.deepcopy(p)
        if s < lo:
            np.set('start', fmt_ts(lo, ts_offset(p.get('start'))))
        if e > hi:
            np.set('stop', fmt_ts(hi, ts_offset(p.get('stop'))))
        out.append(np)
        last_end = min(e, hi)
    return out


def child_index(parent, child):
    """按身份查找子元素位置（Element 无 index 方法）。"""
    for i, el in enumerate(parent):
        if el is child:
            return i
    return -1


def dedup_programmes(root):
    """删除同一频道下 start/stop 完全相同的重复节目（保留第一条），返回删除数。"""
    seen = set()
    removed = 0
    for p in root.findall('programme'):
        key = (p.get('channel'), p.get('start'), p.get('stop'))
        if key in seen:
            root.remove(p)
            removed += 1
        else:
            seen.add(key)
    return removed


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
         'added': 空频道补充总条数, 'deduped': epg 去重条数,
         'sggc_deduped': sggc 去重条数,
         'gap_filled': [(cid, name, 缺口段数, 插入条数, 剩余缺口秒)],
         'gap_inserted': 缺口补充总条数, 'gap_no_source': [(cid, name)],
         'output': 输出文件路径}
    """
    log("=" * 60)
    log("补充 epg 文件中无 programme 的频道")
    log("=" * 60)
    epg_tree = ET.parse(epg_path)
    epg_root = epg_tree.getroot()
    # 1. 去重：删除同频道下起止时间完全相同的重复节目（须在匹配/补充前做）
    n_dedup = dedup_programmes(epg_root)
    log(f'[1] 去重: 删除 epg 同频道起止完全相同的重复节目 {n_dedup} 条')
    sggc_root = load_sggc(sggc_source, log=log)
    n_sggc_dedup = dedup_programmes(sggc_root)
    if n_sggc_dedup:
        log(f'[1] 去重: 删除 sggc 来源重复节目 {n_sggc_dedup} 条')

    # 2. 统计 epg 各频道节目数，找出无 programme 的频道
    prog_count = defaultdict(int)
    for p in epg_root.findall('programme'):
        prog_count[p.get('channel')] += 1
    empty_channels = []
    for ch in epg_root.findall('channel'):
        if prog_count.get(ch.get('id'), 0) == 0:
            dn = ch.find('display-name')
            empty_channels.append((ch.get('id'), dn.text if dn is not None else ''))
    total_channels = len(epg_root.findall('channel'))
    log(f'[2] {epg_path}: 频道 {total_channels} 个，其中无节目 {len(empty_channels)} 个')

    result = {'channels': total_channels, 'empty': empty_channels,
              'filled': [], 'unmatched': [], 'added': 0,
              'deduped': n_dedup, 'sggc_deduped': n_sggc_dedup,
              'gap_filled': [], 'gap_inserted': 0, 'gap_no_source': [],
              'output': None}

    # 3. 建 sggc 别名表与节目索引（空频道补充和缺口补充共用）
    alias = build_alias_table(sggc_root)
    sggc_progs = defaultdict(list)
    for p in sggc_root.findall('programme'):
        sggc_progs[p.get('channel')].append(p)
    for sid in sggc_progs:
        sggc_progs[sid].sort(key=lambda p: p.get('start') or '')

    if empty_channels:
        matched = []
        for cid, name in empty_channels:
            hit = next((alias[k] for k in name_keys(name) if k in alias), None)
            if hit:
                matched.append((cid, name, hit))
            else:
                result['unmatched'].append((cid, name))

        # 4. 空频道：按 epg 已有节目日期范围过滤后整体复制
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

        log(f'[3] 空频道: 匹配 {len(matched)} 个，共补充 {total_added} 条节目')
        if result['unmatched']:
            log(f"[4] 未匹配 {len(result['unmatched'])} 个（sggc 中无对应频道，保持原样）:")
            for _, name in result['unmatched']:
                log(f'    {name}')
        else:
            log('[4] 空频道全部匹配')
        result['added'] = total_added
    else:
        log('[3] 所有频道均有节目，跳过空频道补充')

    # 5. 连续性检查：从 sggc 填补已有频道的时间缺口（epg 已有内容优先）
    cid2name = {ch.get('id'): (ch.find('display-name').text
                               if ch.find('display-name') is not None else '')
                for ch in epg_root.findall('channel')}
    by_ch = defaultdict(list)
    for p in epg_root.findall('programme'):
        by_ch[p.get('channel')].append(p)

    sid_cache = {}
    remain_total = 0.0
    bad_intervals = 0
    for cid, progs in by_ch.items():
        progs.sort(key=lambda p: parse_ts(p.get('start')) or datetime.min)
        gaps = []
        for a, b in zip(progs, progs[1:]):
            as_, pe, ns = parse_ts(a.get('start')), parse_ts(a.get('stop')), parse_ts(b.get('start'))
            if pe and as_ and pe < as_:
                # 源数据异常：跨零点节目的 stop 日期写错，stop 早于 start。
                # 这种节目会产生幻影缺口，跳过并统计。
                bad_intervals += 1
                continue
            if pe and ns and ns > pe:
                gaps.append((a, pe, ns))
        if not gaps:
            continue
        if cid not in sid_cache:
            sid_cache[cid] = next(
                (alias[k] for k in name_keys(cid2name.get(cid, '')) if k in alias), None)
        sid = sid_cache[cid]
        if not sid or sid not in sggc_progs:
            result['gap_no_source'].append((cid, cid2name.get(cid, cid)))
            remain_total += sum((hi - lo).total_seconds() for _, lo, hi in gaps)
            continue
        src = sggc_progs[sid]
        inserted, remain = 0, 0.0
        for prev, lo, hi in gaps:
            fill = fill_gap_from(src, lo, hi)
            covered = 0.0
            base = child_index(epg_root, prev) + 1
            for j, np in enumerate(fill):
                np.set('channel', cid)
                reindent_programme(np)
                epg_root.insert(base + j, np)
                covered += (parse_ts(np.get('stop')) - parse_ts(np.get('start'))).total_seconds()
            inserted += len(fill)
            remain += max(0.0, (hi - lo).total_seconds() - covered)
        result['gap_filled'].append((cid, cid2name.get(cid, cid), len(gaps), inserted, remain))
        result['gap_inserted'] += inserted
        remain_total += remain

    if result['gap_filled'] or result['gap_no_source']:
        log(f"[5] 连续性检查: {len(result['gap_filled'])} 个频道插入缺口节目 "
            f"{result['gap_inserted']} 条，补充后仍缺 {remain_total / 3600:.1f} 小时")
        for _, name, n_gap, n_ins, rem in result['gap_filled']:
            if n_ins or rem >= 60:
                log(f'    {name}: 缺口{n_gap}段, 插入{n_ins}条'
                    + (f', 仍缺{rem / 3600:.1f}小时' if rem >= 60 else ''))
        if result['gap_no_source']:
            log(f"    另有 {len(result['gap_no_source'])} 个缺口频道在 sggc 中无匹配，未处理: "
                + ', '.join(n for _, n in result['gap_no_source']))
    else:
        log('[5] 连续性检查: 所有频道节目均连续')
    if bad_intervals:
        log(f"    注: {bad_intervals} 条节目 stop 早于 start（源导出数据异常），已跳过其缺口计算")

    # 6. 写出
    out_path = output or epg_path
    if out_path == epg_path and backup:
        bak = epg_path + '.bak'
        if not os.path.exists(bak):
            shutil.copy2(epg_path, bak)
            log(f'[6] 已备份原文件 -> {bak}')
    epg_tree.write(out_path, encoding='UTF-8', xml_declaration=True)
    log(f'[6] 已写入 {out_path}')
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
