# 共用仿真工具

当前仿真使用 Icarus Verilog 13.0；本机安装于 iverilog/mingw64/bin，编译器与运行时二进制不加入 Git。
当前和历史硬件工程从这里寻找 iverilog/vvp。克隆仓库后先安装工具并放到该目录；独立摄像头工程还支持 IVERILOG_BIN 环境变量或系统 PATH。
Efinity 2026.1 与 Python 按整机 README 配置；网络/IN 数值对拍还需要 NumPy、PyTorch、Pillow。
