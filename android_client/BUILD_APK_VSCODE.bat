@echo off
setlocal EnableExtensions
title METOT Mobile - VS Code APK Build
chcp 65001 >nul

cd /d "%~dp0"

echo.
echo ============================================================
echo   METOT MOBILE v11.4.84 FINAL - VS CODE APK BUILD
echo ============================================================
echo.

set "SDK=%ANDROID_SDK_ROOT%"
if "%SDK%"=="" set "SDK=%ANDROID_HOME%"
if "%SDK%"=="" if exist "%LOCALAPPDATA%\Android\Sdk" set "SDK=%LOCALAPPDATA%\Android\Sdk"

where java >nul 2>&1
if errorlevel 1 (
  echo [HATA] Java/JDK bulunamadi. JDK 17 gereklidir.
  goto :FAIL
)

if "%SDK%"=="" (
  echo [HATA] Android SDK bulunamadi.
  echo Android SDK bir kez kurulmalidir.
  goto :FAIL
)

set "ANDROID_SDK_ROOT=%SDK%"
set "ANDROID_HOME=%SDK%"

echo [OK] Android SDK: %SDK%
echo [OK] Java bulundu.
echo.

if exist "gradlew.bat" (
  echo Gradle Wrapper ile APK derleniyor...
  call gradlew.bat --no-daemon assembleDebug
) else (
  where gradle >nul 2>&1
  if errorlevel 1 (
    echo [HATA] Gradle bulunamadi.
    echo gradlew.bat yok ve sistem Gradle kurulu degil.
    goto :FAIL
  )
  echo Sistem Gradle ile APK derleniyor...
  call gradle --no-daemon assembleDebug
)

if errorlevel 1 goto :FAIL

set "APK=%~dp0app\build\outputs\apk\debug\app-debug.apk"
if not exist "%APK%" (
  echo [HATA] Derleme bitti fakat APK bulunamadi.
  goto :FAIL
)

copy /Y "%APK%" "%~dp0METOT-Mobile-v11.4.84.apk" >nul

echo.
echo ============================================================
echo   APK BASARIYLA OLUSTURULDU
echo ============================================================
echo.
echo Hazir dosya:
echo %~dp0METOT-Mobile-v11.4.84.apk
echo.
explorer /select,"%~dp0METOT-Mobile-v11.4.84.apk"
pause
exit /b 0

:FAIL
echo.
echo ============================================================
echo   APK OLUSTURULAMADI
echo ============================================================
echo Eksik bilesenleri gormek icin CHECK_ANDROID_ENV.bat dosyasini calistirin.
echo.
pause
exit /b 1
