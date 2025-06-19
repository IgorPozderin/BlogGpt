import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import requests

app = FastAPI()

# Получаем API ключи из переменных окружения
openai.api_key = os.getenv("OPENAI_API_KEY")  # Ключ для доступа к OpenAI API
currentsapi_key = os.getenv("CURRENTS_API_KEY")  # Ключ для доступа к Currents API
proxyapi_url = os.getenv("PROXYAPI_URL", "https://api.proxyapi.ru/openai/v1")  # URL ProxyAPI

# Проверка наличия обязательных API ключей
if not openai.api_key or not currentsapi_key:
    raise ValueError("Необходимо установить переменные окружения OPENAI_API_KEY и CURRENTS_API_KEY")

# Конфигурация для работы через ProxyAPI
openai.api_base = proxyapi_url  # Базовый URL для OpenAI запросов
openai.api_version = "2023-05-15"  # Версия API для совместимости

class Topic(BaseModel):
    topic: str  # Модель запроса с единственным полем 'topic'

def get_recent_news(topic: str):
    """
    Получает последние новости по заданной теме через Currents API.
    
    Параметры:
        topic (str): Тема для поиска новостей
        
    Возвращает:
        str: Заголовки новостей, разделенные переносами строк
    """
    url = "https://api.currentsapi.services/v1/latest-news"
    params = {
        "language": "ru",  # Язык новостей (русский)
        "keywords": topic,  # Ключевые слова для поиска (исправлено с 'АСУ ТП' на 'keywords')
        "category": "technology",  # Категория новостей
        "country": "ru",  # Страна
        "page_size": 5,  # Количество возвращаемых новостей
        "apiKey": currentsapi_key  # API ключ
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        news_data = response.json().get("news", [])
        if not news_data:
            return "Свежих новостей по данной теме не найдено."
            
        return "\n".join([article["title"] for article in news_data[:5]])
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Ошибка при запросе новостей: {str(e)}")

def generate_content(topic: str):
    """
    Генерирует контент на основе темы и актуальных новостей.
    
    Параметры:
        topic (str): Тема для генерации контента
        
    Возвращает:
        dict: Сгенерированный контент (заголовок, описание, текст статьи)
    """
    recent_news = get_recent_news(topic)

    try:
        # Генерация заголовка
        title = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Создайте заголовок для статьи на тему '{topic}' с учетом новостей:\n{recent_news}"
            }],
            max_tokens=60,
            temperature=0.5,
            timeout=15
        ).choices[0].message.content.strip()

        # Генерация описания
        meta_description = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Напишите SEO-описание для статьи '{title}'"
            }],
            max_tokens=120,
            temperature=0.5,
            timeout=15
        ).choices[0].message.content.strip()

        # Генерация основного текста
        post_content = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user",
                "content": f"Напишите развернутую статью на тему '{topic}'. Требования:\n1. 1500+ символов\n2. Структура с подзаголовками\n3. Анализ трендов\n4. Примеры из новостей:\n{recent_news}"
            }],
            max_tokens=1500,
            temperature=0.5,
            timeout=30
        ).choices[0].message.content.strip()

        return {
            "title": title,
            "meta_description": meta_description,
            "post_content": post_content
        }

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Таймаут при запросе к OpenAI")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка генерации: {str(e)}")

@app.post("/generate-post")
async def generate_post_api(topic: Topic):
    """Endpoint для генерации контента по теме"""
    return generate_content(topic.topic)

@app.get("/", methods=["GET", "HEAD"])
async def root():
    """Основной endpoint для проверки работы сервиса"""
    return {"message": "Сервис генерации контента работает"}

@app.get("/health", methods=["GET", "HEAD"])
async def health_check():
    """Endpoint для проверки здоровья сервиса"""
    return {"status": "OK", "details": "Сервис функционирует нормально"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        workers=1,
        timeout_keep_alive=30,
        log_level="info"
    )
    
