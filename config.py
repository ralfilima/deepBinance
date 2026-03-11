"""
Configurações do Bot Scalper para Binance Futures
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# BINANCE API CONFIGURATION
# ============================================================
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_SECRET_KEY = os.getenv('BINANCE_SECRET_KEY', '')
BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

# URLs da API (determinado automaticamente)
if BINANCE_TESTNET:
    BINANCE_BASE_URL = 'https://testnet.binancefuture.com'
    BINANCE_WS_URL = 'wss://stream.binancefuture.com'
else:
    BINANCE_BASE_URL = 'https://fapi.binance.com'
    BINANCE_WS_URL = 'wss://fstream.binance.com'

# Debug Mode (sem filtros de estratégia, apenas para testar ordens)
DEBUG_MODE = os.getenv('DEBUG_MODE', 'false').lower() == 'true'

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
BASE_SYMBOL = 'BTCUSDT'
SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'ADAUSDT',
    'XRPUSDT', 'DOGEUSDT', 'DOTUSDT', 'MATICUSDT', 'AVAXUSDT'
]

# ============================================================
# RISK MANAGEMENT
# ============================================================
MAX_POSITION_SIZE_PERCENT = float(os.getenv('MAX_POSITION_SIZE_PERCENT', '1.0'))
MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', '5'))
MAX_DAILY_LOSS_PERCENT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '3.0'))
MAX_CONSECUTIVE_LOSSES = int(os.getenv('MAX_CONSECUTIVE_LOSSES', '3'))

# ============================================================
# ENTRY/EXIT PARAMETERS
# ============================================================
ENTRY_INTERVAL_SECONDS = int(os.getenv('ENTRY_INTERVAL_SECONDS', '600'))  # 10 minutos
JITTER_MAX_SECONDS = int(os.getenv('JITTER_MAX_SECONDS', '60'))

# Take Profit e Stop Loss (em %)
TP_PERCENT_LONG = float(os.getenv('TP_PERCENT_LONG', '1.05'))
SL_PERCENT_LONG = float(os.getenv('SL_PERCENT_LONG', '0.70'))
TP_PERCENT_SHORT = float(os.getenv('TP_PERCENT_SHORT', '1.05'))
SL_PERCENT_SHORT = float(os.getenv('SL_PERCENT_SHORT', '0.70'))

# Time Stop (minutos)
TIME_STOP_MIN = int(os.getenv('TIME_STOP_MIN', '12'))
TIME_STOP_MAX = int(os.getenv('TIME_STOP_MAX', '22'))

# ============================================================
# CONNECTION SETTINGS
# ============================================================
API_TIMEOUT = int(os.getenv('API_TIMEOUT', '30'))  # segundos
MAX_RETRIES = int(os.getenv('MAX_RETRIES', '5'))
RETRY_DELAY_BASE = float(os.getenv('RETRY_DELAY_BASE', '2.0'))  # segundos

# ============================================================
# LOGGING
# ============================================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('LOG_FILE', 'bot.log')

# ============================================================
# VALIDATION
# ============================================================
def validate_config():
    """Valida configurações críticas"""
    errors = []
    
    if not BINANCE_API_KEY:
        errors.append("BINANCE_API_KEY não configurada")
    if not BINANCE_SECRET_KEY:
        errors.append("BINANCE_SECRET_KEY não configurada")
    
    if MAX_POSITION_SIZE_PERCENT <= 0 or MAX_POSITION_SIZE_PERCENT > 100:
        errors.append("MAX_POSITION_SIZE_PERCENT deve estar entre 0 e 100")
    
    if TP_PERCENT_LONG <= 0:
        errors.append("TP_PERCENT_LONG deve ser maior que 0")
    if SL_PERCENT_LONG <= 0:
        errors.append("SL_PERCENT_LONG deve ser maior que 0")
    
    return errors

def print_config():
    """Imprime configurações atuais (sem expor secrets)"""
    mode = "TESTNET" if BINANCE_TESTNET else "MAINNET (PRODUÇÃO)"
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    CONFIGURAÇÕES DO BOT                       ║
╠══════════════════════════════════════════════════════════════╣
║  Modo: {mode:<54}║
║  URL: {BINANCE_BASE_URL:<55}║
║  Debug: {'ATIVADO' if DEBUG_MODE else 'DESATIVADO':<54}║
╠══════════════════════════════════════════════════════════════╣
║  Max Posições: {MAX_OPEN_POSITIONS:<46}║
║  Tamanho Posição: {MAX_POSITION_SIZE_PERCENT}% do capital{' '*34}║
║  TP Long: {TP_PERCENT_LONG}% | SL Long: {SL_PERCENT_LONG}%{' '*30}║
║  TP Short: {TP_PERCENT_SHORT}% | SL Short: {SL_PERCENT_SHORT}%{' '*29}║
║  Time Stop: {TIME_STOP_MIN}-{TIME_STOP_MAX} minutos{' '*37}║
╚══════════════════════════════════════════════════════════════╝
""")
