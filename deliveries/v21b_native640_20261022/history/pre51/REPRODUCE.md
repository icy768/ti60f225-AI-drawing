# 原冻结网络复核方法
交付目录baseline/student.pt、qparams.npz/json与net_blob.bin均为既有v21b的原字节复制；没有以研究权重替换。baseline/original_generated内是同一既有审计包的原mem/cfg/top，非本轮重新生成/综合的结果。
source/保留本轮F0及原整数合同代码。运行依赖Python/PyTorch/NumPy/Pillow；当前已安装环境在D:/fpga/v21b_return_20261021，完整训练数据不复制进交付包。
从原工作区执行`python -X utf8 r44_preflight.py`可复核基线字节、CPU/CUDA整数前向小图与有限梯度；`python -X utf8 f0_fidelity.py`会写F0，不会训练或烧录。精确输入路径与SHA在evidence/F0_RESULT.json。
source/train_art_styles_r44.py仅研究来源，不是部署命令。没有本轮新CPU-RTL/综合/板测；原mem与top不应当作候选完成HG0的依据。部署如需操作，沿用硬件组RISCV11既有正式包及其验收流程。
模型参数编码计算15960B，实际transport blob48616B；运输脚本4050条写入与原cfg逐字相同，CRC373deed7匹配历史启动记录，但未做新Flash回读/SHA绑定。
