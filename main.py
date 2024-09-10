from fastapi import FastAPI, HTTPException
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
    logger.info(f"Sending data to callback URL: {callback_url}, data: {data}")
    try:
        response = requests.post(callback_url, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

def create_new_thread(api_key, asst_id, message):
    openai.api_key = api_key
    try:
        response = openai.beta.threads.create(
            messages=[
                {"role": "user", "content": message}
            ],
            model="gpt-4o-mini"
        )
        thread_id = response.id
        logger.info(f"✅ New thread created with ID: {thread_id}")
        return thread_id
    except Exception as e:
        logger.error(f"❌ Error creating new thread: {e}")
        return None

def stream_chat_completion(api_key, thread_id, asst_id, message, retries=3):
    openai.api_key = api_key
    messages = []
    attempt = 0

    while attempt < retries:
        attempt += 1
        try:
            # Если тред уже существует, продолжаем диалог
            response = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=asst_id,
                additional_messages=[
                    {"role": "user", "content": message}
                ],
                model="gpt-4o-mini"
            )
            
            # Ожидание завершения выполнения
            while response.status != "completed":
                response = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response.id
                )
                time.sleep(1)
            
            message_response = openai.beta.threads.messages.list(thread_id=thread_id)
            message_chunk = message_response.data[0].content[0].text.value.strip()
            messages.append(message_chunk)
            logger.info(f"🏁 Received message chunk: {message_chunk}")
            
            return ''.join(messages)
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(0.5)
            else:
                logger.error(f"❌ Failed after {retries} attempts.")
                return ''

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    try:
        # Проверяем, если тред не передан, возвращаем ошибку
        if not req.thread_id:
            logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
            raise HTTPException(status_code=400, detail="thread_id must be provided")

        messages = stream_chat_completion(req.gpt_token, req.thread_id, req.asst_id, req.message)

        if messages:
            send_callback(CALLBACK_URL, req.sale_token, req.client_id, messages)
        else:
            logger.error("⚠️ No messages received from ChatGPT")

        return {"status": "success"}
    
    except Exception as e:
        logger.error(f"❌ Error in chat_endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
