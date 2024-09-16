from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
import requests
import logging
from dotenv import load_dotenv
import os
import asyncio
import tiktoken

load_dotenv()
GPT_TOKEN = os.getenv('GPT_TOKEN')

if GPT_TOKEN is None:
    raise RuntimeError("GPT_TOKEN is not set in .env file")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI()
openai.api_key = GPT_TOKEN


class ChatRequest(BaseModel):
    thread_id: str
    asst_id: str
    api_key: str
    client_id: int
    message: str
    callback_text: str


def count_tokens(text: str) -> int:
    tokenizer = tiktoken.encoding_for_model("gpt-4o-mini")
    return len(tokenizer.encode(text))


async def send_callback(callback_url, api_key, client_id, open_ai_text, open_ai_status, open_ai_error, callback_text, usage_info=None):
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
        "usage_info": usage_info
    }
    logger.info(f"Sending data to callback URL: {callback_url}")
    try:
        response = requests.post(callback_url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        logger.info(f"✅ Callback sent successfully to {callback_url}")
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to send callback: {e}")

        error_data = {
            "message": callback_text,
            "client_id": client_id,
            "open_ai_text": "",
            "open_ai_status": "error",
            "open_ai_error": f"Callback failed due to: {e}"
        }

        try:
            error_response = requests.post(callback_url, json=error_data, headers=headers, timeout=60)
            error_response.raise_for_status()
            logger.info(f"✅ Error callback sent successfully to {callback_url}")
        except requests.exceptions.RequestException as retry_exception:
            logger.error(f"❌ Failed to send error callback after retry: {retry_exception}")


async def stream_chat_completion(thread_id, asst_id, user_message, retries=3, timeout_limit=60):
    messages = []
    attempt = 0
    init_message = user_message

    try:
        openai.beta.threads.retrieve(thread_id=thread_id)
    except Exception as e:
        logger.error(f"❌ Error: No thread found with id {thread_id}. Details: {e}")
        return '', f"No thread found with id {thread_id}", None

    while attempt < retries:
        attempt += 1
        try:
            logger.info(f"🚀 Streaming attempt {attempt}/{retries} for thread {thread_id}, message: {init_message}")
            try:
                response_run_create = openai.beta.threads.runs.create(
                    thread_id=thread_id,
                    assistant_id=asst_id,
                    additional_messages=[
                        {"role": "user", "content": init_message}
                    ],
                    model="gpt-4o-mini",
                    timeout=60,
                    max_prompt_tokens=4096,
                    max_completion_tokens=4096
                )
            except Exception as exc:
                logger.error(f"❌ Error during openai.beta.threads.runs.create attempt {attempt}: {exc}")
                return '', str(exc), None

            start_time = asyncio.get_event_loop().time()

            while response_run_create.status != "completed":
                elapsed_time = asyncio.get_event_loop().time() - start_time
                if elapsed_time > timeout_limit:
                    logger.error(f"⏳ Timeout reached: {elapsed_time:.2f} seconds. Retrying...")
                    raise TimeoutError

                response_retrieve = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response_run_create.id
                )
                logger.info(f"🔄 Polling for completion... (status: {response_retrieve.status})")
                await asyncio.sleep(1)

            if response_retrieve.status == "completed":
                message_response = openai.beta.threads.messages.list(thread_id=thread_id)
                message_chunk = message_response.data[0].content[0].text.value.strip()
                messages.append(message_chunk)

                total_token_usage = count_tokens(init_message) + count_tokens(''.join(messages))
                usage_info = {
                    "prompt_tokens": count_tokens(init_message),
                    "completion_tokens": count_tokens(''.join(messages)),
                    "total_tokens": total_token_usage
                }

                return ''.join(messages), None, usage_info

        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                await asyncio.sleep(0.5)
            else:
                return '', str(e), None


@app.post("/")
async def chat_endpoint(req: ChatRequest):
    logger.info("Received chat request: %s\n\n", req.dict())
    if not req.thread_id:
        logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
        raise HTTPException(status_code=400, detail="thread_id must be provided")

    token_count = count_tokens(req.message)

    if token_count > 4096:
        logger.error(f"⚠️ Message too long, exceeds token limit: {token_count} tokens.")
        raise HTTPException(status_code=400, detail=f"Message exceeds token limit: {token_count} tokens.")

    await asyncio.create_task(process_request(req))
    return {"status": "ok", "message": "Processing started"}


async def process_request(req: ChatRequest):
    try:
        gpt_response, error, usage_info = await stream_chat_completion(req.thread_id, req.asst_id, req.message)

        callback_url = f"https://chatter.salebot.pro/api/{req.api_key}/callback"

        if gpt_response is None or gpt_response.strip() == '':
            logger.error("⛔ No valid response from GPT, cannot send empty message.")
            error = error or "No valid response from GPT"
            await send_callback(callback_url, req.api_key, req.client_id, "", "error", error, req.callback_text, usage_info)
            return

        if gpt_response:
            await send_callback(callback_url, req.api_key, req.client_id, gpt_response, "ok", "", req.callback_text, usage_info)
        else:
            await send_callback(callback_url, req.api_key, req.client_id, "", "error", error, req.callback_text, usage_info)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
