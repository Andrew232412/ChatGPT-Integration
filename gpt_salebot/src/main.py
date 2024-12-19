import base64
import json

from pydantic import BaseModel
import openai
import requests
import logging
from dotenv import load_dotenv
import os
import asyncio
import time
from sentry_sdk.integrations.serverless import serverless_function
from src.sentry_helper import *


load_dotenv()
GPT_TOKEN = os.getenv('GPT_TOKEN')

if GPT_TOKEN is None:
    raise RuntimeError("GPT_TOKEN is not set in .env file")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

openai.api_key = GPT_TOKEN


class ChatRequest(BaseModel):
    thread_id: str
    asst_id: str
    api_key: str
    client_id: int
    message: str
    callback_text: str


def send_callback(callback_url, api_key, client_id, open_ai_status, callback_text, open_ai_error=None, open_ai_text=None):
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
        for _ in range(4):
            try:
                response = requests.post(callback_url, json=data, headers=headers, timeout=60)
                response.raise_for_status()
                logger.info(f"✅ Callback sent successfully to {callback_url}")
                return
            except Exception as exc:
                pass
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


def stream_chat_completion(thread_id: str, asst_id: str, user_message: str, retries: int = 3, timeout_limit: int = 60 * 7, max_delay=30):
    messages = []
    attempt = 1
    init_message = user_message
    start_time = time.time()
    gpt_response = None
    gpt_error = None

    # Check if the thread exists
    try:
        openai.beta.threads.retrieve(thread_id=thread_id)
    except Exception as e:
        logger.error(f"❌ Error: No thread found with id {thread_id}. Details: {e}")
        gpt_error = f"No thread found with id {thread_id}"
        return gpt_response, gpt_error

    while attempt < retries:
        try:
            logger.info(f"🚀 Attempt {attempt}/{retries} for thread {thread_id}, message: {init_message}")

            response_run_create = openai.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=asst_id,
                additional_messages=[
                    {"role": "user", "content": init_message}
                ],
                model="gpt-4o-mini",
                timeout=60,
            )

            delay = 1  # Start with a 1-second delay
            while True:
                elapsed_time = time.time() - start_time
                if elapsed_time > timeout_limit:
                    logger.error(f"⏳ Timeout reached: {elapsed_time:.2f} seconds. Retrying...")
                    raise TimeoutError

                response_retrieve = openai.beta.threads.runs.retrieve(
                    thread_id=thread_id, run_id=response_run_create.id
                )
                logger.info(f"🔄 Polling for completion... (status: {response_retrieve.status})")

                if response_retrieve.status == "completed":
                    break

                if response_retrieve.status not in ["in_progress", "queued"]:
                    raise Exception(f"Run failed: {response_retrieve.status}")

                time.sleep(delay)
                delay = 1

            if response_retrieve.status == "completed":
                message_response = openai.beta.threads.messages.list(thread_id=thread_id)
                message_chunk = message_response.data[0].content[0].text.value.strip()
                messages.append(message_chunk)

                return ''.join(messages), None

            elif response_retrieve.status == "failed":
                gpt_error = response_retrieve.error
                return gpt_response, gpt_error

        except TimeoutError:
            logger.error(f"⏳ Timeout reached: {timeout_limit} seconds. Retrying...")
            return '', 'Timeout fetching response from OPENAI API'

        except Exception as e:
            logger.error(f"❌ Error during streaming attempt {attempt}: {e}")
            if attempt < retries:
                logger.info(f"🔄 Retrying... (attempt {attempt + 1}/{retries})")
                time.sleep(1)
            else:
                gpt_error = str(e)
                return gpt_response, gpt_error

        attempt += 1

    return '', 'Max retries exceeded'


@serverless_function
def handler(event, context):
    if event.get("isBase64Encoded"):
        decoded_body = base64.b64decode(event["body"]).decode('utf-8')
        event = json.loads(decoded_body)
    elif event.get("debuuuuug"):
        event = event["body"]
    else:
        event = json.loads(event["body"])

    logger.info("Received event: %s", event)

    if event.get("LOGIN_EXTENSION"):
        return {"status": "ok", "message": "Processing started"}

    logger.info("Received chat request: %s\n\n", event)
    if not event.get("thread_id"):
        logger.error("⚠️ No thread_id provided. Cannot proceed without a thread.")
        raise Exception(f"thread_id must be provided: {event}")

    process_request(event)
    return {"status": "ok", "message": "Processing started"}


def process_request(event):
    thread_id = event["thread_id"]
    ass_id = event["asst_id"]
    message = event["message"]
    api_key = event["api_key"]
    client_id = event["client_id"]
    callback_text = event["callback_text"]

    try:
        if not message:
            raise Exception("message must be provided")

        logger.info(f"🚀 Processing request for thread_id: {thread_id}")
        gpt_response, open_ai_error = stream_chat_completion(thread_id, ass_id, message)

        callback_url = f"https://chatter.salebot.pro/api/{api_key}/callback"

        if gpt_response is None or gpt_response.strip() == '':
            logger.error("⛔ No valid response from GPT, cannot send empty message.")
            open_ai_error = open_ai_error or "No valid response from GPT"
            send_callback(callback_url, api_key, client_id, "ChatGPT did not return a valid response", "error",
                          open_ai_error=open_ai_error)
            return

        if gpt_response:
            logger.info(f"✅ GPT response: {gpt_response}")
            send_callback(callback_url, api_key, client_id, open_ai_text=gpt_response, open_ai_status="ok", callback_text=callback_text)
        else:
            logger.error(f"❌ Error: {open_ai_error}")
            send_callback(callback_url, api_key, client_id, open_ai_status="error", open_ai_error=open_ai_error, callback_text=callback_text)

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        send_callback(f"https://chatter.salebot.pro/api/{api_key}/callback", api_key, client_id, open_ai_status="error", open_ai_error=str(e),
                      callback_text=callback_text)
