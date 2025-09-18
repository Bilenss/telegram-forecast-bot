# app/analysis/fast_prediction.py
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
import pandas as pd
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger(__name__)

class FastPredictionEngine:
    """Оптимизированный движок для быстрых прогнозов"""
    
    def __init__(self):
        self.cache = {}
        self.last_analysis = {}
    
    async def get_fast_prediction(self, 
                                 pair: str, 
                                 timeframe: str,
                                 df: pd.DataFrame,
                                 mode: str = "ind") -> Tuple[str, Dict[str, Any]]:
        """
        Быстрый прогноз за 5-10 секунд
        
        Returns:
            Tuple[prediction_text, data_dict]
        """
        start_time = datetime.now()
        
        try:
            # Параллельный анализ
            tasks = []
            
            if mode == "ind":
                tasks.append(self._analyze_indicators_fast(df))
                tasks.append(self._analyze_patterns_fast(df))
                tasks.append(self._analyze_volume_fast(df))
            else:
                tasks.append(self._analyze_ta_fast(df))
                tasks.append(self._analyze_support_resistance_fast(df))
            
            # Ждем все анализы параллельно
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обрабатываем результаты
            if mode == "ind":
                indicators_result = results[0] if not isinstance(results[0], Exception) else {}
                patterns_result = results[1] if not isinstance(results[1], Exception) else {}
                volume_result = results[2] if not isinstance(results[2], Exception) else {}
                
                # Комбинируем сигналы
                signal = self._combine_signals(indicators_result, patterns_result, volume_result)
                
                # Форматируем прогноз
                prediction = self._format_indicator_prediction(
                    signal, indicators_result, patterns_result, 
                    volume_result, timeframe
                )
                
                data = {
                    'indicators': indicators_result,
                    'patterns': patterns_result,
                    'volume': volume_result,
                    'signal': signal
                }
            else:
                ta_result = results[0] if not isinstance(results[0], Exception) else {}
                sr_result = results[1] if not isinstance(results[1], Exception) else {}
                
                signal = ta_result.get('signal', 'HOLD')
                
                prediction = self._format_ta_prediction(
                    signal, ta_result, sr_result, timeframe
                )
                
                data = {
                    'ta': ta_result,
                    'support_resistance': sr_result,
                    'signal': signal
                }
            
            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"Prediction generated in {elapsed:.1f} seconds")
            
            return prediction, data
            
        except Exception as e:
            logger.error(f"Fast prediction error: {e}")
            return self._get_fallback_prediction(timeframe), {}
    
    async def _analyze_indicators_fast(self, df: pd.DataFrame) -> Dict:
        """Быстрый анализ индикаторов"""
        await asyncio.sleep(0.1)  # Симуляция async операции
        
        try:
            # Быстрые вычисления основных индикаторов
            close = df['close'].values
            
            # RSI (упрощенный)
            rsi = self._calculate_rsi_fast(close)
            
            # EMA
            ema_fast = pd.Series(close).ewm(span=9).mean().iloc[-1]
            ema_slow = pd.Series(close).ewm(span=21).mean().iloc[-1]
            
            # MACD
            exp1 = pd.Series(close).ewm(span=12).mean()
            exp2 = pd.Series(close).ewm(span=26).mean()
            macd = exp1.iloc[-1] - exp2.iloc[-1]
            
            return {
                'RSI': rsi,
                'EMA_fast': ema_fast,
                'EMA_slow': ema_slow,
                'MACD': macd,
                'trend': 'UP' if ema_fast > ema_slow else 'DOWN'
            }
        except Exception as e:
            logger.error(f"Indicator analysis error: {e}")
            return {}
    
    async def _analyze_patterns_fast(self, df: pd.DataFrame) -> Dict:
        """Быстрый поиск паттернов"""
        await asyncio.sleep(0.1)
        
        try:
            # Упрощенный поиск основных паттернов
            last_candles = df.tail(5)
            
            # Проверяем простые паттерны
            pattern = "NEUTRAL"
            strength = 50
            
            # Бычий молот
            if self._is_hammer(last_candles.iloc[-1]):
                pattern = "HAMMER"
                strength = 70
            # Медвежья звезда
            elif self._is_shooting_star(last_candles.iloc[-1]):
                pattern = "SHOOTING_STAR"
                strength = 30
            # Бычье поглощение
            elif self._is_bullish_engulfing(last_candles.iloc[-2:]):
                pattern = "BULLISH_ENGULFING"
                strength = 80
            # Медвежье поглощение
            elif self._is_bearish_engulfing(last_candles.iloc[-2:]):
                pattern = "BEARISH_ENGULFING"
                strength = 20
            
            return {
                'pattern': pattern,
                'strength': strength
            }
        except Exception as e:
            logger.error(f"Pattern analysis error: {e}")
            return {}
    
    async def _analyze_volume_fast(self, df: pd.DataFrame) -> Dict:
        """Быстрый анализ объема"""
        await asyncio.sleep(0.1)
        
        try:
            if 'volume' in df.columns:
                avg_volume = df['volume'].mean()
                last_volume = df['volume'].iloc[-1]
                volume_ratio = last_volume / avg_volume if avg_volume > 0 else 1
                
                return {
                    'avg_volume': avg_volume,
                    'last_volume': last_volume,
                    'ratio': volume_ratio,
                    'signal': 'HIGH' if volume_ratio > 1.5 else 'NORMAL'
                }
            return {'signal': 'NO_DATA'}
        except:
            return {'signal': 'NO_DATA'}
    
    async def _analyze_ta_fast(self, df: pd.DataFrame) -> Dict:
        """Быстрый технический анализ"""
        await asyncio.sleep(0.1)
        
        try:
            close = df['close'].values
            high = df['high'].values
            low = df['low'].values
            
            # Определяем тренд
            sma_20 = pd.Series(close).rolling(20).mean().iloc[-1]
            sma_50 = pd.Series(close).rolling(50).mean().iloc[-1] if len(close) > 50 else sma_20
            
            current_price = close[-1]
            
            if current_price > sma_20 > sma_50:
                trend = "STRONG_UP"
                signal = "BUY"
            elif current_price > sma_20:
                trend = "UP"
                signal = "BUY"
            elif current_price < sma_20 < sma_50:
                trend = "STRONG_DOWN"
                signal = "SELL"
            elif current_price < sma_20:
                trend = "DOWN"
                signal = "SELL"
            else:
                trend = "SIDEWAYS"
                signal = "HOLD"
            
            return {
                'trend': trend,
                'signal': signal,
                'sma_20': sma_20,
                'sma_50': sma_50,
                'current_price': current_price
            }
        except Exception as e:
            logger.error(f"TA analysis error: {e}")
            return {'signal': 'HOLD'}
    
    async def _analyze_support_resistance_fast(self, df: pd.DataFrame) -> Dict:
        """Быстрый поиск уровней поддержки/сопротивления"""
        await asyncio.sleep(0.1)
        
        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values
            
            # Простой метод: последние экстремумы
            resistance = max(high[-20:]) if len(high) > 20 else max(high)
            support = min(low[-20:]) if len(low) > 20 else min(low)
            
            pivot = (high[-1] + low[-1] + close[-1]) / 3
            
            return {
                'support': support,
                'resistance': resistance,
                'pivot': pivot,
                'current': close[-1]
            }
        except:
            return {}
    
    def _calculate_rsi_fast(self, prices, period=14):
        """Упрощенный расчет RSI"""
        try:
            deltas = pd.Series(prices).diff()
            gain = deltas.where(deltas > 0, 0).rolling(period).mean()
            loss = -deltas.where(deltas < 0, 0).rolling(period).mean()
            rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] != 0 else 100
            return 100 - (100 / (1 + rs))
        except:
            return 50
    
    def _is_hammer(self, candle):
        """Проверка на паттерн молот"""
        body = abs(candle['close'] - candle['open'])
        lower_shadow = min(candle['open'], candle['close']) - candle['low']
        upper_shadow = candle['high'] - max(candle['open'], candle['close'])
        
        return lower_shadow > body * 2 and upper_shadow < body * 0.3
    
    def _is_shooting_star(self, candle):
        """Проверка на паттерн падающая звезда"""
        body = abs(candle['close'] - candle['open'])
        upper_shadow = candle['high'] - max(candle['open'], candle['close'])
        lower_shadow = min(candle['open'], candle['close']) - candle['low']
        
        return upper_shadow > body * 2 and lower_shadow < body * 0.3
    
    def _is_bullish_engulfing(self, candles):
        """Проверка на бычье поглощение"""
        if len(candles) < 2:
            return False
        prev, curr = candles.iloc[0], candles.iloc[1]
        return (prev['close'] < prev['open'] and 
                curr['close'] > curr['open'] and
                curr['close'] > prev['open'] and
                curr['open'] < prev['close'])
    
    def _is_bearish_engulfing(self, candles):
        """Проверка на медвежье поглощение"""
        if len(candles) < 2:
            return False
        prev, curr = candles.iloc[0], candles.iloc[1]
        return (prev['close'] > prev['open'] and 
                curr['close'] < curr['open'] and
                curr['close'] < prev['open'] and
                curr['open'] > prev['close'])
    
    def _combine_signals(self, indicators, patterns, volume):
        """Комбинирование сигналов для финального решения"""
        score = 50  # Нейтральный старт
        
        # Учитываем индикаторы
        if indicators:
            rsi = indicators.get('RSI', 50)
            if rsi > 70:
                score -= 20  # Перекупленность
            elif rsi < 30:
                score += 20  # Перепроданность
            
            if indicators.get('trend') == 'UP':
                score += 15
            elif indicators.get('trend') == 'DOWN':
                score -= 15
        
        # Учитываем паттерны
        if patterns:
            pattern_strength = patterns.get('strength', 50)
            score = (score + pattern_strength) / 2
        
        # Учитываем объем
        if volume and volume.get('signal') == 'HIGH':
            score *= 1.2  # Усиливаем сигнал при высоком объеме
        
        # Конвертируем в сигнал
        if score > 65:
            return "📈 STRONG BUY"
        elif score > 55:
            return "📈 BUY"
        elif score < 35:
            return "📉 STRONG SELL"
        elif score < 45:
            return "📉 SELL"
        else:
            return "⏸ HOLD"
    
    def _format_indicator_prediction(self, signal, indicators, patterns, volume, timeframe):
        """Форматирование прогноза на основе индикаторов"""
        lines = [
            f"🎯 **ПРОГНОЗ на {timeframe.upper()}**",
            "",
            f"💡 Рекомендация: **{signal}**",
            ""
        ]
        
        if indicators:
            lines.append("📊 **Индикаторы:**")
            lines.append(f"• RSI: {indicators.get('RSI', 0):.1f}")
            lines.append(f"• Тренд: {indicators.get('trend', 'N/A')}")
            lines.append(f"• EMA быстрая: {indicators.get('EMA_fast', 0):.5f}")
            lines.append(f"• EMA медленная: {indicators.get('EMA_slow', 0):.5f}")
            lines.append("")
        
        if patterns and patterns.get('pattern') != 'NEUTRAL':
            lines.append("🕯 **Паттерн:**")
            pattern_names = {
                'HAMMER': 'Бычий молот',
                'SHOOTING_STAR': 'Падающая звезда',
                'BULLISH_ENGULFING': 'Бычье поглощение',
                'BEARISH_ENGULFING': 'Медвежье поглощение'
            }
            pattern = patterns.get('pattern', 'NEUTRAL')
            lines.append(f"• {pattern_names.get(pattern, pattern)}")
            lines.append(f"• Сила: {patterns.get('strength', 50)}%")
            lines.append("")
        
        if volume and volume.get('signal') != 'NO_DATA':
            lines.append("📈 **Объем:**")
            lines.append(f"• Статус: {volume.get('signal', 'N/A')}")
            if volume.get('ratio'):
                lines.append(f"• Отношение к среднему: {volume.get('ratio', 1):.2f}x")
        
        lines.append("")
        lines.append("⏱ _Анализ выполнен на основе данных PocketOption_")
        
        return "\n".join(lines)
    
    def _format_ta_prediction(self, signal, ta_result, sr_result, timeframe):
        """Форматирование прогноза технического анализа"""
        lines = [
            f"🎯 **ПРОГНОЗ на {timeframe.upper()}**",
            "",
            f"💡 Рекомендация: **{signal}**",
            ""
        ]
        
        if ta_result:
            lines.append("📊 **Технический анализ:**")
            lines.append(f"• Тренд: {ta_result.get('trend', 'N/A')}")
            if ta_result.get('sma_20'):
                lines.append(f"• SMA 20: {ta_result.get('sma_20', 0):.5f}")
            if ta_result.get('sma_50'):
                lines.append(f"• SMA 50: {ta_result.get('sma_50', 0):.5f}")
            lines.append(f"• Текущая цена: {ta_result.get('current_price', 0):.5f}")
            lines.append("")
        
        if sr_result:
            lines.append("📍 **Уровни:**")
            lines.append(f"• Сопротивление: {sr_result.get('resistance', 0):.5f}")
            lines.append(f"• Поддержка: {sr_result.get('support', 0):.5f}")
            lines.append(f"• Pivot: {sr_result.get('pivot', 0):.5f}")
            lines.append("")
        
        lines.append("⏱ _Анализ выполнен на основе данных PocketOption_")
        
        return "\n".join(lines)
    
    def _get_fallback_prediction(self, timeframe):
        """Запасной прогноз при ошибке"""
        return f"""
🎯 **ПРОГНОЗ на {timeframe.upper()}**

⚠️ Временные технические сложности

Попробуйте:
• Выбрать другой таймфрейм
• Повторить через несколько секунд
• Использовать другую пару

_Приносим извинения за неудобства_
"""

# Глобальный экземпляр для использования в боте
fast_predictor = FastPredictionEngine()
