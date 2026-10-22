# 原生640交付上传记录

用户于2026-10-22明确授权上传Git仓库。旁边v21b_native640_20261022/是冻结包的逐字节复制件，原目录和ZIP均未修改。包内“未上传”表示封包时状态；本文件记录后续上传，不回写冻结证据。

交付网络D1B60_B_FWP1；原RISCV11整套回退。新版未经板测/完整SoC启动，艺术目标仍有缺口；720p30 NO_GO。主分支和PR5不修改、不合并，不烧录。

完整ZIP为515265842B，SHA256 `03e091b7f39fa0cb7f055b16f06f6774b5f7425b73dbd24bbd8d2a06712743f4`。ZIP超过普通Git单文件限制，放在仓库Draft Release附件。SHA旁车在本目录；Release地址在上传完成后由本聊天提供。

只读验证：进入../v21b_native640_20261022/，运行`python -B -X utf8 source/verify_final_package.py .`。包内原MANIFEST覆盖1720文件，自身由ZIP SHA绑定。1721个文件均按冻结字节上传。
