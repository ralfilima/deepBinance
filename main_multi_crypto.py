#!/usr/bin/env python3
"""
🤖 MULTI-CRYPTO BOT V3 - MELHORIAS ESTRATÉGICAS

Bot que opera 5 criptomoedas simultaneamente com:
- ✅ Lucro Líquido Real (desconta taxas + slippage)
- ✅ Filtro de Correlação (evita alavancagem oculta)
- ✅ Ordens IOC (fechamento rápido)
- ✅ Filtro de Sobrecompra (RSI + Bollinger)
- ✅ Dashboard com Drawdown
- ✅ TP Individual (+0.7%) - fecha UMA posição
- ✅ Regra 3/5 (+0.3%) - fecha TODAS se 3+ positivas
- ✅ Notificações Telegram
- ✅ Interface colorida
- ✅ Funciona em TESTNET e MAINNET
"""
import os
import sys
import time
import signal
import logging
from datetime import datetime
from typing import Optional

# Cores no terminal
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    HAS_COLORS = True
except ImportError:
    HAS_COLORS = False
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Back:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""

from dotenv import load_dotenv
from binance.client import Client

# Carrega .env
load_dotenv()

from multi_crypto_strategy import (
    MultiCryptoStrategy, 
    INDIVIDUAL_TP_PERCENT, 
    RULE_3_5_THRESHOLD,
    TOTAL_COST_RATE,
    MAX_CORRELATION
)
from top_performers import TopPerformersSelector, format_selection_table
from telegram_notifier import TelegramNotifier
from trend_analyzer import TrendAnalyzer
from correlation_filter import CorrelationFilter

# ============================================================
# VARIÁVEL GLOBAL PARA CONTROLE DE INTERRUPÇÃO (Ctrl+C)
# ============================================================
SHOULD_STOP = False
ACTIVE_STRATEGY = None

def setup_global_signal_handler():
    """Configura signal handler global para Ctrl+C"""
    global SHOULD_STOP, ACTIVE_STRATEGY
    
    def global_signal_handler(signum, frame):
        global SHOULD_STOP, ACTIVE_STRATEGY
        SHOULD_STOP = True
        print(f"\n{Fore.YELLOW}⚠️  Ctrl+C detectado! Encerrando...{Style.RESET_ALL}")
        
        # Fecha posições se houver estratégia ativa
        if ACTIVE_STRATEGY and ACTIVE_STRATEGY.positions:
            print(f"{Fore.YELLOW}🔄 Fechando posições...{Style.RESET_ALL}")
            ACTIVE_STRATEGY.force_close_all_positions("INTERRUPÇÃO (Ctrl+C)")
        
        # Força saída imediata se pressionado duas vezes
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(1))
    
    signal.signal(signal.SIGINT, global_signal_handler)
    signal.signal(signal.SIGTERM, global_signal_handler)

# ============================================================
# LOGGING COLORIDO
# ============================================================
class ColoredFormatter(logging.Formatter):
    """Formatter com cores"""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.WHITE,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Style.BRIGHT,
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, Fore.WHITE)
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        record.msg = f"{color}{record.msg}{Style.RESET_ALL}"
        return super().format(record)


# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s │ %(levelname)-8s │ %(message)s',
    handlers=[
        logging.FileHandler('multi_crypto_v3.log', encoding='utf-8'),
    ]
)

# Handler colorido para console
console_handler = logging.StreamHandler()
console_handler.setFormatter(ColoredFormatter('%(asctime)s │ %(levelname)-8s │ %(message)s'))
logging.getLogger().addHandler(console_handler)

logger = logging.getLogger(__name__)


# ============================================================
# CONFIGURAÇÕES PADRÃO V3
# ============================================================
DEFAULT_CONFIG = {
    'capital_per_crypto': 500.0,
    'tp_percent': 0.5,
    'sl_percent': 0.4,
    'max_daily_entries': 5,
    'testnet': True,
    'use_persistence': True,
    'smart_close': True,
    # Novos V3
    'use_correlation_filter': True,
    'use_overbought_filter': True
}


# ============================================================
# FUNÇÕES DE INTERFACE
# ============================================================
def clear_screen():
    """Limpa a tela"""
    os.system('cls' if os.name == 'nt' else 'clear')


