import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import requests

app = FastAPI()

# Получаем API ключи из переменных окружения
openai.api_key = os.getenv("OPENAI_API_KEY")  # Устанавливаем ключ OpenAI из переменной окружения
currentsapi_key = os.getenv("CURRENTS_API_KEY")  # Устанавливаем ключ Currents API из переменной окружения
proxyapi_url = os.getenv("PROXYAPI_URL", "https://api.proxyapi.ru/openai/v1")  # URL ProxyAPI с дефолтным значением

# Проверяем, что оба API ключа заданы, иначе выбрасываем ошибку
if not openai.api_key or not currentsapi_key:
    raise ValueError("Переменные окружения OPENAI_API_KEY и CURRENTS_API_KEY должны быть установлены")

# Конфигурация OpenAI для работы через ProxyAPI
openai.api_base = proxyapi_url  # Переопределяем базовый URL для всех запросов OpenAI
openai.api_version = "2023-05-15"  # Указываем версию API (может требоваться для ProxyAPI)

class Topic(BaseModel):
    topic: str  # Модель данных для получения темы в запросе

# Функция для получения последних новостей на заданную тему
def get_recent_news(topic: str):
    """
    Получает последние новости по заданной теме через CurrentsAPI.
    
    Args:
        topic (str): Тема для поиска новостей
        
    Returns:
        str: Строка с заголовками новостей, разделенными переносами строк
    """
    url = "https://api.currentsapi.services/v1/latest-news"  # URL API для получения новостей
    params = {
        "language": "ru",  # Задаем язык новостей (английский), mожно изменить на: 'en' 'ru', 'fr', 'de' и другие поддерживаемые языки
        "АСУ ТП": topic,  # Ключевые слова для поиска новостей
        "apiKey": currentsapi_key  # Передаем API ключ CurrentsAPI
    }
    response = requests.get(url, params=params)  # Выполняем GET-запрос к API
    
    if response.status_code != 200:
        # Если статус код не 200, выбрасываем исключение с подробностями ошибки
        raise HTTPException(status_code=500, detail=f"Ошибка при получении данных: {response.text}")
    
    # Извлекаем новости из ответа, если они есть
    news_data = response.json().get("news", [])
    if not news_data:
        return "Свежих новостей не найдено."  # Сообщение, если новости отсутствуют
    
    # Возвращаем заголовки первых 5 новостей, разделенных переносами строк, можно установить больше или меньше
    return "\n".join([article["title"] for article in news_data[:5]])

# Функция для генерации контента на основе темы и новостей
def generate_content(topic: str):
    """
    Генерирует контент (заголовок, описание и текст статьи) по заданной теме.
    
    Args:
        topic (str): Тема для генерации контента
        
    Returns:
        dict: Словарь сгенерированного контента (title, meta_description, post_content)
    """
    recent_news = get_recent_news(topic)  # Получаем последние новости по теме

    try:
        # Генерация заголовка для статьи через ProxyAPI
        title = openai.ChatCompletion.create(
            model="gpt-4o-mini",  # Используем модель GPT-4o-mini (через ProxyAPI может быть доступна другая версия)
            messages=[{
                "role": "user", 
                "content": f"Придумайте привлекательный и точный заголовок для статьи на тему '{topic}', с учётом актуальных новостей:\n{recent_news}. Заголовок должен быть интересным и ясно передавать суть темы."
            }],
            max_tokens=60,  # Ограничиваем длину ответа
            temperature=0.5,  # Умеренная случайность
            stop=["\n"],  # Прерывание на новой строке
            timeout=15  # Таймаут запроса в секундах
        ).choices[0].message.content.strip()

        # Генерация мета-описания для статьи
        meta_description = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user", 
                "content": f"Напишите мета-описание для статьи с заголовком: '{title}'. Оно должно быть полным, информативным и содержать основные ключевые слова."
            }],
            max_tokens=120,  # Увеличиваем лимит токенов для полного ответа
            temperature=0.5,
            stop=["."],
            timeout=15
        ).choices[0].message.content.strip()

        # Генерация полного контента статьи
        post_content = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{
                "role": "user", 
                "content": f"""Напишите подробную статью на тему '{topic}', используя последние новости:\n{recent_news}. 
                Статья должна быть:
                1. Информативной и логичной
                2. Содержать не менее 1500 символов
                3. Иметь четкую структуру с подзаголовками
                4. Включать анализ текущих трендов
                5. Иметь вступление, основную часть и заключение
                6. Включать примеры из актуальных новостей
                7. Каждый абзац должен быть не менее 3-4 предложений
                8. Текст должен быть легким для восприятия и содержательным"""
            }],
            max_tokens=1500,  # Лимит токенов для развернутого текста
            temperature=0.5,
            presence_penalty=0.6,  # Штраф за повторение фраз
            frequency_penalty=0.6,
            timeout=30  # Увеличенный таймаут для длинного контента
        ).choices[0].message.content.strip()

        # Возвращаем сгенерированный контент
        return {
            "title": title,
            "meta_description": meta_description,
            "post_content": post_content
        }
    
    except requests.exceptions.Timeout:
        # Обработка ошибки таймаута
        raise HTTPException(status_code=504, detail="Превышено время ожидания ответа от ProxyAPI")
    except Exception as e:
        # Обрабатываем другие ошибки генерации
        raise HTTPException(status_code=500, detail=f"Ошибка при генерации контента: {str(e)}")

@app.post("/generate-post")
async def generate_post_api(topic: Topic):
    """
    API endpoint для генерации контента по заданной теме.
    
    Args:
        topic (Topic): Объект с полем 'topic' содержащим тему для генерации
        
    Returns:
        dict: Сгенерированный контент или сообщение об ошибке
    """
    return generate_content(topic.topic)

@app.get("/")
async def root():
    """
    Корневой эндпоинт для проверки работоспособности сервиса.
    """
    return {"message": "Служба запущена"}

@app.get("/heartbeat")
async def heartbeat_api():
    """
    Эндпоинт проверки состояния сервиса (healthcheck).
    """
    return {"status": "Все работает, отлично!"}

if __name__ == "__main__":
    import uvicorn
    # Запуск приложения с указанием порта
    port = int(os.getenv("PORT", 8000))  # Порт из переменной окружения или 8000 по умолчанию
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)  # Добавлен reload для разработки
