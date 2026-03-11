"""
Estratégia Multi-Crypto V3 - VERSÃO COM MELHORIAS ESTRATÉGICAS
Opera 5 criptomoedas simultaneamente com:
- ✅ Lucro Líquido Real (desconta taxas + slippage)
- ✅ Filtro de Correlação (evita alavancagem oculta)
- ✅ Ordens IOC (fechamento rápido em flash crash)
- ✅ Filtro de Sobrecompra (RSI + Bollinger)
- ✅ Dashboard com Drawdown
- ✅ Fechamento robusto de posições
- ✅ Monitoramento individual (+0.7% fecha UMA posição)
- ✅ Regra 3/5 positivas (+0.3% fecha TODAS)
"""
import time
import logging
import signal
import sys
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from binance.client import Client
from binance.exceptions import BinanceAPIException

# Cores no terminal
try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""

from top_performers import TopPerformersSelector, format_selection_table
from trend_analyzer import TrendAnalyzer
from correlation_filter import CorrelationFilter
from telegram_notifier import TelegramNotifier
from utils import round_quantity, round_price

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTES DE CONFIGURAÇÃO V3
# ============================================================
INDIVIDUAL_TP_PERCENT = 0.7    # Fechar posição individual se atingir +0.7%
RULE_3_5_THRESHOLD = 0.3       # Threshold para regra 3/5 positivas (+0.3%)
MAX_CLOSE_RETRIES = 5          # Máximo de tentativas para fechar posição
CLOSE_RETRY_DELAY = 0.5        # Segundos entre tentativas (V3: reduzido de 2s)
API_TIMEOUT = 30               # Timeout para requisições

# ============================================================
# CONSTANTES DE CUSTOS (V3)
# ============================================================
MAKER_FEE = 0.0002    # 0.02% taxa maker
TAKER_FEE = 0.0004    # 0.04% taxa taker
SLIPPAGE = 0.0002     # 0.02% slippage estimado
TOTAL_COST_RATE = (TAKER_FEE * 2) + SLIPPAGE  # ~0.10% total (entrada + saída)

# ============================================================
# CONSTANTES DE CORRELAÇÃO (V3)
# ============================================================
MAX_CORRELATION = 0.85  # Correlação máxima permitida entre ativos


@dataclass
class CryptoPosition:
    """Representa uma posição individual com métricas V3"""
    symbol: str
    side: str  # 'BUY' ou 'SELL'
    quantity: float
    entry_price: float
    capital_used: float
    direction: str = ""  # 'LONG' ou 'SHORT'
    entry_time: datetime = field(default_factory=datetime.now)
    current_price: float = 0.0
    pnl: float = 0.0
    pnl_percent: float = 0.0
    closed: bool = False
    # Novos campos V3
    gross_pnl: float = 0.0  # P&L bruto
    net_pnl: float = 0.0    # P&L líquido (após taxas)
    fees_paid: float = 0.0  # Total de taxas estimadas
    
    def update_pnl(self, current_price: float):
        """Atualiza P&L da posição incluindo lucro líquido"""
        self.current_price = current_price
        
        # P&L Bruto
        if self.side == 'BUY':
            self.gross_pnl = (current_price - self.entry_price) * self.quantity
        else:
            self.gross_pnl = (self.entry_price - current_price) * self.quantity
        
        # Calcula taxas estimadas
        position_value = self.capital_used
        self.fees_paid = position_value * TOTAL_COST_RATE
        
        # P&L Líquido = Bruto - Taxas
        self.net_pnl = self.gross_pnl - self.fees_paid
        
        # Mantém pnl/pnl_percent para compatibilidade (agora usa líquido)
        self.pnl = self.gross_pnl  # Display usa bruto
        self.pnl_percent = (self.gross_pnl / self.capital_used) * 100 if self.capital_used > 0 else 0
    
    def get_net_pnl_percent(self) -> float:
        """Retorna P&L líquido em percentual"""
        return (self.net_pnl / self.capital_used) * 100 if self.capital_used > 0 else 0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'direction': self.direction,
            'quantity': self.quantity,
            'entry_price': self.entry_price,
            'current_price': self.current_price,
            'pnl': self.pnl,
            'pnl_percent': self.pnl_percent,
            'net_pnl': self.net_pnl,
            'fees_paid': self.fees_paid
        }


@dataclass
class DailyStats:
    """Estatísticas diárias"""
    date: date = field(default_factory=date.today)
    entries_count: int = 0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    wins: int = 0
    losses: int = 0
    
    def reset_if_new_day(self):
        """Reseta estatísticas se é um novo dia"""
        today = date.today()
        if self.date != today:
            logger.info("[STATS] Novo dia - resetando estatísticas")
            self.date = today
            self.entries_count = 0
            self.total_pnl = 0.0
            self.total_fees = 0.0
            self.wins = 0
            self.losses = 0


class PerformanceDashboard:
    """
    Dashboard de Performance V3
    Rastreia P&L, Drawdown, e métricas avançadas.
    """
    
    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.current_pnl = 0.0
        self.gross_pnl = 0.0
        self.net_pnl = 0.0
        self.total_fees = 0.0
        
        # Drawdown tracking
        self.max_pnl_reached = 0.0
        self.current_drawdown = 0.0
        self.max_drawdown = 0.0
        self.max_drawdown_time: Optional[datetime] = None
        
        # Filtros
        self.correlation_filter_count = 0
        self.overbought_filter_count = 0
        self.blocked_symbols: List[str] = []
    
    def update(self, positions: List[CryptoPosition]):
        """Atualiza métricas do dashboard"""
        active_positions = [p for p in positions if not p.closed]
        
        # Calcula P&L total
        self.gross_pnl = sum(p.gross_pnl for p in active_positions)
        self.total_fees = sum(p.fees_paid for p in active_positions)
        self.net_pnl = self.gross_pnl - self.total_fees
        self.current_pnl = self.gross_pnl  # Para display
        
        # Atualiza máximo atingido
        if self.current_pnl > self.max_pnl_reached:
            self.max_pnl_reached = self.current_pnl
        
        # Calcula Drawdown
        if self.max_pnl_reached > 0:
            self.current_drawdown = (self.max_pnl_reached - self.current_pnl) / self.initial_capital
            
            if self.current_drawdown > self.max_drawdown:
                self.max_drawdown = self.current_drawdown
                self.max_drawdown_time = datetime.now()
        else:
            self.current_drawdown = 0.0
    
    def record_correlation_filter(self, symbols: List[str]):
        """Registra ativos bloqueados pelo filtro de correlação"""
        self.correlation_filter_count += len(symbols)
        self.blocked_symbols.extend(symbols)
    
    def record_overbought_filter(self, symbol: str):
        """Registra ativo bloqueado pelo filtro de sobrecompra"""
        self.overbought_filter_count += 1
        if symbol not in self.blocked_symbols:
            self.blocked_symbols.append(symbol)
    
    def get_drawdown_color(self) -> str:
        """Retorna cor baseada no nível de drawdown"""
        if self.current_drawdown >= 0.003:  # > 0.3%
            return Fore.RED
        elif self.current_drawdown >= 0.002:  # > 0.2%
            return Fore.YELLOW
        else:
            return Fore.WHITE
    
    def get_summary(self) -> Dict:
        """Retorna resumo das métricas"""
        return {
            'gross_pnl': self.gross_pnl,
            'net_pnl': self.net_pnl,
            'total_fees': self.total_fees,
            'max_pnl': self.max_pnl_reached,
            'current_drawdown': self.current_drawdown,
            'current_drawdown_pct': self.current_drawdown * 100,
            'max_drawdown': self.max_drawdown,
            'max_drawdown_pct': self.max_drawdown * 100,
            'correlation_blocks': self.correlation_filter_count,
            'overbought_blocks': self.overbought_filter_count
        }


def calculate_net_profit(gross_profit: float, position_value: float) -> Tuple[float, float]:
    """
    Calcula lucro líquido descontando taxas e slippage.
    
    Args:
        gross_profit: Lucro bruto
        position_value: Valor total da posição
    
    Returns:
        Tuple (net_profit, total_fees)
    """
    # Taxas: entrada (taker) + saída (taker) + slippage
    total_fees = position_value * TOTAL_COST_RATE
    net_profit = gross_profit - total_fees
    return net_profit, total_fees