def print_banner():
    """Banner principal"""
    banner = f"""
{Fore.CYAN}{Style.BRIGHT}
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   {Fore.YELLOW}███╗   ███╗██╗   ██╗██╗  ████████╗██╗      ██████╗██████╗ ██╗   ██╗{Fore.CYAN}   ║
║   {Fore.YELLOW}████╗ ████║██║   ██║██║  ╚══██╔══╝██║     ██╔════╝██╔══██╗╚██╗ ██╔╝{Fore.CYAN}   ║
║   {Fore.YELLOW}██╔████╔██║██║   ██║██║     ██║   ██║     ██║     ██████╔╝ ╚████╔╝{Fore.CYAN}    ║
║   {Fore.YELLOW}██║╚██╔╝██║██║   ██║██║     ██║   ██║     ██║     ██╔══██╗  ╚██╔╝{Fore.CYAN}     ║
║   {Fore.YELLOW}██║ ╚═╝ ██║╚██████╔╝███████╗██║   ██║     ╚██████╗██║  ██║   ██║{Fore.CYAN}      ║
║   {Fore.YELLOW}╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝   ╚═╝      ╚═════╝╚═╝  ╚═╝   ╚═╝{Fore.CYAN}      ║
║                                                                              ║
║   {Fore.WHITE}🤖 BOT V3 ESTRATÉGICO - 5 CRIPTOS SIMULTÂNEAS{Fore.CYAN}                        ║
║   {Fore.GREEN}✅ Lucro Líquido │ Correlação │ RSI/BB │ Drawdown{Fore.CYAN}                     ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}"""
    print(banner)


def print_config(config: dict):
    """Exibe configuração atual"""
    total = config['capital_per_crypto'] * 5
    tp_value = total * (config['tp_percent'] / 100)
    sl_value = total * (config['sl_percent'] / 100)
    
    mode_color = Fore.YELLOW if config['testnet'] else Fore.RED + Style.BRIGHT
    mode = "TESTNET (Seguro)" if config['testnet'] else "⚠️ MAINNET (REAL)"
    
    persist = f"{Fore.GREEN}✅ Ativo" if config['use_persistence'] else f"{Fore.RED}❌ Desativado"
    smart = f"{Fore.GREEN}✅ Ativo" if config['smart_close'] else f"{Fore.RED}❌ Desativado"
    
    print(f"""
{Fore.CYAN}┌──────────────────────────────────────────────────────────────────────────────┐
│  {Fore.WHITE}📊 CONFIGURAÇÃO ATUAL{Fore.CYAN}                                                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  {Fore.WHITE}Modo:{Fore.CYAN}                  {mode_color}{mode:<50}{Fore.CYAN}│
│  {Fore.WHITE}Capital por cripto:{Fore.CYAN}   {Fore.GREEN}${config['capital_per_crypto']:<47.2f}{Fore.CYAN}│
│  {Fore.WHITE}Capital total:{Fore.CYAN}        {Fore.GREEN}${total:<47.2f}{Fore.CYAN}│
│  {Fore.WHITE}Take Profit Global:{Fore.CYAN}   {Fore.GREEN}+{config['tp_percent']}% (+${tp_value:.2f}){' '*36}{Fore.CYAN}│
│  {Fore.WHITE}Stop Loss Global:{Fore.CYAN}     {Fore.RED}-{config['sl_percent']}% (-${sl_value:.2f}){' '*36}{Fore.CYAN}│
│  {Fore.WHITE}Max entradas/dia:{Fore.CYAN}     {Fore.YELLOW}{config['max_daily_entries']:<48}{Fore.CYAN}│
├──────────────────────────────────────────────────────────────────────────────┤
│  {Fore.YELLOW}📍 REGRAS V3 ATIVAS:{Fore.CYAN}                                                       │
│  {Fore.WHITE}TP Individual:{Fore.CYAN}        {Fore.GREEN}+{INDIVIDUAL_TP_PERCENT}% → fecha UMA posição{' '*32}{Fore.CYAN}│
│  {Fore.WHITE}Regra 3/5:{Fore.CYAN}            {Fore.GREEN}+{RULE_3_5_THRESHOLD}% → fecha TODAS se 3+ positivas{' '*22}{Fore.CYAN}│
│  {Fore.WHITE}Custos por trade:{Fore.CYAN}     {Fore.YELLOW}~{TOTAL_COST_RATE*100:.2f}% (taxas + slippage){' '*26}{Fore.CYAN}│
├──────────────────────────────────────────────────────────────────────────────┤
│  {Fore.YELLOW}🆕 FILTROS V3:{Fore.CYAN}                                                              │
│  {Fore.WHITE}Correlação:{Fore.CYAN}           {Fore.GREEN if config.get('use_correlation_filter') else Fore.RED}{'✅ Ativo' if config.get('use_correlation_filter') else '❌ Inativo'} (máx {MAX_CORRELATION*100:.0f}%){' '*26}{Fore.CYAN}│
│  {Fore.WHITE}Sobrecompra:{Fore.CYAN}          {Fore.GREEN if config.get('use_overbought_filter') else Fore.RED}{'✅ Ativo' if config.get('use_overbought_filter') else '❌ Inativo'} (RSI 70/30 + Bollinger){' '*14}{Fore.CYAN}│
├──────────────────────────────────────────────────────────────────────────────┤
│  {Fore.WHITE}Filtro Persistência:{Fore.CYAN}  {persist}{Fore.CYAN}                                           │
│  {Fore.WHITE}Fechamento Intelig.:{Fore.CYAN}  {smart}{Fore.CYAN}                                           │
└──────────────────────────────────────────────────────────────────────────────┘
{Style.RESET_ALL}""")


