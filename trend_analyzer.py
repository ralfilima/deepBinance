"""
Trend Analyzer Module V3
Análise de tendência para decidir LONG ou SHORT
Inclui filtros de sobrecompra/sobrevenda (RSI + Bollinger)
"""
import logging
from typing import Dict, Optional, Tuple, List
from binance.client import Client

logger = logging.getLogger(__name__)

# Cores no terminal
try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""


# ============================================================
# CONSTANTES DE FILTRO DE SOBRECOMPRA
# ============================================================
RSI_OVERBOUGHT = 70       # RSI > 70 = sobrecompra (não entrar LONG)
RSI_OVERSOLD = 30         # RSI < 30 = sobrevenda (não entrar SHORT)
RSI_EXTREME_OB = 80       # RSI extremamente sobrecomprado
RSI_EXTREME_OS = 20       # RSI extremamente sobrevendido
BOLLINGER_PERIOD = 20     # Período das Bandas de Bollinger
BOLLINGER_STD = 2.0       # Desvios padrão para bandas


class TrendAnalyzer:
    """
    Analisador de tendência V3 para decisão LONG/SHORT.
    
    Indicadores utilizados:
    - EMA 9 vs EMA 21 (tendência curta)
    - RSI 14 (momentum e filtro de sobrecompra)
    - Momentum (variação recente)
    - Bollinger Bands (filtro de extremos)
    
    Novos filtros V3:
    - Bloqueia LONG se RSI > 70 ou preço > Banda Superior
    - Bloqueia SHORT se RSI < 30 ou preço < Banda Inferior
    """
    
    def __init__(self, client: Client):
        """
        Inicializa o analisador.
        
        Args:
            client: Cliente Binance autenticado
        """
        self.client = client
        self._blocked_entries: Dict[str, str] = {}  # symbol -> reason
    
    def get_klines(self, symbol: str, interval: str = '5m', limit: int = 50) -> List[Dict]:
        """
        Obtém klines (candles) do par.
        
        Args:
            symbol: Símbolo do par
            interval: Intervalo dos candles
            limit: Número de candles
        
        Returns:
            Lista de candles formatados
        """
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            
            candles = []
            for k in klines:
                candles.append({
                    'open': float(k[1]),
                    'high': float(k[2]),
                    'low': float(k[3]),
                    'close': float(k[4]),
                    'volume': float(k[5])
                })
            
            return candles
            
        except Exception as e:
            logger.error(f"[TREND] Erro ao obter klines de {symbol}: {e}")
            return []
    
    def calculate_ema(self, prices: List[float], period: int) -> float:
        """
        Calcula EMA (Exponential Moving Average).
        
        Args:
            prices: Lista de preços
            period: Período da EMA
        
        Returns:
            Valor da EMA
        """
        if len(prices) < period:
            return prices[-1] if prices else 0
        
        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # SMA inicial
        
        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema
        
        return ema
    
    def calculate_sma(self, prices: List[float], period: int) -> float:
        """Calcula SMA (Simple Moving Average)."""
        if len(prices) < period:
            return sum(prices) / len(prices) if prices else 0
        return sum(prices[-period:]) / period
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """
        Calcula RSI (Relative Strength Index).
        
        Args:
            prices: Lista de preços de fechamento
            period: Período do RSI
        
        Returns:
            Valor do RSI (0-100)
        """
        if len(prices) < period + 1:
            return 50  # Valor neutro
        
        # Calcula mudanças
        changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        
        # Separa ganhos e perdas
        gains = [max(c, 0) for c in changes]
        losses = [abs(min(c, 0)) for c in changes]
        
        # Médias
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def calculate_bollinger_bands(
        self, 
        prices: List[float], 
        period: int = BOLLINGER_PERIOD, 
        std_dev: float = BOLLINGER_STD
    ) -> Tuple[float, float, float]:
        """
        Calcula Bandas de Bollinger.
        
        Args:
            prices: Lista de preços de fechamento
            period: Período da média móvel
            std_dev: Número de desvios padrão
        
        Returns:
            Tuple (upper_band, middle_band, lower_band)
        """
        if len(prices) < period:
            middle = prices[-1] if prices else 0
            return middle, middle, middle
        
        middle = self.calculate_sma(prices, period)
        
        # Calcula desvio padrão
        variance = sum((p - middle) ** 2 for p in prices[-period:]) / period
        std = variance ** 0.5
        
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        
        return upper, middle, lower
    
    def calculate_momentum(self, prices: List[float], period: int = 10) -> float:
        """
        Calcula Momentum (variação percentual).
        
        Args:
            prices: Lista de preços
            period: Período para comparação
        
        Returns:
            Momentum em %
        """
        if len(prices) < period + 1:
            return 0
        
        current = prices[-1]
        past = prices[-period-1]
        
        if past == 0:
            return 0
        
        momentum = ((current - past) / past) * 100
        return momentum
    
    def check_overbought_oversold(
        self, 
        symbol: str, 
        direction: str
    ) -> Tuple[bool, str]:
        """
        Verifica se o ativo está em condição de sobrecompra/sobrevenda
        que impediria a entrada na direção especificada.
        
        Args:
            symbol: Símbolo do par
            direction: 'LONG' ou 'SHORT'
        
        Returns:
            Tuple (is_blocked, reason)
        """
        try:
            candles = self.get_klines(symbol, interval='5m', limit=50)
            
            if len(candles) < 25:
                return False, ""
            
            closes = [c['close'] for c in candles]
            current_price = closes[-1]
            
            # Calcula RSI
            rsi = self.calculate_rsi(closes, 14)
            
            # Calcula Bollinger Bands
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(closes)
            
            # Verifica condições de bloqueio para LONG
            if direction == 'LONG':
                # RSI sobrecomprado
                if rsi >= RSI_OVERBOUGHT:
                    reason = f"RSI={rsi:.1f} (sobrecompra >{RSI_OVERBOUGHT})"
                    self._blocked_entries[symbol] = reason
                    logger.info(f"{Fore.YELLOW}🚫 {symbol}: Bloqueado LONG - {reason}{Style.RESET_ALL}")
                    return True, reason
                
                # Preço acima da Banda Superior
                if current_price > upper_bb:
                    pct_above = ((current_price - upper_bb) / upper_bb) * 100
                    reason = f"Preço {pct_above:.2f}% acima Bollinger Superior"
                    self._blocked_entries[symbol] = reason
                    logger.info(f"{Fore.YELLOW}🚫 {symbol}: Bloqueado LONG - {reason}{Style.RESET_ALL}")
                    return True, reason
                
                # RSI extremamente alto
                if rsi >= RSI_EXTREME_OB:
                    reason = f"RSI={rsi:.1f} (EXTREMO >{RSI_EXTREME_OB})"
                    self._blocked_entries[symbol] = reason
                    return True, reason
            
            # Verifica condições de bloqueio para SHORT
            elif direction == 'SHORT':
                # RSI sobrevendido
                if rsi <= RSI_OVERSOLD:
                    reason = f"RSI={rsi:.1f} (sobrevenda <{RSI_OVERSOLD})"
                    self._blocked_entries[symbol] = reason
                    logger.info(f"{Fore.YELLOW}🚫 {symbol}: Bloqueado SHORT - {reason}{Style.RESET_ALL}")
                    return True, reason
                
                # Preço abaixo da Banda Inferior
                if current_price < lower_bb:
                    pct_below = ((lower_bb - current_price) / lower_bb) * 100
                    reason = f"Preço {pct_below:.2f}% abaixo Bollinger Inferior"
                    self._blocked_entries[symbol] = reason
                    logger.info(f"{Fore.YELLOW}🚫 {symbol}: Bloqueado SHORT - {reason}{Style.RESET_ALL}")
                    return True, reason
                
                # RSI extremamente baixo
                if rsi <= RSI_EXTREME_OS:
                    reason = f"RSI={rsi:.1f} (EXTREMO <{RSI_EXTREME_OS})"
                    self._blocked_entries[symbol] = reason
                    return True, reason
            
            return False, ""
            
        except Exception as e:
            logger.error(f"[TREND] Erro ao verificar sobrecompra {symbol}: {e}")
            return False, ""
    
    def analyze(self, symbol: str, check_overbought: bool = True) -> Dict:
        """
        Analisa tendência completa de um símbolo.
        
        Args:
            symbol: Símbolo para analisar
            check_overbought: Se deve verificar filtros de sobrecompra
        
        Returns:
            Dict com análise completa
        """
        result = {
            'symbol': symbol,
            'direction': 'NEUTRAL',  # LONG, SHORT, NEUTRAL
            'confidence': 0,  # 0-100
            'ema_signal': 'NEUTRAL',
            'rsi': 50,
            'rsi_signal': 'NEUTRAL',
            'momentum': 0,
            'momentum_signal': 'NEUTRAL',
            'score': 0,
            # Novos campos V3
            'bollinger_upper': 0,
            'bollinger_lower': 0,
            'bollinger_position': 'MIDDLE',  # ABOVE_UPPER, UPPER_HALF, MIDDLE, LOWER_HALF, BELOW_LOWER
            'entry_blocked': False,
            'blocked_reason': ''
        }
        
        try:
            # Obtém candles
            candles = self.get_klines(symbol, interval='5m', limit=50)
            
            if len(candles) < 25:
                logger.warning(f"[TREND] {symbol}: dados insuficientes")
                return result
            
            closes = [c['close'] for c in candles]
            current_price = closes[-1]
            
            # ============================================================
            # BOLLINGER BANDS ANALYSIS (V3)
            # ============================================================
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(closes)
            result['bollinger_upper'] = upper_bb
            result['bollinger_lower'] = lower_bb
            
            # Determina posição dentro das bandas
            if current_price > upper_bb:
                result['bollinger_position'] = 'ABOVE_UPPER'
            elif current_price > middle_bb:
                result['bollinger_position'] = 'UPPER_HALF'
            elif current_price < lower_bb:
                result['bollinger_position'] = 'BELOW_LOWER'
            elif current_price < middle_bb:
                result['bollinger_position'] = 'LOWER_HALF'
            else:
                result['bollinger_position'] = 'MIDDLE'
            
            # ============================================================
            # EMA ANALYSIS (40% do score)
            # ============================================================
            ema_9 = self.calculate_ema(closes, 9)
            ema_21 = self.calculate_ema(closes, 21)
            
            ema_score = 0
            
            # EMA 9 > EMA 21 = bullish
            if ema_9 > ema_21:
                ema_diff_pct = ((ema_9 - ema_21) / ema_21) * 100
                if ema_diff_pct > 0.1:
                    result['ema_signal'] = 'BULLISH'
                    ema_score = min(40, ema_diff_pct * 20)
                else:
                    result['ema_signal'] = 'WEAK_BULLISH'
                    ema_score = 10
            elif ema_9 < ema_21:
                ema_diff_pct = ((ema_21 - ema_9) / ema_21) * 100
                if ema_diff_pct > 0.1:
                    result['ema_signal'] = 'BEARISH'
                    ema_score = min(-40, -ema_diff_pct * 20)
                else:
                    result['ema_signal'] = 'WEAK_BEARISH'
                    ema_score = -10
            
            # ============================================================
            # RSI ANALYSIS (30% do score)
            # ============================================================
            rsi = self.calculate_rsi(closes, 14)
            result['rsi'] = rsi
            
            rsi_score = 0
            
            if rsi >= RSI_OVERBOUGHT:
                result['rsi_signal'] = 'OVERBOUGHT'
                rsi_score = -30  # Favorece SHORT
            elif rsi <= RSI_OVERSOLD:
                result['rsi_signal'] = 'OVERSOLD'
                rsi_score = 30  # Favorece LONG
            elif 50 <= rsi < RSI_OVERBOUGHT:
                result['rsi_signal'] = 'BULLISH'
                rsi_score = (rsi - 50) * 1.5  # 0 a 30
            elif RSI_OVERSOLD < rsi < 50:
                result['rsi_signal'] = 'BEARISH'
                rsi_score = (rsi - 50) * 1.5  # -30 a 0
            else:
                result['rsi_signal'] = 'NEUTRAL'
                rsi_score = 0
            
            # ============================================================
            # MOMENTUM ANALYSIS (30% do score)
            # ============================================================
            momentum = self.calculate_momentum(closes, 10)
            result['momentum'] = momentum
            
            mom_score = 0
            
            if momentum > 1:
                result['momentum_signal'] = 'STRONG_UP'
                mom_score = min(30, momentum * 10)
            elif momentum > 0.3:
                result['momentum_signal'] = 'UP'
                mom_score = momentum * 20
            elif momentum < -1:
                result['momentum_signal'] = 'STRONG_DOWN'
                mom_score = max(-30, momentum * 10)
            elif momentum < -0.3:
                result['momentum_signal'] = 'DOWN'
                mom_score = momentum * 20
            else:
                result['momentum_signal'] = 'NEUTRAL'
                mom_score = 0
            
            # ============================================================
            # SCORE FINAL
            # ============================================================
            total_score = ema_score + rsi_score + mom_score
            result['score'] = total_score
            
            # Determina direção preliminar
            if total_score >= 20:
                preliminary_direction = 'LONG'
                confidence = min(100, abs(total_score))
            elif total_score <= -20:
                preliminary_direction = 'SHORT'
                confidence = min(100, abs(total_score))
            else:
                preliminary_direction = 'NEUTRAL'
                confidence = 0
            
            # ============================================================
            # FILTRO DE SOBRECOMPRA (V3)
            # ============================================================
            if check_overbought and preliminary_direction != 'NEUTRAL':
                is_blocked, blocked_reason = self.check_overbought_oversold(
                    symbol, preliminary_direction
                )
                
                if is_blocked:
                    result['entry_blocked'] = True
                    result['blocked_reason'] = blocked_reason
                    # Reduz confiança mas não bloqueia completamente a análise
                    confidence = max(0, confidence - 50)
                    logger.info(
                        f"[TREND] {symbol}: {preliminary_direction} bloqueado - {blocked_reason}"
                    )
            
            result['direction'] = preliminary_direction
            result['confidence'] = confidence
            
            logger.info(
                f"[TREND] {symbol}: {result['direction']} (score={total_score:.1f}, "
                f"EMA={result['ema_signal']}, RSI={rsi:.1f}, Mom={momentum:.2f}%, "
                f"BB={result['bollinger_position']})"
            )
            
        except Exception as e:
            logger.error(f"[TREND] Erro ao analisar {symbol}: {e}")
        
        return result
    
    def get_entry_filter_status(self, symbol: str, direction: str) -> Dict:
        """
        Obtém status completo dos filtros de entrada.
        
        Args:
            symbol: Símbolo do par
            direction: 'LONG' ou 'SHORT'
        
        Returns:
            Dict com status de todos os filtros
        """
        status = {
            'symbol': symbol,
            'direction': direction,
            'can_enter': True,
            'rsi': 50,
            'rsi_ok': True,
            'bollinger_ok': True,
            'blocked_reasons': []
        }
        
        try:
            candles = self.get_klines(symbol, interval='5m', limit=50)
            if len(candles) < 25:
                return status
            
            closes = [c['close'] for c in candles]
            current_price = closes[-1]
            
            # RSI
            rsi = self.calculate_rsi(closes, 14)
            status['rsi'] = rsi
            
            # Bollinger
            upper_bb, middle_bb, lower_bb = self.calculate_bollinger_bands(closes)
            
            if direction == 'LONG':
                if rsi >= RSI_OVERBOUGHT:
                    status['rsi_ok'] = False
                    status['can_enter'] = False
                    status['blocked_reasons'].append(f"RSI={rsi:.1f} (sobrecompra)")
                
                if current_price > upper_bb:
                    status['bollinger_ok'] = False
                    status['can_enter'] = False
                    status['blocked_reasons'].append("Preço > Bollinger Superior")
            
            elif direction == 'SHORT':
                if rsi <= RSI_OVERSOLD:
                    status['rsi_ok'] = False
                    status['can_enter'] = False
                    status['blocked_reasons'].append(f"RSI={rsi:.1f} (sobrevenda)")
                
                if current_price < lower_bb:
                    status['bollinger_ok'] = False
                    status['can_enter'] = False
                    status['blocked_reasons'].append("Preço < Bollinger Inferior")
            
        except Exception as e:
            logger.error(f"[TREND] Erro ao obter status de filtro: {e}")
        
        return status
    
    def detect_reversal(self, symbol: str, current_position_side: str) -> Tuple[bool, str]:
        """
        Detecta possível reversão de tendência.
        
        Args:
            symbol: Símbolo da posição
            current_position_side: 'BUY' (LONG) ou 'SELL' (SHORT)
        
        Returns:
            Tuple (is_reversing, reason)
        """
        try:
            analysis = self.analyze(symbol, check_overbought=False)
            
            is_long = current_position_side == 'BUY'
            
            # Se está LONG e tendência virou SHORT
            if is_long and analysis['direction'] == 'SHORT' and analysis['confidence'] >= 30:
                return True, f"Tendência reverteu para SHORT (score={analysis['score']:.1f})"
            
            # Se está SHORT e tendência virou LONG
            if not is_long and analysis['direction'] == 'LONG' and analysis['confidence'] >= 30:
                return True, f"Tendência reverteu para LONG (score={analysis['score']:.1f})"
            
            # RSI extremo oposto à posição
            if is_long and analysis['rsi'] >= 75:
                return True, f"RSI muito alto ({analysis['rsi']:.1f}) - possível topo"
            
            if not is_long and analysis['rsi'] <= 25:
                return True, f"RSI muito baixo ({analysis['rsi']:.1f}) - possível fundo"
            
            # Momentum oposto forte
            if is_long and analysis['momentum'] < -1:
                return True, f"Momentum negativo forte ({analysis['momentum']:.2f}%)"
            
            if not is_long and analysis['momentum'] > 1:
                return True, f"Momentum positivo forte ({analysis['momentum']:.2f}%)"
            
            # Bollinger extremo (V3)
            if is_long and analysis['bollinger_position'] == 'BELOW_LOWER':
                return True, "Preço rompeu Bollinger Inferior"
            
            if not is_long and analysis['bollinger_position'] == 'ABOVE_UPPER':
                return True, "Preço rompeu Bollinger Superior"
            
            return False, "Tendência ainda favorável"
            
        except Exception as e:
            logger.error(f"[TREND] Erro ao detectar reversão: {e}")
            return False, "Erro na análise"
    
    def get_blocked_entries(self) -> Dict[str, str]:
        """Retorna entradas bloqueadas pelo filtro de sobrecompra."""
        return self._blocked_entries.copy()
    
    def clear_blocked_entries(self):
        """Limpa lista de entradas bloqueadas."""
        self._blocked_entries.clear()
    
    def get_market_sentiment(self) -> Dict:
        """
        Analisa sentimento geral do mercado usando BTC.
        
        Returns:
            Dict com sentimento do mercado
        """
        btc_analysis = self.analyze('BTCUSDT', check_overbought=False)
        
        sentiment = {
            'direction': btc_analysis['direction'],
            'confidence': btc_analysis['confidence'],
            'rsi': btc_analysis['rsi'],
            'momentum': btc_analysis['momentum'],
            'bollinger_position': btc_analysis['bollinger_position'],
            'recommendation': 'NEUTRAL'
        }
        
        if btc_analysis['direction'] == 'LONG' and btc_analysis['confidence'] >= 40:
            sentiment['recommendation'] = 'FAVOR_LONG'
        elif btc_analysis['direction'] == 'SHORT' and btc_analysis['confidence'] >= 40:
            sentiment['recommendation'] = 'FAVOR_SHORT'
        else:
            sentiment['recommendation'] = 'MIXED'
        
        logger.info(
            f"[MARKET] Sentimento: {sentiment['direction']} "
            f"(conf={sentiment['confidence']}, BTC RSI={sentiment['rsi']:.1f}, "
            f"BB={sentiment['bollinger_position']})"
        )
        
        return sentiment
