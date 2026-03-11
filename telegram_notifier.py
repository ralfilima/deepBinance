"""
Telegram Notifier Module
Envia notificações em todas as etapas do bot
"""
import os
import requests
import logging
from datetime import datetime
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Notificador Telegram para acompanhar o bot em tempo real.
    """
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Inicializa o notificador.
        
        Args:
            bot_token: Token do bot Telegram
            chat_id: ID do chat para enviar mensagens
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID', '')
        self.enabled = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        if self.enabled and self.bot_token and self.chat_id:
            logger.info("[TELEGRAM] Notificações habilitadas")
        else:
            logger.info("[TELEGRAM] Notificações desabilitadas")
            self.enabled = False
    
    def _send_message(self, text: str, parse_mode: str = 'HTML') -> bool:
        """
        Envia mensagem para o Telegram.
        
        Args:
            text: Texto da mensagem
            parse_mode: Formato (HTML ou Markdown)
        
        Returns:
            True se enviou com sucesso
        """
        if not self.enabled:
            return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': text,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"[TELEGRAM] Erro ao enviar: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"[TELEGRAM] Falha ao enviar mensagem: {e}")
            return False
    
    # ============================================================
    # MENSAGENS DE SELEÇÃO
    # ============================================================
    
    def notify_scanning_started(self):
        """Notifica início do scan de mercado"""
        msg = """
🔍 <b>SCANNING MERCADO</b>

Iniciando análise do mercado...
Buscando TOP performers com persistência (1 min)
        """
        self._send_message(msg.strip())
    
    def notify_persistence_check(self, check_num: int, total_checks: int, top_coins: List[str]):
        """Notifica verificação de persistência"""
        coins_str = ", ".join(top_coins[:5])
        msg = f"""
⏳ <b>Verificação {check_num}/{total_checks}</b>

TOP 5 atual: {coins_str}
        """
        self._send_message(msg.strip())
    
    def notify_selection_complete(self, selection: List[Dict]):
        """Notifica seleção completa"""
        if not selection:
            msg = "❌ <b>SELEÇÃO FALHOU</b>\nNenhuma moeda passou no filtro de persistência"
            self._send_message(msg)
            return
        
        lines = ["🎯 <b>SELEÇÃO COMPLETA</b>\n", "Moedas selecionadas (persistência 1 min):\n"]
        
        for i, coin in enumerate(selection, 1):
            direction = "🟢 LONG" if coin.get('direction') == 'LONG' else "🔴 SHORT"
            lines.append(f"#{i} <b>{coin['symbol']}</b>")
            lines.append(f"   Score: {coin.get('score', 0):.0f} | {direction}")
            lines.append(f"   Var: {coin.get('price_change_pct', 0):+.2f}% | RSI: {coin.get('rsi', 50):.0f}")
            lines.append("")
        
        self._send_message("\n".join(lines))
    
    # ============================================================
    # MENSAGENS DE TRADE
    # ============================================================
    
    def notify_opening_positions(self, num_positions: int, side: str, capital: float):
        """Notifica abertura de posições"""
        emoji = "🟢" if side == "BUY" else "🔴"
        direction = "LONG" if side == "BUY" else "SHORT"
        
        msg = f"""
{emoji} <b>ABRINDO POSIÇÕES</b>

📊 {num_positions} posições {direction}
💰 Capital total: ${capital:.2f}
💵 Por posição: ${capital/num_positions:.2f}
        """
        self._send_message(msg.strip())
    
    def notify_position_opened(self, symbol: str, side: str, qty: float, price: float, capital: float):
        """Notifica posição aberta"""
        emoji = "🟢" if side == "BUY" else "🔴"
        direction = "LONG" if side == "BUY" else "SHORT"
        
        msg = f"""
{emoji} <b>POSIÇÃO ABERTA</b>

📈 {symbol}
🔄 {direction}
📊 Qty: {qty:.4f}
💵 Preço: ${price:.4f}
💰 Capital: ${capital:.2f}
        """
        self._send_message(msg.strip())
    
    def notify_all_positions_opened(self, positions: List[Dict], total_capital: float):
        """Notifica todas as posições abertas"""
        if not positions:
            return
        
        lines = ["✅ <b>TODAS POSIÇÕES ABERTAS</b>\n"]
        
        for pos in positions:
            emoji = "🟢" if pos['side'] == "BUY" else "🔴"
            lines.append(f"{emoji} {pos['symbol']}: {pos['quantity']:.4f} @ ${pos['entry_price']:.4f}")
        
        lines.append(f"\n💰 Capital total: ${total_capital:.2f}")
        
        self._send_message("\n".join(lines))
    
    # ============================================================
    # MENSAGENS DE MONITORAMENTO
    # ============================================================
    
    def notify_monitoring_update(self, total_pnl: float, pnl_percent: float, 
                                  tp_value: float, sl_value: float,
                                  positions: List[Dict] = None):
        """Notifica atualização de monitoramento"""
        pnl_emoji = "📈" if total_pnl >= 0 else "📉"
        
        lines = [f"{pnl_emoji} <b>MONITORAMENTO</b>\n"]
        
        if positions:
            for pos in positions[:5]:  # Limita a 5 posições
                emoji = "🟢" if pos.get('pnl', 0) >= 0 else "🔴"
                lines.append(f"{emoji} {pos['symbol']}: ${pos.get('pnl', 0):+.2f}")
        
        lines.append(f"\n💰 <b>P&L Total: ${total_pnl:+.2f} ({pnl_percent:+.2f}%)</b>")
        lines.append(f"🎯 TP: +${tp_value:.2f} | 🛡️ SL: -${sl_value:.2f}")
        
        # Barra visual
        total_range = tp_value + sl_value
        progress = ((total_pnl + sl_value) / total_range) * 100 if total_range > 0 else 50
        progress = max(0, min(100, progress))
        filled = int(progress / 10)
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(f"\n[{bar}] {progress:.0f}%")
        
        self._send_message("\n".join(lines))
    
    def notify_trend_reversal_warning(self, symbol: str, current_trend: str, signal: str):
        """Notifica alerta de reversão de tendência"""
        msg = f"""
