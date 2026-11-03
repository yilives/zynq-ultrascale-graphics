# SPDX-License-Identifier: MIT
"""Small, hardware-oriented student. Teachers remain independent references.

All feature maps use signed INT8, scale 1/128, zero point 0. RGB input/output
are centered at 128. Per-output-channel weight scales are powers of two.
Reflection/instance/group normalization of the teachers is NOT silently folded:
the small student is explicitly trained by distillation instead.
"""
import torch
from torch import nn
from torch.nn import functional as F


def straight_through(x, rounded):
    return x + (rounded - x).detach()


class TinyStyle(nn.Module):
    channels = (3, 8, 8, 3)

    def __init__(self):
        super().__init__()
        self.layers = nn.ModuleList(nn.Conv2d(a, b, 3) for a, b in zip(self.channels, self.channels[1:]))

    @staticmethod
    def quant_parameters(layer):
        w = layer.weight
        shift = torch.floor(torch.log2(127 / w.detach().abs().flatten(1).amax(1).clamp_min(1e-8))).clamp(0, 20)
        scale = 2 ** shift
        wq = torch.round(w * scale[:, None, None, None]).clamp(-127, 127)
        bq = torch.round(layer.bias * scale * 128)
        return shift, scale, wq, bq

    def forward(self, x, quantized=False):
        for index, layer in enumerate(self.layers):
            if quantized:
                shift, scale, wq, bq = self.quant_parameters(layer)
                w = straight_through(layer.weight, wq / scale[:, None, None, None])
                b = straight_through(layer.bias, bq / (scale * 128))
                x = F.conv2d(F.pad(x, (1, 1, 1, 1), mode='replicate'), w, b)
            else:
                x = layer(F.pad(x, (1, 1, 1, 1), mode='replicate'))
            low = -1 if index == 2 else 0
            x = x.clamp(low, 127 / 128)
            if quantized:
                rounded = x.sign() * torch.floor(x.abs() * 128 + 0.5) / 128
                x = straight_through(x, rounded)
        return x

    def export(self):
        result = []
        for layer in self.layers:
            shift, _, weight, bias = self.quant_parameters(layer)
            result.append({'weight': weight.to(torch.int8).tolist(), 'bias': bias.to(torch.int32).tolist(),
                           'shift': shift.to(torch.int32).tolist()})
        return {'format': 'RIXCNN1', 'channels': list(self.channels), 'padding': 'replicate',
                'activation_scale': '1/128', 'zero_point': 0,
                'rounding': 'nearest_ties_away_from_zero', 'layers': result}
