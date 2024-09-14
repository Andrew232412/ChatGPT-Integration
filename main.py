from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import requests
import logging
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()
GPT_TOKEN = os.getenv('GPT_TOKEN')

if GPT_TOKEN is None:
    raise RuntimeError("GPT_TOKEN is not set in .env file")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()

class ChatRequest(BaseModel):
    thread_id: str
    asst_id: str
    api_key: str
    client_id: int
    message: str
    callback_text: str

async def send_callback(callback_url, api_key, client_id, open_ai_text, open_ai_status, open_ai_error, callback_text, total_tokens):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "message": callback_text,
        "client_id": client_id,
        "open_ai_text": open_ai_text,
        "open_ai_status": open_ai_status,
        "open_ai_error": open_ai_error,
        "total_tokens": total_tokens
    }
    logger.info(f"Sending data to callback URL: {callback_url}")
    try:
        response = requests.post(callback_url, json=data, headers=headers, timeout=30)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

        error_data = {
            "message": callback_text, 
            "client_id": client_id,
            "open_ai_text": "",
            "open_ai_status": "error",
            "open_ai_error": f"Callback failed due to: {e}",
             "total_tokens": total_tokens
        }
        
        try:
            error_response = requests.post(callback_url, json=error_data, headers=headers, timeout=30)
            error_response.raise_for_status()
            logger.info(f"✅ Error callback sent successfully to {callback_url}")
        except requests.exceptions.RequestException as retry_exception:
            logger.error(f"❌ Failed to send error callback after retry: {retry_exception}")

async def stream_chat_completion(thread_id, asst_id, user_message, retries=3):
    openai.api_key = GPT_TOKEN
    messages = []
    attempt = 0
    total_tokens = 0

    while attempt < retries:
        attempt += 1
        try:
            response = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=asst_id,
                additional_messages=[
                    {"role": "user", "content": user_message}
                ],
                model="gpt-4o-mini",
                timeout=30
            )

            total_tokens = response['usage']['total_tokens']

            while response.status != "completed":
                response = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response.id
                )
                await asyncio.sleep(1)
            
            message_response = openai.beta.threads.messages.list(thread_id=thread_id)
            message_chunk = message_response.data[0].content[0].text.value.strip()
            messages.append(message_chunk)

            # Печатаем, что получили ответ от GPT НАДО УДАЛИТЬ
            print(f"Received GPT message chunk: {message_chunk}")

            return ''.join(messages), None, total_tokens
        
        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(0.5)
            else:
                return '', str(e)

@app.post("/")
async def chat_endpoint(req: ChatRequest):
    if not req.thread_id:
        logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
        raise HTTPException(status_code=400, detail="thread_id must be provided")

    asyncio.create_task(process_request(req))
    return {"status": "ok", "message": "Processing started"}

async def process_request(req: ChatRequest):
    gpt_response, error, total_tokens = await stream_chat_completion(req.thread_id, req.asst_id, req.message)

    callback_url = f"https://chatter.salebot.pro/api/{req.api_key}/callback"

    # Печатаем ответ от GPT и детали для отправки колбека НАДО УДАЛИТЬ
    print(f"GPT Response: {gpt_response}")
    print(f"Callback Text: {req.callback_text}")
    print(f"Error: {error if error else 'No error'}")
    
    if gpt_response:
        await send_callback(callback_url, req.api_key, req.client_id, gpt_response, "ok", "", req.callback_text, total_tokens)
    else:
        await send_callback(callback_url, req.api_key, req.client_id, "", "error", error, req.callback_text, total_tokens)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
