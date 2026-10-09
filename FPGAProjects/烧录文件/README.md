# 烧录文件

当前版本：[RISC-V 08 / V21b / 原生 BGGR 与 RGB 水平翻转](20261009_RISCV08_BGGR_RGBMirror/README.md)，ID `53430a08`。已固化 Flash 地址 0，1,073,814 字节独立回读一致，复位自主启动验收通过，用户已确认画面正常。

历史恢复包：

- [RISC-V 04 / 传感器水平镜像](20261008_RISCV_HMirror/README.md)
- [V21b / SCU09 全 RTL](20261006_SCU09_V21b_摄像头版/README.md)
- [V6 / SCU08 摄像头修复](20261006_SCU08_V6_摄像头修复版/README.md)

各包对应各自源码版本，BIT 用于临时 JTAG，HEX 用于固化。当前工具以 08 为默认，模型 Flash 地址 `0x200000` 保持不变；详细操作、SHA256 和证据见当前发布包。
