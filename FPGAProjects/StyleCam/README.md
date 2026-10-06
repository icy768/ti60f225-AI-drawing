# StyleCam v21b 三风格网络

本目录是当前网络工程。三风格：van_gogh、ukiyo_e、ink_landscape；640×480 输入输出；固定 C24/Fc16、13 层图。

部署文件必须配套使用：`rtl/gen/v21b_ukiyoe_qat900_640x480/`、`sw/net_blob.h`、`sw/in_params.h`。综合入口为 `syn/vision_map.xml`。

固件仅保留 SC431HAI。已移除旧传感器驱动、专用 ISP 与 RAW2 前端。`sw/board_profile.h` 默认未确认，主程序会停止等待板级配置确认。

独立摄像头例程位于仓库根的 `sc431hai_hdmi`，其 1920×1080 模式与这里 1920×1440 RAW3 默认尚未完成视频接口统一；这两个工程没有被标成已完成整机集成。

来源是 develop 的 801488c / PR #2。算法、权重和量化合同来自 v21b；模型检查点、导出 RTL/mem、blob、固件头保持同一版本。

`audits` 保存交付时的历史证据；没有将历史记录标成清理后的板测结果。当前源码清单为 `sha256_manifest.json`，本轮 PC 复验记录单独保存。本轮不做上板验证。

接入说明：`docs/v21_hardware_handoff_20261005.md`。原始完整证据可按 GitHub PR #2 的提交和 Release 查询；不需要下载仓库 ZIP 才能协作。
