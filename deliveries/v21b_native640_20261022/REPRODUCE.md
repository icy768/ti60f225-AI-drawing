# 复核入口

1. 在解压后的DELIVERY_20261022目录运行`python -X utf8 source/verify_final_package.py .`。只读校验包内文件SHA、选定组合、固件字节与CRC、内部链接；不训练、不编译、不烧录。应退出码0且JSON中passed=true。
2. FINAL_DECISION.md给出完整SHA；candidates/D1B60_B_FWP1/包含匹配BIT/HEX/固件/blob/INROM及固件byte-lane ROM。baseline/和rollback_RISCV11/保持原字节。
3. source/原实验程序供复现审查；重跑需要原工作区、Python/PyTorch/NumPy/Pillow/Unicorn和工具，训练数据与全部checkpoint没有复制。当前研究已结束，包验证不调用训练、BRAM更新或BIT生成。
4. evidence/为带范围的本地测试/历史板测来源；research/R44为可离线打开的三风格盲页与key、review、实验元数据。历史部署标志以FINAL_DECISION.md的51轮决定覆盖。
5. 固件13746B仅四指令10字节常量位；源验证程序source/patch_original_firmware_r50.py记录构造和六例raw RV32验证，执行它会创建新研究输出，本次不再次执行。FW_PATCH反汇编/逻辑ROM读回/更新往返原报告在evidence/。

新包不包含完整SoC启动或新板测通过声明；交付后按POST_DELIVERY_TEST.md验证。
