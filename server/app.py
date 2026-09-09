from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime, timezone
import os, json, hashlib, base64, queue, threading, time, uuid, re

app = Flask(__name__)
DATABASE_URL = os.environ.get('DATABASE_URL','').strip()
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = 'postgresql+psycopg://' + DATABASE_URL[len('postgres://'):]
elif DATABASE_URL.startswith('postgresql://') and '+psycopg' not in DATABASE_URL:
    DATABASE_URL = 'postgresql+psycopg://' + DATABASE_URL[len('postgresql://'):]
if not DATABASE_URL:
    DATABASE_URL = 'sqlite:///metot_live_sync.db'

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
Base = declarative_base()
SECRET = os.environ.get('METOT_SYNC_SECRET','change-me-before-production')
serializer = URLSafeTimedSerializer(SECRET, salt='metot-live-sync')

BRIDGE_SECRET = os.environ.get("METOT_BRIDGE_SECRET","").strip()
BRIDGE_QUEUE = queue.Queue()
BRIDGE_WAITERS = {}
BRIDGE_LOCK = threading.Lock()
BRIDGE_LAST_SEEN = 0.0

def bridge_auth_ok():
    supplied=request.headers.get("X-METOT-Bridge-Secret","")
    return bool(BRIDGE_SECRET) and supplied == BRIDGE_SECRET

def _bridge_rewrite_text(text, service):
    prefix=f"/bridge/pc/{service}"
    # Root-relative assets and API requests stay on the same proxied local service.
    replacements=[
        ('href="/static/', f'href="{prefix}/static/'),
        ("href='/static/", f"href='{prefix}/static/"),
        ('src="/static/', f'src="{prefix}/static/'),
        ("src='/static/", f"src='{prefix}/static/"),
        ('url("/static/', f'url("{prefix}/static/'),
        ("url('/static/", f"url('{prefix}/static/"),
        ("fetch('/api/", f"fetch('{prefix}/api/"),
        ('fetch("/api/', f'fetch("{prefix}/api/'),
        ("api('/api/", f"api('{prefix}/api/"),
        ('api("/api/', f'api("{prefix}/api/'),
        ('action="/', f'action="{prefix}/'),
    ]
    for a,b in replacements:
        text=text.replace(a,b)
    if service=="shell":
        for path in ["approvals","manager-ai","ai-office","simulation-center","mobile","manifest.webmanifest","service-worker.js"]:
            text=text.replace(f"'{('/'+path)}'", f"'{prefix}/{path}'")
            text=text.replace(f'"{("/"+path)}"', f'"{prefix}/{path}"')
    return text

def _bridge_proxy(service, path=""):
    if service not in {"shell","tool","ca","scrum"}:
        return jsonify({"error":"Bilinmeyen servis"}),404
    # If the PC agent is not connected, fail quickly instead of leaving the phone hanging.
    if time.time()-BRIDGE_LAST_SEEN > 45:
        return ("METOT PC bağlantısı aktif değil. PC'de METOT v11.4.84 açık olmalıdır.",503,{"Content-Type":"text/plain; charset=utf-8"})
    jid=uuid.uuid4().hex
    body=request.get_data(cache=True) or b""
    headers={}
    for k,v in request.headers.items():
        if k.lower() in {"content-type","accept","accept-language","cookie","referer","user-agent","origin","x-requested-with"}:
            headers[k]=v
    job={"id":jid,"service":service,"path":"/"+path if path else "/","query":request.query_string.decode("utf-8"),
         "method":request.method,"headers":headers,"body_b64":base64.b64encode(body).decode("ascii")}
    ev=threading.Event()
    with BRIDGE_LOCK:
        BRIDGE_WAITERS[jid]={"event":ev,"response":None}
    BRIDGE_QUEUE.put(job)
    if not ev.wait(75):
        with BRIDGE_LOCK: BRIDGE_WAITERS.pop(jid,None)
        return ("METOT PC yanıt vermedi.",504,{"Content-Type":"text/plain; charset=utf-8"})
    with BRIDGE_LOCK:
        item=BRIDGE_WAITERS.pop(jid,None)
    if not item or not item.get("response"):
        return ("METOT bridge yanıtı alınamadı.",502,{"Content-Type":"text/plain; charset=utf-8"})
    r=item["response"]
    data=base64.b64decode(r.get("body_b64") or "")
    status=int(r.get("status") or 200)
    rh=dict(r.get("headers") or {})
    ctype=str(rh.get("Content-Type") or rh.get("content-type") or "")
    # Rewrite proxied HTML/CSS/JS so absolute URLs stay inside the reverse bridge.
    if any(x in ctype.lower() for x in ["text/html","text/css","javascript"]):
        try:
            txt=data.decode("utf-8")
            txt=_bridge_rewrite_text(txt,service)
            data=txt.encode("utf-8")
        except Exception:
            pass
    out_headers={}
    for k,v in rh.items():
        if k.lower() in {"content-type","set-cookie","cache-control","content-disposition","location","etag","last-modified"}:
            if k.lower()=="location" and isinstance(v,str) and v.startswith("/"):
                v=f"/bridge/pc/{service}"+v
            out_headers[k]=v
    return (data,status,out_headers)