def print_menu():
    """Menu principal"""
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}MENU PRINCIPAL{Fore.CYAN}                                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  {Fore.GREEN}[1]{Fore.WHITE} 🚀 Executar Estratégia (com análise LONG/SHORT){Fore.CYAN}                       ║
║  {Fore.GREEN}[2]{Fore.WHITE} 🤖 Modo Automático (até limite diário){Fore.CYAN}                               ║
║  {Fore.GREEN}[3]{Fore.WHITE} 🔍 Visualizar TOP 5 (sem executar){Fore.CYAN}                                   ║
║  {Fore.GREEN}[4]{Fore.WHITE} ⚙️  Configurar Parâmetros{Fore.CYAN}                                             ║
║  {Fore.GREEN}[5]{Fore.WHITE} 📊 Ver Estatísticas da Conta{Fore.CYAN}                                         ║
║  {Fore.GREEN}[6]{Fore.WHITE} 📱 Testar Telegram{Fore.CYAN}                                                   ║
║  {Fore.GREEN}[7]{Fore.WHITE} 🧹 Limpar Posições Abertas{Fore.CYAN}                                           ║
║  {Fore.MAGENTA}[8]{Fore.WHITE} 🔬 Backtest (testar estratégia com dados históricos){Fore.CYAN}                ║
║  {Fore.RED}[0]{Fore.WHITE} 🚪 Sair{Fore.CYAN}                                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")


def print_success(msg: str):
    print(f"{Fore.GREEN}✅ {msg}{Style.RESET_ALL}")


def print_error(msg: str):
    print(f"{Fore.RED}❌ {msg}{Style.RESET_ALL}")


def print_warning(msg: str):
    print(f"{Fore.YELLOW}⚠️  {msg}{Style.RESET_ALL}")


def print_info(msg: str):
    print(f"{Fore.CYAN}ℹ️  {msg}{Style.RESET_ALL}")


# ============================================================
# FUNÇÕES PRINCIPAIS
# ============================================================
def get_client(config: dict) -> Optional[Client]:
    """Cria cliente Binance baseado no modo"""
    if config['testnet']:
        api_key = os.getenv('BINANCE_TESTNET_API_KEY', '')
        secret = os.getenv('BINANCE_TESTNET_SECRET', '')
    else:
        api_key = os.getenv('BINANCE_API_KEY', '')
        secret = os.getenv('BINANCE_API_SECRET', '')
    
    if not api_key or not secret:
        mode = "TESTNET" if config['testnet'] else "MAINNET"
        print_error(f"Credenciais {mode} não configuradas no .env")
        return None
    
    try:
        client = Client(api_key, secret, testnet=config['testnet'])
        client.futures_time()  # Testa conexão
        return client
    except Exception as e:
        print_error(f"Erro ao conectar: {e}")
        return None


def choose_network() -> dict:
    """Menu inicial para escolher rede"""
    clear_screen()
    print_banner()
    
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}ESCOLHA O MODO DE OPERAÇÃO{Fore.CYAN}                                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  {Fore.GREEN}[1]{Fore.WHITE} 🧪 TESTNET (Recomendado para testes){Fore.CYAN}                                  ║
║      └─ Dinheiro fictício, sem risco{Fore.CYAN}                                        ║
║  {Fore.RED}[2]{Fore.WHITE} 💰 MAINNET (Produção){Fore.CYAN}                                                  ║
║      └─ {Fore.RED}⚠️  DINHEIRO REAL - USE COM CUIDADO!{Fore.CYAN}                                  ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")
    
    choice = input(f"{Fore.YELLOW}Escolha [1]: {Style.RESET_ALL}").strip()
    
    config = DEFAULT_CONFIG.copy()
    
    if choice == '2':
        print_warning("\n⚠️  VOCÊ ESTÁ PRESTES A USAR DINHEIRO REAL!")
        confirm = input(f"{Fore.RED}Digite 'CONFIRMO' para continuar: {Style.RESET_ALL}").strip()
        if confirm == 'CONFIRMO':
            config['testnet'] = False
            print_warning("Modo MAINNET ativado!")
        else:
            print_info("Mantendo TESTNET por segurança")
            config['testnet'] = True
    else:
        config['testnet'] = True
        print_success("Modo TESTNET selecionado")
    
    time.sleep(1)
    return config


