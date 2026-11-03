#!/usr/bin/env python3
"""
numeric_compare.py -- 浮点/定点数值逐位比对器

对应 skill 条目 P10：浮点运算重排会改变结果，必须量化而不是假定。

用途
    比较两条计算路径（旧实现 vs 新实现）的输出，报告：
      · 逐位不同的字段数
      · 最大绝对差
      · 最大 ULP（unit in the last place）差
    用于判断「数学上等价」的改动是否真的逐位等价。

为什么需要它
    "最大绝对差很小" 不等于 "可以放行"。
    本项目的一个真实案例：MVP 矩阵预乘在数学上等价，但 float32 下有
    47.08% 的坐标字段逐位不同，最大 ULP 差 1,144。
    若下游对逐位敏感（定点化、裁剪判定、深度比较），这就是缺陷。

用法
    python3 numeric_compare.py old.bin new.bin --dtype float32 --count 11520
    python3 numeric_compare.py old.bin new.bin --dtype float32 --shape 11520,3

参数
    --dtype   float32 | float64 | int32 | int16 | uint32 | uint16
    --count   元素总数（与 --shape 二选一）
    --shape  逗号分隔，如 11520,3
    --stride 每隔多少元素取一个（默认 1，全比）
    --quiet  只输出结论行

退出码
    0  逐位完全一致
    1  存在逐位差异
    2  输入错误
"""
import argparse
import struct
import sys

DTYPES = {
    'float32': ('f', 4),
    'float64': ('d', 8),
    'int32': ('i', 4),
    'uint32': ('I', 4),
    'int16': ('h', 2),
    'uint16': ('H', 2),
    'int8': ('b', 1),
    'uint8': ('B', 1),
}


def load(path, dtype, count, stride):
    fmt, size = DTYPES[dtype]
    with open(path, 'rb') as f:
        raw = f.read()
    total = len(raw) // size
    if count and count * stride > total:
        print('ERROR: %s 只有 %d 个元素，请求 %d' % (path, total, count * stride),
              file=sys.stderr)
        sys.exit(2)
    n = count if count else total
    out = []
    for i in range(0, n, stride):
        off = i * size
        out.append(struct.unpack_from('<' + fmt, raw, off)[0])
    return out


def ulp_diff(a, b, dtype):
    """返回 a、b 之间相差多少个可表示值（按位模式解释）。"""
    if dtype.startswith('float'):
        fmt = '<f' if dtype == 'float32' else '<d'
        ia = struct.unpack('<I' if dtype == 'float32' else '<Q',
                           struct.pack(fmt, a))[0]
        ib = struct.unpack('<I' if dtype == 'float32' else '<Q',
                           struct.pack(fmt, b))[0]
        # 映射成有符号有序整数，处理符号位
        bits = 32 if dtype == 'float32' else 64
        sign = 1 << (bits - 1)
        ia = -(ia & (sign - 1)) if ia & sign else ia
        ib = -(ib & (sign - 1)) if ib & sign else ib
        return abs(ia - ib)
    return abs(int(a) - int(b))


def main():
    ap = argparse.ArgumentParser(description='逐位数值比对（对应 skill P10）')
    ap.add_argument('old')
    ap.add_argument('new')
    ap.add_argument('--dtype', default='float32', choices=sorted(DTYPES))
    ap.add_argument('--count', type=int, default=0)
    ap.add_argument('--shape', default='')
    ap.add_argument('--stride', type=int, default=1)
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    count = args.count
    if args.shape:
        n = 1
        for p in args.shape.split(','):
            n *= int(p)
        count = n

    a = load(args.old, args.dtype, count, args.stride)
    b = load(args.new, args.dtype, count, args.stride)
    if len(a) != len(b):
        print('ERROR: 元素数不同 %d vs %d' % (len(a), len(b)), file=sys.stderr)
        sys.exit(2)

    nbits = 0
    maxabs = 0.0
    maxulp = 0
    first = None
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            nbits += 1
            if first is None:
                first = (i, x, y)
        d = abs(float(x) - float(y))
        if d > maxabs:
            maxabs = d
        u = ulp_diff(x, y, args.dtype)
        if u > maxulp:
            maxulp = u

    n = len(a)
    pct = (nbits / n * 100.0) if n else 0.0
    if not args.quiet:
        print('元素数      : %d' % n)
        print('逐位不同    : %d  (%.4f%%)' % (nbits, pct))
        print('最大绝对差  : %.10g' % maxabs)
        print('最大 ULP 差 : %d' % maxulp)
        if first:
            print('首个不同    : index=%d  old=%.10g  new=%.10g' % first)
    verdict = 'IDENTICAL' if nbits == 0 else 'DIFFERENT'
    print('VERDICT: %s' % verdict)
    sys.exit(0 if nbits == 0 else 1)


if __name__ == '__main__':
    main()
