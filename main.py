from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import requests
import logging
import time
from dotenv import load_dotenv
import os

load_dotenv()
GPT_TOKEN = os.getenv('GPT_TOKEN')

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

class ChatRequest(BaseModel):
    thread_id: str
    asst_id: str
    api_key: str
    sale_token: str
    client_id: int
    message: str

def send_callback(callback_url, sale_token, client_id, open_ai_text, open_ai_status, open_ai_error):
    headers = {
        "Authorization": f"Bearer {sale_token}",
        "Content-Type": "application/json"
    }
    data = {
        "client_id": client_id,
        "open_ai_text": open_ai_text,
        "open_ai_status": open_ai_status,
        "open_ai_error": open_ai_error
    }
    logger.info(f"Sending data to callback URL: {callback_url}")
    try:
        response = requests.post(callback_url, json=data, headers=headers)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

def stream_chat_completion(thread_id, asst_id, message, retries=3):
    openai.api_key = GPT_TOKEN
    messages = []
    attempt = 0

    while attempt < retries:
        attempt += 1
        try:
            response = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=asst_id,
                additional_messages=[
                    {"role": "user", "content": message}
                ],
                model="gpt-4o-mini"
            )
            
            while response.status != "completed":
                response = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response.id
                )
                time.sleep(1)
            
            message_response = openai.beta.threads.messages.list(thread_id=thread_id)
            message_chunk = message_response.data[0].content[0].text.value.strip()
            messages.append(message_chunk)
            return ''.join(messages)
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(0.5)
            else:
                return '', str(e)

@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    if not req.thread_id:
        logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
        raise HTTPException(status_code=400, detail="thread_id must be provided")

    messages, error = stream_chat_completion(req.api_key, req.thread_id, req.asst_id, req.message)

    if messages:
        callback_url = f"https://chatter.salebot.pro/api/{req.api_key}/callback"
        send_callback(callback_url, req.sale_token, req.client_id, messages, "ok", "")
    else:
        callback_url = f"https://chatter.salebot.pro/api/{req.api_key}/callback"
        send_callback(callback_url, req.sale_token, req.client_id, "", "error", error)

    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