def configure_settings(config: dict) -> dict:
    """Menu de configuração"""
    while True:
        clear_screen()
        print_banner()
        print_config(config)
        
        print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}CONFIGURAR PARÂMETROS{Fore.CYAN}                                                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  {Fore.GREEN}[1]{Fore.WHITE} Alterar capital por cripto{Fore.CYAN}                                            ║
║  {Fore.GREEN}[2]{Fore.WHITE} Alterar Take Profit Global %{Fore.CYAN}                                          ║
║  {Fore.GREEN}[3]{Fore.WHITE} Alterar Stop Loss Global %{Fore.CYAN}                                            ║
║  {Fore.GREEN}[4]{Fore.WHITE} Alterar máximo de entradas diárias{Fore.CYAN}                                    ║
║  {Fore.GREEN}[5]{Fore.WHITE} Alternar TESTNET/MAINNET{Fore.CYAN}                                              ║
║  {Fore.GREEN}[6]{Fore.WHITE} Alternar Filtro de Persistência{Fore.CYAN}                                       ║
║  {Fore.GREEN}[7]{Fore.WHITE} Alternar Fechamento Inteligente{Fore.CYAN}                                       ║
║  {Fore.RED}[0]{Fore.WHITE} Voltar ao menu principal{Fore.CYAN}                                               ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")
        
        choice = input(f"{Fore.YELLOW}Escolha: {Style.RESET_ALL}").strip()
        
        if choice == '1':
            try:
                val = float(input(f"{Fore.CYAN}Capital por cripto ($): {Style.RESET_ALL}"))
                if val >= 50:
                    config['capital_per_crypto'] = val
                    print_success(f"Capital atualizado para ${val:.2f}")
                else:
                    print_error("Capital mínimo é $50")
            except ValueError:
                print_error("Valor inválido")
        
        elif choice == '2':
            try:
                val = float(input(f"{Fore.CYAN}Take Profit Global (%): {Style.RESET_ALL}"))
                if 0.1 <= val <= 10:
                    config['tp_percent'] = val
                    print_success(f"TP atualizado para {val}%")
                else:
                    print_error("TP deve estar entre 0.1% e 10%")
            except ValueError:
                print_error("Valor inválido")
        
        elif choice == '3':
            try:
                val = float(input(f"{Fore.CYAN}Stop Loss Global (%): {Style.RESET_ALL}"))
                if 0.1 <= val <= 10:
                    config['sl_percent'] = val
                    print_success(f"SL atualizado para {val}%")
                else:
                    print_error("SL deve estar entre 0.1% e 10%")
            except ValueError:
                print_error("Valor inválido")
        
        elif choice == '4':
            try:
                val = int(input(f"{Fore.CYAN}Máximo de entradas diárias: {Style.RESET_ALL}"))
                if 1 <= val <= 20:
                    config['max_daily_entries'] = val
                    print_success(f"Máximo atualizado para {val}")
                else:
                    print_error("Deve estar entre 1 e 20")
            except ValueError:
                print_error("Valor inválido")
        
        elif choice == '5':
            if not config['testnet']:
                config['testnet'] = True
                print_success("Alterado para TESTNET")
            else:
                print_warning("⚠️  VOCÊ ESTÁ PRESTES A USAR DINHEIRO REAL!")
                confirm = input(f"{Fore.RED}Digite 'CONFIRMO' para continuar: {Style.RESET_ALL}").strip()
                if confirm == 'CONFIRMO':
                    config['testnet'] = False
                    print_warning("Alterado para MAINNET!")
                else:
                    print_info("Mantendo TESTNET")
        
        elif choice == '6':
            config['use_persistence'] = not config['use_persistence']
            status = "ATIVADO" if config['use_persistence'] else "DESATIVADO"
            print_info(f"Filtro de persistência {status}")
        
        elif choice == '7':
            config['smart_close'] = not config['smart_close']
            status = "ATIVADO" if config['smart_close'] else "DESATIVADO"
            print_info(f"Fechamento inteligente {status}")
        
        elif choice == '0':
            break
        
        if choice != '0':
            input(f"\n{Fore.CYAN}Pressione Enter para continuar...{Style.RESET_ALL}")
    
    return config


