"""Frozen-contract integer STE for both R44 training and evaluation."""
from pathlib import Path
import numpy as np
import torch
import golden,hardware_qat
from tinystyle import TinyStyleNet as BaseTinyStyleNet,QCfg

CONTRACT=golden.load(str(Path(__file__).resolve().parents[1]/'audits/v21b_deploy_blob/qparams'))

class TinyStyleNet(BaseTinyStyleNet):
    def forward(self,x,style):
        if QCfg.observe or not QCfg.enabled:
            raise ValueError('R44 requires QAT enabled and observers frozen')
        for layer,ref in zip(self.layers,CONTRACT['layers']):
            if not np.isclose(float(layer.aq.scale()),ref['s_y'],rtol=1e-6,atol=1e-10):
                raise ValueError('activation scale mismatch: '+ref['name'])
        return hardware_qat.forward(self,x,style,CONTRACT)
