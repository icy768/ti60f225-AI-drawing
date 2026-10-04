# StyleCam v6 硬件交付

本目录保存 2026-10-04 交付快照，与本地原始 ZIP 的内容逐文件一致。它是待集成的网络与视觉子系统，不是已经板测通过的完整 StyleCam FPGA 工程。

- [总交付说明](FPGAProjects_StyleCam_v6_20261004/交付说明.md)
- [PC 验证报告](FPGAProjects_StyleCam_v6_20261004/StyleCam/docs/PC验证报告.md)
- [板级集成与烧录步骤](FPGAProjects_StyleCam_v6_20261004/StyleCam/docs/板级集成与烧录步骤.md)
- [硬件组实测与回填](FPGAProjects_StyleCam_v6_20261004/StyleCam/docs/硬件组实测与回填.md)
- [机器可读部署状态](FPGAProjects_StyleCam_v6_20261004/deployment_status.json)
- [原始 ZIP 与校验文件下载](https://github.com/icy768/ti60f225-imx219-camera/releases/tag/stylecam-v6-handoff-20261004)

解压或克隆后的完整性检查：

```powershell
python -X utf8 deliveries/FPGAProjects_StyleCam_v6_20261004/StyleCam/tools/check_manifest.py
```

原始 ZIP 为 112,937,904 字节，SHA256：

```text
812b288d32565d0cada31185834614644c0397c02a97edfc0482a2b334b9ec13
```

ZIP 超过 GitHub 普通 Git 单文件限制，因此保存在 Release 附件中。仓库保存解压后的快照，便于审阅源码与验证报告。保留的厂商镜像只用于原厂摄像头演示，不含本版网络；`net_blob.bin` 也不是 FPGA 配置文件。

本目录 `.gitattributes` 禁止对封存快照做自动换行转换，以保持 `sha256_manifest.json` 校验有效。后续集成修改应在自己的工作目录/分支中进行，并重新记录模型、固件与 bitstream 的配套版本。
