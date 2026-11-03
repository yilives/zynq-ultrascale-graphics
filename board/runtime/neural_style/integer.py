# SPDX-License-Identifier: MIT
"""Bit-exact INT8 reference and the strictly ordered RIXCNN1 model format."""
import json
from pathlib import Path
import struct
import numpy as np

MAGIC = b'RIXCNN1\0'
COUNT = 1776


def config_words(model):
    if model['format'] != 'RIXCNN1' or model['channels'] != [3, 8, 8, 3]:
        raise ValueError('unsupported CNN model')
    weights = np.zeros((3, 8, 9, 8), dtype=np.int32)
    biases = np.zeros((3, 8), dtype=np.int32)
    shifts = np.zeros((3, 8), dtype=np.int32)
    for index, layer in enumerate(model['layers']):
        w = np.array(layer['weight'], dtype=np.int32)
        oc, ic, _, _ = w.shape
        if (oc, ic) != [(8, 3), (8, 8), (3, 8)][index] or w.min() < -128 or w.max() > 127:
            raise ValueError('invalid convolution coefficients')
        b, s = np.array(layer['bias'], dtype=np.int64), np.array(layer['shift'], dtype=np.int32)
        if np.any(abs(b) > (1 << 28)) or np.any(s < 0) or np.any(s > 20):
            raise ValueError('bias/shift exceeds the hardware accumulator contract')
        weights[index, :oc, :, :ic] = w.reshape(oc, ic, 9).transpose(0, 2, 1)
        biases[index, :oc], shifts[index, :oc] = b, s
    return np.concatenate([(weights.flatten() & 255).astype(np.uint32), biases.flatten().view(np.uint32), shifts.flatten().astype(np.uint32)])


def decode(words):
    if len(words) != COUNT:
        raise ValueError('invalid model length')
    w = words[:1728].astype(np.uint8).view(np.int8).astype(np.int64).reshape(3, 8, 9, 8)
    b = words[1728:1752].astype(np.uint32).view(np.int32).astype(np.int64).reshape(3, 8)
    s = words[1752:].astype(np.int64).reshape(3, 8)
    if np.any(abs(b) > (1 << 28)) or np.any(s < 0) or np.any(s > 20):
        raise ValueError('invalid bias or shift')
    return w, b, s


def infer(features, words):
    weights, biases, shifts = decode(words)
    x = np.asarray(features, dtype=np.int8).astype(np.int64)
    if x.ndim != 3 or x.shape[2] != 8:
        raise ValueError('features must be HWC, eight signed lanes')
    height, width = x.shape[:2]
    layers = []
    for layer in range(3):
        pad = np.pad(x, ((1, 1), (1, 1), (0, 0)), mode='edge')
        acc = np.broadcast_to(biases[layer], (height, width, 8)).copy()
        for ky in range(3):
            for kx in range(3):
                acc += pad[ky:ky+height, kx:kx+width] @ weights[layer, :, ky*3+kx, :].T
        if acc.min() < -(1 << 31) or acc.max() >= (1 << 31):
            raise OverflowError('INT32 accumulator overflow')
        shift = shifts[layer]
        rounding = np.where(shift == 0, 0, 1 << np.maximum(shift - 1, 0))
        scaled = ((abs(acc) + rounding) >> shift) * np.sign(acc)
        x = scaled.clip(-128 if layer == 2 else 0, 127)
        layers.append(x.astype(np.int8))
    return layers[-1], layers


def save_binary(path, words):
    Path(path).write_bytes(MAGIC + struct.pack('<I', COUNT) + np.asarray(words, dtype='<u4').tobytes())


def load_binary(path):
    data = Path(path).read_bytes()
    if len(data) != 12 + COUNT*4 or data[:8] != MAGIC or struct.unpack_from('<I', data, 8)[0] != COUNT:
        raise ValueError('invalid RIXCNN1 model file')
    words = np.frombuffer(data, dtype='<u4', offset=12).copy()
    decode(words)
    return words