⚠️ <b>ALERTA DE REVERSÃO</b>

📊 {symbol}
🔄 Tendência atual: {current_trend}
📉 Sinal: {signal}

Monitorando para possível fechamento...
        """
        self._send_message(msg.strip())
    
    def notify_smart_close(self, reason: str, pnl: float, pnl_percent: float):
        """Notifica fechamento inteligente"""
        emoji = "✅" if pnl >= 0 else "⚠️"
        
        msg = f"""
{emoji} <b>FECHAMENTO INTELIGENTE</b>

📝 Motivo: {reason}
💰 P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)
        """
        self._send_message(msg.strip())
    
    # ============================================================
    # MENSAGENS DE FECHAMENTO
    # ============================================================
    
    def notify_closing_positions(self, reason: str):
        """Notifica início de fechamento"""
        msg = f"""
🔄 <b>FECHANDO POSIÇÕES</b>

📝 Motivo: {reason}
        """
        self._send_message(msg.strip())
    
    def notify_position_closed(self, symbol: str, pnl: float, pnl_percent: float):
        """Notifica posição fechada"""
        emoji = "✅" if pnl >= 0 else "❌"
        
        msg = f"""
{emoji} <b>{symbol}</b>
P&L: ${pnl:+.2f} ({pnl_percent:+.2f}%)
        """
        self._send_message(msg.strip())
    
    def notify_all_closed(self, result: str, total_pnl: float, pnl_percent: float,
                          positions_detail: List[Dict] = None):
        """Notifica todas posições fechadas"""
        if result == 'TP':
            emoji = "🎉"
            title = "TAKE PROFIT"
        elif result == 'SL':
            emoji = "😔"
            title = "STOP LOSS"
        elif result == 'SMART':
            emoji = "🧠"
            title = "FECHAMENTO INTELIGENTE"
        else:
            emoji = "🔄"
            title = "FECHAMENTO MANUAL"
        
        lines = [f"{emoji} <b>{title}</b>\n"]
        
        if positions_detail:
            for pos in positions_detail:
                p_emoji = "✅" if pos.get('pnl', 0) >= 0 else "❌"
                lines.append(f"{p_emoji} {pos['symbol']}: ${pos.get('pnl', 0):+.2f}")
        
        lines.append(f"\n{'='*20}")
        lines.append(f"💰 <b>P&L TOTAL: ${total_pnl:+.2f}</b>")
        lines.append(f"📊 <b>({pnl_percent:+.2f}%)</b>")
        
        self._send_message("\n".join(lines))
    
    # ============================================================
    # MENSAGENS DE ESTATÍSTICAS
    # ============================================================
    
    def notify_daily_stats(self, stats: Dict):
        """Notifica estatísticas do dia"""
        win_rate = stats.get('win_rate', 0)
        win_emoji = "🏆" if win_rate >= 60 else "📊"
        pnl_emoji = "📈" if stats.get('total_pnl', 0) >= 0 else "📉"
        
        msg = f"""
{win_emoji} <b>ESTATÍSTICAS DO DIA</b>

📅 Data: {stats.get('date', 'N/A')}
🔄 Entradas: {stats.get('entries', 0)}/{stats.get('max_entries', 5)}
✅ Wins: {stats.get('wins', 0)}
❌ Losses: {stats.get('losses', 0)}
📊 Win Rate: {win_rate:.1f}%
{pnl_emoji} P&L Dia: ${stats.get('total_pnl', 0):+.2f}
        """
        self._send_message(msg.strip())
    
    # ============================================================
    # MENSAGENS DE SISTEMA
    # ============================================================
    
    def notify_bot_started(self, mode: str, capital: float, tp: float, sl: float):
        """Notifica bot iniciado"""
        msg = f"""
🤖 <b>BOT INICIADO</b>

📊 Modo: {mode}
💰 Capital: ${capital:.2f}
🎯 TP: +{tp}%
🛡️ SL: -{sl}%
⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        """
        self._send_message(msg.strip())
    
    def notify_bot_stopped(self, reason: str):
        """Notifica bot parado"""
        msg = f"""
🛑 <b>BOT PARADO</b>

📝 Motivo: {reason}
⏰ {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
        """
        self._send_message(msg.strip())
    
    def notify_error(self, error: str, context: str = ""):
        """Notifica erro"""
        msg = f"""
❌ <b>ERRO</b>

📝 {error}
🔍 Contexto: {context if context else 'N/A'}
⏰ {datetime.now().strftime('%H:%M:%S')}
        """
        self._send_message(msg.strip())
    
    def send_custom(self, message: str):
        """Envia mensagem customizada"""
        self._send_message(message)


# Instância global para uso fácil
_notifier = None

def get_notifier() -> TelegramNotifier:
    """Obtém instância global do notificador"""
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


def notify(message: str):
    """Atalho para enviar mensagem"""
    get_notifier().send_custom(message)
