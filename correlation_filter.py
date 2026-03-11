"""
Correlation Filter Module - V3
Filtra ativos correlacionados para garantir diversificação real.
Evita "alavancagem oculta" quando múltiplos ativos se movem juntos.
"""
import logging
import numpy as np
from typing import List, Dict, Tuple, Optional
from binance.client import Client

logger = logging.getLogger(__name__)

# Cores no terminal
try:
    from colorama import Fore, Style
except ImportError:
    class Fore:
        RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""
    class Style:
        BRIGHT = DIM = NORMAL = RESET_ALL = ""


class CorrelationFilter:
    """
    Filtro de correlação para diversificação de portfólio.
    
    Calcula correlação de Pearson entre retornos percentuais
    e remove ativos muito correlacionados (>0.85).
    """
    
    def __init__(self, client: Client, max_correlation: float = 0.85):
        """
        Inicializa o filtro.
        
        Args:
            client: Cliente Binance autenticado
            max_correlation: Correlação máxima permitida (0.85 = 85%)
        """
        self.client = client
        self.max_correlation = max_correlation
        self._returns_cache: Dict[str, List[float]] = {}
        self._correlation_matrix: Dict[str, Dict[str, float]] = {}
    
    def get_returns(self, symbol: str, interval: str = '1h', limit: int = 24) -> List[float]:
        """
        Obtém retornos percentuais de um símbolo.
        
        Args:
            symbol: Símbolo do par
            interval: Intervalo dos candles ('1h' recomendado)
            limit: Número de períodos (24 = últimas 24 horas)
        
        Returns:
            Lista de retornos percentuais
        """
        cache_key = f"{symbol}_{interval}_{limit}"
        
        if cache_key in self._returns_cache:
            return self._returns_cache[cache_key]
        
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit + 1  # +1 para calcular retornos
            )
            
            if len(klines) < 3:
                logger.warning(f"[CORR] {symbol}: dados insuficientes")
                return []
            
            # Extrai preços de fechamento
            closes = [float(k[4]) for k in klines]
            
            # Calcula retornos percentuais
            returns = []
            for i in range(1, len(closes)):
                if closes[i-1] > 0:
                    ret = ((closes[i] - closes[i-1]) / closes[i-1]) * 100
                    returns.append(ret)
            
            self._returns_cache[cache_key] = returns
            return returns
            
        except Exception as e:
            logger.error(f"[CORR] Erro ao obter retornos de {symbol}: {e}")
            return []
    
    def calculate_correlation(
        self, 
        symbol1: str, 
        symbol2: str, 
        interval: str = '1h', 
        limit: int = 24
    ) -> float:
        """
        Calcula correlação de Pearson entre dois ativos.
        
        Args:
            symbol1: Primeiro símbolo
            symbol2: Segundo símbolo
            interval: Intervalo ('1h' recomendado para 24h)
            limit: Número de períodos
        
        Returns:
            Correlação de Pearson (-1 a 1)
        """
        # Verifica cache da matriz
        if symbol1 in self._correlation_matrix:
            if symbol2 in self._correlation_matrix[symbol1]:
                return self._correlation_matrix[symbol1][symbol2]
        
        # Obtém retornos
        returns1 = self.get_returns(symbol1, interval, limit)
        returns2 = self.get_returns(symbol2, interval, limit)
        
        if len(returns1) < 5 or len(returns2) < 5:
            return 0.0  # Dados insuficientes, assume não correlacionado
        
        # Alinha arrays para mesmo tamanho
        min_len = min(len(returns1), len(returns2))
        r1 = np.array(returns1[-min_len:])
        r2 = np.array(returns2[-min_len:])
        
        # Calcula correlação de Pearson
        try:
            # Verifica se há variância
            if np.std(r1) == 0 or np.std(r2) == 0:
                return 0.0
            
            correlation = np.corrcoef(r1, r2)[0, 1]
            
            # Trata NaN
            if np.isnan(correlation):
                correlation = 0.0
            
            # Salva no cache
            if symbol1 not in self._correlation_matrix:
                self._correlation_matrix[symbol1] = {}
            if symbol2 not in self._correlation_matrix:
                self._correlation_matrix[symbol2] = {}
            
            self._correlation_matrix[symbol1][symbol2] = correlation
            self._correlation_matrix[symbol2][symbol1] = correlation
            
            return correlation
            
        except Exception as e:
            logger.error(f"[CORR] Erro no cálculo: {e}")
            return 0.0
    
    def filter_correlated_assets(
        self, 
        symbols: List[Dict], 
        max_correlation: float = None,
        keep_best_performer: bool = True
    ) -> Tuple[List[Dict], List[Dict], Dict[str, List[str]]]:
        """
        Filtra ativos correlacionados, mantendo apenas um de cada grupo.
        
        Args:
            symbols: Lista de dicts com dados dos ativos (deve ter 'symbol' e 'score_final')
            max_correlation: Correlação máxima (usa self.max_correlation se None)
            keep_best_performer: Se True, mantém o ativo com maior score
        
        Returns:
            Tuple (filtered_list, removed_list, correlation_groups)
        """
        if max_correlation is None:
            max_correlation = self.max_correlation
        
        if len(symbols) <= 1:
            return symbols, [], {}
        
        logger.info(f"\n{Fore.CYAN}📊 ANÁLISE DE CORRELAÇÃO{Style.RESET_ALL}")
        logger.info(f"   Limite: {max_correlation:.0%}")
        
        # Limpa cache para nova análise
        self._returns_cache.clear()
        self._correlation_matrix.clear()
        
        # Cria lista de símbolos com índices
        symbol_list = [(i, s['symbol'], s.get('score_final', 0)) for i, s in enumerate(symbols)]
        
        # Calcula matriz de correlação
        n = len(symbol_list)
        correlation_info = []
        
        for i in range(n):
            for j in range(i + 1, n):
                sym1 = symbol_list[i][1]
                sym2 = symbol_list[j][1]
                
                corr = self.calculate_correlation(sym1, sym2)
                
                if abs(corr) >= max_correlation:
                    correlation_info.append({
                        'pair': (sym1, sym2),
                        'correlation': corr,
                        'scores': (symbol_list[i][2], symbol_list[j][2])
                    })
                    
                    logger.info(f"   ⚠️  {sym1} ↔ {sym2}: {corr:.2%} (ALTA)")
                elif abs(corr) >= 0.5:
                    logger.debug(f"   📊 {sym1} ↔ {sym2}: {corr:.2%} (moderada)")
        
        # Identifica ativos a remover
        removed_symbols = set()
        correlation_groups: Dict[str, List[str]] = {}
        
        for info in correlation_info:
            sym1, sym2 = info['pair']
            score1, score2 = info['scores']
            
            # Remove o de menor score
            if keep_best_performer:
                to_remove = sym2 if score1 >= score2 else sym1
                to_keep = sym1 if score1 >= score2 else sym2
            else:
                # Remove o segundo encontrado
                to_remove = sym2
                to_keep = sym1
            
            # Não remove se já removemos o par
            if to_keep not in removed_symbols:
                removed_symbols.add(to_remove)
                
                # Agrupa correlações
                if to_keep not in correlation_groups:
                    correlation_groups[to_keep] = []
                correlation_groups[to_keep].append(to_remove)
                
                logger.info(f"   🔄 Mantendo {to_keep}, removendo {to_remove}")
        
        # Filtra lista
        filtered = []
        removed = []
        
        for s in symbols:
            if s['symbol'] in removed_symbols:
                removed.append(s)
            else:
                filtered.append(s)
        
        # Log resultado
        if removed:
            print(f"\n{Fore.YELLOW}⚠️  FILTRO DE CORRELAÇÃO ATUOU:{Style.RESET_ALL}")
            print(f"   Removidos {len(removed)} ativos correlacionados")
            for r in removed:
                print(f"   🔴 {r['symbol']} (correlação > {max_correlation:.0%})")
            print(f"   ✅ Restam {len(filtered)} ativos diversificados")
        else:
            print(f"\n{Fore.GREEN}✅ Todos os ativos são diversificados (correlação < {max_correlation:.0%}){Style.RESET_ALL}")
        
        return filtered, removed, correlation_groups
    
    def get_correlation_matrix_display(self, symbols: List[str]) -> str:
        """
        Gera uma representação visual da matriz de correlação.
        
        Args:
            symbols: Lista de símbolos
        
        Returns:
            String formatada com a matriz
        """
        if len(symbols) < 2:
            return "Poucos ativos para matriz"
        
        # Calcula todas as correlações
        n = len(symbols)
        matrix = [[0.0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(n):
                if i == j:
                    matrix[i][j] = 1.0
                else:
                    matrix[i][j] = self.calculate_correlation(symbols[i], symbols[j])
        
        # Formata output
        lines = []
        header = "        " + "  ".join(f"{s[:6]:>6}" for s in symbols)
        lines.append(header)
        lines.append("-" * len(header))
        
        for i, sym in enumerate(symbols):
            row = f"{sym[:6]:>6}  "
            for j in range(n):
                corr = matrix[i][j]
                if corr >= self.max_correlation:
                    row += f"{Fore.RED}{corr:>6.2f}{Style.RESET_ALL}  "
                elif corr >= 0.5:
                    row += f"{Fore.YELLOW}{corr:>6.2f}{Style.RESET_ALL}  "
                else:
                    row += f"{corr:>6.2f}  "
            lines.append(row)
        
        return "\n".join(lines)
    
    def clear_cache(self):
        """Limpa caches de retornos e correlações"""
        self._returns_cache.clear()
        self._correlation_matrix.clear()


def calculate_portfolio_correlation(client: Client, symbols: List[str]) -> float:
    """
    Calcula a correlação média do portfólio.
    
    Args:
        client: Cliente Binance
        symbols: Lista de símbolos
    
    Returns:
        Correlação média entre todos os pares
    """
    if len(symbols) < 2:
        return 0.0
    
    filter_obj = CorrelationFilter(client)
    correlations = []
    
    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            corr = filter_obj.calculate_correlation(symbols[i], symbols[j])
            correlations.append(abs(corr))
    
    return sum(correlations) / len(correlations) if correlations else 0.0
