"""
Sistema de BACKTEST para o Bot Multi-Crypto
============================================
Simula a estratégia completa com dados históricos da Binance.

Características:
- Download de dados históricos (klines)
- Simulação do filtro de persistência
- Simulação de análise LONG/SHORT
- Simulação de abertura e fechamento de posições
- Resultados detalhados e estatísticas
- Interface interativa com cores no terminal
"""
import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json

# Cores ANSI para terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'
    
    @staticmethod
    def success(text): return f"{Colors.GREEN}{text}{Colors.END}"
    @staticmethod
    def error(text): return f"{Colors.RED}{text}{Colors.END}"
    @staticmethod
    def warning(text): return f"{Colors.YELLOW}{text}{Colors.END}"
    @staticmethod
    def info(text): return f"{Colors.CYAN}{text}{Colors.END}"
    @staticmethod
    def bold(text): return f"{Colors.BOLD}{text}{Colors.END}"
    @staticmethod
    def header(text): return f"{Colors.HEADER}{Colors.BOLD}{text}{Colors.END}"


@dataclass
class BacktestTrade:
    """Representa um trade no backtest"""
    symbol: str
    direction: str  # 'LONG' ou 'SHORT'
    entry_price: float
    entry_time: datetime
    exit_price: float = 0.0
    exit_time: Optional[datetime] = None
    quantity: float = 0.0
    capital_used: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    exit_reason: str = ""  # 'TP', 'SL', 'REVERSAL', 'TIMEOUT'
    closed: bool = False
    
    def close(self, exit_price: float, exit_time: datetime, reason: str):
        """Fecha o trade"""
        self.exit_price = exit_price
        self.exit_time = exit_time
        self.exit_reason = reason
        self.closed = True
        
        if self.direction == 'LONG':
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity
        
        self.pnl_percent = (self.pnl / self.capital_used) * 100 if self.capital_used > 0 else 0


