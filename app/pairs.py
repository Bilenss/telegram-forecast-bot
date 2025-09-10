# app/pairs.py
"""
Полный список валютных пар PocketOption с проверкой доступности
"""
import asyncio
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger

# Полный список всех пар
ALL_PAIRS = {
    # Основные пары (FIN)
    "EUR/USD": {"po": "EURUSD", "category": "major"},
    "GBP/USD": {"po": "GBPUSD", "category": "major"},
    "USD/JPY": {"po": "USDJPY", "category": "major"},
    "USD/CHF": {"po": "USDCHF", "category": "major"},
    "USD/CAD": {"po": "USDCAD", "category": "major"},
    "AUD/USD": {"po": "AUDUSD", "category": "major"},
    "NZD/USD": {"po": "NZDUSD", "category": "major"},
    
    # Кросс-пары (FIN)
    "EUR/GBP": {"po": "EURGBP", "category": "cross"},
    "EUR/JPY": {"po": "EURJPY", "category": "cross"},
    "GBP/JPY": {"po": "GBPJPY", "category": "cross"},
    "EUR/CHF": {"po": "EURCHF", "category": "cross"},
    "EUR/AUD": {"po": "EURAUD", "category": "cross"},
    "EUR/CAD": {"po": "EURCAD", "category": "cross"},
    "GBP/CHF": {"po": "GBPCHF", "category": "cross"},
    "GBP/AUD": {"po": "GBPAUD", "category": "cross"},
    "GBP/CAD": {"po": "GBPCAD", "category": "cross"},
    "AUD/JPY": {"po": "AUDJPY", "category": "cross"},
    "AUD/CAD": {"po": "AUDCAD", "category": "cross"},
    "AUD/CHF": {"po": "AUDCHF", "category": "cross"},
    "AUD/NZD": {"po": "AUDNZD", "category": "cross"},
    "CAD/JPY": {"po": "CADJPY", "category": "cross"},
    "CAD/CHF": {"po": "CADCHF", "category": "cross"},
    "CHF/JPY": {"po": "CHFJPY", "category": "cross"},
    "NZD/JPY": {"po": "NZDJPY", "category": "cross"},
}

