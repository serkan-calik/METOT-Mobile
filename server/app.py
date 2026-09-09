from flask import Flask, request, jsonify
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime, timezone
import os, json, hashlib

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
    return jsonify({'ok':True,'service':'METOT Live Sync Server','version':'11.4.83','utc':now_iso()})

@app.get('/health')
def health():
    try:
        with SessionLocal() as db:
            db.query(User).limit(1).all()
        return jsonify({'ok':True,'database':'ok','version':'11.4.83'})
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

if __name__=='__main__':
    app.run(host='0.0.0.0',port=int(os.environ.get('PORT','10000')))
