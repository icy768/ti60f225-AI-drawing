"""Explicit deployable operation order; no Python model reconstruction required."""
def graph_spec(model):
    def build():
        ops=[]
        def emit(op,name,inputs,**kw):
            ops.append(dict(op=op,id=name,inputs=list(inputs),**kw));return name
        def conv(p,x):
            x=emit('conv',p+'.conv',[x],weight_key=p+'.conv')
            from torch import nn
            if isinstance(model.get_submodule(p).act,nn.ReLU6):x=emit('clamp',p+'.act',[x],lo=0,hi=6)
            return x
        def sep(p,x):return conv(p+'.pw',conv(p+'.dw',x))
        def add(p,a,b):return emit('add',p,[a,b],qparam_key=p)
        def direction(p,x):
            z=conv(p+'.expand',x)
            a=[conv(p+'.'+k,z) for k in ['horizontal','vertical','local']]
            z=emit('cat',p+'.cat',a,qparam_key=p+'.cat',axis=1)
            z=conv(p+'.mix',z);z=add(p+'.add',x,z)
            return emit('clamp',p+'.act',[z],lo=0,hi=6)
        return ops,emit,conv,sep,add,direction
    shared,emit,conv,sep,add,direction=build()
    x=emit('input','input',[],qparam_key='quant',format='RGB888_NCHW',float_divisor=255)
    s1=conv('stem',x);s2=sep('down2',s1);s4=sep('down4',s2);s8=sep('down8',s4)
    h=sep('down16',s8) if hasattr(model,'down16') else s8
    experts=[]
    for i,e in enumerate(model.experts):
        ops,emit,conv,sep,add,direction=build();p=f'experts.{i}';z=conv(p+'.spatial',h)
        for j in range(len(e.blocks)):z=direction(p+f'.blocks.{j}',z)
        if hasattr(e,'decode8'):
            z=emit('nearest2',p+'.up8',[z]);z=add(p+'.add8',sep(p+'.decode8',z),conv(p+'.skip8',s8));z=direction(p+'.refine8',z)
        for scale,skip in [(4,s4),(2,s2),(1,s1)]:
            z=emit('nearest2',p+f'.up{scale}',[z]);z=sep(p+f'.decode{scale}',z)
            sp=model.get_submodule(p+f'.skip{scale}')
            sk=sep(p+f'.skip{scale}',skip) if hasattr(sp,'dw') else conv(p+f'.skip{scale}',skip)
            z=add(p+f'.add{scale}',z,sk)
            if scale==4:z=direction(p+'.refine4',z)
            if scale==2:z=sep(p+'.refine2',z)
        z=conv(p+'.out',z);z=emit('clamp',p+'.clip',[z],lo=0,hi=1)
        emit('output',p+'.rgb',[z],format='RGB888_NCHW')
        experts.append(ops)
    return {'shared':shared,'experts':experts,'input_multiple':16 if hasattr(model,'down16') else 8,'layout':'NCHW','conv_padding':'constant input_zero_point','rounding':'nearest ties to even; saturate after rounding','style_admission':'one expert per frame, latched style 0..2'}
