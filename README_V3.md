# Multi Crypto Bot V3.2 - CORREÇÕES DE BUGS CRÍTICOS

## 🐛 Correções V3.2 (11/02/2026) - NOVAS

### Bugs Corrigidos V3.2:

1. **Loop infinito "Já existem posições abertas"** - Bot ficava em loop mesmo após fechar todas as posições
   - ✅ `can_enter()` agora verifica posições na **EXCHANGE**, não apenas lista local
   - ✅ Ignora posições "dust" (valor < $1 ou qty < 0.001)
   - ✅ `check_and_close_existing_positions()` agora limpa lista local após fechar
   
2. **Apenas 3 posições abertas (deveria ser 5)** - Bot parava quando moedas davam erro -4140
   - ✅ Lista de backup aumentada de **10 para 15** moedas
   - ✅ Tratamento específico de erro **-4140** (símbolo não disponível)
   - ✅ Tratamento de erro **-4164** (valor muito pequeno)
   - ✅ Bot continua tentando até conseguir 5 entradas ou esgotar lista
   - ✅ Máximo de 25 tentativas totais

3. **Falta de logs para debugging** 
   - ✅ Log detalhado em cada verificação de posição
   - ✅ Log de cada tentativa de entrada (sucesso/falha)
   - ✅ Log de símbolos que falharam e motivos
   - ✅ Resumo final: "X/5 posições abertas em Y tentativas"

### Fluxo de Entrada Corrigido V3.2:
```
1. check_and_close_existing_positions() - Fecha posições REAIS (ignora dust)
2. Limpa lista local self.positions
3. Para cada moeda na lista de 15 backup:
   a. Verifica filtros (sobrecompra, etc)
   b. Tenta abrir posição
   c. Se erro -4140 → "Não disponível" → próxima moeda
   d. Se erro -4164 → "Valor muito pequeno" → próxima moeda
   e. Se sucesso → contador++
   f. Se contador == 5 → PARA
4. Log resumo: "X/5 posições em Y tentativas"
```

---

## 🐛 Correções V3.1 (11/02/2026)

### Bugs Corrigidos:

1. **Fechamento repetido de posições** - Bot tentava fechar posições já fechadas múltiplas vezes
   - ✅ Adicionado `get_position_amount_from_exchange()` para verificar posição REAL na Binance
   - ✅ Verificação ANTES de cada tentativa de fechamento
   
2. **Regras não sendo seguidas** - Posições marcadas como fechadas ainda eram verificadas
   - ✅ `check_individual_tp()` agora verifica posição na exchange antes de processar
   - ✅ Sincronização automática com exchange em `update_all_pnl()`
   
3. **Barra de progresso estática** - Display não atualizava
   - ✅ Adicionado timestamp visível no header do monitor
   - ✅ Contador de posições ativas atualizado em tempo real

4. **Erros de API silenciados** - Erros -4164 e -2022 eram tratados incorretamente
   - ✅ Agora verifica se posição foi realmente fechada após erros de API

### Fluxo de Fechamento Corrigido:
```
1. check_individual_tp() detecta TP
2. Verifica posição REAL na Binance (get_position_amount_from_exchange)
3. Se posição já fechada → marca como closed e ignora
4. Se posição ainda existe → tenta fechar
5. Após fechar → confirma na Binance
6. Se confirmado → marca closed definitivamente
```

---

# Multi-Crypto Bot V3 - Melhorias Estratégicas

## 🆕 Novidades da V3

### 1. 💰 Lucro Líquido Real
Agora o bot calcula o lucro **descontando taxas e slippage**:
- **Maker Fee**: 0.02%
- **Taker Fee**: 0.04%
- **Slippage estimado**: 0.02%
- **Total por trade**: ~0.10%

O bot só fecha posições se o **lucro líquido** for significativo, evitando "trocar dinheiro" com a corretora.

```python
# Exemplo de uso
from multi_crypto_strategy import calculate_net_profit, is_profit_worth_closing

net_profit, fees = calculate_net_profit(gross_profit=5.0, position_value=500.0)
# Taxas: $0.50, Lucro Líquido: $4.50

should_close = is_profit_worth_closing(gross_profit=5.0, position_value=500.0)
# True se lucro líquido > 0.05%
```

### 2. 📊 Filtro de Correlação
Evita "alavancagem oculta" quando múltiplos ativos se movem juntos:
- Calcula correlação de **Pearson** entre retornos horários (24h)
- Se correlação > **85%**, remove um dos ativos
- Mantém o ativo com maior score
- Garante **diversificação real** do portfólio

```python
from correlation_filter import CorrelationFilter

filter = CorrelationFilter(client, max_correlation=0.85)
filtered, removed, groups = filter.filter_correlated_assets(symbols)
```

### 3. ⚡ Ordens IOC (Immediate or Cancel)
Fechamento rápido em situações de flash crash:
- Usa **IOC** primeiro para execução imediata
- Fallback para **MARKET** se IOC falhar
- Delay entre tentativas: **0.5s** (antes era 2s)
- Máximo 5 tentativas com métodos diferentes

### 4. 🚫 Filtro de Sobrecompra/Sobrevenda
Evita comprar "topos" ou vender "fundos":

