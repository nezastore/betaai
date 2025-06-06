import logging
import os
import re
import asyncio
from io import BytesIO

import google.generativeai as genai
from telegram import Update
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, ContextTypes)
from PIL import Image
from dotenv import load_dotenv

# Muat environment variables dari file .env
load_dotenv()

# ==================== KONFIGURASI =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Konfigurasi logging untuk debugging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Konfigurasi Google Gemini AI
try:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash-latest')
    logger.info("Koneksi ke AI berhasil.")
except Exception as e:
    logger.error(f"Gagal konfigurasi Gemini AI: {e}")
    gemini_model = None

# ==================== PROMPT ENGINEERING UNTUK BOT (REVISI) =========================
# Ini adalah "otak" dari AI kita. Prompt yang bagus menghasilkan analisis yang bagus.
PROMPT_TEMPLATE = """
Anda adalah seorang analis teknikal profesional dan manajer risiko di dunia trading forex, saham, dan kripto. Anda sangat ahli dalam menganalisis chart trading dari gambar.

Tugas Anda adalah menganalisis gambar screenshot dari sebuah chart trading yang saya berikan. Lakukan analisis secara mendalam dan berikan rencana trading yang konkret berdasarkan apa yang terlihat.

Langkah-langkah analisis Anda:
1.  **Identifikasi Aset & Timeframe**: Jika terlihat, sebutkan nama aset (misal: EURUSD, BTCUSDT) dan timeframe chart.
2.  **Analisis Tren Utama**: Tentukan apakah tren utama sedang Bullish (naik), Bearish (turun), atau Sideways (ranging). Gunakan garis tren atau struktur harga (higher highs, lower lows) sebagai acuan.
3.  **Analisis Visual Inti**: Fokus utama pada **price action** dan struktur pasar. Identifikasi elemen berikut:
    - **Pola Chart & Candlestick**: Cari pola chart (misal: Head and Shoulders, Double Top, Triangle) dan pola candlestick penting (misal: Engulfing, Doji).
    - **Level Support & Resistance**: Tentukan level-level kunci di mana harga kemungkinan akan bereaksi.
    - **Analisis sentimen pasar berdasarkan berita.
    - **Visualisasi grafik.
    - **Indikator (Jika Ada)**: Jika dan hanya jika ada indikator teknikal yang terlihat di chart (seperti Moving Average, RSI, dll.), jelaskan sinyal yang diberikannya. **Jika tidak ada indikator sama sekali (chart kosong), cukup fokus pada analisis price action dan jangan sebutkan tentang ketiadaan indikator.**
4.  **Rencana Trading**: Berdasarkan semua analisis di atas, buat sebuah hipotesis atau rencana trading. Tentukan apakah akan mengambil posisi Long (Beli) atau Short (Jual).

**FORMAT OUTPUT (SANGAT PENTING!)**:
Sajikan hasil analisis Anda dalam format yang SAMA PERSIS seperti di bawah ini, menggunakan tag yang telah ditentukan. JANGAN mengubah format ini.

[ARAH]: (Bullish/Bearish/Netral)
[ANALISIS]: (Tuliskan analisis lengkap Anda di sini dalam beberapa paragraf. Jelaskan alasan di balik keputusan Anda dengan logika yang kuat berdasarkan apa yang Anda lihat di chart.)
[ENTRY]: (Titik harga masuk yang optimal berdasarkan analisa teknikal terbaru dan trend pasar.)
[SL]: (Level Stop Loss yang logis dan aman, memperhatikan support/resistance dan volatilitas.)
[TP]: (Target Take Profit dengan Risk/Reward 1:3, disesuaikan dengan peluang pergerakan harga.)
-   Berikan nilai harga dengan akurat dalam format desimal yang biasa dipakai di forex.
---
**Aturan Tambahan**:
-   Jika gambar tidak jelas atau bukan merupakan chart trading, jawab hanya dengan: `[ERROR]: Gambar tidak valid atau tidak jelas.`
-   Fokus hanya pada informasi yang terlihat di dalam gambar. Jangan membuat asumsi.
"""


# ==================== FUNGSI-FUNGSI BOT =========================

async def analyze_image_with_gemini(image_bytes: bytes) -> str:
    """Mengirim gambar ke Gemini dan mengembalikan respons teks."""
    if not gemini_model:
        return "[ERROR]: Klien Gemini AI tidak terkonfigurasi dengan benar."
        
    try:
        image_pil = Image.open(BytesIO(image_bytes))
        response = await gemini_model.generate_content_async([PROMPT_TEMPLATE, image_pil])
        return response.text
    except Exception as e:
        logger.error(f"Error saat memanggil Gemini API: {e}")
        return f"[ERROR]: Terjadi masalah saat berkomunikasi dengan AI. Detail: {e}"

