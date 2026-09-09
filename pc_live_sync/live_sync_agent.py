"""METOT PC <-> Live Sync agent v11.4.83.
Yerel JSON/SQLite verisini merkezi METOT API ile senkronize eder.
Bu dosya bagimsiz calisabilir; daha sonra desktop_app.py icinden otomatik baslatilabilir.
"""
from pathlib import Path
import os, json, sqlite3, hashlib, time, urllib.request, urllib.error

BASE_URL=os.environ.get('METOT_SYNC_URL','').rstrip('/')
USERNAME=os.environ.get('METOT_SYNC_USER','')
PASSWORD=os.environ.get('METOT_SYNC_PASSWORD','')
INTERVAL=max(2,int(os.environ.get('METOT_SYNC_INTERVAL','5') or 5))
LOCALAPP=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))
CA_DIR=LOCALAPP/'CA_Takip'
SCRUM_DIR=LOCALAPP/'METOT_Scrum'
DB_PATH=SCRUM_DIR/'scrum.db'
STATE_PATH=SCRUM_DIR/'live_sync_state.json'

JSON_DOCS={
 'ca/cas':CA_DIR/'cas.json',
 'ca/projects':CA_DIR/'projects.json',
 'ca/pwis':CA_DIR/'pwis.json',
 'ca/tracking':CA_DIR/'tracking.json',
 'ca/workflows':CA_DIR/'ca_workflows.json',
 'ca/control_plans':CA_DIR/'ca_control_plans.json',
 'ca/project_state':CA_DIR/'ca_project_state.json',
 'ca/project_groups':CA_DIR/'project_groups.json',
 'ca/notifications':CA_DIR/'system_notifications.json',
 'shell/kpi_duruslari':SCRUM_DIR/'kpi_duruslari.json',
 'shell/ai_agents':SCRUM_DIR/'ai_agents.json',
 'shell/ai_task_queue':SCRUM_DIR/'ai_task_queue.json',
}
SQL_TABLES=['team','users','sprints','tasks','daily_updates','task_history','workforce_snapshots']

def canon(x): return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def checksum(x): return hashlib.sha256(canon(x).encode('utf-8')).hexdigest()
def load_state():
    try:return json.loads(STATE_PATH.read_text(encoding='utf-8'))
    except:return {'token':'','docs':{},'last_event_id':0}
def save_state(s):
    STATE_PATH.parent.mkdir(parents=True,exist_ok=True)
    STATE_PATH.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
def req(path,method='GET',body=None,token=''):
    data=None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
    h={'Content-Type':'application/json'}
    if token:h['Authorization']='Bearer '+token
    r=urllib.request.Request(BASE_URL+path,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(r,timeout=20) as f:return f.status,json.loads(f.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        try:j=json.loads(e.read().decode('utf-8'))
        except:j={'error':str(e)}
        return e.code,j

def login(state):
    if state.get('token'):
        st,_=req('/api/auth/me',token=state['token'])
        if st==200:return
    st,j=req('/api/auth/login','POST',{'username':USERNAME,'password':PASSWORD})
    if st!=200: raise RuntimeError(j.get('error') or 'Giris yapilamadi')
    state['token']=j['token']; save_state(state)

def read_json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except:return None

def atomic_write(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.sync.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(path)

def db_export():
    if not DB_PATH.exists(): return {}
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row; out={}
    try:
        for t in SQL_TABLES:
            try:out[t]=[dict(x) for x in con.execute(f'SELECT * FROM {t} ORDER BY id').fetchall()]
            except sqlite3.Error:out[t]=[]
    finally:con.close()
    return out

def db_import(payload):
    if not DB_PATH.exists() or not isinstance(payload,dict):return
    con=sqlite3.connect(DB_PATH)
    try:
        con.execute('PRAGMA foreign_keys=OFF')
        for t,rows in payload.items():
            if t not in SQL_TABLES or not isinstance(rows,list):continue
            if not rows:continue
            cols=list(rows[0].keys())
            if not cols:continue
            con.execute(f'DELETE FROM {t}')
            sql=f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
            for row in rows:
                con.execute(sql,[row.get(c) for c in cols])
        con.commit()
    finally:con.close()

def sync_doc(state,key,local_payload,apply_remote):
    meta=state.setdefault('docs',{}).setdefault(key,{})
    local_sum=checksum(local_payload)
    st,remote=req('/api/docs/'+key,token=state['token'])
    if st==404:
        st,j=req('/api/docs/'+key,'PUT',{'payload':local_payload},state['token'])
        if st==200:meta.update({'version':j['version'],'checksum':j['checksum'],'local_checksum':local_sum})
        return
    if st!=200:return
    remote_sum=remote['checksum']; remote_ver=remote['version']
    last_local=meta.get('local_checksum')
    last_remote=meta.get('checksum')
    local_changed=last_local is not None and local_sum!=last_local
    remote_changed=last_remote is not None and remote_sum!=last_remote
    if last_local is None and last_remote is None:
        # Ilk eslesmede PC ana kaynak olarak merkezi servise aktarilir.
        st,j=req('/api/docs/'+key,'PUT',{'payload':local_payload,'expected_version':remote_ver},state['token'])
        if st==200:meta.update({'version':j['version'],'checksum':j['checksum'],'local_checksum':local_sum})
        return
    if remote_changed and not local_changed:
        apply_remote(remote['payload']); local_payload=remote['payload']; local_sum=checksum(local_payload)
    elif local_changed:
        st,j=req('/api/docs/'+key,'PUT',{'payload':local_payload,'expected_version':remote_ver},state['token'])
        if st==200:
            remote_sum=j['checksum']; remote_ver=j['version']
        elif st==409:
            # Es zamanli degisiklikte merkezi sürümü once uygula; veri kaybi olmasin.
            st2,r2=req('/api/docs/'+key,token=state['token'])
            if st2==200:
                apply_remote(r2['payload']); local_sum=checksum(r2['payload']); remote_sum=r2['checksum']; remote_ver=r2['version']
    meta.update({'version':remote_ver,'checksum':remote_sum,'local_checksum':local_sum})

def import_auth_users(state):
    if not DB_PATH.exists(): return
    con=sqlite3.connect(DB_PATH); con.row_factory=sqlite3.Row
    try:
        rows=[dict(x) for x in con.execute('''
          SELECT u.username,u.password_hash,u.role,u.team_id,u.active,tm.name team_name
          FROM users u LEFT JOIN team tm ON tm.id=u.team_id ORDER BY u.id
        ''').fetchall()]
    except sqlite3.Error:
        rows=[]
    finally:
        con.close()
    if rows:
        req('/api/admin/users/import','POST',{'users':rows},state['token'])

def sync_once(state):
    login(state)
    import_auth_users(state)
    for key,path in JSON_DOCS.items():
        payload=read_json(path)
        if payload is None:continue
        sync_doc(state,key,payload,lambda x,p=path: atomic_write(p,x))
    payload=db_export()
    if payload: sync_doc(state,'scrum/database',payload,db_import)
    save_state(state)

def main():
    if not BASE_URL or not USERNAME or not PASSWORD:
        raise SystemExit('METOT_SYNC_URL, METOT_SYNC_USER ve METOT_SYNC_PASSWORD tanimlanmali.')
    state=load_state()
    print('METOT Live Sync Agent aktif:',BASE_URL)
    while True:
        try:sync_once(state)
        except Exception as e:print('SYNC HATA:',e)
        time.sleep(INTERVAL)
if __name__=='__main__':main()
