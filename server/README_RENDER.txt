METOT LIVE SYNC SERVER v11.4.83

Render Web Service ayarlari:
Language: Python 3
Branch: main
Root Directory: server
Build Command: pip install -r requirements.txt
Start Command: gunicorn -w 2 -b 0.0.0.0:$PORT app:app

Gerekli Environment Variables:
DATABASE_URL = Render Postgres/harici Postgres connection string
METOT_SYNC_SECRET = uzun ve rastgele bir gizli anahtar
METOT_ADMIN_USER = mevcut METOT admin kullanici adi
METOT_ADMIN_PASSWORD = ilk merkezi admin sifresi

Not: Kalici senkronizasyon icin SQLite degil Postgres kullanin.
