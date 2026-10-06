# StyleCam v21 硬件组交付说明

日期：2026-10-05。

## 可直接接入的版本

本包默认候选为 `v21b_ukiyoe_qat900_soft15`。它只改变训练监督和权重，固定 v6/v8 推理图不变：C24/Fc16、4 个 `dw1` 残差块、13 层卷积、三风格条件 IN、640×480 输入输出，参数 11,028，VGA 卷积 MAC 339,148,800/帧。

给硬件组的部署文件已经成套生成：

- `rtl/gen/v21b_ukiyoe_qat900_640x480/`：`stylenet_top.v`、13 层 `w*.mem/c*.mem`、`cfg.txt`、`net_blob.bin`、`qparams.json/.npz`。
- `sw/net_blob.h`、`sw/in_params.h`：与上述 v21b blob 和 IN 参数配套，已覆盖交付副本中的旧默认头文件。
- `audits/v21b_deploy_blob/`：部署目录的独立副本，便于校验哈希和拷贝到集成工程。
- `runs/art_styles_c24_v21b_ukiyoe_color_block/student.pt`：FP32 研究候选；`runs/art_styles_c24_v21b_ukiyoe_qat900_soft15/student.pt`：选定 INT8/QAT 候选。

不要把 v21b 的 `.pt`、`net_blob.bin`、`qparams`、`stylenet_top.v` 和 `in_params.h` 与其它版本混用。`net_blob.bin` 不是 FPGA bitstream；`vendor_camera_only_images/` 中的 bit/hex 仍只是原厂摄像头演示镜像。

## 文件校验

- v21b QAT checkpoint：`d0d19437fa91a8424a38baddc2f03d2bbf79bb6a93da94342fb8bef97fd907eb`
- v21b frozen qparams JSON：`b3760512b460306f3c3cff8b0dec879625d3a53d2b32500293408ab8833d98a0`
- v21b `net_blob.bin`：`9a1b2382e2c9953f775f5c9c7e5b06fd93e5cad9bcdffa8086dbbe41541a5d5b`
- cfg 写入 4,050 次，blob 48,616 字节，低于 500 KB 限制。

完整文件哈希见本目录根部的 `sha256_manifest.json`。

## 已完成的可运行验证

使用同一 v21b checkpoint、冻结 R/S 合同和 16 张 VGA 标定图导出参数，然后用包内样本完整复验。正式交付验证为 `audits/delivery_pc_v21_20261005/verification.json` 和其 `rtl_style0/rtl_style1/rtl_style2/rtl_serialized_switch/result.json`。早期 `v21b_pc_validation_ncal16/validation.json` 保留为中间记录，该流程未完成 VGA，不能作为完整通过证据：

- Verilator 5.48.0：三风格各一帧 640×480，13 层 mismatch=0，像素和所选层统计一致。这三项使用同帧 IN oracle，只证明算术。
- 实际初始 bank/cfg：48×32 三帧，不复位切换三风格，逐层/像素/统计通过。完整实际向量在 `vga_and_bank_vectors.zip`，可解压查看。
- 三种风格的固件 IN 双 bank 刷新均 `pass_check=true`，M/B 最大误差为 0，1,072 次写入。
- blob 格式、风格数、cfg 写入数和 500 KB 上限检查通过。
- GCC 主机 guard、SC431HAI/旧传感器 两条分支语法检查通过；包内 RTL/mem/cfg 重新生成逐字节一致。
- 缩小系统仿真使用本版 qparams，合成 RGB 相机→AXI 内存模型→32×24 NN→显示/OSD：原图区、风格图区、全屏均 0 像素差异，统计一致，显示欠载 0。记录为 `audits/delivery_pc_v21_20261005/system/`，不属于真实传感器视频或 VGA 性能测试。
- Efinity 2026.1.132、Ti60F225/I3：本版 SC431HAI `vision_top` 子系统 map 退出码 0。资源为 173 RAM10、125 DSP48、20,629 LUT4、14,388 FF；63 秒综合，不含完整板级 SoC/DDR/CSI/HDMI。工具提示用户配置目录含中文，实际综合 PASS，原日志保留在 `audits/delivery_pc_v21_20261005/efinity/`。
- 24 图风格/量化指标、30 帧 PC USB 相机回放指标和同图对比图见 `audits/v21b_ukiyoe_qat900_soft15_paired24/`、`audits/v21b_ukiyoe_camera30_fp32/`、`audits/v21b_ukiyoe_camera30_integer/`、`audits/v21_selected_city_comparison/`。

PC 验证命令（从 `StyleCam` 根目录执行，无需完整 COCO，输出目录应尚不存在；工具路径换成自己的安装位置）：

```powershell
python -m pip install -r requirements_pc.txt
python -X utf8 tools/check_manifest.py
python -X utf8 tools/verify_delivery.py `
  --workdir C:/fpga_check/v21_pc --gcc C:/mingw64/bin/gcc.exe

# Small RTL regression with Icarus:
python -X utf8 tools/verify_delivery.py `
  --workdir C:/fpga_check/v21_small --rtl `
  --iverilog C:/iverilog/bin/iverilog.exe --vvp C:/iverilog/bin/vvp.exe `
  --gcc C:/mingw64/bin/gcc.exe

# Full VGA: Verilator timing support and MinGW C++20 required.
python -X utf8 tools/verify_delivery.py `
  --workdir C:/fpga_check/v21_vga --rtl --vga --verilator `
  --verilator-root C:/tools/verilator --compiler-bin C:/mingw64/bin `
  --gcc C:/mingw64/bin/gcc.exe

python -X utf8 tools/prepare_efinity_check.py --stage C:/fpga_check/v21_map
Set-Location C:/fpga_check/v21_map
& D:/bin/efx_run.bat vision_map.xml --prj --flow map `
  --output_dir outflow --work_dir work_syn --timeout 300
```

## 接入顺序

1. 交付中的 `syn/vision_map.xml` 已指向 v21 顶层。板级工程仅编译这一份 `stylenet_top.v`，将 `rtl/gen/v21b_ukiyoe_qat900_640x480/` 的生成 RTL/mem/cfg/blob 作为同一版本整体接入，保留厂商摄像头、DDR、HDMI 和 SoC 的真实约束。
2. 将 `sw/net_blob.h`、`sw/in_params.h` 与同一 v21b blob 一起编译，保留固件的 blob 长度、风格数、地址和 board profile 检查。
3. 先运行 PC/RTL 回归，再做 Efinity map、布局布线和板端唯一 frame_id、帧率、风格切换及真实 SC431HAI 视频验收。
4. 只有 bitstream、匹配 ELF、真实传感器视频和持续帧率均通过后，才把本版标为板端部署版。

本交付没有伪造板端结果：当前仍没有完整 StyleCam 板级 bitstream/ELF，也没有完成真实 SC431HAI/Ti60 板卡验证。`deployment_status.json` 保留这些状态。
