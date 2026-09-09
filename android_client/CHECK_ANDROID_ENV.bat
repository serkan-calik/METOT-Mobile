@echo off
setlocal EnableExtensions
title METOT Mobile - Android Ortam Kontrolu
chcp 65001 >nul
echo.
echo ============================================================
echo   METOT MOBILE v11.4.82 - VS CODE APK ORTAM KONTROLU
echo ============================================================
echo.

set "FAIL=0"

echo [1/4] Java kontrol ediliyor...
where java >nul 2>&1
if errorlevel 1 (
  echo [HATA] Java bulunamadi.
  echo JDK 17 gerekli.
  set "FAIL=1"
) else (
  java -version 2>&1 | findstr /i "version"
  echo [OK] Java bulundu.
)
echo.

echo [2/4] JAVA_HOME kontrol ediliyor...
if "%JAVA_HOME%"=="" (
  echo [UYARI] JAVA_HOME tanimli degil.
) else (
  echo [OK] JAVA_HOME=%JAVA_HOME%
)
echo.

echo [3/4] Android SDK kontrol ediliyor...
set "SDK=%ANDROID_SDK_ROOT%"
if "%SDK%"=="" set "SDK=%ANDROID_HOME%"
if "%SDK%"=="" if exist "%LOCALAPPDATA%\Android\Sdk" set "SDK=%LOCALAPPDATA%\Android\Sdk"

if "%SDK%"=="" (
  echo [HATA] Android SDK bulunamadi.
  echo Android SDK bir kez kurulmalidir.
  set "FAIL=1"
) else (
  echo [OK] Android SDK=%SDK%
)
echo.

echo [4/4] Gradle kontrol ediliyor...
if exist "%~dp0gradlew.bat" (
  echo [OK] Gradle Wrapper bulundu.
) else (
  where gradle >nul 2>&1
  if errorlevel 1 (
    echo [HATA] Gradle veya gradlew.bat bulunamadi.
    set "FAIL=1"
  ) else (
    echo [OK] Sistem Gradle bulundu.
  )
)
echo.

if "%FAIL%"=="0" (
  echo ============================================================
  echo   ORTAM HAZIR - APK DERLENEBILIR
  echo ============================================================
) else (
  echo ============================================================
  echo   EKSIK BILESEN VAR
  echo   VS Code tek basina APK derleyemez.
  echo   JDK 17 + Android SDK gereklidir.
  echo ============================================================
)
echo.
pause
endlocal
