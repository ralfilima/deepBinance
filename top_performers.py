"""
Módulo de Seleção Automática das Top Criptomoedas
COM FILTRO DE PERSISTÊNCIA (1 minuto)

Seleciona as melhores criptomoedas baseado em:
- Volume 24h (liquidez)
- Variação de preço (momentum)
- RSI (não sobrecomprado/sobrevendido)
- Volatilidade
- PERSISTÊNCIA: moeda deve estar no TOP por 1 minuto seguido
"""
import logging
import time
from typing import List, Dict, Optional, Callable
from binance.client import Client

logger = logging.getLogger(__name__)


class TopPerformersSelector:
    """
    Seleciona as top N criptomoedas com FILTRO DE PERSISTÊNCIA.
    
    A moeda precisa aparecer no TOP 10 por 2-3 verificações
    a cada 30 segundos (total 1 minuto) para ser selecionada.
    """
    
    # Pares a excluir (stablecoins, pares problemáticos)
    EXCLUDED_PAIRS = [
        'USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'EURUSDT', 'GBPUSDT',
        'AUDUSDT', 'JPYUSDT', 'BRLBUSD', 'USTUSDT', 'DAIUSDT',
        'FDUSDUSDT', 'USDPUSDT'
    ]
    
    # Volume mínimo em USDT (para garantir liquidez)
    MIN_VOLUME_24H = 50_000_000  # 50M USDT
    
    def __init__(self, client: Client, testnet: bool = True):
        """
        Inicializa o seletor.
        
        Args:
            client: Cliente Binance autenticado
            testnet: Se está em modo testnet
        """
        self.client = client
        self.testnet = testnet
    
    def get_all_usdt_pairs(self) -> List[str]:
        """Obtém lista de todos os pares USDT disponíveis."""
        try:
            info = self.client.futures_exchange_info()
            pairs = []
            
            for symbol in info['symbols']:
                if symbol['status'] == 'TRADING' and symbol['symbol'].endswith('USDT'):
                    sym = symbol['symbol']
                    if sym not in self.EXCLUDED_PAIRS:
                        pairs.append(sym)
            
            return pairs
            
        except Exception as e:
            logger.error(f"[TOP] Erro ao obter pares: {e}")
            return ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']
    
    def _get_top_100_by_volume(self) -> List[Dict]:
        """
        Obtém as TOP 100 moedas por volume 24h.
        
        Returns:
            Lista com top 100 moedas ordenadas por volume
        """
        try:
            tickers = self.client.futures_ticker()
            all_coins = []
            
            for ticker in tickers:
                sym = ticker['symbol']
                
                if not sym.endswith('USDT') or sym in self.EXCLUDED_PAIRS:
                    continue
                
                vol = float(ticker['quoteVolume'])
                price = float(ticker['lastPrice'])
                
                if vol > 0 and price > 0:  # Filtra moedas válidas
                    all_coins.append({
                        'symbol': sym,
                        'volume_24h': vol,
                        'last_price': price,
                        'price_change_pct': float(ticker['priceChangePercent']),
                        'high_price': float(ticker['highPrice']),
                        'low_price': float(ticker['lowPrice'])
                    })
            
            # Ordena por volume (maior para menor)
            all_coins.sort(key=lambda x: x['volume_24h'], reverse=True)
            
            # Retorna apenas TOP 100
            top_100 = all_coins[:100]
            
            logger.info(f"[TOP] Total de moedas: {len(all_coins)}, filtradas para TOP 100 por volume")
            
            return top_100
            
        except Exception as e:
            logger.error(f"[TOP] Erro ao obter TOP 100: {e}")
            return []
    
    def _get_top_10_quick(self) -> List[Dict]:
        """
        Obtém TOP 10 rápido usando apenas ticker (sem RSI).
        Usado para verificações de persistência.
        TRABALHA APENAS COM AS TOP 100 POR VOLUME.
        
        Returns:
            Lista com top 10 moedas
        """
        try:
            # Primeiro: obter TOP 100 por volume
            top_100 = self._get_top_100_by_volume()
            
            if not top_100:
                logger.warning("[TOP] TOP 100 vazia, usando fallback")
                return []
            
            logger.info(f"[TOP] Analisando dentre as TOP 100 moedas por volume")
            
            analyzed = []
            
            for coin in top_100:
                sym = coin['symbol']
                vol = coin['volume_24h']
                
                # Aplica filtro de volume mínimo
                if vol < self.MIN_VOLUME_24H:
                    continue
                
                pct = coin['price_change_pct']
                price = coin['last_price']
                high = coin['high_price']
                low = coin['low_price']
                
                volatility = ((high - low) / price) * 100 if price > 0 else 0
                
                # Score simplificado para ranking rápido
                score = 0
                
                # Volume score
                if vol >= 300_000_000:
                    score += 30
                elif vol >= 150_000_000:
                    score += 25
                elif vol >= 100_000_000:
                    score += 20
                else:
                    score += 10
                
                # Momentum score
                abs_pct = abs(pct)
                if 1 <= abs_pct <= 6:
                    score += 40
                elif 0.5 <= abs_pct <= 10:
                    score += 25
                else:
                    score += 10
                
                # Volatilidade score
                if 2 <= volatility <= 7:
                    score += 30
                elif 1 <= volatility <= 10:
                    score += 20
                else:
                    score += 10
                
                analyzed.append({
                    'symbol': sym,
                    'score': score,
                    'volume_24h': vol,
                    'price_change_pct': pct,
                    'last_price': price,
                    'volatility': volatility
                })
            
            # Ordena por score
            analyzed.sort(key=lambda x: x['score'], reverse=True)
            
            return analyzed[:10]
            
        except Exception as e:
            logger.error(f"[TOP] Erro na seleção rápida: {e}")
            return []
    
    def _calculate_rsi(self, symbol: str, period: int = 14) -> Optional[float]:
        """Calcula RSI de um símbolo."""
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval='1h',
                limit=period + 5
            )
            
            closes = [float(k[4]) for k in klines]
            
            if len(closes) < period + 1:
                return None
            
            changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            
            gains = [max(c, 0) for c in changes]
            losses = [abs(min(c, 0)) for c in changes]
            
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period if losses else 0.0001
            
            if avg_loss == 0:
                avg_loss = 0.0001
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.debug(f"[TOP] Erro ao calcular RSI de {symbol}: {e}")
            return None
    
    def select_with_persistence(
        self, 
        n: int = 5, 
        checks: int = 3, 
        interval_seconds: int = 30,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Seleciona TOP N com filtro de persistência.
        
        A moeda precisa aparecer no TOP 10 em TODAS as verificações
        para ser considerada consistente.
        
        Args:
            n: Número de criptos a selecionar
            checks: Número de verificações (2-3 recomendado)
            interval_seconds: Intervalo entre verificações
            progress_callback: Função para callback de progresso
        
        Returns:
            Lista com as N criptos mais persistentes
        """
        logger.info(f"[TOP] Iniciando seleção com persistência ({checks} checks, {interval_seconds}s)")
        
        # Armazena resultados de cada verificação
        all_checks = []
        
        for check_num in range(1, checks + 1):
            logger.info(f"[TOP] Verificação {check_num}/{checks}...")
            
            top_10 = self._get_top_10_quick()
            symbols_this_check = [c['symbol'] for c in top_10]
            
            all_checks.append({
                'check_num': check_num,
                'symbols': symbols_this_check,
                'data': {c['symbol']: c for c in top_10}
            })
            
            # Log visual
            top_5_str = ", ".join(symbols_this_check[:5])
            logger.info(f"[TOP] Check #{check_num} TOP 5: {top_5_str}")
            
            # Callback de progresso
            if progress_callback:
                progress_callback(check_num, checks, symbols_this_check[:5])
            
            # Aguarda entre verificações (exceto última)
            if check_num < checks:
                logger.info(f"[TOP] Aguardando {interval_seconds}s...")
                time.sleep(interval_seconds)
        
        # ============================================================
        # FILTRA MOEDAS PERSISTENTES
        # ============================================================
        # Moedas que aparecem em TODAS as verificações
        
        if not all_checks:
            logger.error("[TOP] Nenhuma verificação completada")
            return []
        
        # Começamos com as moedas da primeira verificação
        persistent_symbols = set(all_checks[0]['symbols'])
        
        # Intersecção com todas as outras verificações
        for check in all_checks[1:]:
            persistent_symbols = persistent_symbols.intersection(set(check['symbols']))
        
        logger.info(f"[TOP] Moedas persistentes: {len(persistent_symbols)}")
        
        if not persistent_symbols:
            logger.warning("[TOP] Nenhuma moeda passou no filtro de persistência!")
            # Fallback: usa a última verificação
            return all_checks[-1]['data'][:n] if all_checks else []
        
        # ============================================================
        # ENRIQUECE DADOS E CALCULA SCORE FINAL
        # ============================================================
        
        final_selection = []
        last_check_data = all_checks[-1]['data']
        
        for symbol in persistent_symbols:
            if symbol not in last_check_data:
                continue
            
            data = last_check_data[symbol].copy()
            
            # Calcula RSI
            rsi = self._calculate_rsi(symbol)
            data['rsi'] = rsi if rsi else 50
            
            # Score final com RSI
            base_score = data['score']
            
            # Bonus/penalidade por RSI
            if rsi:
                if 40 <= rsi <= 60:
                    base_score += 15  # RSI neutro: ideal
                elif 30 <= rsi <= 70:
                    base_score += 10  # RSI aceitável
                else:
                    base_score -= 10  # RSI extremo
            
            data['score'] = base_score
            data['persistent'] = True
            
            final_selection.append(data)
        
        # Ordena por score final
        final_selection.sort(key=lambda x: x['score'], reverse=True)
        
        # Seleciona top N
        result = final_selection[:n]
        
        # Log das selecionadas
        logger.info(f"\n{'='*60}")
        logger.info(f"[TOP] SELEÇÃO FINAL (com persistência 1 min)")
        logger.info(f"{'='*60}")
        
        for i, crypto in enumerate(result, 1):
            logger.info(
                f"[TOP] #{i} {crypto['symbol']}: Score={crypto['score']:.0f}, "
                f"Var={crypto['price_change_pct']:+.2f}%, "
                f"RSI={crypto['rsi']:.1f}, "
                f"Vol=${crypto['volume_24h']/1e6:.1f}M"
            )
        
        return result
    
    def select_top_n(self, n: int = 5, direction: str = 'any') -> List[Dict]:
        """
        Seleção padrão SEM persistência (para compatibilidade).
        
        Args:
            n: Número de criptos a selecionar
            direction: 'long', 'short', ou 'any'
        
        Returns:
            Lista com as top N criptos
        """
        top_10 = self._get_top_10_quick()
        
        result = []
        for crypto in top_10:
            # Filtro de direção
            if direction == 'long' and crypto['price_change_pct'] < 0:
                continue
            if direction == 'short' and crypto['price_change_pct'] > 0:
                continue
            
            # Calcula RSI
            rsi = self._calculate_rsi(crypto['symbol'])
            crypto['rsi'] = rsi if rsi else 50
            
            result.append(crypto)
            
            if len(result) >= n:
                break
        
        return result


def format_selection_table(selection: List[Dict], with_direction: bool = False) -> str:
    """
    Formata a seleção em uma tabela para exibição.
    
    Args:
        selection: Lista de criptos selecionadas
        with_direction: Se deve incluir direção LONG/SHORT
    
    Returns:
        String formatada
    """
    lines = []
    lines.append("")
    lines.append("╔" + "═"*68 + "╗")
    lines.append("║" + " TOP CRIPTOMOEDAS SELECIONADAS ".center(68) + "║")
    lines.append("╠" + "═"*68 + "╣")
    
    if with_direction:
        header = f"║ {'#':>2} │ {'SÍMBOLO':<12} │ {'DIR':^6} │ {'SCORE':>5} │ {'VOL 24H':>12} │ {'VAR%':>7} │ {'RSI':>5} ║"
    else:
        header = f"║ {'#':>2} │ {'SÍMBOLO':<12} │ {'SCORE':>6} │ {'VOL 24H':>14} │ {'VAR%':>8} │ {'RSI':>6} ║"
    
    lines.append(header)
    lines.append("╟" + "─"*68 + "╢")
    
    for i, c in enumerate(selection, 1):
        vol_str = f"${c['volume_24h']/1e6:.1f}M"
        rsi_val = c.get('rsi', 50)
        
        if with_direction:
            direction = c.get('direction', 'N/A')
            line = f"║ {i:>2} │ {c['symbol']:<12} │ {direction:^6} │ {c['score']:>5.0f} │ {vol_str:>12} │ {c['price_change_pct']:>+6.2f}% │ {rsi_val:>5.1f} ║"
        else:
            line = f"║ {i:>2} │ {c['symbol']:<12} │ {c['score']:>6.0f} │ {vol_str:>14} │ {c['price_change_pct']:>+7.2f}% │ {rsi_val:>6.1f} ║"
        
        lines.append(line)
    
    lines.append("╚" + "═"*68 + "╝")
    
    return "\n".join(lines)
