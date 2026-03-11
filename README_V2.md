# 🤖 Multi-Crypto Bot V2 - VERSÃO ROBUSTA

Bot de trading para Binance Futures que opera 5 criptomoedas simultaneamente com fechamento robusto e regras inteligentes.

## ✨ Novas Funcionalidades V2

### 1. 🔒 Fechamento Robusto de Posições
- **`force_close_all_positions()`**: Função que INSISTE até fechar todas as posições
  - Tenta fechar com ordem MARKET
  - Se falhar, tenta com `reduceOnly=True`
  - Se falhar, cancela ordens pendentes primeiro
  - Verifica se realmente fechou após cada tentativa
  - Até 5 tentativas com delay entre elas
  - Log detalhado de cada tentativa

### 2. 🧹 Verificação Antes de Entrar
- **`check_and_close_existing_positions()`**: Verifica posições no início
  - Se encontrar posições abertas, fecha TODAS
  - Só continua após confirmar que não há posições
  - Garante que o bot começa "limpo"

### 3. 🎯 Monitoramento Individual (+0.7%)
- Monitora cada posição individualmente
- Se UMA posição atingir **+0.7%** de lucro → fecha SOMENTE ela
- Remove da lista de posições ativas
- Continua monitorando as outras
- Log: `"🎯 BTCUSDT atingiu +0.7% - Fechando posição individual"`

### 4. ✅ Regra de 3/5 Positivas (+0.3%)
- Conta quantas posições estão positivas com **+0.3%** ou mais
- Calcula soma das positivas e soma das negativas
- Se `(positivas >= 3)` E `(soma_positivas > abs(soma_negativas))`:
  - Fecha **TODAS** as posições
  - Log: `"✅ 3/5 positivas (+0.3%) - Fechando todas para garantir lucro"`

### 5. 🛡️ Robustez e Segurança
- `try/except` em todas as chamadas de API
- Timeout em todas as requisições
- Logs claros com cores
- Signal handler para Ctrl+C funcional
- Funciona igualmente em **TESTNET** e **MAINNET**

## 📊 Interface

### Menu Principal
```
╔══════════════════════════════════════════════════════════════════════════════╗
║  MENU PRINCIPAL                                                                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  [1] 🚀 Executar Estratégia (com análise LONG/SHORT)                       ║
║  [2] 🤖 Modo Automático (até limite diário)                               ║
║  [3] 🔍 Visualizar TOP 5 (sem executar)                                   ║
║  [4] ⚙️  Configurar Parâmetros                                             ║
║  [5] 📊 Ver Estatísticas da Conta                                         ║
║  [6] 📱 Testar Telegram                                                   ║
║  [7] 🧹 Limpar Posições Abertas                                           ║
║  [8] 🔬 Backtest                                                          ║
║  [0] 🚪 Sair                                                                ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

### Monitoramento com Status
```
╔════════════════════════════════════════════════════════════════════╗
║  📊 MONITORAMENTO V2 - POSIÇÕES ATIVAS                              ║
╠════════════════════════════════════════════════════════════════════╣
║ 📍 Regras: TP Individual +0.7% | Regra 3/5 +0.3%                   ║
╠════════════════════════════════════════════════════════════════════╣
║ SÍMBOLO    │ DIR    │ QTD       │ ENTRADA   │ ATUAL     │ P&L      ║
╟────────────────────────────────────────────────────────────────────╢
║ BTCUSDT    │ LONG   │    0.0100 │ $95000.00 │ $95700.00 │ 🎯+$7.00 ║
║ ETHUSDT    │ LONG   │    0.1500 │ $3500.00  │ $3515.00  │ ✅+$2.25 ║
║ BNBUSDT    │ SHORT  │    1.0000 │ $600.00   │ $598.00   │ ✅+$2.00 ║
║ SOLUSDT    │ LONG   │    2.5000 │ $200.00   │ $199.50   │ 🔴-$1.25 ║
║ ADAUSDT    │ SHORT  │  500.0000 │ $1.00     │ $0.9980   │ ✅+$1.00 ║
╠════════════════════════════════════════════════════════════════════╣
║ 📈 P&L TOTAL: +$11.00 (+0.44%)                                     ║
║    Máximo atingido: +$11.00                                         ║
║ Regra 3/5: 3/5 positivas (+0.3%)                                   ║
╚════════════════════════════════════════════════════════════════════╝
```

**Emojis de Status:**
- 🎯 = Atingiu TP individual (+0.7%)
- ✅ = Positiva para regra 3/5 (+0.3%)
- 🟢 = Positiva (abaixo de +0.3%)
- 🔴 = Negativa

## ⚙️ Configuração

### Arquivo .env
```env
# Testnet
BINANCE_TESTNET_API_KEY=sua_api_key_testnet
BINANCE_TESTNET_SECRET=sua_secret_testnet

