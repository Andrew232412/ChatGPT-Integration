from openai import OpenAI
import requests
import logging
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def send_callback(callback_url, sale_token, client_id, messages):
    """
    Отправляем колбек с сообщениями в Sale.
    
    Параметры:
        callback_url (str): URL, куда отправляется ответ.
        sale_token (str): токен для авторизации в Sale.
        client_id (str): идентификатор клиента в Sale.
        messages (list): список сообщений от ChatGPT.
    """
    headers = {
        "Authorization": f"Bearer {sale_token}",
        "Content-Type": "application/json"
    }
    data = {
        "client_id": client_id,
        "messages": messages
    }
    try:
        response = requests.post(callback_url, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

def stream_chat_completion(client, thread_id, asst_id, message, retries=3):
    """
    Отправляем сообщение в существующий тред или создаём новый, используя стриминг ответов.

    Параметры:
        thread_id (str): уникальный идентификатор треда.
        asst_id (str): уникальный идентификатор ассистента.
        message (str): текстовое сообщение от пользователя.
        retries (int): количество попыток в случае ошибки.

    Возвращает:
        list: список сообщений от ChatGPT.
    """
    messages = []
    attempt = 0

    while attempt < retries:
        attempt += 1
        try:
            # Отправляем запрос с использованием стриминга
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": message}
                ],
                stream=True
            )
            
            # Стримим сообщения от ChatGPT
            for chunk in response:
                if chunk.choices[0].delta.content:
                    message_chunk = chunk.choices[0].delta.content
                    messages.append(message_chunk)
                    print(message_chunk, end="")  # Выводим сообщение в консоль по мере получения
            
            logger.info("🏁 Streaming completed.")
            return messages  # Если всё прошло успешно, возвращаем результат.
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(2)  # Добавляем задержку перед повторной попыткой.
            else:
                logger.error(f"❌ Failed after {retries} attempts.")
                return []

def main(thread_id, asst_id, gpt_token, sale_token, client_id, callback_url, message):
    """
    Основная функция для обработки чата с использованием стриминга и отправки колбека.

    Параметры:
        thread_id (str): идентификатор треда.
        asst_id (str): идентификатор ассистента.
        gpt_token (str): токен для ChatGPT.
        sale_token (str): токен для системы Sale.
        client_id (str): идентификатор клиента в системе Sale.
        callback_url (str): URL для отправки ответа.
        message (str): текстовое сообщение от пользователя.
    """
    try:
        # Создаём клиента OpenAI
        client = OpenAI(api_key=gpt_token)
        
        # Стримим сообщения от ChatGPT
        messages = stream_chat_completion(client, thread_id, asst_id, message)
        
        # Отправляем список сообщений в Sale через callback URL
        if messages:
            send_callback(callback_url, sale_token, client_id, messages)
        else:
            logger.error("⚠️ No messages received from ChatGPT")
    
    except Exception as e:
        logger.error(f"❌ Error in main process: {e}")

# Пример использования
if __name__ == "__main__":
    # Примерные входные данные
    thread_id = "example-thread-id"
    asst_id = "example-asst-id"
    gpt_token = "example-gpt-token"
    sale_token = "example-sale-token"
    client_id = "example-client-id"
    callback_url = "https://example.com/callback"
    message = "Пример сообщения для ассистента"

    # Запуск главной функции
    main(thread_id, asst_id, gpt_token, sale_token, client_id, callback_url, message)
