import os,time,json,logging,tempfile
from pathlib import Path
import redis
from sqlalchemy import update
from src.config.database import Session
from src.models.entities import Evaluation
from src.services import analysis
ARTIFACTS=Path(os.environ.get('ARTIFACTS_DIR','/artifacts'))
QUEUE='paired:evaluations'
def redis_client():return redis.Redis.from_url(os.environ['REDIS_URL'])
def publish_artifact(row_id,payload):
 """先写临时文件再原子改名：发布中断后重跑只会覆盖出同一份完整文件。"""
 ARTIFACTS.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=f'.{row_id}.',suffix='.tmp',dir=ARTIFACTS)
 try:
  with os.fdopen(fd,'w',encoding='utf-8') as f:
   json.dump(payload,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
  os.replace(tmp,ARTIFACTS/f'{row_id}.json')
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
def claim(s,row_id):
 """原子条件领取：重复投递或并发领取只有一份能把 queued 推进为 running。"""
 cur=s.get(Evaluation,row_id)
 if not cur or cur.state!='queued':return None
 res=s.execute(update(Evaluation).where(Evaluation.id==row_id,Evaluation.state=='queued').values(state='running').returning(Evaluation.id)).first()
 s.commit()
 return cur if res else None
def run_once(s,row):
 snapshot=row.result['snapshot']
 settings=row.result.get('settings',{})
 total=settings.get('iterations',analysis.ITERATIONS)
 batch=settings.get('batch_size',analysis.BATCH_SIZE)
 base,d,method=analysis.prepare(snapshot,total,batch)
 if method=='exact':
  payload={**base,'snapshot':snapshot};publish_artifact(row.id,payload)
  row.result=payload;row.state='done';row.error='';s.commit();return
 progress=row.result.get('progress')
 if not progress:
  progress=analysis.initial_progress(total,batch)
  row.result={**row.result,'progress':progress,'completed':0};s.commit()
 while progress['completed']<progress['iterations']:
  progress=analysis.advance(base,d,progress)
  row.result={**row.result,'progress':progress,'completed':progress['completed']}
  s.commit()
 payload={**analysis.finalize(base,progress),'snapshot':snapshot}
 publish_artifact(row.id,payload)
 row.result=payload;row.state='done';row.error='';s.commit()
def recover(client):
 """启动恢复：queued/running 全部重新入队，进度从已保存的 completed 续跑。"""
 with Session() as recovery:
  for pending in recovery.query(Evaluation).filter(Evaluation.state.in_(['queued','running'])).all():
   pending.state='queued';client.rpush(QUEUE,pending.id)
  recovery.commit()
def main():
 client=redis_client();recover(client)
 while True:
  Path('/tmp/heartbeat').touch()
  try:
   item=client.blpop(QUEUE,timeout=3)
   if not item:continue
   row_id=int(item[1])
   with Session() as s:
    row=claim(s,row_id)
    if not row:continue
    try:run_once(s,row)
    except ValueError as e:
     s.rollback();cur=s.get(Evaluation,row_id);cur.state='failed';cur.error=str(e);s.commit()
  except Exception:
   logging.exception('worker');time.sleep(2)
if __name__=='__main__':main()