@dataclass
class BacktestResult:
    """Resultado do backtest"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_percent: float = 0.0
    avg_pnl_per_trade: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    final_capital: float = 0.0
    roi_percent: float = 0.0
    trades: List[BacktestTrade] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)


class BacktestEngine:
    """
    Motor de Backtest para simular a estratégia Multi-Crypto
    """
    
    def __init__(self, client):
        """
        Inicializa o engine de backtest.
        
        Args:
            client: Cliente Binance autenticado
        """
        self.client = client
        self.historical_data: Dict[str, List[Dict]] = {}
        self.logger = logging.getLogger(__name__)
        
    def download_historical_data(
        self, 
        symbols: List[str], 
        start_date: datetime, 
        end_date: datetime,
        interval: str = '1m',
        progress_callback: Optional[callable] = None
    ) -> Dict[str, List[Dict]]:
        """
        Baixa dados históricos da Binance.
        
        Args:
            symbols: Lista de símbolos
            start_date: Data de início
            end_date: Data de fim
            interval: Timeframe dos candles
            progress_callback: Função para reportar progresso
        
        Returns:
            Dicionário com dados por símbolo
        """
        data = {}
        total = len(symbols)
        
        print(f"\n{Colors.info('📥 Baixando dados históricos...')}")
        print(f"   Símbolos: {total}")
        print(f"   Período: {start_date.strftime('%Y-%m-%d')} até {end_date.strftime('%Y-%m-%d')}")
        print(f"   Timeframe: {interval}")
        print()
        
        for i, symbol in enumerate(symbols):
            try:
                progress = (i + 1) / total * 100
                print(f"\r   [{i+1}/{total}] {symbol.ljust(12)} {'█' * int(progress/5)}{'░' * (20 - int(progress/5))} {progress:.1f}%", end='', flush=True)
                
                klines = self._fetch_klines(symbol, interval, start_date, end_date)
                
                if klines:
                    data[symbol] = klines
                    
                if progress_callback:
                    progress_callback(i + 1, total, symbol)
                    
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.warning(f"Erro ao baixar {symbol}: {e}")
                continue
        
        print(f"\n\n{Colors.success('✅ Download concluído!')} {len(data)} símbolos carregados")
        self.historical_data = data
        return data
    
    def _fetch_klines(
        self, 
        symbol: str, 
        interval: str, 
        start_date: datetime, 
        end_date: datetime
    ) -> List[Dict]:
        """
        Busca klines para um símbolo específico.
        """
        all_klines = []
        current_start = start_date
        
        while current_start < end_date:
            try:
                klines = self.client.futures_klines(
                    symbol=symbol,
                    interval=interval,
                    startTime=int(current_start.timestamp() * 1000),
                    endTime=int(end_date.timestamp() * 1000),
                    limit=1500
                )
                
                if not klines:
                    break
                
                for k in klines:
                    all_klines.append({
                        'timestamp': datetime.fromtimestamp(k[0] / 1000),
                        'open': float(k[1]),
                        'high': float(k[2]),
                        'low': float(k[3]),
                        'close': float(k[4]),
                        'volume': float(k[5]),
                        'quote_volume': float(k[7])
                    })
                
                # Atualiza para próxima página
                last_ts = klines[-1][0]
                current_start = datetime.fromtimestamp(last_ts / 1000) + timedelta(milliseconds=1)
                
                if len(klines) < 1500:
                    break
                    
            except Exception as e:
                self.logger.warning(f"Erro ao buscar klines de {symbol}: {e}")
                break
        
        return all_klines
    
    def calculate_ema(self, prices: List[float], period: int) -> List[float]:
        """Calcula EMA para série de preços"""
        if len(prices) < period:
            return [prices[-1]] * len(prices) if prices else []
        
        emas = []
        multiplier = 2 / (period + 1)
        
        # SMA inicial
        sma = sum(prices[:period]) / period
        emas = [None] * (period - 1)  # Preenche com None os primeiros valores
        emas.append(sma)
        
        for price in prices[period:]:
            ema = (price - emas[-1]) * multiplier + emas[-1]
            emas.append(ema)
        
        return emas
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calcula RSI para série de preços"""
        if len(prices) < period + 1:
            return [50] * len(prices)
        
        rsi_values = [50] * period
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))
        
        # Primeiro RSI com SMA
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        
        for i in range(period, len(gains)):
            if avg_loss == 0:
                rsi_values.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
            
            # Update with Wilder's smoothing
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
        return rsi_values
    
    def analyze_trend(self, klines: List[Dict], index: int) -> Tuple[str, float]:
        """
        Analisa tendência para um ponto específico nos dados.
        
        Returns:
            (direção, score) - 'LONG', 'SHORT' ou 'NEUTRAL'
        """
        if index < 30:  # Precisa de dados suficientes
            return 'NEUTRAL', 0
        
        # Pega últimos 30 candles até o índice atual
        window = klines[max(0, index-30):index+1]
        closes = [k['close'] for k in window]
        
        # EMA 9 e 21
        ema9 = self.calculate_ema(closes, 9)[-1] if len(closes) >= 9 else closes[-1]
        ema21 = self.calculate_ema(closes, 21)[-1] if len(closes) >= 21 else closes[-1]
        
        # RSI
        rsi_values = self.calculate_rsi(closes)
        rsi = rsi_values[-1] if rsi_values else 50
        
        # Momentum (últimos 5 candles)
        momentum = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if len(closes) >= 5 else 0
        
        # Pontuação
        score = 0
        
        # EMA crossover
        if ema9 > ema21:
            score += 2
        else:
            score -= 2
        
        # RSI
        if rsi > 50:
            score += 1
        else:
            score -= 1
        
        if rsi > 70:
            score -= 1  # Sobrecomprado, cuidado com LONG
        elif rsi < 30:
            score += 1  # Sobrevendido, cuidado com SHORT
        
        # Momentum
        if momentum > 0.1:
            score += 1
        elif momentum < -0.1:
            score -= 1
        
        # Determina direção
        if score >= 2:
            return 'LONG', score
        elif score <= -2:
            return 'SHORT', abs(score)
        else:
            return 'NEUTRAL', abs(score)
    
    def get_top_coins_at_time(
        self, 
        timestamp: datetime, 
        top_n: int = 10
    ) -> List[Dict]:
        """
        Simula seleção das top moedas em um momento específico.
        
        Usa volume recente como critério principal.
        """
        candidates = []
        
        for symbol, klines in self.historical_data.items():
            # Encontra o índice mais próximo do timestamp
            idx = None
            for i, k in enumerate(klines):
                if k['timestamp'] <= timestamp:
                    idx = i
                else:
                    break
            
            if idx is None or idx < 10:
                continue
            
            # Calcula volume das últimas 10 velas
            recent_klines = klines[max(0, idx-10):idx+1]
            total_volume = sum(k['quote_volume'] for k in recent_klines)
            
            # Variação de preço
            if len(recent_klines) >= 2:
                price_change = ((recent_klines[-1]['close'] - recent_klines[0]['close']) 
                               / recent_klines[0]['close']) * 100
            else:
                price_change = 0
            
            candidates.append({
                'symbol': symbol,
                'volume': total_volume,
                'price_change': price_change,
                'last_price': recent_klines[-1]['close'],
                'index': idx
            })
        
        # Ordena por volume
        candidates.sort(key=lambda x: x['volume'], reverse=True)
        
        return candidates[:top_n]
    
    def run_backtest(
        self,
        initial_capital: float = 2500.0,
        position_size: float = 500.0,
        num_positions: int = 5,
        tp_percent: float = 0.5,
        sl_percent: float = 0.4,
        persistence_minutes: int = 1,
        verbose: bool = True
    ) -> BacktestResult:
        """
        Executa o backtest completo.
        
        Args:
            initial_capital: Capital inicial ($)
            position_size: Valor por posição ($)
            num_positions: Número de posições simultâneas
            tp_percent: Take Profit (%)
            sl_percent: Stop Loss (%)
            persistence_minutes: Tempo de persistência no top (minutos)
            verbose: Mostrar detalhes
        
        Returns:
            BacktestResult com todos os resultados
        """
        if not self.historical_data:
            print(Colors.error("❌ Erro: Nenhum dado histórico carregado!"))
            return BacktestResult()
        
        # Configuração inicial
        result = BacktestResult()
        capital = initial_capital
        equity_peak = initial_capital
        max_drawdown = 0
        
        active_positions: List[BacktestTrade] = []
        all_trades: List[BacktestTrade] = []
        equity_curve = [(None, initial_capital)]
        
        # Determina período do backtest
        all_timestamps = []
        for symbol, klines in self.historical_data.items():
            for k in klines:
                all_timestamps.append(k['timestamp'])
        
        all_timestamps = sorted(set(all_timestamps))
        
        if len(all_timestamps) < 100:
            print(Colors.error("❌ Erro: Dados insuficientes para backtest!"))
            return BacktestResult()
        
        # Valores de TP/SL absolutos
        total_position_value = position_size * num_positions
        tp_value = total_position_value * (tp_percent / 100)
        sl_value = total_position_value * (sl_percent / 100)
        
        print(f"\n{Colors.header('═' * 60)}")
        print(f"{Colors.header('              🔬 INICIANDO BACKTEST')}")
        print(f"{Colors.header('═' * 60)}")
        print(f"\n{Colors.bold('Configuração:')}")
        print(f"   Capital inicial: ${initial_capital:,.2f}")
        print(f"   Posição por trade: ${position_size:,.2f}")
        print(f"   Posições simultâneas: {num_positions}")
        print(f"   Take Profit: {tp_percent}% (${tp_value:.2f})")
        print(f"   Stop Loss: {sl_percent}% (${sl_value:.2f})")
        print(f"   Período: {all_timestamps[0].strftime('%Y-%m-%d')} até {all_timestamps[-1].strftime('%Y-%m-%d')}")
        print(f"   Total de candles: {len(all_timestamps):,}")
        print()
        
        # Filtro de persistência
        persistence_count = {}  # symbol -> contagem consecutiva no top
        persistence_threshold = max(1, persistence_minutes)
        
        # Loop principal
        total_candles = len(all_timestamps)
        last_progress = 0
        entry_count_today = 0
        last_entry_date = None
        
        for i, current_time in enumerate(all_timestamps):
            # Progresso
            progress = int((i + 1) / total_candles * 100)
            if progress > last_progress and progress % 5 == 0:
                bar = '█' * (progress // 5) + '░' * (20 - progress // 5)
                print(f"\r   ⏳ Processando: [{bar}] {progress}% | Trades: {len(all_trades)} | Capital: ${capital:,.2f}", end='', flush=True)
                last_progress = progress
            
            # Reset diário
            current_date = current_time.date()
            if last_entry_date != current_date:
                entry_count_today = 0
                last_entry_date = current_date
            
            # 1. MONITORAR POSIÇÕES ABERTAS
            if active_positions:
                total_pnl = 0
                positions_to_close = []
                
                for pos in active_positions:
                    # Obtém preço atual
                    if pos.symbol in self.historical_data:
                        klines = self.historical_data[pos.symbol]
                        current_price = None
                        
                        for k in klines:
                            if k['timestamp'] <= current_time:
                                current_price = k['close']
                            else:
                                break
                        
                        if current_price:
                            # Calcula P&L
                            if pos.direction == 'LONG':
                                pos.pnl = (current_price - pos.entry_price) * pos.quantity
                            else:
                                pos.pnl = (pos.entry_price - current_price) * pos.quantity
                            
                            total_pnl += pos.pnl
                
                # Verifica TP/SL global
                if total_pnl >= tp_value:
                    # TAKE PROFIT
                    for pos in active_positions:
                        if pos.symbol in self.historical_data:
                            klines = self.historical_data[pos.symbol]
                            exit_price = None
                            for k in klines:
                                if k['timestamp'] <= current_time:
                                    exit_price = k['close']
                                else:
                                    break
                            if exit_price:
                                pos.close(exit_price, current_time, 'TP')
                                all_trades.append(pos)
                    
                    capital += total_pnl
                    if verbose and len(all_trades) % 10 == 0:
                        pass  # Log a cada 10 trades
                    
                    active_positions = []
                    
                elif total_pnl <= -sl_value:
                    # STOP LOSS
                    for pos in active_positions:
                        if pos.symbol in self.historical_data:
                            klines = self.historical_data[pos.symbol]
                            exit_price = None
                            for k in klines:
                                if k['timestamp'] <= current_time:
                                    exit_price = k['close']
                                else:
                                    break
                            if exit_price:
                                pos.close(exit_price, current_time, 'SL')
                                all_trades.append(pos)
                    
                    capital += total_pnl
                    active_positions = []
                
                # Verifica reversão de tendência
                else:
                    for pos in list(active_positions):
                        if pos.symbol in self.historical_data:
                            klines = self.historical_data[pos.symbol]
                            # Encontra índice atual
                            idx = None
                            for j, k in enumerate(klines):
                                if k['timestamp'] <= current_time:
                                    idx = j
                                else:
                                    break
                            
                            if idx and idx > 30:
                                direction, score = self.analyze_trend(klines, idx)
                                
                                # Detecta reversão
                                if (pos.direction == 'LONG' and direction == 'SHORT') or \
                                   (pos.direction == 'SHORT' and direction == 'LONG'):
                                    exit_price = klines[idx]['close']
                                    pos.close(exit_price, current_time, 'REVERSAL')
                                    all_trades.append(pos)
                                    capital += pos.pnl
                                    active_positions.remove(pos)
            
            # 2. ABRIR NOVAS POSIÇÕES
            if len(active_positions) == 0 and entry_count_today < 5:
                # Seleciona top moedas
                top_coins = self.get_top_coins_at_time(current_time, top_n=10)
                
                # Atualiza persistência
                current_top_symbols = set(c['symbol'] for c in top_coins)
                
                # Incrementa contagem para moedas no top
                for symbol in current_top_symbols:
                    persistence_count[symbol] = persistence_count.get(symbol, 0) + 1
                
                # Reseta moedas que saíram do top
                for symbol in list(persistence_count.keys()):
                    if symbol not in current_top_symbols:
                        persistence_count[symbol] = 0
                
                # Seleciona moedas com persistência suficiente
                eligible_coins = [
                    c for c in top_coins 
                    if persistence_count.get(c['symbol'], 0) >= persistence_threshold
                ]
                
                if len(eligible_coins) >= num_positions:
                    # Analisa tendência e abre posições
                    selected = eligible_coins[:num_positions]
                    new_positions = []
                    
                    for coin in selected:
                        symbol = coin['symbol']
                        if symbol in self.historical_data:
                            klines = self.historical_data[symbol]
                            idx = coin['index']
                            
                            direction, score = self.analyze_trend(klines, idx)
                            
                            if direction != 'NEUTRAL':
                                entry_price = klines[idx]['close']
                                quantity = position_size / entry_price
                                
                                trade = BacktestTrade(
                                    symbol=symbol,
                                    direction=direction,
                                    entry_price=entry_price,
                                    entry_time=current_time,
                                    quantity=quantity,
                                    capital_used=position_size
                                )
                                new_positions.append(trade)
                    
                    if len(new_positions) >= num_positions:
                        active_positions = new_positions[:num_positions]
                        entry_count_today += 1
                        
                        # Reset persistência após entrada
                        for pos in active_positions:
                            persistence_count[pos.symbol] = 0
            
            # Atualiza equity curve
            current_equity = capital
            if active_positions:
                for pos in active_positions:
                    current_equity += pos.pnl
            
            if i % 60 == 0:  # A cada 60 candles
                equity_curve.append((current_time, current_equity))
            
            # Calcula drawdown
            if current_equity > equity_peak:
                equity_peak = current_equity
            
            dd = equity_peak - current_equity
            if dd > max_drawdown:
                max_drawdown = dd
        
        # Fecha posições restantes no final
        for pos in active_positions:
            if pos.symbol in self.historical_data:
                klines = self.historical_data[pos.symbol]
                exit_price = klines[-1]['close']
                pos.close(exit_price, all_timestamps[-1], 'END')
                all_trades.append(pos)
                capital += pos.pnl
        
        print(f"\n\n{Colors.success('✅ Backtest concluído!')}")
        
        # Calcula estatísticas
        result.total_trades = len(all_trades)
        result.winning_trades = sum(1 for t in all_trades if t.pnl > 0)
        result.losing_trades = sum(1 for t in all_trades if t.pnl < 0)
        result.win_rate = (result.winning_trades / result.total_trades * 100) if result.total_trades > 0 else 0
        
        result.gross_profit = sum(t.pnl for t in all_trades if t.pnl > 0)
        result.gross_loss = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
        result.total_pnl = result.gross_profit - result.gross_loss
        
        result.profit_factor = (result.gross_profit / result.gross_loss) if result.gross_loss > 0 else float('inf')
        result.max_drawdown = max_drawdown
        result.max_drawdown_percent = (max_drawdown / initial_capital * 100) if initial_capital > 0 else 0
        
        result.avg_pnl_per_trade = (result.total_pnl / result.total_trades) if result.total_trades > 0 else 0
        result.avg_win = (result.gross_profit / result.winning_trades) if result.winning_trades > 0 else 0
        result.avg_loss = (result.gross_loss / result.losing_trades) if result.losing_trades > 0 else 0
        
        result.best_trade = max((t.pnl for t in all_trades), default=0)
        result.worst_trade = min((t.pnl for t in all_trades), default=0)
        
        result.final_capital = capital
        result.roi_percent = ((capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
        
        result.trades = all_trades
        result.equity_curve = equity_curve
        
        return result
    
    def print_results(self, result: BacktestResult, initial_capital: float):
        """Imprime resultados formatados"""
        
        print(f"\n{Colors.header('═' * 60)}")
        print(f"{Colors.header('              📊 RESULTADOS DO BACKTEST')}")
        print(f"{Colors.header('═' * 60)}")
        
        # Resumo geral
        print(f"\n{Colors.bold('📈 RESUMO GERAL')}")
        print(f"   {'─' * 40}")
        
        pnl_color = Colors.success if result.total_pnl >= 0 else Colors.error
        roi_color = Colors.success if result.roi_percent >= 0 else Colors.error
        
        print(f"   Capital Inicial:     ${initial_capital:>12,.2f}")
        print(f"   Capital Final:       ${pnl_color(f'{result.final_capital:>12,.2f}')}")
        print(f"   Lucro/Prejuízo:      ${pnl_color(f'{result.total_pnl:>+12,.2f}')}")
        print(f"   ROI:                  {roi_color(f'{result.roi_percent:>+11.2f}%')}")
        
        # Estatísticas de trades
        print(f"\n{Colors.bold('🎯 ESTATÍSTICAS DE TRADES')}")
        print(f"   {'─' * 40}")
        print(f"   Total de Trades:     {result.total_trades:>12}")
        print(f"   Trades Vencedores:   {Colors.success(f'{result.winning_trades:>12}')}")
        print(f"   Trades Perdedores:   {Colors.error(f'{result.losing_trades:>12}')}")
        
        wr_color = Colors.success if result.win_rate >= 50 else Colors.warning if result.win_rate >= 40 else Colors.error
        print(f"   Win Rate:            {wr_color(f'{result.win_rate:>11.2f}%')}")
        
        # Valores médios
        print(f"\n{Colors.bold('💰 VALORES')}")
        print(f"   {'─' * 40}")
        print(f"   Lucro Bruto:         ${Colors.success(f'{result.gross_profit:>12,.2f}')}")
        print(f"   Prejuízo Bruto:      ${Colors.error(f'{result.gross_loss:>12,.2f}')}")
        
        pf_color = Colors.success if result.profit_factor >= 1.5 else Colors.warning if result.profit_factor >= 1 else Colors.error
        print(f"   Profit Factor:        {pf_color(f'{result.profit_factor:>12.2f}')}")
        
        print(f"\n   Média por Trade:     ${result.avg_pnl_per_trade:>+12.2f}")
        print(f"   Média Vitória:       ${Colors.success(f'{result.avg_win:>12,.2f}')}")
        print(f"   Média Derrota:       ${Colors.error(f'{result.avg_loss:>12,.2f}')}")
        print(f"   Melhor Trade:        ${Colors.success(f'{result.best_trade:>+12,.2f}')}")
        print(f"   Pior Trade:          ${Colors.error(f'{result.worst_trade:>+12,.2f}')}")
        
        # Risco
        print(f"\n{Colors.bold('⚠️  RISCO')}")
        print(f"   {'─' * 40}")
        dd_color = Colors.success if result.max_drawdown_percent < 10 else Colors.warning if result.max_drawdown_percent < 20 else Colors.error
        print(f"   Drawdown Máximo:     ${dd_color(f'{result.max_drawdown:>12,.2f}')}")
        print(f"   Drawdown Máximo %:    {dd_color(f'{result.max_drawdown_percent:>11.2f}%')}")
        
        # Motivos de saída
        print(f"\n{Colors.bold('🚪 MOTIVOS DE SAÍDA')}")
        print(f"   {'─' * 40}")
        exit_reasons = defaultdict(int)
        for t in result.trades:
            exit_reasons[t.exit_reason] += 1
        
        reason_names = {'TP': 'Take Profit', 'SL': 'Stop Loss', 'REVERSAL': 'Reversão', 'END': 'Fim do Backtest', 'TIMEOUT': 'Timeout'}
        for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
            pct = count / result.total_trades * 100 if result.total_trades > 0 else 0
            print(f"   {reason_names.get(reason, reason):20} {count:>5} ({pct:>5.1f}%)")
        
        print(f"\n{Colors.header('═' * 60)}")
    
    def print_trade_list(self, result: BacktestResult, limit: int = 20):
        """Imprime lista dos últimos trades"""
        
        print(f"\n{Colors.bold('📋 ÚLTIMOS {min(limit, len(result.trades))} TRADES')}")
        print(f"   {'─' * 85}")
        print(f"   {'#':>4} {'Símbolo':<12} {'Direção':<6} {'Entrada':>10} {'Saída':>10} {'P&L':>12} {'Motivo':<10}")
        print(f"   {'─' * 85}")
        
        for i, trade in enumerate(result.trades[-limit:], 1):
            pnl_color = Colors.success if trade.pnl >= 0 else Colors.error
            dir_color = Colors.info if trade.direction == 'LONG' else Colors.warning
            
            print(f"   {i:>4} {trade.symbol:<12} {dir_color(trade.direction):<6} "
                  f"${trade.entry_price:>9.4f} ${trade.exit_price:>9.4f} "
                  f"{pnl_color(f'${trade.pnl:>+10.2f}')} {trade.exit_reason:<10}")
        
        print(f"   {'─' * 85}")
    
    def save_results_to_file(self, result: BacktestResult, filepath: str):
        """Salva resultados em arquivo JSON"""
        data = {
            'summary': {
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'win_rate': result.win_rate,
                'total_pnl': result.total_pnl,
                'roi_percent': result.roi_percent,
                'profit_factor': result.profit_factor,
                'max_drawdown': result.max_drawdown,
                'max_drawdown_percent': result.max_drawdown_percent,
                'avg_pnl_per_trade': result.avg_pnl_per_trade,
                'best_trade': result.best_trade,
                'worst_trade': result.worst_trade,
                'final_capital': result.final_capital
            },
            'trades': [
                {
                    'symbol': t.symbol,
                    'direction': t.direction,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'entry_time': t.entry_time.isoformat() if t.entry_time else None,
                    'exit_time': t.exit_time.isoformat() if t.exit_time else None,
                    'pnl': t.pnl,
                    'pnl_percent': t.pnl_percent,
                    'exit_reason': t.exit_reason
                }
                for t in result.trades
            ]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n{Colors.success(f'💾 Resultados salvos em: {filepath}')}")


def get_top_100_symbols(client) -> List[str]:
    """Obtém TOP 100 símbolos por volume"""
    try:
        tickers = client.futures_ticker()
        
        usdt_pairs = []
        excluded = ['USDCUSDT', 'BUSDUSDT', 'TUSDUSDT', 'FDUSDUSDT']
        
        for t in tickers:
            sym = t['symbol']
            if sym.endswith('USDT') and sym not in excluded:
                usdt_pairs.append({
                    'symbol': sym,
                    'volume': float(t['quoteVolume'])
                })
        
        usdt_pairs.sort(key=lambda x: x['volume'], reverse=True)
        return [p['symbol'] for p in usdt_pairs[:100]]
        
    except Exception as e:
        print(f"Erro ao obter símbolos: {e}")
        return ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT']


def interactive_menu():
    """Menu interativo para configuração do backtest"""
    
    print(f"\n{Colors.header('═' * 60)}")
    print(f"{Colors.header('         🔬 SISTEMA DE BACKTEST - MULTI CRYPTO')}")
    print(f"{Colors.header('═' * 60)}")
    print(f"\n{Colors.info('Configure os parâmetros do backtest:')}\n")
    
    # Período
    print(f"{Colors.bold('📅 PERÍODO')}")
    default_end = datetime.now()
    default_start = default_end - timedelta(days=7)
    
    start_input = input(f"   Data início (YYYY-MM-DD) [{default_start.strftime('%Y-%m-%d')}]: ").strip()
    if start_input:
        try:
            start_date = datetime.strptime(start_input, '%Y-%m-%d')
        except:
            print(Colors.warning("   Formato inválido, usando padrão"))
            start_date = default_start
    else:
        start_date = default_start
    
    end_input = input(f"   Data fim (YYYY-MM-DD) [{default_end.strftime('%Y-%m-%d')}]: ").strip()
    if end_input:
        try:
            end_date = datetime.strptime(end_input, '%Y-%m-%d')
        except:
            print(Colors.warning("   Formato inválido, usando padrão"))
            end_date = default_end
    else:
        end_date = default_end
    
    # Capital
    print(f"\n{Colors.bold('💰 CAPITAL')}")
    capital_input = input(f"   Capital inicial [$2500]: ").strip()
    initial_capital = float(capital_input) if capital_input else 2500.0
    
    position_input = input(f"   Valor por posição [$500]: ").strip()
    position_size = float(position_input) if position_input else 500.0
    
    num_pos_input = input(f"   Número de posições [5]: ").strip()
    num_positions = int(num_pos_input) if num_pos_input else 5
    
    # TP/SL
    print(f"\n{Colors.bold('🎯 TAKE PROFIT / STOP LOSS')}")
    tp_input = input(f"   Take Profit % [0.5]: ").strip()
    tp_percent = float(tp_input) if tp_input else 0.5
    
    sl_input = input(f"   Stop Loss % [0.4]: ").strip()
    sl_percent = float(sl_input) if sl_input else 0.4
    
    # Timeframe
    print(f"\n{Colors.bold('⏱️  TIMEFRAME')}")
    print("   Opções: 1m, 5m, 15m, 1h")
    tf_input = input(f"   Timeframe [1m]: ").strip()
    timeframe = tf_input if tf_input in ['1m', '5m', '15m', '1h'] else '1m'
    
    # Persistência
    print(f"\n{Colors.bold('⏳ PERSISTÊNCIA')}")
    pers_input = input(f"   Tempo de persistência (minutos) [1]: ").strip()
    persistence = int(pers_input) if pers_input else 1
    
    # Moedas
    print(f"\n{Colors.bold('🪙 MOEDAS')}")
    print("   1. TOP 100 por volume (recomendado)")
    print("   2. Moedas específicas")
    coins_choice = input(f"   Escolha [1]: ").strip()
    
    specific_symbols = None
    if coins_choice == '2':
        symbols_input = input("   Símbolos separados por vírgula (ex: BTCUSDT,ETHUSDT): ").strip()
        if symbols_input:
            specific_symbols = [s.strip().upper() for s in symbols_input.split(',')]
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'initial_capital': initial_capital,
        'position_size': position_size,
        'num_positions': num_positions,
        'tp_percent': tp_percent,
        'sl_percent': sl_percent,
        'timeframe': timeframe,
        'persistence': persistence,
        'specific_symbols': specific_symbols
    }


def run_backtest_system():
    """Função principal para executar o sistema de backtest"""
    
    # Carrega variáveis de ambiente
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    testnet = os.getenv('USE_TESTNET', 'true').lower() == 'true'
    
    if not api_key or not api_secret:
        print(Colors.error("❌ Erro: Credenciais Binance não configuradas no .env"))
        return
    
    # Inicializa cliente
    print(f"\n{Colors.info('🔗 Conectando à Binance...')}")
    
    from binance.client import Client
    
    if testnet:
        client = Client(api_key, api_secret, testnet=True)
        client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
        print(Colors.warning("   ⚠️  Modo TESTNET ativo"))
    else:
        client = Client(api_key, api_secret)
    
    # Obtém configuração do usuário
    config = interactive_menu()
    
    # Confirmação
    print(f"\n{Colors.header('═' * 60)}")
    print(f"{Colors.bold('Confirma configuração?')}")
    print(f"   Período: {config['start_date'].strftime('%Y-%m-%d')} até {config['end_date'].strftime('%Y-%m-%d')}")
    print(f"   Capital: ${config['initial_capital']:,.2f}")
    print(f"   Posições: {config['num_positions']} x ${config['position_size']:,.2f}")
    print(f"   TP/SL: {config['tp_percent']}% / {config['sl_percent']}%")
    print(f"   Timeframe: {config['timeframe']}")
    
    confirm = input(f"\n{Colors.info('Iniciar backtest? (s/n) [s]: ')}").strip().lower()
    if confirm == 'n':
        print(Colors.warning("Backtest cancelado."))
        return
    
    # Obtém símbolos
    if config['specific_symbols']:
        symbols = config['specific_symbols']
    else:
        print(f"\n{Colors.info('📊 Obtendo TOP 100 moedas por volume...')}")
        symbols = get_top_100_symbols(client)
        print(f"   Encontradas: {len(symbols)} moedas")
    
    # Inicializa engine
    engine = BacktestEngine(client)
    
    # Download dados
    engine.download_historical_data(
        symbols=symbols,
        start_date=config['start_date'],
        end_date=config['end_date'],
        interval=config['timeframe']
    )
    
    # Executa backtest
    result = engine.run_backtest(
        initial_capital=config['initial_capital'],
        position_size=config['position_size'],
        num_positions=config['num_positions'],
        tp_percent=config['tp_percent'],
        sl_percent=config['sl_percent'],
        persistence_minutes=config['persistence']
    )
    
    # Mostra resultados
    engine.print_results(result, config['initial_capital'])
    engine.print_trade_list(result)
    
    # Salvar resultados?
    save_input = input(f"\n{Colors.info('Salvar resultados em arquivo? (s/n) [s]: ')}").strip().lower()
    if save_input != 'n':
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f"/home/ubuntu/multi_crypto_bot/backtest_results_{timestamp}.json"
        engine.save_results_to_file(result, filepath)
    
    print(f"\n{Colors.success('✅ Backtest finalizado!')}\n")


if __name__ == '__main__':
    run_backtest_system()