def preview_selection(client: Client, config: dict):
    """Visualiza seleção sem executar"""
    clear_screen()
    print_banner()
    
    print_info("Analisando mercado para selecionar TOP 5 criptos...")
    print_info(f"Filtro de persistência: {'SIM' if config['use_persistence'] else 'NÃO'}\n")
    
    selector = TopPerformersSelector(client, config['testnet'])
    analyzer = TrendAnalyzer(client)
    
    try:
        if config['use_persistence']:
            selection = selector.select_with_persistence(n=5, checks=3, interval_seconds=20)
        else:
            selection = selector.select_top_n(n=5)
        
        if selection:
            # Adiciona análise de direção
            for coin in selection:
                try:
                    analysis = analyzer.analyze(coin['symbol'])
                    coin['direction'] = analysis['direction']
                except:
                    coin['direction'] = 'LONG'
            
            print(format_selection_table(selection, with_direction=True))
            
            print(f"\n{Fore.CYAN}Análise de tendência:{Style.RESET_ALL}")
            for coin in selection:
                dir_color = Fore.GREEN if coin['direction'] == 'LONG' else Fore.RED
                print(f"  {coin['symbol']}: {dir_color}{coin['direction']}{Style.RESET_ALL}")
        else:
            print_error("Não foi possível obter seleção")
    except Exception as e:
        print_error(f"Erro: {e}")
    
    input(f"\n{Fore.CYAN}Pressione Enter para voltar ao menu...{Style.RESET_ALL}")


def clean_positions(client: Client, config: dict):
    """Limpa posições abertas"""
    clear_screen()
    print_banner()
    
    print_info("Verificando posições abertas na conta...\n")
    
    strategy = MultiCryptoStrategy(
        client=client,
        capital_per_crypto=config['capital_per_crypto'],
        tp_percent=config['tp_percent'],
        sl_percent=config['sl_percent'],
        max_daily_entries=config['max_daily_entries'],
        testnet=config['testnet'],
        telegram=None
    )
    
    strategy.check_and_close_existing_positions()
    
    input(f"\n{Fore.CYAN}Pressione Enter para voltar ao menu...{Style.RESET_ALL}")


