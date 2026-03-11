"""
Indicadores Técnicos para o Bot Scalper
"""
import pandas as pd
import numpy as np
from typing import List


def calculate_ema(prices: List[float], period: int) -> float:
    """
    Calcula EMA (Exponential Moving Average).
    
    Args:
        prices: Lista de preços de fechamento
        period: Período da EMA
    
    Returns:
        Valor da EMA
    """
    if len(prices) < period:
        return prices[-1] if prices else 0.0
    
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]


def calculate_sma(prices: List[float], period: int) -> float:
    """
    Calcula SMA (Simple Moving Average).
    
    Args:
        prices: Lista de preços de fechamento
        period: Período da SMA
    
    Returns:
        Valor da SMA
    """
    if len(prices) < period:
        return sum(prices) / len(prices) if prices else 0.0
    
    return sum(prices[-period:]) / period


def calculate_rsi(prices: List[float], period: int = 14) -> float:
    """
    Calcula RSI (Relative Strength Index).
    
    Args:
        prices: Lista de preços de fechamento
        period: Período do RSI (default: 14)
    
    Returns:
        Valor do RSI (0-100)
    """
    if len(prices) < period + 1:
        return 50.0  # Valor neutro se não há dados suficientes
    
    deltas = np.diff(prices)
    seed = deltas[:period + 1]
    
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    
    if down == 0:
        return 100.0 if up > 0 else 50.0
    
    rs = up / down
    rsi = 100 - (100 / (1 + rs))
    
    for delta in deltas[period + 1:]:
        if delta > 0:
            upval = delta
            downval = 0
        else:
            upval = 0
            downval = -delta
        
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        
        if down == 0:
            rsi = 100.0 if up > 0 else 50.0
        else:
            rs = up / down
            rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    """
    Calcula ATR (Average True Range).
    
    Args:
        highs: Lista de preços altos
        lows: Lista de preços baixos
        closes: Lista de preços de fechamento
        period: Período do ATR (default: 14)
    
    Returns:
        Valor do ATR
    """
    if len(closes) < 2:
        return 0.0
    
    true_ranges = []
    
    for i in range(1, len(closes)):
        high_low = highs[i] - lows[i]
        high_close = abs(highs[i] - closes[i - 1])
        low_close = abs(lows[i] - closes[i - 1])
        
        true_range = max(high_low, high_close, low_close)
        true_ranges.append(true_range)
    
    if len(true_ranges) < period:
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0
    
    # ATR com suavização exponencial
    atr = sum(true_ranges[:period]) / period
    
    for tr in true_ranges[period:]:
        atr = ((period - 1) * atr + tr) / period
    
    return atr


def calculate_bollinger_bands(
    prices: List[float], 
    period: int = 20, 
    std_dev: float = 2.0
) -> tuple:
    """
    Calcula Bollinger Bands.
    
    Args:
        prices: Lista de preços de fechamento
        period: Período da média móvel (default: 20)
        std_dev: Número de desvios padrão (default: 2.0)
    
    Returns:
        Tuple (upper_band, middle_band, lower_band)
    """
    if len(prices) < period:
        middle = prices[-1] if prices else 0.0
        return middle, middle, middle
    
    middle = calculate_sma(prices, period)
    
    # Calcula desvio padrão
    variance = sum((p - middle) ** 2 for p in prices[-period:]) / period
    std = variance ** 0.5
    
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return upper, middle, lower


def calculate_macd(
    prices: List[float], 
    fast_period: int = 12, 
    slow_period: int = 26, 
    signal_period: int = 9
) -> tuple:
    """
    Calcula MACD (Moving Average Convergence Divergence).
    
    Args:
        prices: Lista de preços de fechamento
        fast_period: Período da EMA rápida (default: 12)
        slow_period: Período da EMA lenta (default: 26)
        signal_period: Período da linha de sinal (default: 9)
    
    Returns:
        Tuple (macd_line, signal_line, histogram)
    """
    if len(prices) < slow_period:
        return 0.0, 0.0, 0.0
    
    # Calcula EMAs
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast_period, adjust=False).mean()
    ema_slow = series.ewm(span=slow_period, adjust=False).mean()
    
    # MACD line
    macd_line = ema_fast - ema_slow
    
    # Signal line
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    
    # Histogram
    histogram = macd_line - signal_line
    
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
