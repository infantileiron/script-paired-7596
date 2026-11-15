import math,json,hashlib
import numpy as np
from scipy import stats
SEED=1115
ITERATIONS=10000
BATCH_SIZE=1000
def _rows_kept(rows):
 kept=[r for r in rows if r['before'] is not None and r['after'] is not None]
 excluded=[{'code':r['code'],'reason':'缺少前测' if r['before'] is None else '缺少后测'} for r in rows if r not in kept]
 return kept,excluded
def prepare(rows,iterations=ITERATIONS,batch_size=BATCH_SIZE):
 """冻结输入并完成与抽样无关的统计量；返回 JSON 安全的 base、差值向量 d 与方法。"""
 kept,excluded=_rows_kept(rows)
 if len(kept)<3:raise ValueError('至少需要3个完整顾问配对；缺失记录不会被补零')
 d=np.array([r['after']-r['before'] for r in kept],dtype=float)
 n=len(d);mean=float(d.mean());sd=float(d.std(ddof=1))
 if sd==0:raise ValueError('所有配对差值相同，t检验标准误为零；请核对样本，勿以无效显著性采纳')
 se=sd/math.sqrt(n);t=mean/se;p=float(stats.t.sf(abs(t),n-1)*2);margin=float(stats.t.ppf(.975,n-1))*se
 base=dict(n=n,excluded=excluded,total=len(rows),before_mean=float(np.mean([r['before'] for r in kept])),after_mean=float(np.mean([r['after'] for r in kept])),difference=mean,sd=sd,t=t,df=n-1,p_value=p,ci=[mean-margin,mean+margin],cohen_dz=mean/sd,pairs=kept,checksum=hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),warning='配对t检验假设顾问之间独立、差值近似正态；符号翻转假设零假设下差值符号可交换。前后评估同时受到客户结构与季节影响，不能直接解释为话术因果效应。')
 if n<=16:
  signs=1-2*((np.arange(2**n)[:,None]>>np.arange(n))&1)
  perm=signs@d/n;permutation_p=float(np.mean(np.abs(perm)>=abs(mean)-1e-12))
  base.update(permutation_p=permutation_p,permutation_method='exact',iterations=2**n,seed=SEED,completed=2**n)
  return base,d,'exact'
 base.update(permutation_method='monte-carlo-add-one',seed=SEED)
 return base,d,'monte-carlo'
def initial_progress(iterations,batch_size):
 rng=np.random.default_rng(SEED)
 return {'rng_state':rng.bit_generator.state,'completed':0,'extreme':0,'iterations':int(iterations),'batch_size':int(batch_size)}
def advance(base,d,progress):
 """推进一个批次；纯函数式返回新进度，已完成的抽样不会被重复计入。"""
 rng=np.random.default_rng();rng.bit_generator.state=progress['rng_state']
 remaining=progress['iterations']-progress['completed']
 size=min(progress['batch_size'],remaining)
 perm=(rng.choice([-1,1],size=(size,len(d)))*d).mean(axis=1)
 return {**progress,'rng_state':rng.bit_generator.state,'extreme':progress['extreme']+int(np.count_nonzero(np.abs(perm)>=abs(base['difference'])-1e-12)),'completed':progress['completed']+size}
def finalize(base,progress):
 if progress['completed']!=progress['iterations']:raise ValueError('抽样未完成，不能冻结结果')
 permutation_p=(progress['extreme']+1)/(progress['iterations']+1)
 return {**base,'permutation_p':permutation_p,'iterations':progress['iterations'],'batch_size':progress['batch_size'],'completed':progress['iterations']}
def evaluate(rows,iterations=ITERATIONS,batch_size=BATCH_SIZE):
 """保留旧入口：一次性跑完并返回完整冻结结果。"""
 base,d,method=prepare(rows,iterations,batch_size)
 if method=='exact':return {**base,'snapshot':rows}
 progress=initial_progress(iterations,batch_size)
 while progress['completed']<progress['iterations']:progress=advance(base,d,progress)
 return {**finalize(base,progress),'snapshot':rows}
