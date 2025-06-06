import logging
import requests
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from telegram import Bot, Update, InputFile
from telegram.ext import CommandHandler, Updater, CallbackContext
from ta.trend import SMAIndicator
from ta.momentum import RSIIndicator
from textblob import TextBlob

# ==================== CONFIG ===========================
API_TOKEN = "7927741258:AAFVVCig7i2_jAavoBerZi0MzX0BAg8Vyko"
TWELVEDATA_API_KEY = "76d6393478d3421ab78202f8495e6d62"
TIMEFRAME = "1h"
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
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])
    return df

# ==================== Fungsi Analisis Teknikal =========================
def analyze_technical(df: pd.DataFrame):
    ma_short = SMAIndicator(df["close"], PERIOD_MA_SHORT).sma_indicator()
    ma_long = SMAIndicator(df["close"], PERIOD_MA_LONG).sma_indicator()
    rsi = RSIIndicator(df["close"], RSI_PERIOD).rsi()
    
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
        sl = entry * 0.995
        tp = entry + (entry - sl) * 3
    elif trend == "Bearish":
        entry = close
        sl = entry * 1.005
        tp = entry - (sl - entry) * 3
    else:
        entry = sl = tp = close
    return entry, sl, tp

# ==================== Fungsi Buat Chart =========================
def create_chart(df: pd.DataFrame, ma_short, ma_long, entry, sl, tp, pair: str):
    plt.figure(figsize=(10,6))
    
    # Plot candle sticks
    plt.plot(df.index, df['close'], label='Close Price', color='blue')
    
    # Plot moving averages
    plt.plot(df.index, ma_short, label=f'MA {PERIOD_MA_SHORT}', color='green')
    plt.plot(df.index, ma_long, label=f'MA {PERIOD_MA_LONG}', color='red')
    
    # Plot entry, SL, TP lines
    plt.axhline(y=entry, color='green', linestyle='--', label='Entry')
    plt.axhline(y=sl, color='red', linestyle='--', label='Stop Loss')
    plt.axhline(y=tp, color='orange', linestyle='--', label='Take Profit')
    
    plt.title(f"{pair} - Forex Prediction")
    plt.xlabel('Date')
    plt.ylabel('Price')
    plt.legend()
    plt.grid()
    
    # Simpan ke buffer
    buf = BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return buf

# ==================== Fungsi Analisis Sentimen Berita Sederhana =========================
def analyze_sentiment():
    sentiment = "Netral"
    score = 0.0
    
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

        df = fetch_forex_data(pair)
        ma_short, ma_long, rsi, trend = analyze_technical(df)
        entry, sl, tp = determine_levels(df, trend)
        sentiment, sentiment_score = analyze_sentiment()
        buf = create_chart(df, ma_short, ma_long, entry, sl, tp, pair)
        
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

    except Exception as e:
        logger.error(f"Error saat memproses perintah /prediksi: {e}", exc_info=True)
        update.message.reply_text("Maaf, terjadi error saat mencoba mengambil data atau memproses permintaan Anda. Mohon coba lagi nanti atau pastikan pair mata uang benar.")
        return

# ==================== Fungsi Main =========================
def main():
    updater = Updater(API_TOKEN)
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("prediksi", prediksi))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
    
