from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
from openai import AsyncOpenAI
import requests
import logging
from dotenv import load_dotenv
import os
import asyncio
import time 

load_dotenv()
GPT_TOKEN = os.getenv('GPT_TOKEN')

if GPT_TOKEN is None:
    raise RuntimeError("GPT_TOKEN is not set in .env file")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()
openai.api_key = GPT_TOKEN

client = AsyncOpenAI(api_key=GPT_TOKEN)

class ChatRequest(BaseModel):
    thread_id: str
    asst_id: str
    api_key: str
    client_id: int
    message: str
    callback_text: str


async def send_callback(callback_url, api_key, client_id, open_ai_text, open_ai_status, open_ai_error, callback_text):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "message": callback_text,
        "client_id": client_id,
        "open_ai_status": open_ai_status
    }

    # If we have a response from ChatGPT, we send it in the callback
    if open_ai_text:
        data["open_ai_text"] = open_ai_text
    
    # If an error occurs, we send it to the callback
    if open_ai_error:
        data["open_ai_error"] = open_ai_error

    try:
        response = requests.post(callback_url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

        # If the callback is not sent, try to resend with error information
        error_data = {
            "message": callback_text,
            "client_id": client_id,
            "open_ai_status": "error",
            "open_ai_error": f"Callback failed due to: {e}"
        }

        logger.info(f"Sending callback to {callback_url} with status {open_ai_status}, error: {open_ai_error}")

        try:
            error_response = requests.post(callback_url, json=error_data, headers=headers, timeout=60)
            error_response.raise_for_status()
            logger.info(f"✅ Error callback sent successfully to {callback_url}")
        except requests.exceptions.RequestException as retry_exception:
            logger.error(f"❌ Failed to send error callback after retry: {retry_exception}")


async def stream_chat_completion(thread_id: str, asst_id: str, user_message: str, retries: int = 3, timeout_limit: int = 60):
    messages = []
    attempt = 0
    init_message = user_message
    start_time = time.time()

    # Check if the thread exists
    try:
        await client.beta.threads.retrieve(thread_id=thread_id)
    except Exception as e:
        logger.error(f"❌ Error: No thread found with id {thread_id}. Details: {e}")
        return '', f"No thread found with id {thread_id}"

    while attempt < retries:
        attempt += 1
        try:
            logger.info(f"🚀 Attempt {attempt}/{retries} for thread {thread_id}, message: {init_message}")
            
            response_run_create = await client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=asst_id,
                additional_messages=[
                    {"role": "user", "content": init_message}
                ],
                model="gpt-4o-mini",
                timeout=60,
            )

            while True:
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout_limit:
                    logger.error(f"⏳ Timeout reached: {elapsed_time:.2f} seconds. Retrying...")
                    raise TimeoutError 

                response_retrieve = await client.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response_run_create.id
                )
                logger.info(f"🔄 Polling for completion... (status: {response_retrieve.status})")
                if response_retrieve.status == "completed":
                    break
                await asyncio.sleep(1)

            if response_retrieve.status == "completed":
                message_response = await client.beta.threads.messages.list(thread_id=thread_id)
                message_chunk = message_response.data[0].content[0].text.value.strip()
                messages.append(message_chunk)

                return ''.join(messages), None

        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(0.5)
            else:
                return '', str(e)

    return '', 'Max retries exceeded'



@app.post("/")
async def chat_endpoint(req: ChatRequest):
    logger.info("Received chat request: %s\n\n", req.dict())
    if not req.thread_id:
        logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
        raise HTTPException(status_code=400, detail="thread_id must be provided")

    asyncio.create_task(process_request(req))
    return {"status": "ok", "message": "Processing started"}


async def process_request(req: ChatRequest):
    try:
        logger.info(f"🚀 Processing request for thread_id: {req.thread_id}")
        gpt_response, open_ai_error = await stream_chat_completion(req.thread_id, req.asst_id, req.message)

        callback_url = f"https://chatter.salebot.pro/api/{req.api_key}/callback"

        if gpt_response is None or gpt_response.strip() == '':
            logger.error("⛔ No valid response from GPT, cannot send empty message.")
            open_ai_error = open_ai_error or "No valid response from GPT"
            await send_callback(callback_url, req.api_key, req.client_id, "ChatGPT did not return a valid response", "error", open_ai_error, req.callback_text)
            return

        if gpt_response:
            logger.info(f"✅ GPT response: {gpt_response}")
            await send_callback(callback_url, req.api_key, req.client_id, open_ai_text=gpt_response, open_ai_status="ok", callback_text=req.callback_text)
        else:
            logger.error(f"❌ Error: {open_ai_error}")
            await send_callback(callback_url, req.api_key, req.client_id, open_ai_status="error", open_ai_error=open_ai_error, callback_text=req.callback_text)

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await send_callback(f"https://chatter.salebot.pro/api/{req.api_key}/callback", req.api_key, req.client_id, open_ai_status="error", open_ai_error=str(e), callback_text=req.callback_text)



if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
