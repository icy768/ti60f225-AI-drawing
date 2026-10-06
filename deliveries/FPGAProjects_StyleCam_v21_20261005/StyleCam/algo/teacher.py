# Johnson 风格迁移网络（pytorch/examples fast_neural_style 结构），仅作蒸馏教师
import re
import torch
import torch.nn as nn
import torch.nn.functional as F


class ConvLayer(nn.Module):
    def __init__(self, cin, cout, k, stride):
        super().__init__()
        self.reflection_pad = nn.ReflectionPad2d(k // 2)
        self.conv2d = nn.Conv2d(cin, cout, k, stride)

    def forward(self, x):
        return self.conv2d(self.reflection_pad(x))


class ResidualBlock(nn.Module):
    def __init__(self, c):
        super().__init__()
        self.conv1 = ConvLayer(c, c, 3, 1)
        self.in1 = nn.InstanceNorm2d(c, affine=True)
        self.conv2 = ConvLayer(c, c, 3, 1)
        self.in2 = nn.InstanceNorm2d(c, affine=True)

    def forward(self, x):
        y = F.relu(self.in1(self.conv1(x)))
        return self.in2(self.conv2(y)) + x


class UpsampleConvLayer(nn.Module):
    def __init__(self, cin, cout, k, stride, upsample=None):
        super().__init__()
        self.upsample = upsample
        self.reflection_pad = nn.ReflectionPad2d(k // 2)
        self.conv2d = nn.Conv2d(cin, cout, k, stride)

    def forward(self, x):
        if self.upsample:
            x = F.interpolate(x, mode="nearest", scale_factor=self.upsample)
        return self.conv2d(self.reflection_pad(x))


class TransformerNet(nn.Module):
    # 输入/输出范围 0~255
    def __init__(self):
        super().__init__()
        self.conv1 = ConvLayer(3, 32, 9, 1)
        self.in1 = nn.InstanceNorm2d(32, affine=True)
        self.conv2 = ConvLayer(32, 64, 3, 2)
        self.in2 = nn.InstanceNorm2d(64, affine=True)
        self.conv3 = ConvLayer(64, 128, 3, 2)
        self.in3 = nn.InstanceNorm2d(128, affine=True)
        self.res1 = ResidualBlock(128)
        self.res2 = ResidualBlock(128)
        self.res3 = ResidualBlock(128)
        self.res4 = ResidualBlock(128)
        self.res5 = ResidualBlock(128)
        self.deconv1 = UpsampleConvLayer(128, 64, 3, 1, upsample=2)
        self.in4 = nn.InstanceNorm2d(64, affine=True)
        self.deconv2 = UpsampleConvLayer(64, 32, 3, 1, upsample=2)
        self.in5 = nn.InstanceNorm2d(32, affine=True)
        self.deconv3 = ConvLayer(32, 3, 9, 1)

    def forward(self, x):
        y = F.relu(self.in1(self.conv1(x)))
        y = F.relu(self.in2(self.conv2(y)))
        y = F.relu(self.in3(self.conv3(y)))
        y = self.res5(self.res4(self.res3(self.res2(self.res1(y)))))
        y = F.relu(self.in4(self.deconv1(y)))
        y = F.relu(self.in5(self.deconv2(y)))
        return self.deconv3(y)


def load_teacher(path, device):
    sd = torch.load(path, map_location="cpu")
    # 旧版 InstanceNorm 存了 running 统计量，需剔除
    for k in list(sd.keys()):
        if re.search(r"in\d+\.running_(mean|var)$", k):
            del sd[k]
    net = TransformerNet()
    net.load_state_dict(sd)
    return net.to(device).eval()


def teacher_macs_per_pixel():
    # 以输入像素为单位的乘加次数（输出面积/输入面积 作权重）
    full = 81 * 3 * 32 + 9 * 64 * 32 + 81 * 32 * 3      # conv1, deconv2, deconv3
    quarter = 9 * 32 * 64 + 9 * 128 * 64                 # conv2, deconv1
    sixteenth = 9 * 64 * 128 + 10 * 9 * 128 * 128        # conv3, 5 个残差块
    return full + quarter / 4 + sixteenth / 16
