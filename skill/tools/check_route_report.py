#!/usr/bin/env python3
"""
check_route_report.py -- Vivado 布线报告检查器

对应 skill 条目 P1（OOC 面积不能直接相加）与 P3（布局失败时任何时序数字都不存在）。

用途
    从 Vivado 的 utilization / timing / drc 报告里抽取关键事实，并判定：
      · 这份报告是综合阶段、布局前估计，还是布线后（唯一可信）
      · LUT / FF / BRAM / DSP 是否超容量
      · WNS / WHS 是否为正，有无失败端点
    若设计未完成布线，直接拒绝给出任何时序结论。

为什么需要它
    本项目的一个真实事故：同一份报告里 WNS +0.741 ns（看起来很好）
    但 WHS -0.110 ns（保持违例），而且 place_design 根本没成功。
    把布局前的统计估计当成布线后时序，是最常见的误读。

用法
    python3 check_route_report.py --util utilization.rpt [--timing timing.rpt]
    python3 check_route_report.py --log implement.log      # 从日志抓 Summary 行

退出码
    0  布线完成且全部通过
    1  有违例（超容量 / 负裕量 / 失败端点）
    2  无法确定状态（缺报告或未布线）
"""
import argparse
import os
import re
import sys

# Vivado utilization.rpt 的典型行：| CLB LUTs  | 64033 | 0 | 0 | 70560 | 90.75 |
UTIL_PAT = {
    'lut':  re.compile(r'\|\s*CLB LUTs\s*\|\s*([\d.]+)\s*\|.*?\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'),
    'ff':   re.compile(r'\|\s*CLB Registers\s*\|\s*([\d.]+)\s*\|.*?\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'),
    'bram': re.compile(r'\|\s*Block RAM Tile\s*\|\s*([\d.]+)\s*\|.*?\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'),
    'dsp':  re.compile(r'\|\s*DSPs\s*\|\s*([\d.]+)\s*\|.*?\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|'),
}

# timing.rpt 里 Intra Clock Table 的 WNS 行
WNS_PAT = re.compile(r'^\s*(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)')

STAGE_PAT = {
    'synth':   re.compile(r'Design State\s*:\s*Synthesized', re.I),
    'placed':  re.compile(r'Design State\s*:\s*Placed', re.I),
    'routed':  re.compile(r'Design State\s*:\s*Routed', re.I),
}


UTIL_NAME = {
    'lut': 'CLB LUTs',
    'ff': 'CLB Registers',
    'bram': 'Block RAM Tile',
    'dsp': 'DSPs',
}


def _num(s):
    try:
        return float(s.replace(',', '').strip())
    except ValueError:
        return None


def parse_util(path):
    """
    按 | 分列解析。Vivado 的行格式：
        | CLB LUTs  | 64033 | 0 | 0 | 70560 | 90.75 |
    字段索引: 0='' 1=名称 2=Used 3..-3=各项  -3=Total  -2=Pct  -1=''
    """
    txt = open(path, encoding='utf-8', errors='replace').read()
    stage = None
    for k, p in STAGE_PAT.items():
        if p.search(txt):
            stage = k

    out = {}
    for line in txt.splitlines():
        if '|' not in line:
            continue
        cols = [c.strip() for c in line.split('|')]
        if len(cols) < 6:
            continue
        name = cols[1]
        for key, want in UTIL_NAME.items():
            if name != want:
                continue
            used = _num(cols[2])
            total = _num(cols[-3])
            if used is None or total is None:
                continue
            # 同一名称可能出现多次（不同表格），保留 Total 最大的一行
            if key in out and out[key][1] >= total:
                continue
            out[key] = (used, total)
    return stage, out


def parse_timing(path):
    rows = []
    for line in open(path, encoding='utf-8', errors='replace'):
        m = WNS_PAT.match(line)
        if m and m.group(1) not in ('Clock', '-----', 'From'):
            try:
                rows.append({'clock': m.group(1),
                             'wns': float(m.group(2)),
                             'tns': float(m.group(3)),
                             'fail_ep': int(m.group(4)),
                             'total_ep': int(m.group(5)),
                             'whs': float(m.group(6))})
            except ValueError:
                pass
    return rows


def parse_log(path):
    txt = open(path, encoding='utf-8', errors='replace').read()
    wns = whs = None
    routed = bool(re.search(r'write_bitstream completed successfully', txt))
    for m in re.finditer(r'Estimated Timing Summary \| WNS=\s*(-?[\d.]+)\s*\|.*?WHS=\s*(-?[\d.]+)', txt):
        wns, whs = float(m.group(1)), float(m.group(2))
    if wns is None:
        for m in re.finditer(r'WNS=\s*(-?[\d.]+)\s*\|.*?WHS=\s*(-?[\d.]+)', txt):
            wns, whs = float(m.group(1)), float(m.group(2))
    limited = bool(re.search(r'timing requirements are not met', txt, re.I))
    return {'wns': wns, 'whs': whs, 'bitstream': routed, 'violated': limited}


def main():
    ap = argparse.ArgumentParser(description='Vivado 布线报告检查（对应 skill P1/P3）')
    ap.add_argument('--util')
    ap.add_argument('--timing')
    ap.add_argument('--log')
    args = ap.parse_args()

    ok = True
    stage = None

    if args.util and os.path.exists(args.util):
        stage, util = parse_util(args.util)
        print('== 资源（%s）==' % (stage or '未知阶段'))
        for k in ('lut', 'ff', 'bram', 'dsp'):
            if k in util:
                used, cap = util[k]
                pct = (used / cap * 100.0) if cap else 0
                over = used > cap
                ok = ok and not over
                print('  %-5s %10.1f / %-10.1f %6.2f%%%s'
                      % (k.upper(), used, cap, pct, '   ** 超容量 **' if over else ''))
        if stage != 'routed':
            print('  ! 设计状态不是 Routed —— 以上均为布局前估计，不能作为最终结论')

    if args.timing and os.path.exists(args.timing):
        rows = parse_timing(args.timing)
        print('== 时序（Intra Clock）==')
        if not rows:
            print('  ! 未解析到时钟行，请检查报告格式')
        worst = None
        for r in rows:
            flag = ''
            if r['wns'] < 0 or r['whs'] < 0 or r['fail_ep'] > 0:
                flag = '   ** 违例 **'
                ok = False
            print('  %-40s WNS %+8.3f  WHS %+8.3f  失败端点 %d/%d%s'
                  % (r['clock'][:40], r['wns'], r['whs'], r['fail_ep'], r['total_ep'], flag))
            if worst is None or r['wns'] < worst:
                worst = r['wns']
        if worst is not None:
            print('  最小 WNS: %+.3f ns' % worst)

    if args.log and os.path.exists(args.log):
        d = parse_log(args.log)
        print('== 实现日志 ==')
        print('  位流已生成 : %s' % ('是' if d['bitstream'] else '否'))
        print('  WNS        : %s' % ('%.3f ns' % d['wns'] if d['wns'] is not None else '未找到'))
        print('  WHS        : %s' % ('%.3f ns' % d['whs'] if d['whs'] is not None else '未找到'))
        if d['violated']:
            print('  ! 日志明确记录时序未满足')
            ok = False
        if not d['bitstream']:
            print('  ! 未生成位流 —— 不得声称「时序通过」')
            ok = False

    if stage and stage != 'routed':
        print('\n结论：报告不是布线后状态，无法给出最终时序判定。')
        sys.exit(2)

    print('\n%s' % ('VERDICT: PASS' if ok else 'VERDICT: FAIL'))
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