def is_profit_worth_closing(gross_profit: float, position_value: float, min_net_percent: float = 0.05) -> bool:
    """
    Verifica se o lucro líquido justifica fechar a posição.
    
    Args:
        gross_profit: Lucro bruto
        position_value: Valor da posição
        min_net_percent: Lucro líquido mínimo em % (default 0.05%)
    
    Returns:
        True se lucro líquido > custos + mínimo
    """
    net_profit, fees = calculate_net_profit(gross_profit, position_value)
    min_required = position_value * (min_net_percent / 100)
    
    return net_profit > min_required


class MultiCryptoStrategy:
    """
    Estratégia Multi-Crypto V3 com melhorias estratégicas.
    
    Novidades V3:
    - calculate_net_profit(): Lucro real após taxas
    - CorrelationFilter: Filtra ativos correlacionados
    - Ordens IOC: Fechamento rápido
    - Filtro de Sobrecompra: RSI + Bollinger
    - PerformanceDashboard: Drawdown e métricas
    """
    
    def __init__(
        self,
        client: Client,
        capital_per_crypto: float = 500.0,
        tp_percent: float = 0.5,
        sl_percent: float = 0.4,
        max_daily_entries: int = 5,
        testnet: bool = True,
        telegram: Optional[TelegramNotifier] = None,
        use_correlation_filter: bool = True,
        use_overbought_filter: bool = True
    ):
        """
        Inicializa a estratégia V3.
        
        Args:
            client: Cliente Binance autenticado
            capital_per_crypto: Capital por cripto ($500 padrão)
            tp_percent: Take Profit % do total
            sl_percent: Stop Loss % do total
            max_daily_entries: Máximo de entradas no dia
            testnet: Se está em modo testnet
            telegram: Notificador Telegram
            use_correlation_filter: Ativa filtro de correlação (V3)
            use_overbought_filter: Ativa filtro de sobrecompra (V3)
        """
        self.client = client
        self.capital_per_crypto = capital_per_crypto
        self.tp_percent = tp_percent
        self.sl_percent = sl_percent
        self.max_daily_entries = max_daily_entries
        self.testnet = testnet
        
        self.num_cryptos = 5
        self.total_capital = capital_per_crypto * self.num_cryptos
        
        # Valores absolutos de TP/SL
        self.tp_value = self.total_capital * (tp_percent / 100)
        self.sl_value = self.total_capital * (sl_percent / 100)
        
        # Componentes
        self.selector = TopPerformersSelector(client, testnet)
        self.trend_analyzer = TrendAnalyzer(client)
        self.telegram = telegram or TelegramNotifier()
        
        # V3: Novos componentes
        self.correlation_filter = CorrelationFilter(client, MAX_CORRELATION)
        self.dashboard = PerformanceDashboard(self.total_capital)
        self.use_correlation_filter = use_correlation_filter
        self.use_overbought_filter = use_overbought_filter
        
        # Estado
        self.positions: List[CryptoPosition] = []
        self.daily_stats = DailyStats()
        self.is_running = False
        self.should_stop = False
        self._symbol_info_cache = {}
        
        # Configura signal handler para Ctrl+C
        self._setup_signal_handlers()
        
        logger.info(f"[MULTI-V3] Estratégia com MELHORIAS ESTRATÉGICAS inicializada:")
        logger.info(f"  Capital total: ${self.total_capital:.2f}")
        logger.info(f"  Capital por cripto: ${capital_per_crypto:.2f}")
        logger.info(f"  TP Global: +{tp_percent}% (+${self.tp_value:.2f})")
        logger.info(f"  SL Global: -{sl_percent}% (-${self.sl_value:.2f})")
        logger.info(f"  📍 TP Individual: +{INDIVIDUAL_TP_PERCENT}%")
        logger.info(f"  📍 Regra 3/5: +{RULE_3_5_THRESHOLD}%")
        logger.info(f"  💰 Custos estimados: {TOTAL_COST_RATE*100:.2f}% por trade")
        logger.info(f"  📊 Filtro Correlação: {'ATIVO' if use_correlation_filter else 'INATIVO'}")
        logger.info(f"  📈 Filtro Sobrecompra: {'ATIVO' if use_overbought_filter else 'INATIVO'}")
    
    def _setup_signal_handlers(self):
        """Configura handlers para interrupção limpa"""
        def signal_handler(signum, frame):
            print(f"\n{Fore.YELLOW}⚠️  Ctrl+C detectado! Fechando posições...{Style.RESET_ALL}")
            logger.info("[MULTI-V3] Interrupção detectada (Ctrl+C)")
            self.should_stop = True
            self.is_running = False
            # Força fechamento
            if self.positions:
                self.force_close_all_positions("INTERRUPÇÃO (Ctrl+C)")
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    # ============================================================
    # FUNÇÕES DE FECHAMENTO V3 (COM IOC)
    # ============================================================
    
    def get_position_amount_from_exchange(self, symbol: str) -> float:
        """
        Obtém a quantidade real da posição na exchange.
        Retorna 0 se não há posição aberta.
        """
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                amt = float(pos['positionAmt'])
                if amt != 0:
                    return amt
            return 0.0
        except Exception as e:
            logger.error(f"[GET-POS] Erro ao obter posição {symbol}: {e}")
            return 0.0
    
    def force_close_single_position_ioc(self, symbol: str, quantity: float, side: str) -> bool:
        """
        Força fechamento de UMA posição usando IOC (Immediate or Cancel).
        V3-FIX: Verifica posição REAL na exchange antes de cada tentativa.
        
        Args:
            symbol: Par de trading
            quantity: Quantidade a fechar
            side: 'BUY' ou 'SELL' (lado da posição, NÃO o lado de fechamento)
        
        Returns:
            True se fechou com sucesso
        """
        # V3-FIX: Verificar se posição ainda existe na exchange ANTES de tudo
        real_amount = self.get_position_amount_from_exchange(symbol)
        if real_amount == 0:
            logger.info(f"{Fore.GREEN}[CLOSE-IOC] {symbol}: Posição já fechada na exchange!{Style.RESET_ALL}")
            return True
        
        # Usa quantidade real da exchange
        quantity = abs(real_amount)
        close_side = 'SELL' if real_amount > 0 else 'BUY'
        
        logger.info(f"[CLOSE-IOC] {symbol}: Fechando {quantity:.6f} ({close_side})")
        
        for attempt in range(1, MAX_CLOSE_RETRIES + 1):
            # V3-FIX: Verificar novamente antes de cada tentativa
            real_amount = self.get_position_amount_from_exchange(symbol)
            if real_amount == 0:
                logger.info(f"{Fore.GREEN}[CLOSE-IOC] {symbol}: ✅ Posição fechada com sucesso!{Style.RESET_ALL}")
                return True
            
            quantity = abs(real_amount)
            close_side = 'SELL' if real_amount > 0 else 'BUY'
            
            logger.info(f"{Fore.YELLOW}[CLOSE-IOC] Tentativa {attempt}/{MAX_CLOSE_RETRIES} para {symbol}...{Style.RESET_ALL}")
            
            try:
                # Método 1 e 2: IOC Order (Immediate or Cancel)
                if attempt <= 2:
                    logger.info(f"  └─ Método: IOC (Immediate or Cancel)")
                    
                    # Obtém preço atual para LIMIT IOC
                    ticker = self.client.futures_ticker(symbol=symbol)
                    current_price = float(ticker['lastPrice'])
                    
                    # Preço agressivo para garantir execução
                    if close_side == 'SELL':
                        price = current_price * 0.995  # 0.5% abaixo
                    else:
                        price = current_price * 1.005  # 0.5% acima
                    
                    step_size, tick_size, _ = self.get_symbol_filters(symbol)
                    price = round_price(price, tick_size)
                    
                    try:
                        order = self.client.futures_create_order(
                            symbol=symbol,
                            side=close_side,
                            type='LIMIT',
                            timeInForce='IOC',
                            quantity=quantity,
                            price=price
                        )
                        
                        # Verifica se executou
                        status = order.get('status', '')
                        executed_qty = float(order.get('executedQty', 0))
                        
                        if status == 'FILLED' or executed_qty >= quantity * 0.99:
                            logger.info(f"{Fore.GREEN}  └─ ✅ IOC executado! Qty: {executed_qty}{Style.RESET_ALL}")
                            return True
                        elif executed_qty > 0:
                            # Execução parcial - tenta fechar resto
                            remaining = quantity - executed_qty
                            logger.info(f"  └─ Execução parcial: {executed_qty}/{quantity}")
                            quantity = remaining
                        else:
                            logger.info(f"  └─ IOC cancelado (sem liquidez)")
                            
                    except BinanceAPIException as e:
                        if e.code == -4131:  # PERCENT_PRICE filter
                            logger.info(f"  └─ Preço fora do range, tentando MARKET")
                        else:
                            raise
                
                # Método 3: MARKET Order direta (fallback rápido)
                elif attempt == 3:
                    logger.info(f"  └─ Método: MARKET order (fallback)")
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=close_side,
                        type='MARKET',
                        quantity=quantity
                    )
                    logger.info(f"{Fore.GREEN}  └─ ✅ MARKET executada! OrderID: {order.get('orderId')}{Style.RESET_ALL}")
                    return True
                
                # Método 4: MARKET com reduceOnly
                elif attempt == 4:
                    logger.info(f"  └─ Método: MARKET + reduceOnly=true")
                    order = self.client.futures_create_order(
                        symbol=symbol,
                        side=close_side,
                        type='MARKET',
                        quantity=quantity,
                        reduceOnly='true'
                    )
                    logger.info(f"{Fore.GREEN}  └─ ✅ Ordem executada!{Style.RESET_ALL}")
                    return True
                
                # Método 5: Obter posição atual e fechar
                else:
                    logger.info(f"  └─ Método: Verificar posição e fechar")
                    positions = self.client.futures_position_information(symbol=symbol)
                    for pos in positions:
                        amt = float(pos['positionAmt'])
                        if amt != 0:
                            qty = abs(amt)
                            close_side = 'SELL' if amt > 0 else 'BUY'
                            
                            order = self.client.futures_create_order(
                                symbol=symbol,
                                side=close_side,
                                type='MARKET',
                                quantity=qty
                            )
                            logger.info(f"{Fore.GREEN}  └─ ✅ Ordem executada!{Style.RESET_ALL}")
                            return True
                    
                    logger.info(f"{Fore.GREEN}  └─ ✅ Posição já está fechada!{Style.RESET_ALL}")
                    return True
                    
            except BinanceAPIException as e:
                logger.error(f"{Fore.RED}  └─ ❌ Erro API: {e.code} - {e.message}{Style.RESET_ALL}")
                if e.code in [-2022, -4164]:  # ReduceOnly rejected ou Notional too small
                    # Verificar se posição foi fechada
                    if self.get_position_amount_from_exchange(symbol) == 0:
                        logger.info(f"  └─ Posição já está fechada")
                        return True
            except Exception as e:
                logger.error(f"{Fore.RED}  └─ ❌ Erro: {e}{Style.RESET_ALL}")
            
            if attempt < MAX_CLOSE_RETRIES:
                logger.info(f"  └─ Aguardando {CLOSE_RETRY_DELAY}s...")
                time.sleep(CLOSE_RETRY_DELAY)
        
        # Verificação final
        if self.get_position_amount_from_exchange(symbol) == 0:
            logger.info(f"{Fore.GREEN}[CLOSE-IOC] {symbol}: ✅ Posição fechada na verificação final!{Style.RESET_ALL}")
            return True
        
        return False
    
    # Alias para manter compatibilidade
    def force_close_single_position(self, symbol: str, quantity: float, side: str) -> bool:
        """Alias para force_close_single_position_ioc (compatibilidade)"""
        return self.force_close_single_position_ioc(symbol, quantity, side)
    
    def verify_position_closed(self, symbol: str) -> bool:
        """Verifica se uma posição está realmente fechada"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                if float(pos['positionAmt']) != 0:
                    return False
            return True
        except Exception as e:
            logger.error(f"[VERIFY] Erro ao verificar {symbol}: {e}")
            return False
    
    def force_close_all_positions(self, reason: str) -> float:
        """
        FORÇA fechamento de TODAS as posições com IOC/MARKET.
        
        Args:
            reason: Motivo do fechamento
        
        Returns:
            P&L total
        """
        print(f"\n{Fore.YELLOW}{'='*70}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}🔄 FORÇANDO FECHAMENTO DE TODAS AS POSIÇÕES (V3){Style.RESET_ALL}")
        print(f"{Fore.YELLOW}   Motivo: {reason}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}{'='*70}{Style.RESET_ALL}")
        
        logger.info(f"\n{'='*60}")
        logger.info(f"[FORCE-CLOSE] FECHANDO TODAS: {reason}")
        logger.info(f"{'='*60}")
        
        self.telegram.notify_closing_positions(reason)
        
        total_gross_pnl = 0.0
        total_net_pnl = 0.0
        total_fees = 0.0
        positions_detail = []
        failed_to_close = []
        
        for pos in self.positions:
            if pos.closed:
                continue
            
            print(f"\n{Fore.CYAN}📍 Fechando {pos.symbol} ({pos.direction})...{Style.RESET_ALL}")
            
            # Tenta fechar com IOC
            success = self.force_close_single_position_ioc(pos.symbol, pos.quantity, pos.side)
            
            if success:
                time.sleep(0.3)  # Pausa curta
                if self.verify_position_closed(pos.symbol):
                    pos.closed = True
                    total_gross_pnl += pos.gross_pnl
                    total_net_pnl += pos.net_pnl
                    total_fees += pos.fees_paid
                    positions_detail.append(pos.to_dict())
                    
                    emoji = "✅" if pos.gross_pnl >= 0 else "❌"
                    pnl_color = Fore.GREEN if pos.gross_pnl >= 0 else Fore.RED
                    
                    print(f"{emoji} {pos.symbol}: Bruto {pnl_color}${pos.gross_pnl:+.2f}{Style.RESET_ALL} | Líquido ${pos.net_pnl:+.2f} | Taxas ${pos.fees_paid:.2f}")
                    logger.info(f"[FORCE-CLOSE] {emoji} {pos.symbol}: Bruto ${pos.gross_pnl:+.2f} | Líquido ${pos.net_pnl:+.2f}")
                    
                    self.telegram.notify_position_closed(pos.symbol, pos.gross_pnl, pos.pnl_percent)
                else:
                    failed_to_close.append(pos)
            else:
                failed_to_close.append(pos)
        
        # Segunda rodada para falhas
        if failed_to_close:
            print(f"\n{Fore.YELLOW}⚠️  Tentando novamente posições não fechadas...{Style.RESET_ALL}")
            for pos in failed_to_close:
                for _ in range(3):
                    success = self.force_close_single_position_ioc(pos.symbol, pos.quantity, pos.side)
                    if success and self.verify_position_closed(pos.symbol):
                        pos.closed = True
                        total_gross_pnl += pos.gross_pnl
                        total_net_pnl += pos.net_pnl
                        total_fees += pos.fees_paid
                        positions_detail.append(pos.to_dict())
                        print(f"{Fore.GREEN}✅ {pos.symbol} fechado na segunda tentativa{Style.RESET_ALL}")
                        break
                    time.sleep(0.5)
        
        # Atualiza stats
        total_invested = sum(p.capital_used for p in self.positions)
        total_pnl_percent = (total_gross_pnl / total_invested) * 100 if total_invested > 0 else 0
        
        self.daily_stats.total_pnl += total_gross_pnl
        self.daily_stats.total_fees += total_fees
        if total_gross_pnl >= 0:
            self.daily_stats.wins += 1
        else:
            self.daily_stats.losses += 1
        
        # Determina resultado
        result = 'MANUAL'
        if 'TAKE PROFIT' in reason.upper():
            result = 'TP'
        elif 'STOP LOSS' in reason.upper():
            result = 'SL'
        elif 'INTELIGENTE' in reason.upper() or 'INDIVIDUAL' in reason.upper() or '3/5' in reason:
            result = 'SMART'
        
        self.telegram.notify_all_closed(result, total_gross_pnl, total_pnl_percent, positions_detail)
        
        # Limpa lista
        self.positions.clear()
        
        # Display final
        pnl_color = Fore.GREEN if total_gross_pnl >= 0 else Fore.RED
        net_color = Fore.GREEN if total_net_pnl >= 0 else Fore.RED
        
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"💰 P&L BRUTO:   {pnl_color}${total_gross_pnl:+.2f} ({total_pnl_percent:+.2f}%){Style.RESET_ALL}")
        print(f"💸 TAXAS:       ${total_fees:.2f}")
        print(f"💵 P&L LÍQUIDO: {net_color}${total_net_pnl:+.2f}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        
        logger.info(f"\n[FORCE-CLOSE] P&L BRUTO: ${total_gross_pnl:+.2f} | LÍQUIDO: ${total_net_pnl:+.2f} | TAXAS: ${total_fees:.2f}")
        return total_gross_pnl
    
    def check_and_close_existing_positions(self) -> bool:
        """
        Verifica se há posições abertas na conta e fecha todas.
        V3.2-FIX: Ignora posições "dust" (valor < $1) e sincroniza lista local.
        
        Returns:
            True se não há mais posições abertas (ou só dust)
        """
        print(f"\n{Fore.CYAN}🔍 Verificando posições existentes...{Style.RESET_ALL}")
        logger.info("[CHECK] Verificando posições existentes na conta...")
        
        # Limite mínimo para considerar uma posição (valor em USD)
        MIN_POSITION_VALUE = 1.0  # $1
        MIN_POSITION_QTY = 0.001  # Quantidade mínima
        
        try:
            positions = self.client.futures_position_information()
            
            # Filtra posições REAIS (ignora dust/posições muito pequenas)
            open_positions = []
            dust_positions = []
            
            for p in positions:
                amt = float(p['positionAmt'])
                if amt == 0:
                    continue
                
                # Calcula valor da posição
                entry_price = float(p['entryPrice'])
                mark_price = float(p.get('markPrice', entry_price))
                position_value = abs(amt) * mark_price
                
                logger.info(f"[CHECK] {p['symbol']}: qty={amt:.6f}, valor=${position_value:.2f}")
                
                # Verifica se é dust
                if abs(amt) < MIN_POSITION_QTY or position_value < MIN_POSITION_VALUE:
                    dust_positions.append(p)
                    logger.info(f"[CHECK] {p['symbol']}: DUST ignorado (qty={amt:.6f}, valor=${position_value:.2f})")
                else:
                    open_positions.append(p)
            
            if not open_positions:
                if dust_positions:
                    print(f"{Fore.YELLOW}ℹ️  {len(dust_positions)} posições dust ignoradas (valor < ${MIN_POSITION_VALUE}){Style.RESET_ALL}")
                print(f"{Fore.GREEN}✅ Nenhuma posição REAL aberta. Conta limpa!{Style.RESET_ALL}")
                
                # Limpa lista local de posições
                self.positions.clear()
                logger.info("[CHECK] Lista local de posições limpa")
                return True
            
            print(f"\n{Fore.YELLOW}⚠️  {len(open_positions)} posições REAIS encontradas!{Style.RESET_ALL}")
            
            for pos in open_positions:
                symbol = pos['symbol']
                amt = float(pos['positionAmt'])
                entry = float(pos['entryPrice'])
                pnl = float(pos['unRealizedProfit'])
                side = 'LONG' if amt > 0 else 'SHORT'
                mark_price = float(pos.get('markPrice', entry))
                value = abs(amt) * mark_price
                
                print(f"  📍 {symbol}: {side} {abs(amt):.4f} @ ${entry:.4f} | Valor: ${value:.2f} | P&L: ${pnl:+.2f}")
                logger.info(f"[CHECK] Posição encontrada: {symbol} {side} qty={abs(amt):.4f} valor=${value:.2f}")
            
            print(f"\n{Fore.YELLOW}⚠️  Posições serão FECHADAS antes de continuar!{Style.RESET_ALL}")
            
            for pos in open_positions:
                symbol = pos['symbol']
                amt = float(pos['positionAmt'])
                side = 'BUY' if amt > 0 else 'SELL'
                quantity = abs(amt)
                
                print(f"\n{Fore.CYAN}Fechando {symbol}...{Style.RESET_ALL}")
                logger.info(f"[CHECK] Fechando {symbol}: qty={quantity}")
                success = self.force_close_single_position_ioc(symbol, quantity, side)
                
                if success:
                    print(f"{Fore.GREEN}✅ {symbol} fechado{Style.RESET_ALL}")
                    logger.info(f"[CHECK] {symbol} fechado com sucesso")
                else:
                    print(f"{Fore.RED}❌ Falha ao fechar {symbol}{Style.RESET_ALL}")
                    logger.error(f"[CHECK] Falha ao fechar {symbol}")
            
            time.sleep(1)
            
            # Verificação final - ignora dust novamente
            positions = self.client.futures_position_information()
            remaining = []
            for p in positions:
                amt = float(p['positionAmt'])
                if amt == 0:
                    continue
                mark_price = float(p.get('markPrice', float(p['entryPrice'])))
                value = abs(amt) * mark_price
                if abs(amt) >= MIN_POSITION_QTY and value >= MIN_POSITION_VALUE:
                    remaining.append(p)
            
            if remaining:
                print(f"\n{Fore.RED}❌ Ainda há {len(remaining)} posições abertas!{Style.RESET_ALL}")
                for r in remaining:
                    logger.error(f"[CHECK] Posição não fechada: {r['symbol']}")
                return False
            
            print(f"\n{Fore.GREEN}✅ Todas as posições REAIS foram fechadas!{Style.RESET_ALL}")
            
            # Limpa lista local de posições
            self.positions.clear()
            logger.info("[CHECK] Lista local de posições limpa após fechamento")
            return True
            
        except Exception as e:
            print(f"{Fore.RED}❌ Erro ao verificar posições: {e}{Style.RESET_ALL}")
            logger.error(f"[CHECK] Erro: {e}")
            return False
    
    def close_single_position_by_index(self, index: int, reason: str) -> bool:
        """
        Fecha UMA posição específica da lista.
        V3-FIX: Marca como fechada IMEDIATAMENTE e verifica exchange.
        """
        if index >= len(self.positions):
            return False
        
        pos = self.positions[index]
        if pos.closed:
            logger.info(f"[CLOSE-IDX] {pos.symbol}: Já está marcado como fechado, ignorando")
            return True
        
        # V3-FIX: Verificar se posição já está fechada na exchange
        real_amount = self.get_position_amount_from_exchange(pos.symbol)
        if real_amount == 0:
            logger.info(f"[CLOSE-IDX] {pos.symbol}: Posição já fechada na exchange!")
            pos.closed = True
            return True
        
        print(f"\n{Fore.YELLOW}🎯 Fechando posição individual: {pos.symbol}{Style.RESET_ALL}")
        print(f"   Motivo: {reason}")
        logger.info(f"[INDIVIDUAL] Fechando {pos.symbol}: {reason}")
        
        # V3-FIX: Marcar como fechada ANTES de chamar a API para evitar loops
        pos.closed = True
        
        success = self.force_close_single_position_ioc(pos.symbol, pos.quantity, pos.side)
        
        if success:
            # Confirma que fechou verificando exchange
            time.sleep(0.2)
            final_amount = self.get_position_amount_from_exchange(pos.symbol)
            
            if final_amount == 0:
                emoji = "✅" if pos.gross_pnl >= 0 else "❌"
                pnl_color = Fore.GREEN if pos.gross_pnl >= 0 else Fore.RED
                print(f"{emoji} {pos.symbol}: Bruto {pnl_color}${pos.gross_pnl:+.2f}{Style.RESET_ALL} | Líquido ${pos.net_pnl:+.2f}")
                
                self.telegram.notify_position_closed(pos.symbol, pos.gross_pnl, pos.pnl_percent)
                self.daily_stats.total_pnl += pos.gross_pnl
                self.daily_stats.total_fees += pos.fees_paid
                
                logger.info(f"[CLOSE-IDX] {pos.symbol}: ✅ FECHADO COM SUCESSO!")
                return True
            else:
                # Posição ainda existe - desmarcar para nova tentativa no próximo ciclo
                logger.warning(f"[CLOSE-IDX] {pos.symbol}: Posição ainda existe ({final_amount}), tentando novamente...")
                pos.closed = False
                return False
        else:
            # Falha no fechamento - desmarcar para nova tentativa
            pos.closed = False
            logger.error(f"[CLOSE-IDX] {pos.symbol}: Falha no fechamento")
            return False
    
    # ============================================================
    # FUNÇÕES AUXILIARES
    # ============================================================
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Obtém informações do símbolo (com cache)"""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        
        try:
            info = self.client.futures_exchange_info()
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    self._symbol_info_cache[symbol] = s
                    return s
            return None
        except Exception as e:
            logger.error(f"[MULTI-V3] Erro ao obter info de {symbol}: {e}")
            return None
    
    def get_symbol_filters(self, symbol: str) -> Tuple[float, float, float]:
        """Obtém step_size, tick_size, min_qty"""
        info = self.get_symbol_info(symbol)
        if not info:
            return 0.001, 0.01, 0.001
        
        step_size = tick_size = min_qty = 0.001
        
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                min_qty = float(f['minQty'])
            elif f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
        
        return step_size, tick_size, min_qty
    
    def get_account_balance(self) -> float:
        """Obtém saldo disponível em USDT"""
        try:
            account = self.client.futures_account()
            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    return float(asset['availableBalance'])
            return 0.0
        except Exception as e:
            logger.error(f"[MULTI-V3] Erro ao obter saldo: {e}")
            return 0.0
    
    def validate_capital(self) -> Tuple[bool, str]:
        """Valida se há capital suficiente"""
        balance = self.get_account_balance()
        required = self.total_capital * 1.1
        
        if balance < required:
            return False, f"Saldo insuficiente: ${balance:.2f} < ${required:.2f}"
        
        return True, f"Saldo OK: ${balance:.2f}"
    
    def can_enter(self) -> Tuple[bool, str]:
        """
        Verifica se pode fazer nova entrada.
        V3.2-FIX: Verifica posições na EXCHANGE, não apenas lista local.
        """
        self.daily_stats.reset_if_new_day()
        
        if self.daily_stats.entries_count >= self.max_daily_entries:
            return False, f"Limite de entradas atingido ({self.max_daily_entries}/dia)"
        
        # V3.2-FIX: Verifica se há posições ATIVAS (não fechadas) na lista local
        active_local = [p for p in self.positions if not p.closed]
        if active_local:
            logger.info(f"[CAN-ENTER] {len(active_local)} posições ativas na lista local")
            return False, f"Já existem {len(active_local)} posições abertas"
        
        # V3.2-FIX: Verifica também na exchange (ignora dust < $1)
        try:
            positions = self.client.futures_position_information()
            MIN_POSITION_VALUE = 1.0
            MIN_POSITION_QTY = 0.001
            
            real_positions = []
            for p in positions:
                amt = float(p['positionAmt'])
                if amt == 0:
                    continue
                mark_price = float(p.get('markPrice', float(p['entryPrice'])))
                value = abs(amt) * mark_price
                if abs(amt) >= MIN_POSITION_QTY and value >= MIN_POSITION_VALUE:
                    real_positions.append(p['symbol'])
            
            if real_positions:
                logger.info(f"[CAN-ENTER] Posições REAIS na exchange: {real_positions}")
                # Sincroniza: se há posições na exchange mas não na lista local, avisa
                return False, f"Posições abertas na exchange: {', '.join(real_positions[:3])}"
        except Exception as e:
            logger.error(f"[CAN-ENTER] Erro ao verificar exchange: {e}")
            # Continua com verificação de capital mesmo se falhar
        
        valid, msg = self.validate_capital()
        if not valid:
            return False, msg
        
        return True, "OK"
    
    def select_with_analysis(self, use_persistence: bool = True) -> List[Dict]:
        """
        Seleciona moedas COM análise LONG/SHORT e filtros V3.
        V3.2-FIX: Aumenta lista de backup para 15 moedas.
        """
        self.telegram.notify_scanning_started()
        
        def progress_callback(check_num, total, top_coins):
            self.telegram.notify_persistence_check(check_num, total, top_coins)
        
        # V3.2-FIX: Aumentado de 10 para 15 para ter mais backup
        num_with_backup = 15
        
        if use_persistence:
            selection = self.selector.select_with_persistence(
                n=num_with_backup,
                checks=3,
                interval_seconds=20,
                progress_callback=progress_callback
            )
        else:
            selection = self.selector.select_top_n(n=num_with_backup)
        
        if not selection:
            logger.error("[MULTI-V3] Nenhuma moeda selecionada")
            return []
        
        logger.info(f"[MULTI-V3] Selecionadas {len(selection)} moedas iniciais")
        
        # ============================================================
        # V3: FILTRO DE CORRELAÇÃO
        # ============================================================
        if self.use_correlation_filter and len(selection) > 1:
            filtered, removed, groups = self.correlation_filter.filter_correlated_assets(
                selection, max_correlation=MAX_CORRELATION
            )
            
            if removed:
                self.dashboard.record_correlation_filter([r['symbol'] for r in removed])
                selection = filtered
                
                # Notifica Telegram
                removed_symbols = [r['symbol'] for r in removed]
                self.telegram.send_custom(
                    f"📊 <b>FILTRO DE CORRELAÇÃO</b>\n\n"
                    f"Removidos {len(removed)} ativos correlacionados:\n"
                    f"{', '.join(removed_symbols)}\n\n"
                    f"Restam {len(filtered)} ativos diversificados"
                )
        
        # ============================================================
        # ANÁLISE DE TENDÊNCIA COM FILTRO DE SOBRECOMPRA
        # ============================================================
        blocked_by_overbought = []
        
        for coin in selection:
            try:
                analysis = self.trend_analyzer.analyze(
                    coin['symbol'], 
                    check_overbought=self.use_overbought_filter
                )
                
                coin['direction'] = analysis['direction']
                coin['trend_score'] = analysis['score']
                coin['trend_confidence'] = analysis['confidence']
                coin['ema_signal'] = analysis['ema_signal']
                coin['momentum'] = analysis['momentum']
                coin['rsi'] = analysis['rsi']
                coin['bollinger_position'] = analysis['bollinger_position']
                coin['entry_blocked'] = analysis['entry_blocked']
                coin['blocked_reason'] = analysis['blocked_reason']
                
                if analysis['entry_blocked']:
                    blocked_by_overbought.append({
                        'symbol': coin['symbol'],
                        'reason': analysis['blocked_reason']
                    })
                    self.dashboard.record_overbought_filter(coin['symbol'])
                    
            except Exception as e:
                logger.warning(f"[MULTI-V3] Erro ao analisar {coin['symbol']}: {e}")
                coin['direction'] = 'LONG'
                coin['entry_blocked'] = False
        
        # Notifica bloqueios por sobrecompra
        if blocked_by_overbought and self.use_overbought_filter:
            print(f"\n{Fore.YELLOW}🚫 FILTRO DE SOBRECOMPRA BLOQUEOU:{Style.RESET_ALL}")
            for b in blocked_by_overbought:
                print(f"   ❌ {b['symbol']}: {b['reason']}")
            
            self.telegram.send_custom(
                f"🚫 <b>FILTRO DE SOBRECOMPRA</b>\n\n"
                f"Bloqueadas {len(blocked_by_overbought)} entradas:\n" +
                "\n".join([f"• {b['symbol']}: {b['reason']}" for b in blocked_by_overbought])
            )
        
        self.telegram.notify_selection_complete(selection[:5])
        
        return selection
    
    def enter_all_positions(self, selection: List[Dict], fixed_side: str = None) -> bool:
        """
        Entra em todas as posições.
        V3.2-FIX: Garante 5 entradas, tratando melhor erros -4140.
        """
        if len(selection) < 1:
            logger.error("[MULTI-V3] Seleção vazia")
            return False
        
        # Verificar e fechar posições existentes
        if not self.check_and_close_existing_positions():
            print(f"{Fore.RED}❌ Não foi possível limpar posições existentes.{Style.RESET_ALL}")
            return False
        
        target_positions = self.num_cryptos
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}🚀 ABRINDO {target_positions} POSIÇÕES (V3.2){Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        
        self.telegram.notify_opening_positions(
            target_positions, 
            fixed_side or "MIXED", 
            self.capital_per_crypto * target_positions
        )
        
        success_count = 0
        opened_positions = []
        skipped_overbought = 0
        failed_symbols = []  # V3.2-FIX: Lista de símbolos que falharam
        total_attempts = 0
        max_attempts = 25  # V3.2-FIX: Máximo de tentativas totais
        
        logger.info(f"[ENTER] Iniciando abertura de {target_positions} posições (backup: {len(selection)} moedas)")
        
        for crypto in selection:
            # V3.2-FIX: Verifica se já atingiu objetivo ou máximo de tentativas
            if success_count >= target_positions:
                logger.info(f"[ENTER] ✅ Objetivo atingido: {success_count}/{target_positions} posições")
                break
            
            if total_attempts >= max_attempts:
                logger.warning(f"[ENTER] ⚠️  Máximo de tentativas atingido ({max_attempts})")
                break
            
            total_attempts += 1
            symbol = crypto['symbol']
            price = crypto['last_price']
            
            logger.info(f"[ENTER] Tentativa {total_attempts}: {symbol} (sucesso={success_count}/{target_positions})")
            
            # V3: Verifica se entrada está bloqueada por sobrecompra
            if self.use_overbought_filter and crypto.get('entry_blocked', False):
                reason = crypto.get('blocked_reason', 'Sobrecompra')
                print(f"{Fore.YELLOW}⏭️  {symbol}: PULADO - {reason}{Style.RESET_ALL}")
                logger.info(f"[ENTER] {symbol}: PULADO (sobrecompra) - {reason}")
                skipped_overbought += 1
                continue
            
            if fixed_side:
                side = fixed_side
                direction = 'LONG' if side == 'BUY' else 'SHORT'
            else:
                direction = crypto.get('direction', 'LONG')
                side = 'SELL' if direction == 'SHORT' else 'BUY'
            
            # V3: Verifica novamente antes de entrar
            if self.use_overbought_filter:
                filter_status = self.trend_analyzer.get_entry_filter_status(symbol, direction)
                if not filter_status['can_enter']:
                    reasons = ", ".join(filter_status['blocked_reasons'])
                    print(f"{Fore.YELLOW}⏭️  {symbol}: BLOQUEADO - {reasons}{Style.RESET_ALL}")
                    logger.info(f"[ENTER] {symbol}: BLOQUEADO - {reasons}")
                    skipped_overbought += 1
                    continue
            
            try:
                step_size, tick_size, min_qty = self.get_symbol_filters(symbol)
                raw_qty = self.capital_per_crypto / price
                quantity = round_quantity(raw_qty, step_size)
                
                if quantity < min_qty:
                    logger.warning(f"[ENTER] {symbol}: qty insuficiente ({quantity} < {min_qty})")
                    print(f"{Fore.YELLOW}⏭️  {symbol}: quantidade insuficiente{Style.RESET_ALL}")
                    continue
                
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='MARKET',
                    quantity=quantity
                )
                
                fill_price = float(order.get('avgPrice', price))
                if fill_price == 0:
                    fill_price = price
                
                position = CryptoPosition(
                    symbol=symbol,
                    side=side,
                    direction=direction,
                    quantity=quantity,
                    entry_price=fill_price,
                    capital_used=self.capital_per_crypto,
                    current_price=fill_price
                )
                
                self.positions.append(position)
                opened_positions.append(position.to_dict())
                success_count += 1
                
                dir_emoji = "🟢" if direction == 'LONG' else "🔴"
                print(f"{dir_emoji} [{success_count}/{target_positions}] {symbol}: {direction} {quantity:.4f} @ ${fill_price:.4f}")
                logger.info(f"[ENTER] ✅ {symbol}: ABERTA ({success_count}/{target_positions})")
                
                self.telegram.notify_position_opened(
                    symbol, side, quantity, fill_price, self.capital_per_crypto
                )
                
            except BinanceAPIException as e:
                # V3.2-FIX: Tratamento específico de erros
                if e.code == -4140:
                    # Símbolo não disponível para trading
                    print(f"{Fore.RED}❌ {symbol}: Não disponível para trading - pulando{Style.RESET_ALL}")
                    logger.error(f"[ENTER] ❌ {symbol}: NÃO DISPONÍVEL (erro -4140) - removido da lista")
                    failed_symbols.append(symbol)
                elif e.code == -4164:
                    # Notional too small
                    print(f"{Fore.YELLOW}⏭️  {symbol}: Valor muito pequeno - pulando{Style.RESET_ALL}")
                    logger.error(f"[ENTER] ⏭️  {symbol}: Valor muito pequeno (erro -4164)")
                else:
                    print(f"{Fore.RED}❌ {symbol}: Erro {e.code}{Style.RESET_ALL}")
                    logger.error(f"[ENTER] ❌ {symbol}: API Error {e.code} - {e.message}")
                    failed_symbols.append(symbol)
                continue
            except Exception as e:
                print(f"{Fore.RED}❌ {symbol}: {str(e)[:50]}{Style.RESET_ALL}")
                logger.error(f"[ENTER] ❌ {symbol}: {e}")
                continue
        
        # V3.2-FIX: Log resumo
        logger.info(f"[ENTER] RESUMO: {success_count}/{target_positions} posições abertas em {total_attempts} tentativas")
        if failed_symbols:
            logger.info(f"[ENTER] Símbolos que falharam: {failed_symbols}")
        
        if skipped_overbought > 0:
            print(f"\n{Fore.YELLOW}ℹ️  {skipped_overbought} entradas bloqueadas por filtro de sobrecompra{Style.RESET_ALL}")
        
        if failed_symbols:
            print(f"{Fore.RED}ℹ️  {len(failed_symbols)} símbolos indisponíveis: {', '.join(failed_symbols[:5])}{Style.RESET_ALL}")
        
        if success_count > 0:
            self.daily_stats.entries_count += 1
            
            # V3.2-FIX: Aviso se não atingiu objetivo
            if success_count < target_positions:
                print(f"\n{Fore.YELLOW}⚠️  ATENÇÃO: Apenas {success_count}/{target_positions} posições abertas{Style.RESET_ALL}")
                logger.warning(f"[ENTER] Objetivo não atingido: {success_count}/{target_positions}")
            else:
                print(f"\n{Fore.GREEN}✅ {success_count}/{target_positions} posições abertas{Style.RESET_ALL}")
            
            self.telegram.notify_all_positions_opened(
                opened_positions, 
                self.capital_per_crypto * success_count
            )
            return True
        
        logger.error("[ENTER] ❌ Nenhuma posição aberta!")
        print(f"\n{Fore.RED}❌ Nenhuma posição foi aberta!{Style.RESET_ALL}")
        return False
    
    def update_all_pnl(self) -> Tuple[float, float]:
        """
        Atualiza P&L de todas as posições.
        V3-FIX: Sincroniza com exchange e marca posições fechadas.
        """
        total_pnl = 0.0
        
        for pos in self.positions:
            if pos.closed:
                continue
            
            try:
                # V3-FIX: Verificar se posição ainda existe na exchange
                real_amount = self.get_position_amount_from_exchange(pos.symbol)
                if real_amount == 0:
                    logger.info(f"[UPDATE-PNL] {pos.symbol}: Posição fechada na exchange, marcando")
                    pos.closed = True
                    continue
                
                ticker = self.client.futures_ticker(symbol=pos.symbol)
                current_price = float(ticker['lastPrice'])
                pos.update_pnl(current_price)
                total_pnl += pos.gross_pnl
            except Exception as e:
                logger.debug(f"[MULTI-V3] Erro ao atualizar {pos.symbol}: {e}")
        
        # V3-FIX: Calcula total investido apenas para posições abertas
        active_positions = [p for p in self.positions if not p.closed]
        total_invested = sum(p.capital_used for p in active_positions)
        total_pnl_percent = (total_pnl / total_invested) * 100 if total_invested > 0 else 0
        
        # Atualiza dashboard
        self.dashboard.update(self.positions)
        
        # V3-FIX: Log para debug de atualização
        if len(active_positions) > 0:
            logger.debug(f"[UPDATE-PNL] {len(active_positions)} posições ativas | P&L: ${total_pnl:.2f} ({total_pnl_percent:.2f}%)")
        
        return total_pnl, total_pnl_percent
    
    def check_individual_tp(self) -> Tuple[bool, int, str]:
        """
        Verifica se alguma posição individual atingiu TP.
        V3-FIX: Verifica posição REAL na exchange antes de processar.
        """
        for i, pos in enumerate(self.positions):
            if pos.closed:
                continue
            
            # V3-FIX: Verificar se posição ainda existe na exchange
            real_amount = self.get_position_amount_from_exchange(pos.symbol)
            if real_amount == 0:
                logger.info(f"[CHECK-TP] {pos.symbol}: Posição já fechada na exchange, marcando como closed")
                pos.closed = True
                continue
            
            # V3: Verifica se lucro líquido justifica fechar
            if pos.pnl_percent >= INDIVIDUAL_TP_PERCENT:
                # Verifica se lucro líquido é significativo
                if is_profit_worth_closing(pos.gross_pnl, pos.capital_used, 0.05):
                    logger.info(f"[CHECK-TP] {pos.symbol}: TP individual atingido ({pos.pnl_percent:.2f}%) - DISPARANDO FECHAMENTO")
                    return True, i, pos.symbol
                else:
                    logger.info(f"[V3] {pos.symbol}: TP individual atingido mas lucro líquido insuficiente")
        
        return False, -1, ""
    
    def check_rule_3_5(self) -> Tuple[bool, str]:
        """
        Verifica regra 3/5 positivas.
        V3: Considera lucro líquido na decisão.
        """
        active_positions = [p for p in self.positions if not p.closed]
        
        if len(active_positions) < 3:
            return False, ""
        
        positive_positions = []
        negative_positions = []
        
        for pos in active_positions:
            if pos.pnl_percent >= RULE_3_5_THRESHOLD:
                positive_positions.append(pos)
            elif pos.gross_pnl < 0:
                negative_positions.append(pos)
        
        if len(positive_positions) < 3:
            return False, ""
        
        soma_positivas = sum(p.gross_pnl for p in positive_positions)
        soma_negativas = sum(abs(p.gross_pnl) for p in negative_positions)
        
        # V3: Calcula lucro líquido total
        total_gross = soma_positivas - soma_negativas
        total_invested = sum(p.capital_used for p in active_positions)
        net_profit, fees = calculate_net_profit(total_gross, total_invested)
        
        # Só fecha se lucro líquido for positivo
        if soma_positivas > soma_negativas and net_profit > 0:
            reason = f"3/5 positivas: {len(positive_positions)} moedas (Bruto ${total_gross:.2f} | Líquido ${net_profit:.2f})"
            return True, reason
        
        return False, ""
    
    def check_trend_reversal(self) -> Tuple[bool, str, int]:
        """Verifica se há reversão de tendência nas posições."""
        reversing_count = 0
        reversal_details = []
        
        for pos in self.positions:
            if pos.closed:
                continue
            
            try:
                is_reversing, reason = self.trend_analyzer.detect_reversal(pos.symbol, pos.side)
                
                if is_reversing:
                    reversing_count += 1
                    reversal_details.append(f"{pos.symbol}: {reason}")
            except:
                pass
        
        active_positions = len([p for p in self.positions if not p.closed])
        
        if reversing_count >= (active_positions / 2):
            combined_reason = "; ".join(reversal_details[:3])
            return True, combined_reason, reversing_count
        
        return False, "", reversing_count
    
    def monitor_positions(
        self, 
        update_interval: float = 2.0,
        smart_close_enabled: bool = True,
        reversal_check_interval: int = 30
    ) -> str:
        """
        Loop de monitoramento V3 com dashboard de drawdown.
        """
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}📊 MONITORAMENTO V3 INICIADO{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"  TP Global: +${self.tp_value:.2f}")
        print(f"  SL Global: -${self.sl_value:.2f}")
        print(f"  {Fore.YELLOW}📍 TP Individual: +{INDIVIDUAL_TP_PERCENT}%{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}📍 Regra 3/5: +{RULE_3_5_THRESHOLD}%{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}💰 Custos por trade: ~{TOTAL_COST_RATE*100:.2f}%{Style.RESET_ALL}")
        print(f"\n  Pressione {Fore.RED}Ctrl+C{Style.RESET_ALL} para fechar todas as posições\n")
        
        logger.info(f"[MONITOR-V3] Iniciando monitoramento...")
        
        self.is_running = True
        self.should_stop = False
        
        last_reversal_check = time.time()
        last_telegram_update = time.time()
        
        while self.is_running and not self.should_stop:
            try:
                total_pnl, total_pnl_percent = self.update_all_pnl()
                
                # Display V3 com dashboard
                self._display_monitor_status_v3(total_pnl, total_pnl_percent)
                
                # ============================================================
                # 1. TAKE PROFIT GLOBAL
                # ============================================================
                if total_pnl >= self.tp_value:
                    self.force_close_all_positions("🎉 TAKE PROFIT GLOBAL ATINGIDO")
                    self.is_running = False
                    return 'TP'
                
                # ============================================================
                # 2. STOP LOSS GLOBAL
                # ============================================================
                if total_pnl <= -self.sl_value:
                    self.force_close_all_positions("😔 STOP LOSS GLOBAL ATINGIDO")
                    self.is_running = False
                    return 'SL'
                
                # ============================================================
                # 3. TP INDIVIDUAL (+0.7%)
                # ============================================================
                should_close_individual, pos_index, symbol = self.check_individual_tp()
                if should_close_individual:
                    pos = self.positions[pos_index]
                    reason = f"🎯 {symbol} atingiu +{INDIVIDUAL_TP_PERCENT}% (Líquido: ${pos.net_pnl:.2f})"
                    
                    print(f"\n{Fore.GREEN}{reason}{Style.RESET_ALL}")
                    self.telegram.send_custom(f"🎯 <b>{symbol}</b> atingiu TP individual\n\nLíquido: ${pos.net_pnl:.2f}")
                    
                    self.close_single_position_by_index(pos_index, reason)
                    
                    active = [p for p in self.positions if not p.closed]
                    if not active:
                        print(f"\n{Fore.GREEN}✅ Todas as posições fechadas!{Style.RESET_ALL}")
                        self.is_running = False
                        return 'INDIVIDUAL'
                    
                    continue
                
                # ============================================================
                # 4. REGRA 3/5
                # ============================================================
                should_close_all, rule_reason = self.check_rule_3_5()
                if should_close_all:
                    print(f"\n{Fore.GREEN}✅ {rule_reason}{Style.RESET_ALL}")
                    self.telegram.send_custom(f"✅ <b>REGRA 3/5 ATIVADA</b>\n\n{rule_reason}")
                    
                    self.force_close_all_positions(f"✅ REGRA 3/5: {rule_reason}")
                    self.is_running = False
                    return 'RULE_3_5'
                
                # ============================================================
                # 5. FECHAMENTO INTELIGENTE
                # ============================================================
                if smart_close_enabled:
                    now = time.time()
                    
                    if now - last_reversal_check >= reversal_check_interval:
                        last_reversal_check = now
                        
                        if total_pnl > 0:
                            is_reversing, reason, num_reversing = self.check_trend_reversal()
                            
                            # V3: Verifica se lucro líquido justifica fechar
                            net_pnl = self.dashboard.net_pnl
                            
                            if is_reversing and net_pnl >= self.tp_value * 0.2:
                                self.telegram.notify_smart_close(
                                    f"Reversão + Lucro líquido positivo",
                                    total_pnl,
                                    total_pnl_percent
                                )
                                
                                self.force_close_all_positions(f"🧠 FECHAMENTO INTELIGENTE: {reason}")
                                self.is_running = False
                                return 'SMART'
                            
                            # Protege lucro se drawdown alto
                            if self.dashboard.current_drawdown >= 0.003 and net_pnl > 0:
                                self.telegram.notify_smart_close(
                                    "Protegendo lucro (drawdown > 0.3%)",
                                    total_pnl,
                                    total_pnl_percent
                                )
                                
                                self.force_close_all_positions("🧠 FECHAMENTO INTELIGENTE: Drawdown alto")
                                self.is_running = False
                                return 'SMART'
                    
                    # Telegram update
                    if now - last_telegram_update >= 60:
                        last_telegram_update = now
                        positions_data = [p.to_dict() for p in self.positions if not p.closed]
                        self.telegram.notify_monitoring_update(
                            total_pnl, total_pnl_percent,
                            self.tp_value, self.sl_value,
                            positions_data
                        )
                
                # Sleep interrompível
                sleep_steps = int(update_interval * 10)
                for _ in range(sleep_steps):
                    if self.should_stop:
                        break
                    time.sleep(0.1)
                
            except KeyboardInterrupt:
                self.should_stop = True
                break
            except Exception as e:
                logger.error(f"[MONITOR-V3] Erro: {e}")
                if self.should_stop:
                    break
                time.sleep(5)
        
        if self.positions:
            active = [p for p in self.positions if not p.closed]
            if active:
                self.force_close_all_positions("FECHAMENTO MANUAL")
        
        self.is_running = False
        return 'MANUAL'
    
    def _display_monitor_status_v3(self, total_pnl: float, total_pnl_percent: float):
        """Exibe status no terminal com dashboard V3"""
        print("\033[H\033[J", end="")  # Limpa tela
        
        dashboard = self.dashboard
        active_positions = [p for p in self.positions if not p.closed]
        
        # V3-FIX: Timestamp para confirmar atualização
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Header
        print(f"{Fore.CYAN}╔{'═'*72}╗{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL}{f' 📊 MONITORAMENTO V3 | {timestamp} | {len(active_positions)} posições ativas '.center(72)}{Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╠{'═'*72}╣{Style.RESET_ALL}")
        
        # Métricas V3
        dd_color = dashboard.get_drawdown_color()
        print(f"{Fore.CYAN}║{Style.RESET_ALL} 💰 Custos: {TOTAL_COST_RATE*100:.2f}% | Correlação: <{MAX_CORRELATION:.0%} | RSI: {70}/{30}".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╠{'═'*72}╣{Style.RESET_ALL}")
        
        # Cabeçalho da tabela
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {'SÍMBOLO':<10} │ {'DIR':^6} │ {'ENTRADA':>9} │ {'ATUAL':>9} │ {'BRUTO':>9} │ {'LÍQ':>9} │ {'TX':>6} {Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}╟{'─'*72}╢{Style.RESET_ALL}")
        
        positive_count = 0
        
        # V3-FIX: Itera apenas sobre posições ativas
        for pos in active_positions:
            if pos.pnl_percent >= RULE_3_5_THRESHOLD:
                positive_count += 1
            
            # Emoji baseado no P&L
            if pos.pnl_percent >= INDIVIDUAL_TP_PERCENT:
                emoji = "🎯"
            elif pos.pnl_percent >= RULE_3_5_THRESHOLD:
                emoji = "✅"
            elif pos.gross_pnl >= 0:
                emoji = "🟢"
            else:
                emoji = "🔴"
            
            pnl_color = Fore.GREEN if pos.gross_pnl >= 0 else Fore.RED
            net_color = Fore.GREEN if pos.net_pnl >= 0 else Fore.RED
            
            print(f"{Fore.CYAN}║{Style.RESET_ALL} {pos.symbol:<10} │ {pos.direction:^6} │ ${pos.entry_price:>8.4f} │ ${pos.current_price:>8.4f} │ {emoji}{pnl_color}${pos.gross_pnl:>+7.2f}{Style.RESET_ALL} │ {net_color}${pos.net_pnl:>+7.2f}{Style.RESET_ALL} │ ${pos.fees_paid:>5.2f} {Fore.CYAN}║{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}╠{'═'*72}╣{Style.RESET_ALL}")
        
        # P&L Total
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        pnl_color = Fore.GREEN if total_pnl >= 0 else Fore.RED
        net_color = Fore.GREEN if dashboard.net_pnl >= 0 else Fore.RED
        
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {pnl_emoji} P&L BRUTO:   {pnl_color}${total_pnl:+.2f} ({total_pnl_percent:+.2f}%){Style.RESET_ALL}".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL}    P&L LÍQUIDO: {net_color}${dashboard.net_pnl:+.2f}{Style.RESET_ALL} (após taxas ~${dashboard.total_fees:.2f})".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL}    Máximo atingido: ${dashboard.max_pnl_reached:+.2f}".ljust(73) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        # Drawdown
        print(f"{Fore.CYAN}╟{'─'*72}╢{Style.RESET_ALL}")
        dd_pct = dashboard.current_drawdown * 100
        max_dd_pct = dashboard.max_drawdown * 100
        
        print(f"{Fore.CYAN}║{Style.RESET_ALL} 📉 DRAWDOWN ATUAL: {dd_color}{dd_pct:.3f}%{Style.RESET_ALL} │ Máximo: {max_dd_pct:.3f}%".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        # Status da regra 3/5
        active_count = len(active_positions)
        rule_status = f"Regra 3/5: {positive_count}/{active_count} positivas (+{RULE_3_5_THRESHOLD}%)"
        rule_color = Fore.GREEN if positive_count >= 3 else Fore.YELLOW
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {rule_color}{rule_status}{Style.RESET_ALL}".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        # Filtros V3
        if dashboard.correlation_filter_count > 0 or dashboard.overbought_filter_count > 0:
            print(f"{Fore.CYAN}╟{'─'*72}╢{Style.RESET_ALL}")
            filters_info = f"🔒 Filtros: Correlação({dashboard.correlation_filter_count}) | Sobrecompra({dashboard.overbought_filter_count})"
            print(f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}{filters_info}{Style.RESET_ALL}".ljust(81) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        # Barra de progresso
        total_range = self.tp_value + self.sl_value
        position_in_range = total_pnl + self.sl_value
        progress = (position_in_range / total_range) * 100 if total_range > 0 else 50
        progress = max(0, min(100, progress))
        
        bar_width = 44
        filled = int(bar_width * progress / 100)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        print(f"{Fore.CYAN}╟{'─'*72}╢{Style.RESET_ALL}")
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.RED}SL -${self.sl_value:.2f}{Style.RESET_ALL} [{bar}] {Fore.GREEN}TP +${self.tp_value:.2f}{Style.RESET_ALL} {Fore.CYAN}║{Style.RESET_ALL}")
        
        # Stats do dia
        print(f"{Fore.CYAN}╟{'─'*72}╢{Style.RESET_ALL}")
        wr = (self.daily_stats.wins / max(1, self.daily_stats.wins + self.daily_stats.losses)) * 100
        stats_line = f"📅 DIA: {self.daily_stats.entries_count}/{self.max_daily_entries} │ W:{self.daily_stats.wins} L:{self.daily_stats.losses} │ WR:{wr:.0f}% │ P&L: ${self.daily_stats.total_pnl:+.2f} │ Taxas: ${self.daily_stats.total_fees:.2f}"
        print(f"{Fore.CYAN}║{Style.RESET_ALL} {stats_line}".ljust(73) + f"{Fore.CYAN}║{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}╚{'═'*72}╝{Style.RESET_ALL}")
        print(f"\n⌨️  {Fore.RED}Ctrl+C{Style.RESET_ALL} para fechar todas as posições")
    
    # Mantém método antigo para compatibilidade
    def close_all_positions(self, reason: str) -> float:
        """Alias para force_close_all_positions"""
        return self.force_close_all_positions(reason)
    
    def get_daily_stats(self) -> Dict:
        """Retorna estatísticas do dia"""
        self.daily_stats.reset_if_new_day()
        return {
            'date': str(self.daily_stats.date),
            'entries': self.daily_stats.entries_count,
            'max_entries': self.max_daily_entries,
            'remaining': self.max_daily_entries - self.daily_stats.entries_count,
            'total_pnl': self.daily_stats.total_pnl,
            'total_fees': self.daily_stats.total_fees,
            'net_pnl': self.daily_stats.total_pnl - self.daily_stats.total_fees,
            'wins': self.daily_stats.wins,
            'losses': self.daily_stats.losses,
            'win_rate': (self.daily_stats.wins / max(1, self.daily_stats.wins + self.daily_stats.losses)) * 100
        }
    
    def get_dashboard_summary(self) -> Dict:
        """Retorna resumo do dashboard V3"""
        return self.dashboard.get_summary()
