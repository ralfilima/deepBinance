"""
Estratégia de Trading: Randomized Trend Scalping
"""
import random
import logging
from typing import Optional, List, Dict
from binance.client import Client
from indicators import calculate_ema, calculate_rsi
import config
from utils import retry_api_call

logger = logging.getLogger(__name__)


class RandomizedTrendScalp:
    """
    Estratégia de scalping baseada em tendência com elementos de aleatoriedade.
    
    A estratégia:
    1. Detecta tendência macro usando EMA200 do BTCUSDT
    2. Filtra símbolos elegíveis baseado em critérios técnicos
    3. Escolhe aleatoriamente entre os elegíveis (ponderado por volume)
    4. Adiciona jitter nos tempos para evitar detecção
    """
    
    def __init__(self, client: Client):
        """
        Inicializa a estratégia.
        
        Args:
            client: Cliente da Binance já autenticado
        """
        self.client = client
        self.base_symbol = config.BASE_SYMBOL
        self.symbols = config.SYMBOLS
        self._symbol_cache = {}
        
        logger.info(f"[STRATEGY] Inicializada com {len(self.symbols)} símbolos")
    
    def detect_trend(self) -> str:
        """
        Detecta tendência do mercado usando BTCUSDT como referência.
        
        Returns:
            'UP' para tendência de alta
            'DOWN' para tendência de baixa
            'NONE' para mercado lateral
        """
        if config.DEBUG_MODE:
            trend = random.choice(['UP', 'DOWN'])
            logger.info(f"[DEBUG] Tendência forçada = {trend}")
            return trend
        
        try:
            klines = retry_api_call(
                self.client.futures_klines,
                symbol=self.base_symbol,
                interval='15m',
                limit=250
            )
            
            closes = [float(k[4]) for k in klines]
            
            if len(closes) < 200:
                logger.warning(f"[STRATEGY] Dados insuficientes para EMA200 ({len(closes)} candles)")
                return 'NONE'
            
            ema200 = calculate_ema(closes, 200)
            current_price = closes[-1]
            
            # Buffer de 0.2% para evitar sinais falsos em zonas de transição
            buffer = 0.002
            
            if current_price > ema200 * (1 + buffer):
                logger.info(f"[TREND] {self.base_symbol}: ${current_price:.2f} > EMA200 ${ema200:.2f} → ALTA")
                return 'UP'
            elif current_price < ema200 * (1 - buffer):
                logger.info(f"[TREND] {self.base_symbol}: ${current_price:.2f} < EMA200 ${ema200:.2f} → BAIXA")
                return 'DOWN'
            else:
                logger.info(f"[TREND] {self.base_symbol}: ${current_price:.2f} ≈ EMA200 ${ema200:.2f} → LATERAL")
                return 'NONE'
        
        except Exception as e:
            logger.error(f"[STRATEGY] Erro ao detectar tendência: {e}")
            return 'NONE'
    
    def _get_symbol_data(self, symbol: str) -> Optional[Dict]:
        """
        Obtém dados de um símbolo para análise.
        
        Args:
            symbol: Símbolo a analisar
        
        Returns:
            Dict com dados do símbolo ou None se falhar
        """
        try:
            klines = retry_api_call(
                self.client.futures_klines,
                symbol=symbol,
                interval='15m',
                limit=250
            )
            
            ticker = retry_api_call(
                self.client.futures_ticker,
                symbol=symbol
            )
            
            closes = [float(k[4]) for k in klines]
            highs = [float(k[2]) for k in klines]
            lows = [float(k[3]) for k in klines]
            volumes = [float(k[5]) for k in klines]
            
            return {
                'symbol': symbol,
                'closes': closes,
                'highs': highs,
                'lows': lows,
                'volumes': volumes,
                'current_price': closes[-1],
                'open_price': float(klines[-1][1]),
                'bid': float(ticker['bidPrice']),
                'ask': float(ticker['askPrice']),
                'volume_24h': float(ticker['quoteVolume'])
            }
        
        except Exception as e:
            logger.debug(f"[STRATEGY] Erro ao obter dados de {symbol}: {e}")
            return None
    
    def _eligible_symbols(self, trend: str) -> List[Dict]:
        """
        Filtra símbolos elegíveis baseado na tendência e critérios técnicos.
        
        Args:
            trend: 'UP' ou 'DOWN'
        
        Returns:
            Lista de dicts com símbolos elegíveis e métricas
        """
        if config.DEBUG_MODE:
            return self._eligible_symbols_debug()
        
        eligible = []
        
        for symbol in self.symbols:
            data = self._get_symbol_data(symbol)
            
            if not data:
                continue
            
            try:
                closes = data['closes']
                highs = data['highs']
                lows = data['lows']
                volumes = data['volumes']
                
                # Calcula indicadores
                ema200 = calculate_ema(closes, 200)
                ema20 = calculate_ema(closes, 20)
                rsi = calculate_rsi(closes, 14)
                
                current_price = data['current_price']
                open_price = data['open_price']
                
                avg_volume = sum(volumes[-20:]) / 20
                current_volume = volumes[-1]
                
                # Spread
                bid, ask = data['bid'], data['ask']
                spread_percent = ((ask - bid) / bid) * 100 if bid > 0 else 999
                
                # Condições baseadas na tendência
                if trend == 'UP':
                    conditions = [
                        current_price > ema200,         # Acima da EMA200
                        lows[-1] < ema20,               # Tocou EMA20 (pullback)
                        closes[-1] > open_price,        # Candle de alta
                        current_volume > avg_volume * 0.8,  # Volume acima da média
                        55 <= rsi <= 70,                # RSI em zona de força
                        spread_percent < 0.15           # Spread aceitável
                    ]
                else:  # DOWN
                    conditions = [
                        current_price < ema200,         # Abaixo da EMA200
                        highs[-1] > ema20,              # Tocou EMA20 (pullback)
                        closes[-1] < open_price,        # Candle de baixa
                        current_volume > avg_volume * 0.8,  # Volume acima da média
                        30 <= rsi <= 45,                # RSI em zona de fraqueza
                        spread_percent < 0.15           # Spread aceitável
                    ]
                
                if all(conditions):
                    eligible.append({
                        'symbol': symbol,
                        'volume': data['volume_24h'],
                        'spread': spread_percent,
                        'price': current_price,
                        'rsi': rsi,
                        'ema200': ema200
                    })
                    logger.debug(
                        f"[ELIGIBLE] {symbol}: RSI={rsi:.1f}, "
                        f"Spread={spread_percent:.3f}%, Vol=${data['volume_24h']:,.0f}"
                    )
            
            except Exception as e:
                logger.debug(f"[STRATEGY] Erro ao processar {symbol}: {e}")
                continue
        
        logger.info(f"[STRATEGY] {len(eligible)}/{len(self.symbols)} símbolos elegíveis para {trend}")
        return eligible
    
    def _eligible_symbols_debug(self) -> List[Dict]:
        """
        Modo debug: retorna símbolos com filtro mínimo.
        """
        eligible = []
        
        for symbol in self.symbols:
            try:
                ticker = retry_api_call(
                    self.client.futures_ticker,
                    symbol=symbol
                )
                
                volume_24h = float(ticker['quoteVolume'])
                
                # Apenas filtro de volume mínimo
                if volume_24h > 10_000_000:  # Min 10M
                    eligible.append({
                        'symbol': symbol,
                        'volume': volume_24h,
                        'spread': 0.1,
                        'price': float(ticker['lastPrice'])
                    })
                    logger.debug(f"[DEBUG] {symbol} adicionado (Volume: ${volume_24h:,.0f})")
            
            except Exception as e:
                logger.debug(f"[DEBUG] Erro ao processar {symbol}: {e}")
                continue
        
        return eligible
    
    def pick_symbol(self, trend: str) -> Optional[str]:
        """
        Escolhe um símbolo aleatório entre os elegíveis.
        
        A escolha é ponderada por volume para favorecer pares mais líquidos.
        
        Args:
            trend: 'UP' ou 'DOWN'
        
        Returns:
            Símbolo escolhido ou None se nenhum elegível
        """
        eligible = self._eligible_symbols(trend)
        
        if not eligible:
            logger.info(f"[STRATEGY] Nenhum símbolo elegível para {trend}")
            return None
        
        # Sorteio ponderado por volume
        symbols = [e['symbol'] for e in eligible]
        weights = [e['volume'] for e in eligible]
        
        chosen = random.choices(symbols, weights=weights, k=1)[0]
        
        # Log com informações do escolhido
        chosen_data = next(e for e in eligible if e['symbol'] == chosen)
        logger.info(
            f"[PICK] Símbolo sorteado: {chosen} "
            f"(de {len(eligible)} elegíveis, Vol: ${chosen_data['volume']:,.0f})"
        )
        
        return chosen
    
    def get_trade_plan(self, symbol: str, trend: str) -> Optional[Dict]:
        """
        Cria plano de trade com entry, TP, SL e timing.
        
        Args:
            symbol: Símbolo para negociar
            trend: 'UP' ou 'DOWN'
        
        Returns:
            Dict com plano de trade ou None se falhar
        """
        try:
            ticker = retry_api_call(
                self.client.futures_ticker,
                symbol=symbol
            )
            
            entry_price = float(ticker['lastPrice'])
            
            # Jitter aleatório (0 a JITTER_MAX segundos)
            jitter = random.randint(0, config.JITTER_MAX_SECONDS)
            
            # Time stop aleatório (TIME_STOP_MIN a TIME_STOP_MAX minutos)
            time_stop = random.randint(config.TIME_STOP_MIN, config.TIME_STOP_MAX) * 60
            
            if trend == 'UP':
                side = 'BUY'
                tp_price = entry_price * (1 + config.TP_PERCENT_LONG / 100)
                sl_price = entry_price * (1 - config.SL_PERCENT_LONG / 100)
            else:  # DOWN
                side = 'SELL'
                tp_price = entry_price * (1 - config.TP_PERCENT_SHORT / 100)
                sl_price = entry_price * (1 + config.SL_PERCENT_SHORT / 100)
            
            plan = {
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'jitter': jitter,
                'time_stop': time_stop,
                'trend': trend
            }
            
            logger.info(
                f"[PLAN] {side} {symbol} @ ${entry_price:.4f} | "
                f"TP: ${tp_price:.4f} ({config.TP_PERCENT_LONG}%) | "
                f"SL: ${sl_price:.4f} ({config.SL_PERCENT_LONG}%) | "
                f"TimeStop: {time_stop//60}min | Jitter: {jitter}s"
            )
            
            return plan
        
        except Exception as e:
            logger.error(f"[STRATEGY] Erro ao criar plano de trade: {e}")
            return None