# Mainnet
BINANCE_API_KEY=sua_api_key
BINANCE_API_SECRET=sua_secret

# Telegram (opcional)
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=seu_bot_token
TELEGRAM_CHAT_ID=seu_chat_id
```

### Constantes de Configuração (em multi_crypto_strategy.py)
```python
INDIVIDUAL_TP_PERCENT = 0.7    # Fechar posição individual se atingir +0.7%
RULE_3_5_THRESHOLD = 0.3       # Threshold para regra 3/5 positivas (+0.3%)
MAX_CLOSE_RETRIES = 5          # Máximo de tentativas para fechar posição
CLOSE_RETRY_DELAY = 2          # Segundos entre tentativas
API_TIMEOUT = 30               # Timeout para requisições
```

## 🚀 Como Usar

### 1. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 2. Configurar .env
```bash
cp .env.example .env
# Edite o arquivo .env com suas credenciais
```

### 3. Executar o Bot
```bash
python main_multi_crypto.py
```

## 📋 Regras de Fechamento (Ordem de Prioridade)

1. **TP Global**: Se P&L total >= +tp_percent% → fecha TODAS
2. **SL Global**: Se P&L total <= -sl_percent% → fecha TODAS
3. **TP Individual**: Se UMA posição >= +0.7% → fecha SOMENTE ela
4. **Regra 3/5**: Se 3+ posições >= +0.3% E soma_positivas > soma_negativas → fecha TODAS
5. **Fechamento Inteligente**: Se detectar reversão com lucro → fecha TODAS

## 🔧 Estrutura do Projeto

```
multi_crypto_bot_v2/
├── main_multi_crypto.py      # Arquivo principal com interface
├── multi_crypto_strategy.py  # Estratégia V2 com todas as regras
├── top_performers.py         # Seleção de TOP 5 criptos
├── trend_analyzer.py         # Análise LONG/SHORT
├── telegram_notifier.py      # Notificações Telegram
├── utils.py                  # Funções auxiliares
├── config.py                 # Configurações
├── backtest.py               # Sistema de backtest
├── requirements.txt          # Dependências
├── .env                      # Credenciais (não commitado)
├── .env.example              # Exemplo de configuração
└── README_V2.md              # Esta documentação
```

## ⚠️ Avisos Importantes

1. **Teste primeiro na TESTNET** antes de usar dinheiro real
2. **Não deixe o bot sem supervisão** em MAINNET
3. **Configure alertas Telegram** para acompanhar em tempo real
4. **Use valores de capital que você pode perder**
5. **Ctrl+C funciona** - sempre fecha posições antes de sair

## 📝 Changelog V2

- ✅ Fechamento robusto com múltiplas tentativas
- ✅ Verificação de posições antes de entrar
- ✅ TP individual (+0.7%)
- ✅ Regra 3/5 positivas (+0.3%)
- ✅ Interface atualizada com status de cada posição
- ✅ Logs coloridos e detalhados
- ✅ Signal handler melhorado
- ✅ Opção de limpar posições no menu
