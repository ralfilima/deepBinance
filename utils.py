"""
Utilitários para o Bot Scalper
- Retry com exponential backoff
- Decorators para tratamento de erros
- Funções auxiliares
"""
import time
import logging
import functools
from decimal import Decimal, ROUND_DOWN
from typing import Callable, Any, Optional
import config

logger = logging.getLogger(__name__)

# ============================================================
# RETRY COM EXPONENTIAL BACKOFF
# ============================================================
def retry_with_backoff(
    max_retries: int = None,
    base_delay: float = None,
    max_delay: float = 60.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable = None
):
    """
    Decorator para retry com exponential backoff.
    
    Args:
        max_retries: Número máximo de tentativas
        base_delay: Delay inicial em segundos
        max_delay: Delay máximo em segundos
        exceptions: Tupla de exceções para capturar
        on_retry: Callback chamado em cada retry
    """
    if max_retries is None:
        max_retries = config.MAX_RETRIES
    if base_delay is None:
        base_delay = config.RETRY_DELAY_BASE
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        
                        logger.warning(
                            f"[RETRY {attempt + 1}/{max_retries}] {func.__name__} falhou: {e}. "
                            f"Tentando novamente em {delay:.1f}s..."
                        )
                        
                        if on_retry:
                            on_retry(attempt, e)
                        
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"[FALHOU] {func.__name__} falhou após {max_retries} tentativas: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def retry_api_call(func: Callable, *args, **kwargs) -> Any:
    """
    Executa uma função com retry.
    
    Args:
        func: Função a executar
        *args, **kwargs: Argumentos para a função
    
    Returns:
        Resultado da função
    """
    last_exception = None
    
    for attempt in range(config.MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            
            if attempt < config.MAX_RETRIES - 1:
                delay = min(config.RETRY_DELAY_BASE * (2 ** attempt), 60.0)
                logger.warning(f"[RETRY {attempt + 1}] Erro: {e}. Aguardando {delay:.1f}s...")
                time.sleep(delay)
    
    raise last_exception


# ============================================================
# FUNÇÕES DE ARREDONDAMENTO
# ============================================================
def round_quantity(quantity: float, step_size: float) -> float:
    """
    Arredonda quantidade baseado no step_size do símbolo.
    
    Args:
        quantity: Quantidade a arredondar
        step_size: Step size do símbolo (ex: 0.001)
    
    Returns:
        Quantidade arredondada
    """
    if step_size <= 0:
        return quantity
    
    step = Decimal(str(step_size))
    qty = Decimal(str(quantity))
    result = float((qty // step) * step)
    
    return result


def round_price(price: float, tick_size: float) -> float:
    """
    Arredonda preço baseado no tick_size do símbolo.
    
    Args:
        price: Preço a arredondar
        tick_size: Tick size do símbolo (ex: 0.01)
    
    Returns:
        Preço arredondado
    """
    if tick_size <= 0:
        return price
    
    tick = Decimal(str(tick_size))
    p = Decimal(str(price))
    result = float((p // tick) * tick)
    
    return result


def get_precision_from_step(step_size: float) -> int:
    """
    Obtém precisão decimal a partir do step_size.
    
    Args:
        step_size: Step size (ex: 0.001)
    
    Returns:
        Número de casas decimais (ex: 3)
    """
    step_str = str(step_size)
    if '.' in step_str:
        return len(step_str.split('.')[1].rstrip('0'))
    return 0


# ============================================================
# VALIDAÇÕES
# ============================================================
def validate_sl_tp_prices(
    side: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    current_price: float = None
) -> tuple:
    """
    Valida e corrige preços de SL/TP baseado na direção.
    
    Para LONG (BUY):
    - SL deve estar ABAIXO do preço de entrada
    - TP deve estar ACIMA do preço de entrada
    - stopPrice do SL deve estar ABAIXO do preço atual
    - stopPrice do TP deve estar ACIMA do preço atual
    
    Para SHORT (SELL):
    - SL deve estar ACIMA do preço de entrada
    - TP deve estar ABAIXO do preço de entrada
    - stopPrice do SL deve estar ACIMA do preço atual
    - stopPrice do TP deve estar ABAIXO do preço atual
    
    Args:
        side: 'BUY' ou 'SELL'
        entry_price: Preço de entrada
        sl_price: Preço do Stop Loss
        tp_price: Preço do Take Profit
        current_price: Preço atual (opcional)
    
    Returns:
        Tuple (sl_price, tp_price, is_valid, error_message)
    """
    if current_price is None:
        current_price = entry_price
    
    is_valid = True
    error_message = None
    
    if side == 'BUY':  # LONG
        # SL deve estar abaixo do preço
        if sl_price >= entry_price:
            error_message = f"LONG: SL ({sl_price}) deve ser menor que entrada ({entry_price})"
            is_valid = False
        
        # TP deve estar acima do preço
        if tp_price <= entry_price:
            error_message = f"LONG: TP ({tp_price}) deve ser maior que entrada ({entry_price})"
            is_valid = False
        
        # Validar contra preço atual
        if sl_price >= current_price:
            error_message = f"LONG: SL ({sl_price}) deve ser menor que preço atual ({current_price})"
            is_valid = False
        
        if tp_price <= current_price:
            error_message = f"LONG: TP ({tp_price}) deve ser maior que preço atual ({current_price})"
            is_valid = False
    
    else:  # SHORT (SELL)
        # SL deve estar acima do preço
        if sl_price <= entry_price:
            error_message = f"SHORT: SL ({sl_price}) deve ser maior que entrada ({entry_price})"
            is_valid = False
        
        # TP deve estar abaixo do preço
        if tp_price >= entry_price:
            error_message = f"SHORT: TP ({tp_price}) deve ser menor que entrada ({entry_price})"
            is_valid = False
        
        # Validar contra preço atual
        if sl_price <= current_price:
            error_message = f"SHORT: SL ({sl_price}) deve ser maior que preço atual ({current_price})"
            is_valid = False
        
        if tp_price >= current_price:
            error_message = f"SHORT: TP ({tp_price}) deve ser menor que preço atual ({current_price})"
            is_valid = False
    
    return sl_price, tp_price, is_valid, error_message


# ============================================================
# FORMATAÇÃO
# ============================================================
def format_price(price: float, precision: int = 4) -> str:
    """Formata preço para exibição"""
    return f"${price:,.{precision}f}"


def format_quantity(quantity: float, precision: int = 4) -> str:
    """Formata quantidade para exibição"""
    return f"{quantity:.{precision}f}"


def format_percent(value: float) -> str:
    """Formata porcentagem para exibição"""
    return f"{value:.2f}%"


# ============================================================
# LOGGING HELPERS
# ============================================================
def log_order_params(params: dict, prefix: str = ""):
    """Loga parâmetros de uma ordem de forma formatada"""
    logger.debug(f"{prefix} Parâmetros da ordem:")
    for key, value in params.items():
        logger.debug(f"  {key}: {value}")


def log_api_response(response: dict, prefix: str = ""):
    """Loga resposta da API de forma formatada"""
    if response:
        logger.debug(f"{prefix} Resposta da API:")
        for key, value in response.items():
            logger.debug(f"  {key}: {value}")