def run_strategy(client: Client, config: dict, telegram: TelegramNotifier):
    """Executa a estratégia"""
    global ACTIVE_STRATEGY
    
    clear_screen()
    print_banner()
    
    strategy = MultiCryptoStrategy(
        client=client,
        capital_per_crypto=config['capital_per_crypto'],
        tp_percent=config['tp_percent'],
        sl_percent=config['sl_percent'],
        max_daily_entries=config['max_daily_entries'],
        testnet=config['testnet'],
        telegram=telegram
    )
    
    ACTIVE_STRATEGY = strategy
    
    # Valida capital
    valid, msg = strategy.validate_capital()
    print_info(f"💰 {msg}")
    
    if not valid:
        ACTIVE_STRATEGY = None
        input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")
        return
    
    # Mostra regras ativas
    print(f"\n{Fore.YELLOW}📍 REGRAS V2 ATIVAS:{Style.RESET_ALL}")
    print(f"  • TP Individual: +{INDIVIDUAL_TP_PERCENT}% → fecha UMA posição")
    print(f"  • Regra 3/5: +{RULE_3_5_THRESHOLD}% → fecha TODAS se 3+ positivas")
    print(f"  • TP Global: +{config['tp_percent']}%")
    print(f"  • SL Global: -{config['sl_percent']}%")
    
    # Seleciona com análise
    print_info("\n🔍 Selecionando TOP 5 com análise de tendência...")
    selection = strategy.select_with_analysis(use_persistence=config['use_persistence'])
    
    if len(selection) < 5:
        print_warning(f"Seleção com apenas {len(selection)} moedas")
        if len(selection) < 1:
            print_error("Nenhuma moeda selecionada!")
            ACTIVE_STRATEGY = None
            input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")
            return
    
    # Mostra seleção
    print(format_selection_table(selection, with_direction=True))
    
    # Confirmação
    print(f"\n{Fore.YELLOW}{'='*70}{Style.RESET_ALL}")
    confirm = input(f"{Fore.YELLOW}Confirmar entrada? [S/n]: {Style.RESET_ALL}").strip().lower()
    
    if confirm in ('n', 'no', 'não', 'nao'):
        print_warning("Operação cancelada")
        ACTIVE_STRATEGY = None
        input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")
        return
    
    # Pergunta direção
    print(f"\n{Fore.CYAN}Direção da operação:{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}[1]{Style.RESET_ALL} 🟢 LONG (todas as posições)")
    print(f"  {Fore.RED}[2]{Style.RESET_ALL} 🔴 SHORT (todas as posições)")
    print(f"  {Fore.YELLOW}[3]{Style.RESET_ALL} 🎯 AUTOMÁTICO (usa análise individual)")
    
    dir_choice = input(f"\n{Fore.YELLOW}Escolha [3]: {Style.RESET_ALL}").strip()
    
    if dir_choice == '1':
        fixed_side = 'BUY'
    elif dir_choice == '2':
        fixed_side = 'SELL'
    else:
        fixed_side = None  # Usa análise
    
    # Entra em todas as posições
    direction_str = fixed_side if fixed_side else "AUTOMÁTICO"
    print_info(f"\n🚀 Abrindo posições ({direction_str})...")
    
    telegram.notify_bot_started(
        "TESTNET" if config['testnet'] else "MAINNET",
        config['capital_per_crypto'] * 5,
        config['tp_percent'],
        config['sl_percent']
    )
    
    if not strategy.enter_all_positions(selection, fixed_side):
        print_error("Falha ao abrir posições")
        ACTIVE_STRATEGY = None
        input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")
        return
    
    # Monitora
    print_info("\n📊 Iniciando monitoramento... (Ctrl+C para fechar)")
    time.sleep(2)
    
    try:
        result = strategy.monitor_positions(
            update_interval=2.0,
            smart_close_enabled=config['smart_close']
        )
        
        # Resultado
        if result == 'TP':
            print_success("\n🎉 TAKE PROFIT GLOBAL ATINGIDO!")
        elif result == 'SL':
            print_error("\n😔 STOP LOSS GLOBAL ATINGIDO")
        elif result == 'SMART':
            print_success("\n🧠 FECHAMENTO INTELIGENTE")
        elif result == 'INDIVIDUAL':
            print_success("\n🎯 TODAS AS POSIÇÕES FECHADAS INDIVIDUALMENTE!")
        elif result == 'RULE_3_5':
            print_success("\n✅ REGRA 3/5 ATIVADA - LUCRO GARANTIDO!")
        else:
            print_info("\n🔄 FECHAMENTO MANUAL")
        
        # Stats do dia
        stats = strategy.get_daily_stats()
        print(f"\n{Fore.CYAN}Estatísticas do dia:{Style.RESET_ALL}")
        print(f"  Entradas: {stats['entries']}/{stats['max_entries']}")
        print(f"  Wins: {Fore.GREEN}{stats['wins']}{Style.RESET_ALL} | Losses: {Fore.RED}{stats['losses']}{Style.RESET_ALL}")
        print(f"  P&L Dia: {'${:+.2f}'.format(stats['total_pnl'])}")
        print(f"  Win Rate: {stats['win_rate']:.1f}%")
        
        telegram.notify_daily_stats(stats)
        
    except Exception as e:
        logger.error(f"Erro na execução: {e}")
        print_error(f"Erro: {e}")
        if strategy.positions:
            strategy.force_close_all_positions("ERRO")
    
    ACTIVE_STRATEGY = None
    input(f"\n{Fore.CYAN}Pressione Enter para voltar ao menu...{Style.RESET_ALL}")


def run_auto_mode(client: Client, config: dict, telegram: TelegramNotifier):
    """Modo automático"""
    global SHOULD_STOP, ACTIVE_STRATEGY
    SHOULD_STOP = False
    
    clear_screen()
    print_banner()
    
    print(f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}🤖 MODO AUTOMÁTICO V2{Fore.CYAN}                                                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Executará automaticamente até {config['max_daily_entries']} entradas hoje                            ║