| Condição | Ação |
|----------|------|
| RSI > 70 | **Não entrar LONG** |
| RSI < 30 | **Não entrar SHORT** |
| Preço > Bollinger Superior | **Evitar LONG** |
| Preço < Bollinger Inferior | **Evitar SHORT** |

### 5. 📈 Dashboard com Drawdown
Novo dashboard mostra métricas avançadas:
- **P&L Bruto** e **P&L Líquido** (após taxas)
- **Drawdown atual** e **Drawdown máximo**
- **Taxas pagas** por posição
- **Indicadores visuais** de filtros atuando

#### Cores do Drawdown:
- ⚪ Branco: Drawdown < 0.2%
- 🟡 Amarelo: Drawdown 0.2% - 0.3%
- 🔴 Vermelho: Drawdown > 0.3%

## 📋 Estrutura de Arquivos

```
multi_crypto_bot_v3/
├── multi_crypto_strategy.py   # Estratégia principal V3
├── correlation_filter.py      # 🆕 Filtro de correlação
├── trend_analyzer.py          # Análise + filtro sobrecompra
├── top_performers.py          # Seleção de moedas
├── telegram_notifier.py       # Notificações
├── main_multi_crypto.py       # Script principal
├── config.py                  # Configurações
├── utils.py                   # Utilitários
└── README_V3.md               # Este arquivo
```

## 🚀 Uso

```python
from binance.client import Client
from multi_crypto_strategy import MultiCryptoStrategy

client = Client(api_key, api_secret, testnet=True)

strategy = MultiCryptoStrategy(
    client=client,
    capital_per_crypto=500.0,
    tp_percent=0.5,
    sl_percent=0.4,
    testnet=True,
    use_correlation_filter=True,   # 🆕 Ativa filtro de correlação
    use_overbought_filter=True     # 🆕 Ativa filtro de sobrecompra
)

# Seleciona moedas (com todos os filtros)
selection = strategy.select_with_analysis()

# Entra nas posições
strategy.enter_all_positions(selection)

# Monitora com dashboard V3
result = strategy.monitor_positions()
```

## ⚙️ Configuração de Taxas

Edite as constantes no início de `multi_crypto_strategy.py`:

```python
MAKER_FEE = 0.0002    # 0.02%
TAKER_FEE = 0.0004    # 0.04%
SLIPPAGE = 0.0002     # 0.02%
```

## 📊 Exemplo de Dashboard V3

```
╔════════════════════════════════════════════════════════════════════════╗
║         📊 MONITORAMENTO V3 - DASHBOARD COM DRAWDOWN                   ║
╠════════════════════════════════════════════════════════════════════════╣
║ 💰 Custos: 0.10% | Correlação: <85% | RSI: 70/30                       ║
╠════════════════════════════════════════════════════════════════════════╣
║ SÍMBOLO    │  DIR   │   ENTRADA │     ATUAL │    BRUTO │      LÍQ │   TX ║
╟────────────────────────────────────────────────────────────────────────╢
║ ETHUSDT    │  LONG  │ $2500.00  │ $2510.00  │ 🟢+$4.00 │   +$3.50 │ $0.50 ║
║ BTCUSDT    │  LONG  │ $45000.00 │ $45200.00 │ 🟢+$2.22 │   +$1.72 │ $0.50 ║
╠════════════════════════════════════════════════════════════════════════╣
║ 📈 P&L BRUTO:   +$6.22 (+0.25%)                                        ║
║    P&L LÍQUIDO: +$5.22 (após taxas ~$1.00)                             ║
║    Máximo atingido: +$6.50                                             ║
╟────────────────────────────────────────────────────────────────────────╢
║ 📉 DRAWDOWN ATUAL: 0.011% │ Máximo: 0.015%                             ║
║ Regra 3/5: 2/5 positivas (+0.3%)                                       ║
╟────────────────────────────────────────────────────────────────────────╢
║ 🔒 Filtros: Correlação(2) | Sobrecompra(1)                             ║
╚════════════════════════════════════════════════════════════════════════╝
```

## 🔄 Changelog V3

### Adições
- ✅ `calculate_net_profit()` - Calcula lucro líquido
- ✅ `CorrelationFilter` - Filtra ativos correlacionados
- ✅ `check_overbought_oversold()` - Filtro RSI/Bollinger
- ✅ `PerformanceDashboard` - Dashboard com drawdown
- ✅ `force_close_single_position_ioc()` - Fechamento IOC

### Melhorias
- ⚡ Delay de fechamento reduzido: 2s → 0.5s
- 📊 Dashboard com P&L bruto e líquido
- 🎨 Cores de drawdown (amarelo/vermelho)
- 📱 Notificações de filtros no Telegram

### Constantes
| Constante | Valor | Descrição |
|-----------|-------|-----------|
| `TOTAL_COST_RATE` | 0.10% | Custo total por trade |
| `MAX_CORRELATION` | 85% | Correlação máxima |
| `RSI_OVERBOUGHT` | 70 | Limite sobrecompra |
| `RSI_OVERSOLD` | 30 | Limite sobrevenda |
| `CLOSE_RETRY_DELAY` | 0.5s | Delay entre tentativas |