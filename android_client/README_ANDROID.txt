METOT MOBILE STANDALONE — v11.4.82 FINAL

BU SÜRÜMDE IT İŞLEMİ GEREKMEZ
-----------------------------
- Bilgisayar IP adresi girilmez.
- 51929 portu kullanılmaz.
- Windows firewall kuralı gerekmez.
- Telefonun bilgisayarla aynı Wi-Fi'da olması gerekmez.
- Uygulama kendi içindeki mobil arayüzü açar.
- Veriler telefonda yerel olarak saklanır.
- JSON yedek alma / geri yükleme bulunur.

APK OLUŞTURMA
-------------
1. Android Studio'yu açın.
2. Bu paketteki android_client klasörünü seçin.
3. Gradle Sync tamamlanınca:
   Build > Build Bundle(s) / APK(s) > Build APK(s)
4. APK:
   app\build\outputs\apk\debug\app-debug.apk
   konumunda oluşur.
5. APK'yı telefona gönderip kurun.

ÖNEMLİ
------
Bu standalone sürüm, bilgisayardaki ana METOT veritabanına otomatik bağlanmaz.
IT gerektirmeyen bağımsız kullanım için tasarlanmıştır.
Ana sistemle ortak canlı veri istendiğinde güvenli senkronizasyon servisi gerekir.
