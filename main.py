from openai import OpenAI
import requests
import logging
import time
import responses

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

def send_callback(callback_url, sale_token, client_id, messages):
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
    messages = []
    attempt = 0

    while attempt < retries:
        attempt += 1
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": message}
                ],
                stream=True
            )
            
            for chunk in response:
                if chunk.choices[0].delta.content:
                    message_chunk = chunk.choices[0].delta.content
                    messages.append(message_chunk)
                    print(message_chunk, end="")
            
            logger.info("🏁 Streaming completed.")
            return messages
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(10)
            else:
                logger.error(f"❌ Failed after {retries} attempts.")
                return []

def main(thread_id, asst_id, gpt_token, sale_token, client_id, callback_url, message):
    try:
        client = OpenAI(api_key=gpt_token)
        
        messages = stream_chat_completion(client, thread_id, asst_id, message)
        
        if messages:
            send_callback(callback_url, sale_token, client_id, messages)
        else:
            logger.error("⚠️ No messages received from ChatGPT")
    
    except Exception as e:
        logger.error(f"❌ Error in main process: {e}")

if __name__ == "__main__":
    thread_id = "mock-thread-id"
    asst_id = "mock-asst-id"
    gpt_token = "mock-gpt-token"
    sale_token = "mock-sale-token"
    client_id = "mock-client-id"
    callback_url = "https://httpbin.org/post"
    message = "Пример сообщения для ассистента"

    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "https://api.openai.com/v1/chat/completions", 
                 json={"choices": [{"delta": {"content": "Test response"}}]}, 
                 status=200)
        
        rsps.add(responses.POST, callback_url, json={"status": "success"}, status=200)
        
        main(thread_id, asst_id, gpt_token, sale_token, client_id, callback_url, message)
