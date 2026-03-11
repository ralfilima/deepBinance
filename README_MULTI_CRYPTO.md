# 🤖 Multi-Crypto Bot - Versão Melhorada

Bot de trading que opera 5 criptomoedas simultaneamente com análise inteligente.

## ✨ Funcionalidades

### 🎯 Filtro de Persistência (1 minuto)
- Moeda precisa estar no TOP 10 por **1 minuto seguido**
- 3 verificações a cada 20 segundos
- Só seleciona moedas que aparecem em **TODAS** as verificações
- Evita ser enganado por movimentos bruscos

### 📈 Análise LONG/SHORT Inteligente
- **EMA 9 vs EMA 21** (tendência curta)
- **RSI 14** (momentum/força)
- **Momentum** (variação recente)
- Cada moeda recebe direção independente

### 🧠 Monitoramento Inteligente
- Verifica tendência a cada 30 segundos
- Detecta reversão de tendência
- **Se lucro > 0 e tendência virando → fecha posições**
- Protege lucro automaticamente

### 📱 Notificações Telegram
Mensagens em todas as etapas:
- ✅ Início do scan
- ✅ Verificações de persistência
- ✅ Seleção completa
- ✅ Abertura de posições
- ✅ Monitoramento (a cada 1 min)
- ✅ Alertas de reversão
- ✅ Fechamento de posições
- ✅ Estatísticas do dia

### 🎨 Interface Colorida
- Cores no terminal (colorama)
- Boxes e separadores visuais
- Logs claros e formatados
- Menu interativo

### ⚡ Simplicidade
- **SEM threads complexas**
- **SEM deadlocks**
- **Ctrl+C funciona sempre**
- Tudo sequencial e simples
- Signal handlers implementados

## 📁 Estrutura de Arquivos

```
multi_crypto_bot/
├── main_multi_crypto.py      # Interface principal (execute este)
├── multi_crypto_strategy.py  # Estratégia com monitoramento inteligente
├── top_performers.py         # Seleção com filtro de persistência
├── trend_analyzer.py         # Análise LONG/SHORT (EMA, RSI, Momentum)
├── telegram_notifier.py      # Notificações Telegram
├── utils.py                  # Funções utilitárias
├── .env                      # Credenciais (NÃO COMPARTILHE!)
└── requirements.txt          # Dependências
```

## 🚀 Como Usar

### 1. Instalar Dependências
```bash
cd /home/ubuntu/multi_crypto_bot
pip install -r requirements.txt
```

### 2. Verificar Credenciais
O arquivo `.env` já está configurado com suas credenciais:
- Binance Testnet
- Binance Mainnet
- Telegram Bot

### 3. Executar o Bot
```bash
python main_multi_crypto.py
```

### 4. Menu Principal
```
[1] 🚀 Executar Estratégia - Uma entrada manual com análise
[2] 🤖 Modo Automático - Executa até limite diário
[3] 🔍 Visualizar TOP 5 - Ver seleção sem executar
[4] ⚙️  Configurar - Alterar parâmetros
[5] 📊 Estatísticas - Ver saldo e posições
[6] 📱 Testar Telegram - Verificar conexão
[0] 🚪 Sair
```

## ⚙️ Configurações Padrão

| Parâmetro | Valor | Descrição |
|-----------|-------|-----------|
| Capital por cripto | $500 | Valor investido em cada moeda |
| Take Profit | 0.5% | Meta de lucro (+$12.50 para $2500) |
| Stop Loss | 0.4% | Limite de perda (-$10 para $2500) |
| Max entradas/dia | 5 | Limite de operações diárias |
| Filtro Persistência | ✅ Ativo | Verificação de 1 minuto |
| Fechamento Intel. | ✅ Ativo | Protege lucro automaticamente |

## 📊 Fluxo de Operação

```
1. SELEÇÃO COM PERSISTÊNCIA
   └─ 3 verificações a cada 20s
   └─ Filtra moedas consistentes

2. ANÁLISE DE TENDÊNCIA
   └─ EMA 9 vs EMA 21
   └─ RSI 14
   └─ Momentum 10 períodos
   └─ Determina LONG ou SHORT

3. ABERTURA DE POSIÇÕES
   └─ 5 moedas simultaneamente
   └─ Cada uma com direção própria

4. MONITORAMENTO
   └─ P&L agregado
   └─ Verifica reversão a cada 30s
   └─ TP: +$12.50 | SL: -$10

5. FECHAMENTO
   └─ TP atingido: fecha todas 🎉
   └─ SL atingido: fecha todas 😔
   └─ Reversão detectada: fecha com lucro 🧠
   └─ Manual: Ctrl+C
```

## 🔔 Telegram

O bot envia notificações detalhadas:

```
🔍 SCANNING MERCADO
⏳ Verificação 1/3 - TOP: BTC, ETH, SOL...
⏳ Verificação 2/3 - TOP: BTC, ETH, SOL...
⏳ Verificação 3/3 - TOP: BTC, ETH, SOL...
🎯 SELEÇÃO COMPLETA - 5 moedas
🟢 POSIÇÃO ABERTA - BTCUSDT LONG
📈 MONITORAMENTO - P&L: +$5.50
⚠️ ALERTA DE REVERSÃO - ETH tendência virando
✅ FECHAMENTO INTELIGENTE - P&L: +$8.20
```

## ⚠️ Avisos Importantes

1. **Sempre comece no TESTNET** para testar
2. **MAINNET usa dinheiro real** - cuidado!
3. O bot é autônomo mas requer monitoramento
4. Ctrl+C fecha posições e encerra com segurança
5. Mantenha o terminal aberto durante operação

## 🐛 Solução de Problemas

### Erro de conexão
```
Verifique:
- Credenciais no .env
- Conexão com internet
- API da Binance disponível
```

### Telegram não funciona
```
Verifique:
- TELEGRAM_ENABLED=true no .env
- Token do bot correto
- Chat ID correto
- Bot iniciado no Telegram (@BotFather)
```

### Ctrl+C não funciona
```
Aguarde 2-3 segundos após Ctrl+C
O bot fecha posições antes de encerrar
```

---

**Desenvolvido para trading inteligente e seguro** 🚀
