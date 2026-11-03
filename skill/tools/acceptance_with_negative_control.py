#!/usr/bin/env python3
"""
acceptance_with_negative_control.py -- 带强制负对照的验收器

对应 skill 条目 P14：验收脚本本身会是最大的假失败源。

核心思想
    一个"通过"的验收结论，只有在**验证器被证明能报错**时才有意义。
    否则验证器可能永远返回"通过"——你不会知道。

    本脚本强制先跑一次**负对照**：故意把一个已知错误的输入喂给检查器。
    如果检查器抓不到这个错误，脚本直接拒绝出"通过"结论。

为什么需要它
    本项目两次真实事故：
      1. 验收器把显示模式与双缓冲 bank 位一起比较，导致 bank 1 的正常值 0x203
         被误判为"快照过期"——**其实快照是好的**。
      2. 验收器把「单行汇总统计」误当成「多行时间序列」，拒绝了实际处理了
         1.07 亿顶点的正常结果。
    两次都是"验收器错"，不是"实现错"。

用法
    python3 acceptance_with_negative_control.py \
        --reference golden.bin --actual new.bin --dtype uint16

    或作为库使用：
        from acceptance_with_negative_control import acceptance
        result = acceptance(ref_bytes, act_bytes, negative_control=True)

退出码
    0  负对照通过 且 实际数据通过
    1  实际数据不一致
    3  负对照未通过（验证器无效，结论不可信）
"""
import argparse
import sys


def compare(a, b):
    """逐字节比较，返回 (是否一致, 首个差异位置, 差异字节数)。"""
    if len(a) != len(b):
        return False, 0, abs(len(a) - len(b))
    diff = 0
    first = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            diff += 1
            if first is None:
                first = i
    return diff == 0, first, diff


def negative_control(a, check_fn):
    """
    对一个"已知正确"的输入做人工破坏，确认 check_fn 能报错。
    返回 True 表示验证器有效。
    """
    if not a:
        return False
    # 破坏方式 1：翻一个字节
    mut = bytearray(a)
    mut[0] ^= 0xFF
    ok1, _, _ = check_fn(a, bytes(mut))
    # 破坏方式 2：截断一半
    half = len(a) // 2
    ok2, _, _ = check_fn(a, a[:half])
    # 破坏方式 3：末尾追加
    ok3, _, _ = check_fn(a, a + b'\x00')
    # 三种破坏都必须被检出
    return (not ok1) and (not ok2) and (not ok3)


def acceptance(reference, actual, enforce_negative_control=True):
    """
    返回 dict：
        {'ok': bool, 'negative_control_ok': bool, 'detail': {...}}
    """
    nc = negative_control(reference, compare) if enforce_negative_control else True
    same, first, diff = compare(reference, actual)
    res = {
        'ok': bool(same and nc),
        'negative_control_ok': bool(nc),
        'detail': {
            'identical': same,
            'first_diff_offset': first,
            'diff_bytes': diff,
            'reference_bytes': len(reference),
            'actual_bytes': len(actual),
        },
    }
    return res


def main():
    ap = argparse.ArgumentParser(
        description='带强制负对照的验收器（对应 skill P14）')
    ap.add_argument('--reference', required=True)
    ap.add_argument('--actual', required=True)
    ap.add_argument('--skip-negative-control', action='store_true',
                    help='不推荐；仅用于调试验证器本身')
    args = ap.parse_args()

    ref = open(args.reference, 'rb').read()
    act = open(args.actual, 'rb').read()

    r = acceptance(ref, act, not args.skip_negative_control)

    print('参考文件     : %s  (%d 字节)' % (args.reference, len(ref)))
    print('实际文件     : %s  (%d 字节)' % (args.actual, len(act)))
    print('负对照       : %s' % ('通过（验证器能检出错误）'
                                if r['negative_control_ok'] else '** 未通过 **'))
    print('逐字节一致   : %s' % ('是' if r['detail']['identical'] else '否'))
    if not r['detail']['identical']:
        print('  首个差异偏移 : %d' % r['detail']['first_diff_offset'])
        print('  差异字节数   : %d' % r['detail']['diff_bytes'])

    if not r['negative_control_ok']:
        print('\nVERDICT: INCONCLUSIVE —— 验证器本身无效，不能给出通过结论')
        sys.exit(3)
    if not r['detail']['identical']:
        print('\nVERDICT: FAIL')
        sys.exit(1)
    print('\nVERDICT: PASS（含有效负对照）')
    sys.exit(0)


if __name__ == '__main__':
    main()