║  Cada entrada: 5 moedas com análise de tendência                             ║
║  Intervalo entre entradas: 30 segundos                                       ║
║                                                                              ║
║  {Fore.YELLOW}📍 REGRAS V2 ATIVAS:{Fore.CYAN}                                                        ║
║    • TP Individual: +{INDIVIDUAL_TP_PERCENT}% → fecha UMA posição                                ║
║    • Regra 3/5: +{RULE_3_5_THRESHOLD}% → fecha TODAS se 3+ positivas                         ║
║                                                                              ║
║  Pressione Ctrl+C a qualquer momento para parar                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")
    
    confirm = input(f"{Fore.YELLOW}Iniciar modo automático? [s/N]: {Style.RESET_ALL}").strip().lower()
    if confirm not in ('s', 'sim', 'y', 'yes'):
        print_info("Modo automático cancelado")
        return
    
    strategy = MultiCryptoStrategy(
        client=client,
        capital_per_crypto=config['capital_per_crypto'],
        tp_percent=config['tp_percent'],
        sl_percent=config['sl_percent'],
        max_daily_entries=config['max_daily_entries'],
        testnet=config['testnet'],
        telegram=telegram
    )
    
    ACTIVE_STRATEGY = strategy
    
    telegram.notify_bot_started(
        f"AUTO V2 - {'TESTNET' if config['testnet'] else 'MAINNET'}",
        config['capital_per_crypto'] * 5,
        config['tp_percent'],
        config['sl_percent']
    )
    
    try:
        while not SHOULD_STOP:
            can, reason = strategy.can_enter()
            
            if not can:
                print_warning(f"Aguardando: {reason}")
                
                if "Limite" in reason:
                    print_success("\n✅ Limite diário atingido!")
                    break
                
                for _ in range(60):
                    if SHOULD_STOP:
                        break
                    time.sleep(1)
                continue
            
            if SHOULD_STOP:
                break
            
            selection = strategy.select_with_analysis(use_persistence=config['use_persistence'])
            
            if SHOULD_STOP:
                break
            
            if selection:
                if strategy.enter_all_positions(selection):
                    result = strategy.monitor_positions(
                        smart_close_enabled=config['smart_close']
                    )
                    logger.info(f"[AUTO] Resultado: {result}")
            
            if SHOULD_STOP:
                break
            
            stats = strategy.get_daily_stats()
            if stats['remaining'] > 0:
                print_info(f"⏳ Próxima entrada em 30s ({stats['remaining']} restantes)")
                for _ in range(30):
                    if SHOULD_STOP:
                        break
                    time.sleep(1)
    
    except KeyboardInterrupt:
        pass
    
    # Sempre fecha posições ao sair
    if strategy.positions:
        print_warning("\n⏹️  Fechando posições antes de sair...")
        strategy.force_close_all_positions("INTERRUPÇÃO MANUAL")
    
    # Stats finais
    stats = strategy.get_daily_stats()
    
    print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"{Fore.WHITE}RESUMO DO DIA{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    print(f"  Entradas: {stats['entries']}")
    print(f"  Wins: {Fore.GREEN}{stats['wins']}{Style.RESET_ALL} | Losses: {Fore.RED}{stats['losses']}{Style.RESET_ALL}")
    print(f"  P&L Total: {'${:+.2f}'.format(stats['total_pnl'])}")
    print(f"  Win Rate: {stats['win_rate']:.1f}%")
    
    telegram.notify_daily_stats(stats)
    telegram.notify_bot_stopped("Modo automático V2 finalizado")
    
    ACTIVE_STRATEGY = None
    input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")


def show_stats(client: Client, config: dict):
    """Mostra estatísticas da conta"""
    clear_screen()
    print_banner()
    
    print(f"\n{Fore.CYAN}📊 ESTATÍSTICAS DA CONTA{Style.RESET_ALL}\n")
    
    try:
        account = client.futures_account()
        
        total_balance = float(account['totalWalletBalance'])
        available = float(account['availableBalance'])
        unrealized_pnl = float(account['totalUnrealizedProfit'])
        
        pnl_color = Fore.GREEN if unrealized_pnl >= 0 else Fore.RED
        
        print(f"  {Fore.WHITE}Saldo Total:{Style.RESET_ALL}      {Fore.GREEN}${total_balance:.2f}{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}Disponível:{Style.RESET_ALL}       {Fore.GREEN}${available:.2f}{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}P&L Não Realizado:{Style.RESET_ALL} {pnl_color}${unrealized_pnl:+.2f}{Style.RESET_ALL}")
        
        # Posições abertas
        positions = client.futures_position_information()
        open_positions = [p for p in positions if float(p['positionAmt']) != 0]
        
        print(f"\n  {Fore.WHITE}Posições Abertas:{Style.RESET_ALL} {len(open_positions)}")
        
        if open_positions:
            print(f"\n  {Fore.CYAN}Detalhes:{Style.RESET_ALL}")
            for p in open_positions:
                sym = p['symbol']
                amt = float(p['positionAmt'])
                entry = float(p['entryPrice'])
                pnl = float(p['unRealizedProfit'])
                side = "LONG" if amt > 0 else "SHORT"
                side_color = Fore.GREEN if amt > 0 else Fore.RED
                pnl_color = Fore.GREEN if pnl >= 0 else Fore.RED
                
                # Calcula % P&L
                capital_est = abs(amt) * entry
                pnl_percent = (pnl / capital_est * 100) if capital_est > 0 else 0
                
                # Emoji baseado no P&L
                if pnl_percent >= INDIVIDUAL_TP_PERCENT:
                    emoji = "🎯"
                elif pnl_percent >= RULE_3_5_THRESHOLD:
                    emoji = "✅"
                elif pnl >= 0:
                    emoji = "🟢"
                else:
                    emoji = "🔴"
                
                print(f"    {emoji} {sym}: {side_color}{side}{Style.RESET_ALL} {abs(amt):.4f} @ ${entry:.4f} | P&L: {pnl_color}${pnl:+.2f} ({pnl_percent:+.2f}%){Style.RESET_ALL}")
        
    except Exception as e:
        print_error(f"Erro ao obter estatísticas: {e}")
    
    input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")


