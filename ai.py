import logging
import requests
import pandas as pd
import mplfinance as mpf
from io import BytesIO
from telegram import Bot, Update, InputFile
from telegram.ext import CommandHandler, Updater, CallbackContext
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from textblob import TextBlob

# ==================== CONFIG ===========================
API_TOKEN = "7927741258:AAFVVCig7i2_jAavoBerZi0MzX0BAg8Vyko"  # Ganti dengan token API bot Telegram Anda yang sebenarnya
TWELVEDATA_API_KEY = "76d6393478d3421ab78202f8495e6d62"
# Default timeframe dan periode untuk analisis
TIMEFRAME = "1h"  # Bisa juga gantikan dengan "15min", "1day"
PERIOD_MA_SHORT = 7
PERIOD_MA_LONG = 21
RSI_PERIOD = 14

# ==================== LOGGING =========================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== Fungsi Ambil Data Harga =========================
def fetch_forex_data(pair: str, interval: str = TIMEFRAME, outputsize=100) -> pd.DataFrame:
    symbol = pair.upper().replace("/", "")
    url = f"https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "apikey": TWELVEDATA_API_KEY,
        "format": "JSON",
        "outputsize": outputsize,
        "timezone": "UTC"
    }
    res = requests.get(url, params=params)
    data = res.json()
    if "values" not in data:
        raise ValueError(f"Error fetching data: {data.get('message', 'Unknown error')}")
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.set_index("datetime", inplace=True)
    df = df.sort_index()
    # Convert to numeric
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    return df

# ==================== Fungsi Analisis Teknikal =========================
def analyze_technical(df: pd.DataFrame):
    # Hitung MA pendek dan MA panjang
    ma_short = SMAIndicator(df["close"], PERIOD_MA_SHORT).sma_indicator()
    ma_long = SMAIndicator(df["close"], PERIOD_MA_LONG).sma_indicator()
    rsi = RSIIndicator(df["close"], RSI_PERIOD).rsi()
    
    # Sinyal MA crossover
    trend = "Sideways"
    if ma_short.iloc[-2] < ma_long.iloc[-2] and ma_short.iloc[-1] > ma_long.iloc[-1]:
        trend = "Bullish"
    elif ma_short.iloc[-2] > ma_long.iloc[-2] and ma_short.iloc[-1] < ma_long.iloc[-1]:
        trend = "Bearish"
    else:
        if ma_short.iloc[-1] > ma_long.iloc[-1]:
            trend = "Bullish"
        elif ma_short.iloc[-1] < ma_long.iloc[-1]:
            trend = "Bearish"

    return ma_short, ma_long, rsi, trend

# ==================== Fungsi Tentukan Entry, SL, TP =========================
def determine_levels(df: pd.DataFrame, trend: str):
    close = df["close"].iloc[-1]
    if trend == "Bullish":
        entry = close
        sl = entry * 0.995  # SL 0.5% dibawah entry
        tp = entry + (entry - sl) * 3  # TP rasio 3:1
    elif trend == "Bearish":
        entry = close
        sl = entry * 1.005  # SL 0.5% di atas entry
        tp = entry - (sl - entry) * 3
    else:
        entry = sl = tp = close
    return entry, sl, tp

# ==================== Fungsi Buat Chart =========================
def create_chart(df: pd.DataFrame, ma_short, ma_long, entry, sl, tp, pair: str):
    apds = [
        mpf.make_addplot(ma_short, color='blue'),
        mpf.make_addplot(ma_long, color='red')
    ]

    fig, axlist = mpf.plot(df, type='candle', style='yahoo', addplot=apds, returnfig=True,
                           title=f"{pair} - Forex Prediction", figsize=(10,6))
    ax = axlist[0]

    # Tandai entry, SL, TP
    last_date = df.index[-1]
    ax.hlines([entry, sl, tp], xmin=df.index[0], xmax=last_date, colors=['green', 'red', 'orange'], linestyles='--')
    ax.text(df.index[0], entry, 'Entry', color='green', verticalalignment='bottom')
    ax.text(df.index[0], sl, 'SL', color='red', verticalalignment='bottom')
    ax.text(df.index[0], tp, 'TP', color='orange', verticalalignment='bottom')

    # Simpan ke buffer
    buf = BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    return buf

# ==================== Fungsi Analisis Sentimen Berita Sederhana =========================
def analyze_sentiment():
    # Placeholder: Bisa diganti dengan ambil RSS/API berita forex dan analisa judulnya
    # Sekarang kita buat dummy sentiment positif
    sentiment = "Netral"
    score = 0.0
    
    # Contoh analisa sederhana dengan TextBlob, ganti dengan API atau RSS nyata
    sample_news_title = "Euro menguat karena data ekonomi AS lemah"
    blob = TextBlob(sample_news_title)
    polarity = blob.sentiment.polarity
    if polarity > 0.1:
        sentiment = "Positif"
    elif polarity < -0.1:
        sentiment = "Negatif"
    else:
        sentiment = "Netral"
    score = polarity
    return sentiment, score

# ==================== Command Handler =========================
def prediksi(update: Update, context: CallbackContext):
 try:
     if not context.args:
         update.message.reply_text("Gunakan perintah dengan format: /prediksi (pair mata uang), contoh: /prediksi EURUSD")
         return
     pair = context.args[0].upper()

     # Ambil data
     df = fetch_forex_data(pair)

     # Analisis teknikal
     ma_short, ma_long, rsi, trend = analyze_technical(df)
     entry, sl, tp = determine_levels(df, trend)
     
     # Analisis sentimen
     sentiment, sentiment_score = analyze_sentiment()

     # Buat chart
     buf = create_chart(df, ma_short, ma_long, entry, sl, tp, pair)
     
     # Kirim hasil ke pengguna
     message = (
         f"💰 *Prediksi Forex untuk {pair} ({TIMEFRAME})*\n\n"
         f"📊 *Analisis Teknikal:*\n"
         f"  - Tren: `{trend}`\n"
         f"  - Entry: `{entry:.5f}`\n"
         f"  - Stop Loss: `{sl:.5f}`\n"
         f"  - Take Profit: `{tp:.5f}`\n"
         f"  - RSI: `{rsi.iloc[-1]:.2f}`\n\n"
         f"📰 *Analisis Sentimen Berita:*\n"
         f"  - Sentimen: `{sentiment}` (Skor: `{sentiment_score:.2f}`)\n\n"
         f"Catatan: Prediksi ini bersifat indikatif."
     )
     
     update.message.reply_photo(photo=InputFile(buf, filename=f'{pair}_chart.png'), caption=message, parse_mode='Markdown')

 except Exception as e: # Ini akan menangkap semua jenis error
     logger.error(f"Error saat memproses perintah /prediksi: {e}", exc_info=True) # Tambahkan logging detail error
     update.message.reply_text(f"Maaf, terjadi error saat mencoba mengambil data atau memproses permintaan Anda. Mohon coba lagi nanti atau pastikan pair mata uang benar.")
     return # Penting untuk menghentikan eksekusi jika terjadi error

# ==================== Fungsi Main =========================
def main():
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    # Hapus use_context=True karena sudah tidak digunakan di versi baru
    updater = Updater(API_TOKEN, update_queue=None)

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("prediksi", prediksi))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()

if __name__ == '__main__':
    main()
