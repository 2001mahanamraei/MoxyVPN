# آموزش ساخت MoxyVPN از روی سورس

همه‌چیز روی **لینوکس** کامپایل میشه و لازم نیست ویژوال استودیو یا چیز سنگینی نصب کنی.
روی ویندوز از **WSL** استفاده کن (یک بار در PowerShell با دسترسی ادمین بزن `wsl --install` و کامپیوتر رو ریستارت کن؛ بعد برنامه‌ی «Ubuntu» رو از Start باز کن).

## قدم ۰: آپلود پروژه روی گیت‌هاب
1. در github.com یک ریپوی جدید بساز (مثلاً `MoxyVPN`). حالت **Public**.
2. پوشه‌ی پروژه رو باز کن و در ترمینال بزن:
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/MoxyVPN.git
git push -u origin main
```
(به جای `USERNAME` اسم کاربری خودت رو بنویس. اگر گیت نداری، در صفحه‌ی ریپو روی **Add file → Upload files** بزن و پوشه‌ها رو بکش بنداز.)
3. فایل `LICENSE` رو باز کن و `MoxyVPN contributors` رو با اسم خودت عوض کن.

## روش ۱ (ساده‌ترین): ساخت خودکار با GitHub Actions
نیازی به نصب هیچ‌چیز نیست.
1. بعد از آپلود، در ریپو به تب **Actions** برو.
2. **Build Windows installer** ← **Run workflow** رو بزن (حدود ۳ تا ۵ دقیقه).
3. وقتی تموم شد، روی اجرا کلیک کن و پایین صفحه در **Artifacts** فایل `MoxyVPN-Setup` رو دانلود کن (zip که داخلش `MoxyVPN-Setup.exe` هست).
4. برای انتشار رسمی (Release):
```bash
git tag v1.3.0
git push origin v1.3.0
```
با این کار نصب‌کننده خودکار به صفحه‌ی Releases اضافه میشه.

## روش ۲: ساخت روی کامپیوتر خودت (با WSL)
```bash
sudo apt update
sudo apt install -y mingw-w64 nsis unzip curl python3-pip git
git clone https://github.com/USERNAME/MoxyVPN.git
cd MoxyVPN
bash tools/build_windows.sh
```
خروجی: `dist/MoxyVPN-Setup.exe` (حدود ۳۱ مگابایت). برای برداشتن فایل از ویندوز، در File Explorer آدرس `\\wsl$\Ubuntu\home\<نام‌کاربری>\MoxyVPN\dist` رو باز کن.

اسکریپت این کارها رو انجام میده: دانلود موتور تونل (mihomo)، `wintun.dll`، پایتون قابل‌حمل و پکیج‌ها ← چیدن همه در `build/stage/` ← کامپایل `MoxyVPN.exe` (آیکون روباه + درخواست ادمین) ← ساخت نصب‌کننده با NSIS.
دفعه‌ی دوم چون دانلودها در `build/cache` ذخیره شده‌اند خیلی سریع‌تره.

## روش ۳: اجرا مستقیم از سورس (برای توسعه، روی خود ویندوز)
1. پایتون ۳.۱۲ رو نصب کن (از python.org، تیک Add to PATH).
2. در پوشه‌ی پروژه:
```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 app\moxyvpn_gui.py
```
3. برای تونل کل سیستم، فایل‌های `mihomo.exe` و `wintun.dll` رو در پوشه‌ی `tun\` بذار (از صفحه‌ی Releases پروژه‌ی mihomo و از zip برنامه‌ی hev-socks5-tunnel) و PowerShell رو با دسترسی ادمین باز کن. بدون این‌ها فقط حالت Proxy-only کار میکنه.

## ساخت APK اندروید
```bash
sudo apt install -y apktool zipalign apksigner default-jre-headless
pip install pillow
python3 android/rebrand_apk.py
```
خروجی: `dist/MoxyVPN.apk`. بار اول یک کلید امضا در `android/moxyvpn.keystore` ساخته میشه.
**این فایل و `keystore-password.txt` رو هرگز روی گیت‌هاب نذار** (در `.gitignore` هست) و یک کپی امن ازش نگه دار. بدون همین کلید نمیتونی آپدیت بدی.
این اسکریپت APK رسمی و متن‌باز FoxyVPN رو دانلود و اسمش رو به MoxyVPN و آیکونش رو روباه عوض میکنه.

## افزونه‌ی کروم
ساخت لازم نیست: `chrome://extensions` ← **Developer mode** ← **Load unpacked** ← پوشه‌ی `extension`.
برای گذاشتن در Chrome Web Store محتویات پوشه‌ی `extension` رو zip کن.

## تغییر دادن چیزها
| میخوام... | کجا |
|---|---|
| نسخه رو عوض کنم | `VERSION` در `app/moxyvpn_gui.py` |
| اسم یا رنگ‌ها | `APP_NAME` و `app/theme.py` و `installer/installer.nsi` |
| آیکون | `tools/make_icon.py` رو ویرایش و اجرا کن |
| قوانین تونل یا DNS | `app/tunconf.py` |
| پیش‌فرض تنظیمات | `DEFAULT_SETTINGS` در `app/moxyvpn_gui.py` |
| نسخه‌ی mihomo یا پایتون | متغیرهای بالای `tools/fetch_deps.sh` |

## مشکلات رایج
- `missing tool: x86_64-w64-mingw32-gcc` ← بسته‌ی `mingw-w64` رو نصب کن.
- دانلود قطع شد ← دوباره همان دستور رو بزن؛ ادامه میده.
- ویندوز هشدار SmartScreen میده ← نصب‌کننده امضای دیجیتال ندارد (گواهی امضا پولیه). More info ← Run anyway.
- آنتی‌ویروس هشدار الکی داد ← به‌خاطر موتور تونل است؛ فایل رو از Releases بگیر و خودت بساز تا مطمئن باشی.

## نکته‌ی لایسنس
کد خودت MIT است، ولی `mihomo` لایسنس **GPL-3.0** دارد. فایلش داخل ریپو نیست و موقع ساخت دانلود میشه. اگر نصب‌کننده‌ای که شامل آن است رو منتشر میکنی، لینک سورس mihomo رو هم در README بذار (در `THIRD_PARTY_NOTICES.md` هست).