def parse_gemini_response(text: str) -> dict | None:
    """Mem-parsing respons teks dari Gemini menggunakan regex."""
    try:
        # Pola regex untuk mengekstrak data dari format yang ditentukan
        pattern = re.compile(
            r"\[ARAH\]:\s*(?P<arah>.*?)\s*"
            r"\[ANALISIS\]:\s*(?P<analisis>.*?)\s*"
            r"\[ENTRY\]:\s*(?P<entry>.*?)\s*"
            r"\[SL\]:\s*(?P<sl>.*?)\s*"
            r"\[TP\]:\s*(?P<tp>.*)",
            re.DOTALL | re.IGNORECASE
        )
        match = pattern.search(text)
        if match:
            return match.groupdict()
        return None
    except Exception as e:
        logger.error(f"Gagal mem-parsing respons: {e}")
        return None

# ==================== HANDLER TELEGRAM =========================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk perintah /start."""
    user = update.effective_user
    await update.message.reply_html(
        f"Halo, {user.mention_html()}! 👋\n\n"
        "Saya adalah Bot Analis Chart Anda, ditenagai oleh AI.\n\n"
        "Kirimkan saya screenshot chart trading (Forex, Kripto, Saham), dan saya akan memberikan analisis teknikal mendalam beserta rencana tradingnya.\n\n"
        "Silakan kirim gambar pertama Anda!"
    )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk pesan gambar."""
    message = await update.message.reply_text("🧠 Menerima gambar... Menganalisis dengan AI, mohon tunggu sebentar...")

    try:
        photo_file = await update.message.photo[-1].get_file()
        image_bytes = await photo_file.download_as_bytearray()

        # Analisis gambar dengan Gemini
        gemini_result_text = await analyze_image_with_gemini(bytes(image_bytes))

        if "[ERROR]" in gemini_result_text:
            await message.edit_text(gemini_result_text)
            return

        # Parsing hasil dari Gemini
        parsed_data = parse_gemini_response(gemini_result_text)

        if not parsed_data:
            await message.edit_text(
                "Maaf, saya kesulitan memahami format respons dari AI. Coba lagi dengan gambar yang lebih jelas.\n\n"
                f"```\n{gemini_result_text}\n```"
            )
            return

        # Membuat pesan balasan yang terformat dengan baik
        arah = parsed_data.get('arah', 'N/A').strip()
        analisis = parsed_data.get('analisis', 'N/A').strip()
        entry = parsed_data.get('entry', 'N/A').strip()
        sl = parsed_data.get('sl', 'N/A').strip()
        tp = parsed_data.get('tp', 'N/A').strip()

        icon = "📈" if "bullish" in arah.lower() else "📉" if "bearish" in arah.lower() else "📊"
        
        # <<< PENAMBAHAN FITUR DI SINI >>>
        # Menentukan label rencana trading berdasarkan arah
        if "bullish" in arah.lower():
            rencana_label = "🟢 Rencana Beli (Long)"
        elif "bearish" in arah.lower():
            rencana_label = "🔴 Rencana Jual (Short)"
        else:
            rencana_label = "⚪️ Rencana Netral"

        response_message = (
            f"*{icon} Hasil Analisis Chart dari AI*\n\n"
            f"🎯 *Potensi Arah*: `{arah}`\n\n"
            f"💬 *Analisis Mendalam*:\n{analisis}\n\n"
            f"📋 *{rencana_label}*:\n" # <<< PERUBAHAN DI SINI >>>
            f"   - *Entry Point*: `{entry}`\n"
            f"   - *Stop Loss*: `{sl}`\n"
            f"   - *Take Profit (RR 1:3)*: `{tp}`\n\n"
            f"⚠️ *Disclaimer*: Selalu kelola risiko dengan baik."
        )

        await message.edit_text(response_message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error di photo_handler: {e}", exc_info=True)
        await message.edit_text("Maaf, terjadi kesalahan internal saat memproses gambar Anda. Silakan coba lagi nanti.")


# ==================== FUNGSI UTAMA =========================
def main():
    """Fungsi utama untuk menjalankan bot."""
    if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
        logger.critical("TOKEN TELEGRAM atau API KEY GEMINI tidak ditemukan. Pastikan file .env sudah benar.")
        return

    logger.info("Memulai Bot...")
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Daftarkan handler
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    # Jalankan bot
    application.run_polling()
    logger.info("Bot Berhenti.")


if __name__ == '__main__':
    main()
