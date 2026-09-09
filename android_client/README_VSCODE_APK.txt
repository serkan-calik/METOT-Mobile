METOT MOBILE v11.4.84 FINAL — VS CODE APK BUILD

VS CODE İLE NASIL APK OLUŞTURULUR?
==================================

1) Visual Studio Code'u açın.
2) File > Open Folder ile bu "android_client" klasörünü açın.
3) Önce:
   Terminal > Run Task > "METOT: Ortam Kontrolü"
   seçeneğini çalıştırın.

4) Ortam hazır görünüyorsa:
   Ctrl + Shift + B
   tuşlarına basın.

   Bu, varsayılan görev olan:
   "METOT: APK Oluştur"
   işlemini çalıştırır.

5) Başarılı derleme sonunda android_client klasöründe:
   METOT-Mobile-v11.4.84.apk
   dosyası oluşur.

6) Bu APK'yı telefona gönderin ve kurun.

ÖNEMLİ
======
Visual Studio Code tek başına Android APK derleyemez.
Bilgisayarda bir kez şu bileşenler bulunmalıdır:
- JDK 17
- Android SDK (API 35)
- Gradle veya Gradle Wrapper

Bu sürüm Android Studio arayüzünü kullanmadan, VS Code içinden APK üretmek
için hazırlanmıştır. Android Studio'nun kendisi zorunlu değildir; fakat Android
SDK mutlaka gereklidir.

TELEFONDA ÇALIŞMA
=================
Bu sürüm standalone/offline'dır:
- IP adresi gerekmez.
- 51929 portu gerekmez.
- Windows firewall işlemi gerekmez.
- Aynı Wi-Fi şart değildir.
- IT'den port açma talebi gerekmez.
- Telefon uygulaması kendi yerel verisini kullanır.