class User(Base):
    __tablename__='users'
    id=Column(Integer, primary_key=True)
    username=Column(String(120), unique=True, nullable=False)
    password_hash=Column(String(512), nullable=False)
    role=Column(String(32), nullable=False, default='personnel')
    team_id=Column(Integer, nullable=True)
    team_name=Column(String(160), nullable=True)
    active=Column(Boolean, default=True, nullable=False)
    created_at=Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class SharedDoc(Base):
    __tablename__='shared_docs'
    id=Column(Integer, primary_key=True)
    key=Column(String(240), unique=True, nullable=False)
    payload=Column(Text, nullable=False, default='null')
    version=Column(Integer, nullable=False, default=1)
    checksum=Column(String(64), nullable=False, default='')
    updated_by=Column(String(120), nullable=True)
    updated_at=Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class ChangeEvent(Base):
    __tablename__='change_events'
    id=Column(Integer, primary_key=True)
    doc_key=Column(String(240), nullable=False)
    version=Column(Integer, nullable=False)
    checksum=Column(String(64), nullable=False)
    actor=Column(String(120), nullable=True)
    created_at=Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

Base.metadata.create_all(engine)

def now_iso(dt=None):
    dt = dt or datetime.now(timezone.utc)
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

def sha(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',',':')).encode('utf-8')).hexdigest()

def seed_admin():
    user=os.environ.get('METOT_ADMIN_USER','').strip()
    pwd=os.environ.get('METOT_ADMIN_PASSWORD','')
    if not user or not pwd: return
    with SessionLocal() as db:
        row=db.query(User).filter(User.username.ilike(user)).first()
        if not row:
            db.add(User(username=user,password_hash=generate_password_hash(pwd),role='admin',active=True))
            db.commit()
seed_admin()

def token_user(required=True):
    auth=request.headers.get('Authorization','')
    if not auth.startswith('Bearer '):
        return (None, (jsonify({'error':'Yetkilendirme gerekli.'}),401)) if required else (None,None)
    token=auth[7:].strip()
    try:
        data=serializer.loads(token,max_age=60*60*24*30)
    except (BadSignature,SignatureExpired):
        return None,(jsonify({'error':'Oturum süresi doldu veya token geçersiz.'}),401)
    uid=data.get('user_id')
    with SessionLocal() as db:
        u=db.get(User,uid)
        if not u or not u.active:
            return None,(jsonify({'error':'Kullanıcı aktif değil.'}),401)
        return {'id':u.id,'username':u.username,'role':u.role,'team_id':u.team_id,'team_name':u.team_name,'active':u.active},None

def admin_only(u):
    return u and u.get('role')=='admin'

@app.get('/')
def root():
    return jsonify({'ok':True,'service':'METOT Live Sync Server','version':'11.4.84','utc':now_iso()})

@app.get('/health')
def health():
    try:
        with SessionLocal() as db:
            db.query(User).limit(1).all()
        return jsonify({'ok':True,'database':'ok','version':'11.4.84'})
    except Exception as e:
        return jsonify({'ok':False,'database':'error','error':str(e)}),500

@app.post('/api/auth/login')
def login():
    d=request.get_json(silent=True) or {}
    username=str(d.get('username') or '').strip()
    password=str(d.get('password') or '')
    with SessionLocal() as db:
        u=db.query(User).filter(User.username.ilike(username)).first()
        if not u or not u.active or not check_password_hash(u.password_hash,password):
            return jsonify({'error':'Kullanıcı adı veya şifre hatalı.'}),401
        token=serializer.dumps({'user_id':u.id})
        return jsonify({'ok':True,'token':token,'user':{'id':u.id,'username':u.username,'role':u.role,'team_id':u.team_id,'team_name':u.team_name,'active':u.active}})

@app.get('/api/auth/me')
def me():
    u,err=token_user()
    if err:return err
    return jsonify({'ok':True,'user':u})

@app.post('/api/admin/users/import')
def import_users():
    u,err=token_user()
    if err:return err
    if not admin_only(u): return jsonify({'error':'Admin yetkisi gerekli.'}),403
    d=request.get_json(silent=True) or {}
    rows=d.get('users') or []
    if not isinstance(rows,list): return jsonify({'error':'users liste olmalıdır.'}),400
    count=0
    with SessionLocal() as db:
        for x in rows:
            if not isinstance(x,dict): continue
            username=str(x.get('username') or '').strip()
            ph=str(x.get('password_hash') or '').strip()
            if not username or not ph: continue
            row=db.query(User).filter(User.username.ilike(username)).first()
            if not row:
                row=User(username=username,password_hash=ph)
                db.add(row)
            row.password_hash=ph
            row.role=str(x.get('role') or 'personnel')
            row.team_id=x.get('team_id')
            row.team_name=x.get('team_name')
            row.active=bool(x.get('active',True))
            count+=1
        db.commit()
    return jsonify({'ok':True,'imported':count})

