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
TELEGRAM_TOKEN = "7927741258:AAFVVCig7i2_jAavoBerZi0MzX0BAg8Vyko"
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
            update.message.reply_text("Gunakan perintah dengan format: /prediksi <PAIR>, contoh: /prediksi EUR/USD")
            return
        pair = context.args[0].upper()
        
        # Ambil data
        df = fetch_forex_data(pair)