# OTC пары (добавляем _OTC ко всем основным)
OTC_PAIRS = {
    # Основные OTC
    "EUR/USD OTC": {"po": "EURUSD_OTC", "category": "otc", "otc": True},
    "GBP/USD OTC": {"po": "GBPUSD_OTC", "category": "otc", "otc": True},
    "USD/JPY OTC": {"po": "USDJPY_OTC", "category": "otc", "otc": True},
    "USD/CHF OTC": {"po": "USDCHF_OTC", "category": "otc", "otc": True},
    "USD/CAD OTC": {"po": "USDCAD_OTC", "category": "otc", "otc": True},
    "AUD/USD OTC": {"po": "AUDUSD_OTC", "category": "otc", "otc": True},
    "NZD/USD OTC": {"po": "NZDUSD_OTC", "category": "otc", "otc": True},
    
    # Кросс OTC
    "EUR/GBP OTC": {"po": "EURGBP_OTC", "category": "otc", "otc": True},
    "EUR/JPY OTC": {"po": "EURJPY_OTC", "category": "otc", "otc": True},
    "GBP/JPY OTC": {"po": "GBPJPY_OTC", "category": "otc", "otc": True},
    "EUR/CHF OTC": {"po": "EURCHF_OTC", "category": "otc", "otc": True},
    "EUR/AUD OTC": {"po": "EURAUD_OTC", "category": "otc", "otc": True},
    "EUR/CAD OTC": {"po": "EURCAD_OTC", "category": "otc", "otc": True},
    "GBP/CHF OTC": {"po": "GBPCHF_OTC", "category": "otc", "otc": True},
    "GBP/AUD OTC": {"po": "GBPAUD_OTC", "category": "otc", "otc": True},
    "GBP/CAD OTC": {"po": "GBPCAD_OTC", "category": "otc", "otc": True},
    "AUD/JPY OTC": {"po": "AUDJPY_OTC", "category": "otc", "otc": True},
    "AUD/CAD OTC": {"po": "AUDCAD_OTC", "category": "otc", "otc": True},
    "AUD/CHF OTC": {"po": "AUDCHF_OTC", "category": "otc", "otc": True},
    "AUD/NZD OTC": {"po": "AUDNZD_OTC", "category": "otc", "otc": True},
    "CAD/JPY OTC": {"po": "CADJPY_OTC", "category": "otc", "otc": True},
    "CAD/CHF OTC": {"po": "CADCHF_OTC", "category": "otc", "otc": True},
    "CHF/JPY OTC": {"po": "CHFJPY_OTC", "category": "otc", "otc": True},
    "NZD/JPY OTC": {"po": "NZDJPY_OTC", "category": "otc", "otc": True},
    
    # Экзотические OTC
    "EUR/NZD OTC": {"po": "EURNZD_OTC", "category": "otc", "otc": True},
    "EUR/RUB OTC": {"po": "EURRUB_OTC", "category": "otc", "otc": True},
    "EUR/TRY OTC": {"po": "EURTRY_OTC", "category": "otc", "otc": True},
    "EUR/HUF OTC": {"po": "EURHUF_OTC", "category": "otc", "otc": True},
    "USD/RUB OTC": {"po": "USDRUB_OTC", "category": "otc", "otc": True},
    "USD/MXN OTC": {"po": "USDMXN_OTC", "category": "otc", "otc": True},
    "USD/INR OTC": {"po": "USDINR_OTC", "category": "otc", "otc": True},
    "USD/CNH OTC": {"po": "USDCNH_OTC", "category": "otc", "otc": True},
    "USD/THB OTC": {"po": "USDTHB_OTC", "category": "otc", "otc": True},
    "USD/SGD OTC": {"po": "USDSGD_OTC", "category": "otc", "otc": True},
    "USD/BRL OTC": {"po": "USDBRL_OTC", "category": "otc", "otc": True},
    "USD/ARS OTC": {"po": "USDARS_OTC", "category": "otc", "otc": True},
    "USD/CLP OTC": {"po": "USDCLP_OTC", "category": "otc", "otc": True},
    "USD/COP OTC": {"po": "USDCOP_OTC", "category": "otc", "otc": True},
    "USD/PKR OTC": {"po": "USDPKR_OTC", "category": "otc", "otc": True},
    "USD/EGP OTC": {"po": "USDEGP_OTC", "category": "otc", "otc": True},
    "USD/VND OTC": {"po": "USDVND_OTC", "category": "otc", "otc": True},
    "USD/IDR OTC": {"po": "USDIDR_OTC", "category": "otc", "otc": True},
    "USD/PHP OTC": {"po": "USDPHP_OTC", "category": "otc", "otc": True},
    "USD/MYR OTC": {"po": "USDMYR_OTC", "category": "otc", "otc": True},
    "USD/BDT OTC": {"po": "USDBDT_OTC", "category": "otc", "otc": True},
    "USD/DZD OTC": {"po": "USDDZD_OTC", "category": "otc", "otc": True},
    
    # Специальные OTC
    "CHF/NOK OTC": {"po": "CHFNOK_OTC", "category": "otc", "otc": True},
    "ZAR/USD OTC": {"po": "ZARUSD_OTC", "category": "otc", "otc": True},
    "NGN/USD OTC": {"po": "NGNUSD_OTC", "category": "otc", "otc": True},
    "TND/USD OTC": {"po": "TNDUSD_OTC", "category": "otc", "otc": True},
    "MAD/USD OTC": {"po": "MADUSD_OTC", "category": "otc", "otc": True},
    "LBP/USD OTC": {"po": "LBPUSD_OTC", "category": "otc", "otc": True},
    "YER/USD OTC": {"po": "YERUSD_OTC", "category": "otc", "otc": True},
    "KES/USD OTC": {"po": "KESUSD_OTC", "category": "otc", "otc": True},
    "UAH/USD OTC": {"po": "UAHUSD_OTC", "category": "otc", "otc": True},
    
    # Криптовалютные индексы OTC
    "AED/CNY OTC": {"po": "AEDCNY_OTC", "category": "otc", "otc": True},
    "BHD/CNY OTC": {"po": "BHDCNY_OTC", "category": "otc", "otc": True},
    "JOD/CNY OTC": {"po": "JODCNY_OTC", "category": "otc", "otc": True},
    "OMR/CNY OTC": {"po": "OMRCNY_OTC", "category": "otc", "otc": True},
    "QAR/CNY OTC": {"po": "QARCNY_OTC", "category": "otc", "otc": True},
    "SAR/CNY OTC": {"po": "SARCNY_OTC", "category": "otc", "otc": True},
}

