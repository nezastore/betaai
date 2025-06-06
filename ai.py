import os
import io
import requests
import pandas as pd
import mplfinance as mpf
from ta.momentum import RSIIndicator
from telegram import Update, InputFile
from telegram.ext import Updater, CommandHandler, CallbackContext
from textblob import TextBlob
from datetime import datetime

# Settings
TWELVE_DATA_API_KEY = "76d6393478d3421ab78202f8495e6d62"
TELEGRAM_BOT_TOKEN = "7927741258:AAFVVCig7i2_jAavoBerZi0MzX0BAg8Vyko"

def fetch_forex_data(pair: str, interval='15min', outputsize=100):
    symbol = pair.upper().replace('/', '')
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&format=JSON&apikey={TWELVE_DATA_API_KEY}"
    resp = requests.get(url)
    data = resp.json()
    if "values" not in data:
        raise ValueError(f"Error fetching data: {data.get('message', 'unknown error')}")
    df = pd.DataFrame(data['values'])
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.set_index('datetime')
    df = df.astype(float)
    df = df.sort_index()
    return df

def calculate_indicators(df: pd.DataFrame):
    df['MA_short'] = df['close'].rolling(window=5).mean()
    df['MA_long'] = df['close'].rolling(window=20).mean()
    rsi_indicator = RSIIndicator(df['close'], window=14)
    df['RSI'] = rsi_indicator.rsi()
    return df

def analyze_trend(df: pd.DataFrame):
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    trend = "Sideways"
    signal = None

    # MA crossover
    if prev['MA_short'] < prev['MA_long'] and latest['MA_short'] > latest['MA_long']:
        trend = "Bullish"
        signal = "Buy"
    elif prev['MA_short'] > prev['MA_long'] and latest['MA_short'] < latest['MA_long']:
        trend = "Bearish"
        signal = "Sell"
    else:
        signal = "Hold"

    rsi = latest['RSI']
    rsi_status = "Neutral"
    if rsi is not None:
        if rsi > 70:
            rsi_status = "Overbought"
        elif rsi < 30:
            rsi_status = "Oversold"

    return trend, signal, rsi, rsi_status

def determine_levels(df: pd.DataFrame, signal: str):
    latest_close = df['close'].iloc[-1]
    sl = None
    tp = None
    risk = 0.005  # 0.5% risk as default

    if signal == "Buy":
        sl = latest_close * (1 - risk)
        tp = latest_close + (latest_close - sl) * 3
    elif signal == "Sell":
        sl = latest_close * (1 + risk)
        tp = latest_close - (sl - latest_close) * 3

    if sl is not None:
        sl = round(sl, 5)
    if tp is not None:
        tp = round(tp, 5)

    return round(latest_close, 5), sl, tp

def draw_chart(df: pd.DataFrame, pair: str, entry: float, sl: float, tp: float):
    apds = [
        mpf.make_addplot(df['MA_short'], color='blue'),
        mpf.make_addplot(df['MA_long'], color='orange'),
        mpf.make_addplot(df['RSI'], panel=1, color='green'),
    ]

    fig, axlist = mpf.plot(df,
                           type='candle',
                           style='yahoo',
                           addplot=apds,
                           returnfig=True,
                           figscale=1.2,
                           title=f'{pair} Chart with MA and RSI',
                           ylabel='Price',
                           ylabel_panel='RSI',
                           panel_ratios=(3,1))

    ax = axlist[0]  # price axis
    # Draw entry, SL, TP lines
    ymin, ymax = ax.get_ylim()
    ax.hlines([entry, sl, tp], xmin=df.index[0], xmax=df.index[-1],
              colors=['green', 'red', 'purple'], linestyles=['--','--','--'],
              label=['Entry', 'Stop Loss', 'Take Profit'])

    ax.legend(['MA Short', 'MA Long', 'Entry', 'Stop Loss', 'Take Profit'])

    # Save to buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png')
    buf.seek(0)
    return buf

def analyze_sentiment(pair: str):
    # Simple sentiment analysis from forex news titles (static examples due to no web scraping)
    # In actual bot, fetch RSS feed and analyze titles for pair relevance
    example_news = [
        "EURUSD bullish momentum expected to continue",
        "US dollar weakens as risk appetite returns",
        "GBPUSD faces resistance amid Brexit concerns"
    ]
    sentiments = []
    for news in example_news:
        if pair.upper().replace('/', '') in news.replace(' ', '').upper():
            blob = TextBlob(news)
            sentiments.append(blob.sentiment.polarity)
    if sentiments:
        avg_sentiment = sum(sentiments) / len(sentiments)
        if avg_sentiment > 0.1:
            return "Positive"
        elif avg_sentiment < -0.1:
            return "Negative"
        else:
            return "Neutral"
    else:
        return "No relevant news found"

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Halo! Gunakan perintah /prediksi <PAIR>, contoh: /prediksi EUR/USD")

def prediksi(update: Update, context: CallbackContext):
    try:
        if len(context.args) != 1:
            update.message.reply_text("Format salah. Gunakan: /prediksi <PAIR> contoh: /prediksi EUR/USD")
            return
        pair = context.args[0].upper()

        update.message.reply_text(f"Mengambil data dan melakukan analisis untuk pair {pair}...")

        # Fetch data
        df = fetch_forex_data(pair)

        # Calculate indicators
        df = calculate_indicators(df)

        # Analyze trend and signal
        trend, signal, rsi, rsi_status = analyze_trend(df)

        # Determine entry, SL, TP
        entry, sl, tp = determine_levels(df, signal)

        # Analyze sentiments
        sentiment = analyze_sentiment(pair)

        # Draw chart
        chart_buf = draw_chart(df, pair, entry, sl, tp)

        # Compose message
        msg = (f"Pair: {pair}\n"
               f"Trend saat ini: {trend}\n"
               f"Signal: {signal}\n"
               f"RSI: {rsi:.2f} ({rsi_status})\n"
               f"
  
