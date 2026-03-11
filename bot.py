"""
Bot Scalper para Binance Futures
Versão corrigida com tratamento robusto de SL/TP
"""
import time
import logging
import threading
from datetime import datetime
from typing import Optional, Dict, List
from binance.client import Client
from binance.exceptions import BinanceAPIException

import config
from strategy import RandomizedTrendScalp
from risk_manager import RiskManager
from utils import (
    round_quantity, round_price, retry_api_call,
    validate_sl_tp_prices, retry_with_backoff
)

# ============================================================
# CONFIGURAÇÃO DE LOGGING
# ============================================================
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ============================================================
# CLASSE POSITION
# ============================================================
class Position:
    """Representa uma posição aberta"""
    
    def __init__(
        self,
        symbol: str,
        side: str,
        quantity: float,
        entry_price: float,
        fill_price: float,
        tp_price: float,
        sl_price: float,
        time_stop: int,
        sl_order_id: Optional[int] = None,
        tp_order_id: Optional[int] = None,
        has_auto_sl: bool = False,
        has_auto_tp: bool = False
    ):
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.entry_price = entry_price
        self.fill_price = fill_price  # Preço real de preenchimento
        self.tp_price = tp_price
        self.sl_price = sl_price
        self.entry_time = datetime.now()
        self.time_stop = time_stop
        self.sl_order_id = sl_order_id
        self.tp_order_id = tp_order_id
        self.has_auto_sl = has_auto_sl
        self.has_auto_tp = has_auto_tp
    
    def __repr__(self):
        return (
            f"Position({self.side} {self.quantity} {self.symbol} @ ${self.fill_price:.4f}, "
            f"SL=${self.sl_price:.4f}, TP=${self.tp_price:.4f})"
        )


