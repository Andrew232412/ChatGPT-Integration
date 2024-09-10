from fastapi import FastAPI
from pydantic import BaseModel
import openai
import requests
import logging
import time

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

CALLBACK_URL = "https://webhook.site/cd3aa6b0-97b2-4fe8-a071-d58a33b165f0"  # Замени на реальный URL

app = FastAPI()

class ChatRequest(BaseModel):
    thread_id: str = None
    asst_id: str
    gpt_token: str
    sale_token: str
    client_id: str
    message: str

def send_callback(callback_url, sale_token, client_id, messages):
    headers = {
        "Authorization": f"Bearer {sale_token}",
        "Content-Type": "application/json"
    }
    data = {
        "client_id": client_id,
        "messages": messages
    }
    logger.info(f"Sending data to callback URL: {callback_url}, data: {data}") ## вывод в консоль для проверки
    try:
        response = requests.post(callback_url, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

def stream_chat_completion(api_key, thread_id, asst_id, message, retries=3):
    openai.api_key = api_key
    messages = []
    attempt = 0

    while attempt < retries:
        attempt += 1
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": message}
                ]
            )
            
            message_chunk = response.choices[0].message['content'].strip()
            messages.append(message_chunk)
            print(message_chunk)
            
            logger.info("🏁 Streaming completed.")
            return ''.join(messages)
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(10)
            else:
                logger.error(f"❌ Failed after {retries} attempts.")
                return ''

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    try:
        # Если thread_id не предоставлен, создаем новый тред
        if req.thread_id is None:
            req.thread_id = create_thread()
            logger.info(f"Created new thread with ID: {req.thread_id}")
        else:
            logger.info(f"Using existing thread with ID: {req.thread_id}")

        messages = stream_chat_completion(req.gpt_token, req.thread_id, req.asst_id, req.message)

        if messages:
            send_callback(CALLBACK_URL, req.sale_token, req.client_id, messages)
        else:
            logger.error("⚠️ No messages received from ChatGPT")

        return {"status": "success"}
    
    except Exception as e:
        logger.error(f"❌ Error in chat_endpoint: {e}")
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