@app.get('/api/docs')
def list_docs():
    u,err=token_user()
    if err:return err
    with SessionLocal() as db:
        rows=db.query(SharedDoc).order_by(SharedDoc.key).all()
        return jsonify({'ok':True,'docs':[{'key':x.key,'version':x.version,'checksum':x.checksum,'updated_by':x.updated_by,'updated_at':now_iso(x.updated_at)} for x in rows]})

@app.get('/api/docs/<path:key>')
def get_doc(key):
    u,err=token_user()
    if err:return err
    with SessionLocal() as db:
        x=db.query(SharedDoc).filter_by(key=key).first()
        if not x:return jsonify({'error':'Kayıt bulunamadı.','key':key}),404
        return jsonify({'ok':True,'key':x.key,'payload':json.loads(x.payload),'version':x.version,'checksum':x.checksum,'updated_by':x.updated_by,'updated_at':now_iso(x.updated_at)})

@app.put('/api/docs/<path:key>')
def put_doc(key):
    u,err=token_user()
    if err:return err
    d=request.get_json(silent=True) or {}
    payload=d.get('payload')
    expected=d.get('expected_version')
    checksum=sha(payload)
    with SessionLocal() as db:
        x=db.query(SharedDoc).filter_by(key=key).first()
        if x:
            if expected is not None and int(expected)!=int(x.version):
                return jsonify({'error':'Sürüm çakışması.','key':key,'server_version':x.version,'server_checksum':x.checksum}),409
            if x.checksum==checksum:
                return jsonify({'ok':True,'unchanged':True,'key':key,'version':x.version,'checksum':x.checksum,'updated_at':now_iso(x.updated_at)})
            x.version+=1
        else:
            x=SharedDoc(key=key,version=1)
            db.add(x)
        x.payload=json.dumps(payload,ensure_ascii=False)
        x.checksum=checksum
        x.updated_by=u['username']
        x.updated_at=datetime.now(timezone.utc)
        db.flush()
        db.add(ChangeEvent(doc_key=key,version=x.version,checksum=checksum,actor=u['username']))
        db.commit()
        return jsonify({'ok':True,'key':key,'version':x.version,'checksum':checksum,'updated_by':u['username'],'updated_at':now_iso(x.updated_at)})

@app.get('/api/events')
def events():
    u,err=token_user()
    if err:return err
    since=int(request.args.get('since','0') or 0)
    limit=min(max(int(request.args.get('limit','200') or 200),1),1000)
    with SessionLocal() as db:
        rows=db.query(ChangeEvent).filter(ChangeEvent.id>since).order_by(ChangeEvent.id).limit(limit).all()
        return jsonify({'ok':True,'events':[{'id':x.id,'key':x.doc_key,'version':x.version,'checksum':x.checksum,'actor':x.actor,'created_at':now_iso(x.created_at)} for x in rows],'last_id':rows[-1].id if rows else since})


@app.get("/bridge")
@app.get("/bridge/")
def bridge_home():
    return jsonify({
        "ok":True,
        "service":"METOT PC Remote Bridge",
        "version":"11.4.84",
        "pc_online": bool(time.time()-BRIDGE_LAST_SEEN <= 45)
    })

@app.route("/bridge/pc/<service>/", defaults={"path":""}, methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
@app.route("/bridge/pc/<service>/<path:path>", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
def bridge_pc(service,path):
    return _bridge_proxy(service,path)

@app.get("/bridge/agent/next")
def bridge_agent_next():
    global BRIDGE_LAST_SEEN
    if not bridge_auth_ok():
        return jsonify({"error":"Bridge yetkisi geçersiz."}),403
    BRIDGE_LAST_SEEN=time.time()
    try:
        job=BRIDGE_QUEUE.get(timeout=25)
    except queue.Empty:
        return ("",204)
    return jsonify(job)

@app.post("/bridge/agent/respond")
def bridge_agent_respond():
    global BRIDGE_LAST_SEEN
    if not bridge_auth_ok():
        return jsonify({"error":"Bridge yetkisi geçersiz."}),403
    BRIDGE_LAST_SEEN=time.time()
    d=request.get_json(silent=True) or {}
    jid=str(d.get("id") or "")
    with BRIDGE_LOCK:
        item=BRIDGE_WAITERS.get(jid)
        if not item:
            return jsonify({"ok":False,"ignored":True}),200
        item["response"]=d
        item["event"].set()
    return jsonify({"ok":True})

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))