def test_telegram(telegram: TelegramNotifier):
    """Testa notificações Telegram"""
    clear_screen()
    print_banner()
    
    print(f"\n{Fore.CYAN}📱 TESTE DE TELEGRAM{Style.RESET_ALL}\n")
    
    if not telegram.enabled:
        print_error("Telegram não está habilitado no .env")
        print_info("Verifique TELEGRAM_ENABLED=true")
    else:
        print_info("Enviando mensagem de teste...")
        
        telegram.send_custom(f"""
🧪 <b>TESTE DE CONEXÃO - V2</b>

✅ Bot V2 ROBUSTO funcionando corretamente!
📅 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}

📍 <b>Regras V2 Ativas:</b>
• TP Individual: +{INDIVIDUAL_TP_PERCENT}%
• Regra 3/5: +{RULE_3_5_THRESHOLD}%
        """)
        
        print_success("Mensagem enviada! Verifique seu Telegram.")
    
    input(f"\n{Fore.CYAN}Pressione Enter para voltar...{Style.RESET_ALL}")


# ============================================================
# BACKTEST
# ============================================================
def run_backtest_menu():
    """Executa o sistema de backtest"""
    clear_screen()
    print(f"""
{Fore.MAGENTA}╔══════════════════════════════════════════════════════════════════════════════╗
║  {Fore.WHITE}🔬 SISTEMA DE BACKTEST{Fore.MAGENTA}                                                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  {Fore.WHITE}Teste a estratégia com dados históricos da Binance{Fore.MAGENTA}                           ║
║  {Fore.WHITE}Simula filtro de persistência, análise LONG/SHORT e TP/SL{Fore.MAGENTA}                    ║
╚══════════════════════════════════════════════════════════════════════════════╝
{Style.RESET_ALL}""")
    
    try:
        from backtest import run_backtest_system
        run_backtest_system()
    except ImportError as e:
        print_error(f"Módulo de backtest não encontrado: {e}")
    except Exception as e:
        print_error(f"Erro no backtest: {e}")
        import traceback
        traceback.print_exc()
    
    input(f"\n{Fore.CYAN}Pressione Enter para voltar ao menu...{Style.RESET_ALL}")


# ============================================================
# MAIN
# ============================================================
def main():
    """Função principal"""
    # Configura signal handler global para Ctrl+C
    setup_global_signal_handler()
    
    # Escolhe rede inicial
    config = choose_network()
    
    # Cria cliente
    client = get_client(config)
    if not client:
        input(f"\n{Fore.CYAN}Pressione Enter para sair...{Style.RESET_ALL}")
        return
    
    # Cria notificador Telegram
    telegram = TelegramNotifier()
    
    mode = "TESTNET" if config['testnet'] else "MAINNET"
    logger.info(f"[MAIN] Bot V2 iniciado em modo {mode}")
    
    while True:
        clear_screen()
        print_banner()
        print_config(config)
        print_menu()
        
        choice = input(f"{Fore.YELLOW}Escolha uma opção: {Style.RESET_ALL}").strip()
        
        # Recria cliente se modo mudou
        current_testnet = config['testnet']
        if hasattr(client, '_testnet') and client._testnet != current_testnet:
            client = get_client(config)
            if not client:
                continue
        
        if choice == '1':
            run_strategy(client, config, telegram)
        elif choice == '2':
            run_auto_mode(client, config, telegram)
        elif choice == '3':
            preview_selection(client, config)
        elif choice == '4':
            config = configure_settings(config)
            # Recria cliente se modo mudou
            if config['testnet'] != current_testnet:
                client = get_client(config)
        elif choice == '5':
            show_stats(client, config)
        elif choice == '6':
            test_telegram(telegram)
        elif choice == '7':
            clean_positions(client, config)
        elif choice == '8':
            run_backtest_menu()
        elif choice == '0':
            print(f"\n{Fore.CYAN}👋 Até logo!{Style.RESET_ALL}")
            telegram.notify_bot_stopped("Usuário encerrou")
            break
        else:
            print_error("Opção inválida")
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Fore.CYAN}👋 Bot encerrado pelo usuário{Style.RESET_ALL}")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        print_error(f"Erro fatal: {e}")
        raise
