import json
import logging
import os
import time

from openai import OpenAI


client = OpenAI(
    api_key=os.getenv("GPT_TOKEN"),
)
logger = logging.getLogger(__name__)


def invoke_analyzis(assistant_id, content):
    # Create a thread with a message.
    thread = client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ]
    )

    # Submit the thread to the assistant (as a new run).
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id=assistant_id
    )
    logger.info(f"🚀 Run Created: {run.id} for Assistant: {assistant_id}")

    # Wait for run to complete.
    while run.status != "completed":
        if run.status == "failed":
            logger.exception(f"❌ Run Failed: {run.id}")
            raise Exception(f"Run failed with error: {str(run.last_error)}")
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        time.sleep(1)
    else:
        logger.info(f"🏁 Run Completed!")

    message_response = client.beta.threads.messages.list(thread_id=thread.id)
    return message_response.data[0].content[0].text.value


def __wait_for_message(_run, _thread):
    counter = 0
    while _run.status != "completed":
        _run = client.beta.threads.runs.retrieve(thread_id=_thread.id, run_id=_run.id)
        time.sleep(1)
        counter += 1
        if counter > 120:
            logger.error(f"❌ Run Timeout: {_run.id}")
            break
    else:
        logger.info(f"🏁 Run Completed!")

    return client.beta.threads.messages.list(thread_id=_thread.id)
