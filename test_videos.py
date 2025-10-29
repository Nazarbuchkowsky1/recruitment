#!/usr/bin/env python3
"""
Скрипт для тестирования доступности видео с CDN сервера
"""

import asyncio
import aiohttp
import json
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def check_video_availability(video_url):
    """Проверяет доступность видео по URL"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.head(video_url) as response:
                if response.status == 200:
                    logger.info(f"✅ Видео доступно: {video_url} (статус: {response.status})")
                    return True
                else:
                    logger.warning(f"❌ Видео недоступно: {video_url} (статус: {response.status})")
                    return False
    except Exception as e:
        logger.error(f"❌ Ошибка проверки видео {video_url}: {str(e)}")
        return False

async def test_all_videos():
    """Тестирует все видео из файла reviews.json"""
    try:
        with open("reviews.json", "r", encoding="utf-8") as f:
            reviews = json.load(f)
    except FileNotFoundError:
        logger.error("Файл reviews.json не найден")
        return
    except json.JSONDecodeError:
        logger.error("Ошибка чтения JSON из файла reviews.json")
        return
    
    logger.info(f"🔍 Тестируем {len(reviews)} видео...")
    
    available_count = 0
    unavailable_count = 0
    
    for i, review in enumerate(reviews):
        logger.info(f"📹 Проверяем видео {i+1}/{len(reviews)} (ID: {review['id']})")
        
        is_available = await check_video_availability(review['video'])
        if is_available:
            available_count += 1
        else:
            unavailable_count += 1
        
        await asyncio.sleep(0.5)
    
    logger.info(f"📊 Результаты тестирования:")
    logger.info(f"✅ Доступно: {available_count} видео")
    logger.info(f"❌ Недоступно: {unavailable_count} видео")
    logger.info(f"📈 Процент доступности: {(available_count/len(reviews)*100):.1f}%")

if __name__ == "__main__":
    asyncio.run(test_all_videos())
