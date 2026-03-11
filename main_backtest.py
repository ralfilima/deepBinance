#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════
              🔬 BACKTEST - MULTI CRYPTO BOT
═══════════════════════════════════════════════════════════════

Sistema de backtest para testar a estratégia com dados históricos.

Uso:
    python main_backtest.py

O sistema irá guiar você através das configurações.
"""
import sys
import os

# Adiciona o diretório ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backtest import run_backtest_system

if __name__ == '__main__':
    try:
        run_backtest_system()
    except KeyboardInterrupt:
        print("\n\n⚠️  Backtest interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
