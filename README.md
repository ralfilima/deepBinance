# 🤖 Randomized Trend Scalper - Binance Futures

Bot de scalping automatizado para Binance Futures com gestão de risco avançada e suporte completo a Stop Loss e Take Profit.

## 📋 Índice

- [Características](#-características)
- [Requisitos](#-requisitos)
- [Instalação](#-instalação)
- [Configuração](#-configuração)
- [Uso](#-uso)
- [Estratégia](#-estratégia)
- [Gerenciamento de Risco](#-gerenciamento-de-risco)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)

## ✨ Características

### Funcionalidades Principais
- ✅ **Stop Loss e Take Profit automáticos** com validação de direção
- ✅ **Monitoramento manual de SL/TP** como fallback
- ✅ **Time Stop** para fechar posições após tempo determinado
- ✅ **Confirmação de posição** antes de colocar SL/TP
- ✅ **Retry com exponential backoff** para conexões instáveis
- ✅ **Gerenciamento de risco** completo (perdas consecutivas, perda diária, etc.)

### Robustez
- Suporte a **Testnet** e **Mainnet**
- Múltiplos métodos para criar ordens SL/TP (fallback automático)
- Logs detalhados para debug
- Tratamento de erros em todos os pontos críticos

## 📦 Requisitos

- Python 3.8+
- Conta Binance Futures (Testnet ou Mainnet)
- API Key e Secret Key

## 🚀 Instalação

### 1. Clonar/Baixar o projeto

```bash
cd /caminho/para/o/projeto
```

### 2. Criar ambiente virtual (recomendado)

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
.\venv\Scripts\activate  # Windows
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar credenciais

```bash
cp .env.example .env
# Edite o arquivo .env com suas credenciais
```

## ⚙️ Configuração

### Arquivo `.env`

```env
# Credenciais (obtenha em https://testnet.binancefuture.com para testnet)
BINANCE_API_KEY=sua_api_key
BINANCE_SECRET_KEY=sua_secret_key

# Modo de operação
BINANCE_TESTNET=true   # true = testnet, false = mainnet (dinheiro real!)
DEBUG_MODE=false       # true = ignora filtros da estratégia

# Risco
MAX_POSITION_SIZE_PERCENT=1.0  # 1% do capital por trade
MAX_OPEN_POSITIONS=5           # Máximo 5 posições simultâneas
MAX_DAILY_LOSS_PERCENT=3.0     # Para se perder 3% no dia
MAX_CONSECUTIVE_LOSSES=3       # Para após 3 perdas seguidas

# TP/SL
TP_PERCENT_LONG=1.05    # Take Profit de 1.05%
SL_PERCENT_LONG=0.70    # Stop Loss de 0.70%
TIME_STOP_MIN=12        # Time stop mínimo (minutos)
TIME_STOP_MAX=22        # Time stop máximo (minutos)
```

### Obter API Keys

#### Testnet (Recomendado para testes)
1. Acesse [https://testnet.binancefuture.com](https://testnet.binancefuture.com)
2. Crie uma conta ou faça login
3. Vá em **API Management**
4. Crie uma nova API Key
5. Copie a API Key e Secret Key para o `.env`

#### Mainnet (Dinheiro Real)
1. Acesse [https://www.binance.com](https://www.binance.com)
2. Vá em **API Management** nas configurações da conta
3. Crie uma nova API Key
4. **IMPORTANTE**: Habilite apenas permissões necessárias:
   - ✅ Enable Reading
   - ✅ Enable Futures
   - ❌ NÃO habilite transferências!
5. Configure IP whitelist se possível

## 🎮 Uso

### Iniciar o bot

```bash
python bot.py
```

### Parar o bot

Pressione `Ctrl+C` para parar graciosamente.

### Verificar logs

```bash
tail -f bot.log
```

## 📈 Estratégia

### Randomized Trend Scalping

1. **Detecção de Tendência**: Usa EMA200 do BTCUSDT como referência
   - Preço > EMA200 + 0.2% → Tendência de ALTA
   - Preço < EMA200 - 0.2% → Tendência de BAIXA
   - Caso contrário → Mercado LATERAL (não opera)

2. **Filtros de Entrada** (modo normal):
   - **Alta**: Preço > EMA200, pullback na EMA20, candle de alta, volume acima da média, RSI 55-70
   - **Baixa**: Preço < EMA200, pullback na EMA20, candle de baixa, volume acima da média, RSI 30-45

3. **Seleção de Ativo**: Escolha aleatória ponderada por volume entre ativos elegíveis

4. **Execução**:
   - Ordem de entrada: MARKET
   - Stop Loss: STOP_MARKET com `closePosition=true`
   - Take Profit: TAKE_PROFIT_MARKET com `closePosition=true`

### Fluxo de Abertura de Posição

```
1. Calcular tamanho da posição baseado no risco
2. Executar ordem de entrada (MARKET)
3. AGUARDAR confirmação da posição
4. Obter preço real de preenchimento
5. Recalcular SL/TP baseado no preço real
6. Colocar Stop Loss (múltiplos métodos como fallback)
7. Colocar Take Profit (múltiplos métodos como fallback)
8. Se SL/TP falhar, monitorar manualmente
```

## 🛡️ Gerenciamento de Risco

### Limites Configuráveis

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `MAX_POSITION_SIZE_PERCENT` | % do capital por trade | 1.0% |
| `MAX_OPEN_POSITIONS` | Posições simultâneas | 5 |
| `MAX_DAILY_LOSS_PERCENT` | Perda diária máxima | 3.0% |
| `MAX_CONSECUTIVE_LOSSES` | Perdas consecutivas | 3 |

### Proteções Automáticas

- **Validação de SL/TP**: Verifica direção correta antes de enviar
  - LONG: SL < Preço Atual < TP
  - SHORT: TP < Preço Atual < SL
- **Monitoramento Manual**: Se ordens automáticas falharem, o bot monitora e fecha no preço correto
- **Time Stop**: Fecha posição após tempo determinado independente de lucro/prejuízo

## 🔧 Troubleshooting

### Erro: "Order would trigger immediately" (-2021)

**Causa**: O `stopPrice` está do lado errado do preço atual.

**Solução**: O bot já valida a direção automaticamente. Se persistir:
1. Verifique se o preço se moveu muito rápido
2. Aumente o % de SL/TP nas configurações

### Erro: "Order type not supported" (-4120)

**Causa**: O testnet da Binance tem limitações em alguns tipos de ordem.

**Solução**: O bot tenta múltiplos métodos automaticamente:
1. STOP_MARKET com closePosition
2. STOP_MARKET com reduceOnly
3. STOP com price
4. Monitoramento manual (fallback)

### Erro: "Connection timed out" / "Name resolution failed"

**Causa**: Problemas de conectividade de rede.

**Solução**: 
- O bot tem retry automático com backoff exponencial
- Verifique sua conexão de internet
- Aumente `API_TIMEOUT` e `MAX_RETRIES` no `.env`

### Erro: "Invalid API key"

**Causa**: Credenciais incorretas ou testnet vs mainnet misturados.

**Solução**:
1. Verifique se `BINANCE_TESTNET` está correto
2. Use API Key do testnet para testnet
3. Use API Key da mainnet para mainnet

### SL/TP não está sendo executado

**Possíveis causas**:
1. **Ordens automáticas falharam**: Verifique os logs para "MANUAL"
2. **Bot foi parado**: Se parar o bot, ordens manuais não são executadas
3. **Slippage**: Em movimentos rápidos, o preço pode pular o SL/TP

**Solução**: 
- Mantenha o bot rodando
- Use o modo DEBUG_MODE=false para ver logs detalhados

## ❓ FAQ

### O bot funciona na mainnet?

Sim! Altere `BINANCE_TESTNET=false` no `.env`. **CUIDADO: Você estará usando dinheiro real!**

### Posso usar em outras corretoras?

Não, o bot foi desenvolvido especificamente para a Binance Futures.

### Quanto posso ganhar?

Não há garantias. Trading é arriscado e você pode perder todo o capital investido.

### O bot precisa ficar rodando 24/7?

Sim, para monitorar posições. Se o SL/TP automático estiver ativo, suas posições estão protegidas mesmo se o bot parar. Mas o Time Stop e monitoramento manual precisam do bot rodando.

### Posso rodar múltiplas instâncias?

Não recomendado, pois podem interferir nas ordens uma da outra.

---

## ⚠️ Aviso Legal

Este software é fornecido "como está", sem garantias. Trading de criptomoedas é altamente arriscado. Você pode perder todo o capital investido. Use por sua conta e risco.

---

## 📝 Licença

MIT License - Use livremente, mas sem garantias.