# ============================================================
# FUNÇÕES DE ORDEM
# ============================================================
class OrderManager:
    """Gerencia ordens na Binance Futures"""
    
    def __init__(self, client: Client):
        self.client = client
        self._symbol_info_cache = {}
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Obtém informações de precisão do símbolo (com cache)"""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        
        try:
            info = retry_api_call(self.client.futures_exchange_info)
            
            for s in info['symbols']:
                if s['symbol'] == symbol:
                    self._symbol_info_cache[symbol] = s
                    return s
            
            logger.error(f"[ORDER] Símbolo {symbol} não encontrado")
            return None
        
        except Exception as e:
            logger.error(f"[ORDER] Erro ao obter info de {symbol}: {e}")
            return None
    
    def get_symbol_filters(self, symbol: str) -> tuple:
        """
        Obtém filtros de precisão do símbolo.
        
        Returns:
            Tuple (step_size, tick_size, min_qty)
        """
        info = self.get_symbol_info(symbol)
        if not info:
            return None, None, None
        
        step_size = None
        tick_size = None
        min_qty = None
        
        for f in info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                min_qty = float(f['minQty'])
            elif f['filterType'] == 'PRICE_FILTER':
                tick_size = float(f['tickSize'])
        
        return step_size, tick_size, min_qty
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Obtém preço atual do símbolo"""
        try:
            ticker = retry_api_call(
                self.client.futures_ticker,
                symbol=symbol
            )
            return float(ticker['lastPrice'])
        except Exception as e:
            logger.error(f"[ORDER] Erro ao obter preço de {symbol}: {e}")
            return None
    
    def get_account_balance(self) -> float:
        """Obtém saldo disponível em USDT"""
        try:
            account = retry_api_call(self.client.futures_account)
            
            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    return float(asset['availableBalance'])
            return 0.0
        
        except Exception as e:
            logger.error(f"[ORDER] Erro ao obter saldo: {e}")
            return 0.0
    
    def cancel_all_orders(self, symbol: str):
        """Cancela todas as ordens abertas de um símbolo"""
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            logger.debug(f"[ORDER] Ordens abertas canceladas para {symbol}")
        except Exception as e:
            logger.debug(f"[ORDER] Erro ao cancelar ordens de {symbol}: {e}")
    
    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """Cancela uma ordem específica"""
        try:
            self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
            return True
        except Exception as e:
            logger.debug(f"[ORDER] Erro ao cancelar ordem {order_id}: {e}")
            return False
    
    def get_order_status(self, symbol: str, order_id: int) -> Optional[str]:
        """Obtém status de uma ordem"""
        try:
            order = self.client.futures_get_order(symbol=symbol, orderId=order_id)
            return order.get('status')
        except Exception as e:
            logger.debug(f"[ORDER] Erro ao obter status da ordem {order_id}: {e}")
            return None
    
    def place_market_order(self, symbol: str, side: str, quantity: float) -> Optional[Dict]:
        """
        Coloca ordem de mercado.
        
        Args:
            symbol: Símbolo
            side: 'BUY' ou 'SELL'
            quantity: Quantidade
        
        Returns:
            Dict com resposta da ordem ou None se falhar
        """
        try:
            logger.info(f"[ORDER] Enviando MARKET {side} {quantity} {symbol}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            
            logger.info(
                f"[ORDER] ✅ Ordem executada: ID={order['orderId']}, "
                f"Status={order['status']}"
            )
            
            return order
        
        except BinanceAPIException as e:
            logger.error(f"[ORDER] ❌ Erro API ao colocar ordem: {e.code} - {e.message}")
            return None
        except Exception as e:
            logger.error(f"[ORDER] ❌ Erro ao colocar ordem: {e}")
            return None
    
    def get_fill_price(self, symbol: str, order_id: int, max_wait: int = 10) -> Optional[float]:
        """
        Obtém preço de preenchimento de uma ordem.
        
        Args:
            symbol: Símbolo
            order_id: ID da ordem
            max_wait: Tempo máximo de espera em segundos
        
        Returns:
            Preço médio de preenchimento ou None
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                order = self.client.futures_get_order(symbol=symbol, orderId=order_id)
                
                if order['status'] == 'FILLED':
                    avg_price = float(order['avgPrice'])
                    logger.info(f"[ORDER] Preço de preenchimento: ${avg_price:.4f}")
                    return avg_price
                
                time.sleep(0.5)
            
            except Exception as e:
                logger.debug(f"[ORDER] Erro ao verificar preenchimento: {e}")
                time.sleep(1)
        
        logger.warning(f"[ORDER] Timeout ao obter preço de preenchimento")
        return None
    
    def wait_for_position(self, symbol: str, expected_side: str, max_wait: int = 15) -> bool:
        """
        Aguarda até que a posição esteja aberta.
        
        Args:
            symbol: Símbolo
            expected_side: 'BUY' para long, 'SELL' para short
            max_wait: Tempo máximo de espera
        
        Returns:
            True se posição confirmada, False caso contrário
        """
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            try:
                positions = self.client.futures_position_information(symbol=symbol)
                
                for p in positions:
                    if p['symbol'] == symbol:
                        pos_amt = float(p['positionAmt'])
                        
                        # LONG: positionAmt > 0
                        # SHORT: positionAmt < 0
                        if expected_side == 'BUY' and pos_amt > 0:
                            logger.info(f"[ORDER] ✅ Posição LONG confirmada: {pos_amt} {symbol}")
                            return True
                        elif expected_side == 'SELL' and pos_amt < 0:
                            logger.info(f"[ORDER] ✅ Posição SHORT confirmada: {pos_amt} {symbol}")
                            return True
                
                time.sleep(0.5)
            
            except Exception as e:
                logger.debug(f"[ORDER] Erro ao verificar posição: {e}")
                time.sleep(1)
        
        logger.warning(f"[ORDER] Timeout ao confirmar posição de {symbol}")
        return False
    
    def place_stop_loss(
        self,
        symbol: str,
        side: str,
        stop_price: float,
        quantity: float,
        tick_size: float
    ) -> Optional[Dict]:
        """
        Coloca ordem de Stop Loss.
        
        Tenta múltiplos métodos para garantir compatibilidade com testnet/mainnet.
        
        Args:
            symbol: Símbolo
            side: 'BUY' (para fechar short) ou 'SELL' (para fechar long)
            stop_price: Preço de gatilho
            quantity: Quantidade
            tick_size: Tick size para arredondamento
        
        Returns:
            Dict com resposta ou None se falhar
        """
        stop_price = round_price(stop_price, tick_size)
        
        # Verifica preço atual para validar direção
        current_price = self.get_current_price(symbol)
        if current_price is None:
            return None
        
        # Valida direção do stop
        if side == 'SELL':  # Stop para fechar LONG
            if stop_price >= current_price:
                logger.error(
                    f"[SL] ❌ LONG SL ({stop_price}) deve ser MENOR que preço atual ({current_price})"
                )
                return None
        else:  # Stop para fechar SHORT
            if stop_price <= current_price:
                logger.error(
                    f"[SL] ❌ SHORT SL ({stop_price}) deve ser MAIOR que preço atual ({current_price})"
                )
                return None
        
        # Método 1: STOP_MARKET com closePosition
        try:
            logger.info(f"[SL] Tentando STOP_MARKET closePosition em ${stop_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='STOP_MARKET',
                stopPrice=str(stop_price),
                closePosition='true',
                timeInForce='GTC',
                workingType='MARK_PRICE'
            )
            
            logger.info(f"[SL] ✅ Stop Loss criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[SL] Método 1 falhou: {e.code} - {e.message}")
        
        # Método 2: STOP_MARKET com quantity e reduceOnly
        try:
            logger.info(f"[SL] Tentando STOP_MARKET reduceOnly em ${stop_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='STOP_MARKET',
                stopPrice=str(stop_price),
                quantity=quantity,
                reduceOnly='true',
                timeInForce='GTC',
                workingType='MARK_PRICE'
            )
            
            logger.info(f"[SL] ✅ Stop Loss criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[SL] Método 2 falhou: {e.code} - {e.message}")
        
        # Método 3: STOP com price
        try:
            logger.info(f"[SL] Tentando STOP com price em ${stop_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='STOP',
                stopPrice=str(stop_price),
                price=str(stop_price),
                quantity=quantity,
                reduceOnly='true',
                timeInForce='GTC'
            )
            
            logger.info(f"[SL] ✅ Stop Loss criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[SL] Método 3 falhou: {e.code} - {e.message}")
        
        logger.error(f"[SL] ❌ Todos os métodos falharam para Stop Loss")
        return None
    
    def place_take_profit(
        self,
        symbol: str,
        side: str,
        tp_price: float,
        quantity: float,
        tick_size: float
    ) -> Optional[Dict]:
        """
        Coloca ordem de Take Profit.
        
        Args:
            symbol: Símbolo
            side: 'BUY' (para fechar short) ou 'SELL' (para fechar long)
            tp_price: Preço de gatilho
            quantity: Quantidade
            tick_size: Tick size para arredondamento
        
        Returns:
            Dict com resposta ou None se falhar
        """
        tp_price = round_price(tp_price, tick_size)
        
        # Verifica preço atual para validar direção
        current_price = self.get_current_price(symbol)
        if current_price is None:
            return None
        
        # Valida direção do TP
        if side == 'SELL':  # TP para fechar LONG
            if tp_price <= current_price:
                logger.error(
                    f"[TP] ❌ LONG TP ({tp_price}) deve ser MAIOR que preço atual ({current_price})"
                )
                return None
        else:  # TP para fechar SHORT
            if tp_price >= current_price:
                logger.error(
                    f"[TP] ❌ SHORT TP ({tp_price}) deve ser MENOR que preço atual ({current_price})"
                )
                return None
        
        # Método 1: TAKE_PROFIT_MARKET com closePosition
        try:
            logger.info(f"[TP] Tentando TAKE_PROFIT_MARKET closePosition em ${tp_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=str(tp_price),
                closePosition='true',
                timeInForce='GTC',
                workingType='MARK_PRICE'
            )
            
            logger.info(f"[TP] ✅ Take Profit criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[TP] Método 1 falhou: {e.code} - {e.message}")
        
        # Método 2: TAKE_PROFIT_MARKET com quantity e reduceOnly
        try:
            logger.info(f"[TP] Tentando TAKE_PROFIT_MARKET reduceOnly em ${tp_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=str(tp_price),
                quantity=quantity,
                reduceOnly='true',
                timeInForce='GTC',
                workingType='MARK_PRICE'
            )
            
            logger.info(f"[TP] ✅ Take Profit criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[TP] Método 2 falhou: {e.code} - {e.message}")
        
        # Método 3: LIMIT com reduceOnly (não ativa automaticamente, mas serve como TP)
        try:
            logger.info(f"[TP] Tentando LIMIT reduceOnly em ${tp_price:.4f}...")
            
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='LIMIT',
                price=str(tp_price),
                quantity=quantity,
                reduceOnly='true',
                timeInForce='GTC'
            )
            
            logger.info(f"[TP] ✅ Take Profit (LIMIT) criado: ID={order['orderId']}")
            return order
        
        except BinanceAPIException as e:
            logger.warning(f"[TP] Método 3 falhou: {e.code} - {e.message}")
        
        logger.error(f"[TP] ❌ Todos os métodos falharam para Take Profit")
        return None
    
    def close_position(self, symbol: str, side: str, quantity: float) -> bool:
        """
        Fecha uma posição com ordem de mercado.
        
        Args:
            symbol: Símbolo
            side: Lado para fechar ('SELL' para fechar long, 'BUY' para fechar short)
            quantity: Quantidade a fechar
        
        Returns:
            True se fechou com sucesso
        """
        try:
            self.client.futures_create_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity,
                reduceOnly='true'
            )
            logger.info(f"[ORDER] ✅ Posição fechada: {side} {quantity} {symbol}")
            return True
        
        except Exception as e:
            logger.error(f"[ORDER] ❌ Erro ao fechar posição: {e}")
            return False
    
    def get_position_info(self, symbol: str) -> Optional[Dict]:
        """Obtém informações da posição atual"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            
            for p in positions:
                if p['symbol'] == symbol:
                    return p
            
            return None
        
        except Exception as e:
            logger.debug(f"[ORDER] Erro ao obter posição de {symbol}: {e}")
            return None


# ============================================================
# VARIÁVEIS GLOBAIS
# ============================================================
open_positions: List[Position] = []
positions_lock = threading.Lock()


# ============================================================
# FUNÇÃO DE ABERTURA DE POSIÇÃO
# ============================================================
def open_position(
    order_manager: OrderManager,
    risk_manager: RiskManager,
    plan: Dict
) -> Optional[Position]:
    """
    Abre uma posição com SL e TP.
    
    Fluxo:
    1. Obter informações do símbolo
    2. Calcular tamanho da posição
    3. Executar ordem de entrada
    4. Confirmar posição aberta
    5. Obter preço real de preenchimento
    6. Recalcular SL/TP baseado no preço real
    7. Colocar ordens de SL/TP
    
    Args:
        order_manager: Gerenciador de ordens
        risk_manager: Gerenciador de risco
        plan: Plano de trade
    
    Returns:
        Position se sucesso, None se falhar
    """
    symbol = plan['symbol']
    side = plan['side']
    entry_price = plan['entry_price']
    tp_price = plan['tp_price']
    sl_price = plan['sl_price']
    time_stop = plan['time_stop']
    
    logger.info(f"\n{'='*60}")
    logger.info(f"[TRADE] ABRINDO POSIÇÃO: {side} {symbol}")
    logger.info(f"{'='*60}")
    
    # 1. Obter informações do símbolo
    step_size, tick_size, min_qty = order_manager.get_symbol_filters(symbol)
    
    if not all([step_size, tick_size, min_qty]):
        logger.error(f"[TRADE] Filtros incompletos para {symbol}")
        return None
    
    # 2. Calcular tamanho da posição
    balance = order_manager.get_account_balance()
    
    if balance <= 0:
        logger.error("[TRADE] Saldo insuficiente")
        return None
    
    raw_quantity = risk_manager.calculate_position_size(balance, entry_price, sl_price)
    quantity = round_quantity(raw_quantity, step_size)
    
    if quantity < min_qty:
        logger.warning(f"[TRADE] Quantidade {quantity} menor que mínimo {min_qty}")
        return None
    
    logger.info(f"[TRADE] Saldo: ${balance:.2f}, Quantidade: {quantity}")
    
    # 3. Cancelar ordens antigas
    order_manager.cancel_all_orders(symbol)
    
    # 4. Executar ordem de entrada
    entry_order = order_manager.place_market_order(symbol, side, quantity)
    
    if not entry_order:
        logger.error("[TRADE] Falha ao abrir posição")
        return None
    
    # 5. Confirmar posição e obter preço de preenchimento
    if not order_manager.wait_for_position(symbol, side):
        logger.error("[TRADE] Posição não confirmada")
        return None
    
    fill_price = order_manager.get_fill_price(symbol, entry_order['orderId'])
    
    if fill_price is None:
        fill_price = entry_price
        logger.warning(f"[TRADE] Usando preço estimado: ${fill_price:.4f}")
    
    # 6. Recalcular SL/TP baseado no preço real
    if side == 'BUY':
        tp_price = fill_price * (1 + config.TP_PERCENT_LONG / 100)
        sl_price = fill_price * (1 - config.SL_PERCENT_LONG / 100)
    else:
        tp_price = fill_price * (1 - config.TP_PERCENT_SHORT / 100)
        sl_price = fill_price * (1 + config.SL_PERCENT_SHORT / 100)
    
    tp_price = round_price(tp_price, tick_size)
    sl_price = round_price(sl_price, tick_size)
    
    logger.info(f"[TRADE] Preços recalculados: Entry=${fill_price:.4f}, TP=${tp_price:.4f}, SL=${sl_price:.4f}")
    
    # 7. Colocar ordens de SL/TP
    close_side = 'SELL' if side == 'BUY' else 'BUY'
    
    sl_order = order_manager.place_stop_loss(
        symbol, close_side, sl_price, quantity, tick_size
    )
    
    tp_order = order_manager.place_take_profit(
        symbol, close_side, tp_price, quantity, tick_size
    )
    
    # 8. Criar objeto Position
    position = Position(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        fill_price=fill_price,
        tp_price=tp_price,
        sl_price=sl_price,
        time_stop=time_stop,
        sl_order_id=sl_order['orderId'] if sl_order else None,
        tp_order_id=tp_order['orderId'] if tp_order else None,
        has_auto_sl=sl_order is not None,
        has_auto_tp=tp_order is not None
    )
    
    # Log final
    logger.info(f"\n[TRADE] ✅ POSIÇÃO ABERTA COM SUCESSO")
    logger.info(f"  Símbolo:    {symbol}")
    logger.info(f"  Lado:       {side}")
    logger.info(f"  Quantidade: {quantity}")
    logger.info(f"  Entrada:    ${fill_price:.4f}")
    logger.info(f"  Take Profit: ${tp_price:.4f} {'(AUTO)' if position.has_auto_tp else '(MANUAL)'}")
    logger.info(f"  Stop Loss:   ${sl_price:.4f} {'(AUTO)' if position.has_auto_sl else '(MANUAL)'}")
    logger.info(f"  Time Stop:   {time_stop // 60} minutos")
    
    if not position.has_auto_sl:
        logger.warning(f"[TRADE] ⚠️ SL será monitorado MANUALMENTE pelo bot!")
    
    if not position.has_auto_tp:
        logger.warning(f"[TRADE] ⚠️ TP será monitorado MANUALMENTE pelo bot!")
    
    return position


# ============================================================
# MONITORAMENTO DE POSIÇÕES
# ============================================================
def check_position_status(
    order_manager: OrderManager,
    position: Position
) -> str:
    """
    Verifica status de uma posição.
    
    Returns:
        'OPEN' - Posição ainda aberta
        'CLOSED' - Posição fechada por SL/TP automático
        'HIT_SL' - Atingiu SL (monitoramento manual)
        'HIT_TP' - Atingiu TP (monitoramento manual)
        'TIME_STOP' - Atingiu time stop
        'UNKNOWN' - Erro ao verificar
    """
    try:
        # Verifica se ainda existe posição
        pos_info = order_manager.get_position_info(position.symbol)
        
        if pos_info:
            pos_amt = float(pos_info['positionAmt'])
            
            # Posição fechada
            if abs(pos_amt) < 0.0001:
                return 'CLOSED'
            
            # Monitoramento manual de SL/TP
            current_price = float(pos_info['markPrice'])
            
            if not position.has_auto_sl:
                # LONG: fecha se preço <= SL
                if position.side == 'BUY' and current_price <= position.sl_price:
                    logger.warning(
                        f"[MONITOR] {position.symbol} HIT SL: "
                        f"${current_price:.4f} <= ${position.sl_price:.4f}"
                    )
                    return 'HIT_SL'
                
                # SHORT: fecha se preço >= SL
                if position.side == 'SELL' and current_price >= position.sl_price:
                    logger.warning(
                        f"[MONITOR] {position.symbol} HIT SL: "
                        f"${current_price:.4f} >= ${position.sl_price:.4f}"
                    )
                    return 'HIT_SL'
            
            if not position.has_auto_tp:
                # LONG: fecha se preço >= TP
                if position.side == 'BUY' and current_price >= position.tp_price:
                    logger.info(
                        f"[MONITOR] {position.symbol} HIT TP: "
                        f"${current_price:.4f} >= ${position.tp_price:.4f}"
                    )
                    return 'HIT_TP'
                
                # SHORT: fecha se preço <= TP
                if position.side == 'SELL' and current_price <= position.tp_price:
                    logger.info(
                        f"[MONITOR] {position.symbol} HIT TP: "
                        f"${current_price:.4f} <= ${position.tp_price:.4f}"
                    )
                    return 'HIT_TP'
        
        # Verifica time stop
        elapsed = (datetime.now() - position.entry_time).total_seconds()
        if elapsed >= position.time_stop:
            return 'TIME_STOP'
        
        return 'OPEN'
    
    except Exception as e:
        logger.error(f"[MONITOR] Erro ao verificar {position.symbol}: {e}")
        return 'UNKNOWN'


def close_position_with_cleanup(
    order_manager: OrderManager,
    risk_manager: RiskManager,
    position: Position,
    reason: str
):
    """
    Fecha uma posição e faz limpeza.
    
    Args:
        order_manager: Gerenciador de ordens
        risk_manager: Gerenciador de risco
        position: Posição a fechar
        reason: Motivo do fechamento
    """
    logger.info(f"\n[CLOSE] Fechando {position.symbol}: {reason}")
    
    # Cancela ordens pendentes
    if position.sl_order_id:
        order_manager.cancel_order(position.symbol, position.sl_order_id)
    
    if position.tp_order_id:
        order_manager.cancel_order(position.symbol, position.tp_order_id)
    
    # Fecha posição se ainda aberta
    close_side = 'SELL' if position.side == 'BUY' else 'BUY'
    
    pos_info = order_manager.get_position_info(position.symbol)
    if pos_info:
        pos_amt = abs(float(pos_info['positionAmt']))
        if pos_amt > 0.0001:
            order_manager.close_position(position.symbol, close_side, pos_amt)
            
            # Calcula PnL aproximado
            current_price = float(pos_info['markPrice'])
            if position.side == 'BUY':
                pnl = (current_price - position.fill_price) * position.quantity
            else:
                pnl = (position.fill_price - current_price) * position.quantity
            
            risk_manager.record_trade(pnl, position.symbol)


def monitor_positions(order_manager: OrderManager, risk_manager: RiskManager):
    """Thread que monitora posições abertas"""
    global open_positions
    
    logger.info("[MONITOR] Thread de monitoramento iniciada")
    
    while True:
        try:
            with positions_lock:
                for position in open_positions[:]:
                    status = check_position_status(order_manager, position)
                    
                    if status == 'CLOSED':
                        logger.info(f"[MONITOR] {position.symbol} fechada por SL/TP automático")
                        open_positions.remove(position)
                    
                    elif status in ('HIT_SL', 'HIT_TP'):
                        reason = "Stop Loss Manual" if status == 'HIT_SL' else "Take Profit Manual"
                        close_position_with_cleanup(order_manager, risk_manager, position, reason)
                        open_positions.remove(position)
                    
                    elif status == 'TIME_STOP':
                        close_position_with_cleanup(order_manager, risk_manager, position, "Time Stop")
                        open_positions.remove(position)
            
            # Intervalo de monitoramento
            if any(not p.has_auto_sl or not p.has_auto_tp for p in open_positions):
                # Monitoramento mais frequente se há SL/TP manual
                time.sleep(5)
            else:
                time.sleep(30)
        
        except Exception as e:
            logger.error(f"[MONITOR] Erro: {e}")
            time.sleep(30)


# ============================================================
# FUNÇÃO PRINCIPAL
# ============================================================
def main():
    """Função principal do bot"""
    
    # Banner
    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║       RANDOMIZED TREND SCALPER - BINANCE FUTURES             ║
║                                                              ║
║              Bot de Scalping Automatizado                    ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Validar configuração
    errors = config.validate_config()
    if errors:
        logger.error("Erros de configuração:")
        for err in errors:
            logger.error(f"  - {err}")
        return
    
    # Mostrar configuração
    config.print_config()
    
    logger.info("="*60)
    logger.info("INICIANDO BOT...")
    logger.info("="*60)
    
    # Inicializar cliente Binance
    try:
        client = Client(
            config.BINANCE_API_KEY,
            config.BINANCE_SECRET_KEY,
            testnet=config.BINANCE_TESTNET
        )
        
        # Testar conexão
        server_time = client.futures_time()
        logger.info(f"[API] Conectado à Binance. Server time: {server_time}")
        
    except Exception as e:
        logger.error(f"[API] Erro ao conectar à Binance: {e}")
        return
    
    # Inicializar componentes
    order_manager = OrderManager(client)
    strategy = RandomizedTrendScalp(client)
    risk_manager = RiskManager(
        config.MAX_POSITION_SIZE_PERCENT,
        config.MAX_OPEN_POSITIONS,
        config.MAX_DAILY_LOSS_PERCENT,
        config.MAX_CONSECUTIVE_LOSSES
    )
    
    # Obter saldo inicial
    balance = order_manager.get_account_balance()
    risk_manager.set_initial_balance(balance)
    logger.info(f"[INIT] Saldo disponível: ${balance:.2f}")
    
    # Iniciar thread de monitoramento
    monitor_thread = threading.Thread(
        target=monitor_positions,
        args=(order_manager, risk_manager),
        daemon=True
    )
    monitor_thread.start()
    
    # Loop principal
    logger.info("[MAIN] Loop principal iniciado. Pressione Ctrl+C para parar.")
    
    while True:
        try:
            logger.info("\n" + "="*60)
            logger.info(f"[MAIN] Ciclo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info("="*60)
            
            # Verificar se pode abrir nova posição
            can_open, reason = risk_manager.can_open_position(open_positions)
            
            if not can_open:
                logger.info(f"[MAIN] Aguardando: {reason}")
                time.sleep(config.ENTRY_INTERVAL_SECONDS)
                continue
            
            # Detectar tendência
            trend = strategy.detect_trend()
            
            if trend == 'NONE':
                logger.info("[MAIN] Mercado lateral, aguardando tendência...")
                time.sleep(config.ENTRY_INTERVAL_SECONDS)
                continue
            
            # Escolher símbolo
            symbol = strategy.pick_symbol(trend)
            
            if not symbol:
                logger.info("[MAIN] Nenhum símbolo elegível, aguardando...")
                time.sleep(config.ENTRY_INTERVAL_SECONDS)
                continue
            
            # Obter plano de trade
            plan = strategy.get_trade_plan(symbol, trend)
            
            if not plan:
                logger.warning("[MAIN] Falha ao criar plano de trade")
                time.sleep(config.ENTRY_INTERVAL_SECONDS)
                continue
            
            # Aplicar jitter
            if plan['jitter'] > 0:
                logger.info(f"[MAIN] Aguardando jitter de {plan['jitter']}s...")
                time.sleep(plan['jitter'])
            
            # Abrir posição
            position = open_position(order_manager, risk_manager, plan)
            
            if position:
                with positions_lock:
                    open_positions.append(position)
                logger.info(f"[MAIN] Posições abertas: {len(open_positions)}/{config.MAX_OPEN_POSITIONS}")
            
            # Aguardar próximo ciclo
            logger.info(f"[MAIN] Próximo ciclo em {config.ENTRY_INTERVAL_SECONDS}s...")
            time.sleep(config.ENTRY_INTERVAL_SECONDS)
        
        except KeyboardInterrupt:
            logger.info("\n[MAIN] Bot interrompido pelo usuário")
            break
        
        except Exception as e:
            logger.error(f"[MAIN] Erro no loop principal: {e}")
            time.sleep(60)
    
    # Cleanup
    logger.info("[MAIN] Encerrando bot...")
    risk_manager.print_status()


if __name__ == "__main__":
    main()