class PairAvailability:
    """
    Класс для проверки доступности пар
    """
    def __init__(self):
        self.unavailable_pairs = set()
        self.last_check = None
        self.check_interval = timedelta(minutes=5)  # Проверяем каждые 5 минут
    
    async def check_pair_availability(self, pair_name: str) -> bool:
        """
        Проверяет доступность конкретной пары
        Можно реализовать проверку через API или веб-скрапинг
        """
        # Временная заглушка - считаем все пары доступными
        # В реальности здесь должна быть проверка через PocketOption
        
        # Симуляция недоступных пар (для примера)
        temporarily_unavailable = [
            "EUR/HUF OTC",
            "USD/DZD OTC", 
            "YER/USD OTC"
        ]
        
        if pair_name in temporarily_unavailable:
            return False
        
        return True
    
    async def update_availability(self):
        """
        Обновляет список доступных пар
        """
        logger.info("Updating pairs availability...")
        
        unavailable = set()
        
        # Проверяем каждую пару
        all_pairs_combined = {**ALL_PAIRS, **OTC_PAIRS}
        
        for pair_name in all_pairs_combined:
            is_available = await self.check_pair_availability(pair_name)
            if not is_available:
                unavailable.add(pair_name)
                logger.info(f"Pair {pair_name} is N/A")
        
        self.unavailable_pairs = unavailable
        self.last_check = datetime.now()
        
        logger.info(f"Found {len(unavailable)} unavailable pairs")
    
    async def is_available(self, pair_name: str) -> bool:
        """
        Проверяет доступность пары с кэшированием
        """
        # Обновляем если прошло больше интервала
        if (self.last_check is None or 
            datetime.now() - self.last_check > self.check_interval):
            await self.update_availability()
        
        return pair_name not in self.unavailable_pairs
    
    def get_status_text(self, pair_name: str) -> str:
        """
        Возвращает статус пары
        """
        if pair_name in self.unavailable_pairs:
            return f"{pair_name} (N/A)"
        return pair_name

# Глобальный экземпляр
availability_checker = PairAvailability()

def all_pairs(category: str) -> Dict:
    """
    Возвращает пары по категории с учетом доступности
    """
    if category == "fin":
        return ALL_PAIRS
    elif category == "otc":
        return OTC_PAIRS
    else:
        # Все пары
        return {**ALL_PAIRS, **OTC_PAIRS}

async def get_available_pairs(category: str) -> Dict:
    """
    Возвращает только доступные пары
    """
    pairs = all_pairs(category)
    available = {}
    
    for name, info in pairs.items():
        if await availability_checker.is_available(name):
            available[name] = info
        else:
            # Добавляем с пометкой N/A
            available[f"{name} (N/A)"] = {**info, "available": False}
    
    return available

def get_pair_info(pair_name: str) -> Optional[Dict]:
    """
    Получает информацию о паре
    """
    # Убираем (N/A) если есть
    clean_name = pair_name.replace(" (N/A)", "")
    
    all_pairs_combined = {**ALL_PAIRS, **OTC_PAIRS}
    return all_pairs_combined.get(clean_name)
