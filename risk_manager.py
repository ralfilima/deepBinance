"""
Gerenciador de Risco para o Bot Scalper
"""
import logging
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Gerencia risco do bot de trading.
    
    Responsabilidades:
    - Limitar número de posições abertas
    - Controlar perda diária máxima
    - Rastrear perdas consecutivas
    - Calcular tamanho da posição
    """
    
    def __init__(
        self,
        max_position_percent: float,
        max_open_positions: int,
        max_daily_loss_percent: float,
        max_consecutive_losses: int
    ):
        """
        Inicializa o gerenciador de risco.
        
        Args:
            max_position_percent: % máximo do capital por posição
            max_open_positions: Número máximo de posições simultâneas
            max_daily_loss_percent: % máximo de perda diária
            max_consecutive_losses: Número máximo de perdas seguidas
        """
        self.max_position_percent = max_position_percent
        self.max_open_positions = max_open_positions
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_consecutive_losses = max_consecutive_losses
        
        # Estado interno
        self.consecutive_losses = 0
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_wins = 0
        self.daily_losses = 0
        self.last_reset = datetime.now().date()
        self.initial_balance = 0.0
        
        logger.info(
            f"[RISK] Inicializado: max_pos={max_open_positions}, "
            f"max_size={max_position_percent}%, max_loss={max_daily_loss_percent}%"
        )
    
    def _reset_daily_stats(self):
        """Reseta estatísticas diárias à meia-noite"""
        if datetime.now().date() > self.last_reset:
            logger.info("[RISK] Reset diário das estatísticas")
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.daily_wins = 0
            self.daily_losses = 0
            self.consecutive_losses = 0
            self.last_reset = datetime.now().date()
    
    def set_initial_balance(self, balance: float):
        """Define saldo inicial para cálculos de perda %"""
        self.initial_balance = balance
        logger.info(f"[RISK] Saldo inicial: ${balance:,.2f}")
    
    def can_open_position(self, current_positions: List) -> tuple:
        """
        Verifica se pode abrir nova posição.
        
        Args:
            current_positions: Lista de posições abertas
        
        Returns:
            Tuple (pode_abrir, motivo)
        """
        self._reset_daily_stats()
        
        # Verifica número de posições
        if len(current_positions) >= self.max_open_positions:
            reason = f"Máximo de {self.max_open_positions} posições atingido"
            logger.warning(f"[RISK] {reason}")
            return False, reason
        
        # Verifica perdas consecutivas
        if self.consecutive_losses >= self.max_consecutive_losses:
            reason = f"Máximo de {self.max_consecutive_losses} perdas consecutivas"
            logger.warning(f"[RISK] {reason}. Bot pausado.")
            return False, reason
        
        # Verifica perda diária
        if self.initial_balance > 0:
            loss_percent = abs(self.daily_pnl) / self.initial_balance * 100
            if self.daily_pnl < 0 and loss_percent >= self.max_daily_loss_percent:
                reason = f"Perda diária de {loss_percent:.2f}% atingiu limite de {self.max_daily_loss_percent}%"
                logger.warning(f"[RISK] {reason}")
                return False, reason
        
        return True, "OK"
    
    def calculate_position_size(
        self, 
        balance: float, 
        entry_price: float, 
        sl_price: float,
        leverage: int = 1
    ) -> float:
        """
        Calcula tamanho da posição baseado no risco.
        
        Fórmula: quantidade = (saldo * % risco) / distância até SL
        
        Args:
            balance: Saldo disponível
            entry_price: Preço de entrada
            sl_price: Preço do Stop Loss
            leverage: Alavancagem (default: 1)
        
        Returns:
            Quantidade a ser negociada
        """
        if balance <= 0:
            logger.warning("[RISK] Saldo insuficiente para calcular posição")
            return 0.0
        
        price_diff = abs(entry_price - sl_price)
        
        if price_diff == 0:
            logger.warning("[RISK] Diferença de preço é zero, não é possível calcular posição")
            return 0.0
        
        # Valor de risco = % do capital
        risk_amount = balance * (self.max_position_percent / 100)
        
        # Quantidade = risco / distância de preço
        quantity = risk_amount / price_diff
        
        # Ajuste por alavancagem
        quantity *= leverage
        
        logger.debug(
            f"[RISK] Cálculo posição: saldo=${balance:.2f}, risco=${risk_amount:.2f}, "
            f"diff=${price_diff:.4f}, qty={quantity:.6f}"
        )
        
        return quantity
    
    def record_trade(self, pnl: float, symbol: str = ""):
        """
        Registra resultado de um trade.
        
        Args:
            pnl: Profit/Loss do trade
            symbol: Símbolo negociado
        """
        self.daily_pnl += pnl
        self.daily_trades += 1
        
        if pnl >= 0:
            self.daily_wins += 1
            self.consecutive_losses = 0
            status = "✅ GANHO"
        else:
            self.daily_losses += 1
            self.consecutive_losses += 1
            status = "❌ PERDA"
        
        win_rate = (self.daily_wins / self.daily_trades * 100) if self.daily_trades > 0 else 0
        
        logger.info(
            f"[TRADE] {status} {symbol}: ${pnl:+.2f} | "
            f"PnL Diário: ${self.daily_pnl:+.2f} | "
            f"W/L: {self.daily_wins}/{self.daily_losses} ({win_rate:.1f}%) | "
            f"Perdas Consec.: {self.consecutive_losses}"
        )
    
    def get_status(self) -> dict:
        """Retorna status atual do gerenciador de risco"""
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'daily_wins': self.daily_wins,
            'daily_losses': self.daily_losses,
            'consecutive_losses': self.consecutive_losses,
            'win_rate': (self.daily_wins / self.daily_trades * 100) if self.daily_trades > 0 else 0,
            'can_trade': self.consecutive_losses < self.max_consecutive_losses
        }
    
    def print_status(self):
        """Imprime status formatado"""
        status = self.get_status()
        print(f"""
╔════════════════════════════════════════╗
║          STATUS DO RISCO                ║
╠════════════════════════════════════════╣
║  PnL Diário:       ${status['daily_pnl']:>+12.2f}      ║
║  Trades Hoje:      {status['daily_trades']:>12}      ║
║  Ganhos:           {status['daily_wins']:>12}      ║
║  Perdas:           {status['daily_losses']:>12}      ║
║  Win Rate:         {status['win_rate']:>11.1f}%      ║
║  Perdas Consec.:   {status['consecutive_losses']:>12}      ║
║  Pode Operar:      {'SIM' if status['can_trade'] else 'NÃO':>12}      ║
╚════════════════════════════════════════╝
""")
