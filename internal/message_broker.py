import json
import os
import uuid
import pika

from fastapi import HTTPException

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST')
RABBITMQ_PORT = os.getenv('RABBITMQ_PORT')
RABBITMQ_USER = os.getenv('RABBITMQ_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_PASS')

RABBITMQ_QUEUE = os.getenv('RABBITMQ_QUEUE')
RABBITMQ_EXCHANGE = os.getenv('RABBITMQ_EXCHANGE')
RABBITMQ_ROUTING_KEY = os.getenv('RABBITMQ_ROUTING_KEY')


# Initialize connection, channel, and declare queue.
try:
    credentials = pika.PlainCredentials(username=RABBITMQ_USER, password=RABBITMQ_PASS)
    parameters = pika.ConnectionParameters(host=RABBITMQ_HOST, port=RABBITMQ_PORT, credentials=credentials)

    # Establish connection and channel
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
    print(f"Queue {RABBITMQ_QUEUE} declared successfully.")
except Exception as e:
    print(f"Error during RabbitMQ startup initialization: {e}")
    raise e


def publish_message_with_response(message: dict) -> dict:
    try:
        # Declare a callback queue for the reply
        result = channel.queue_declare(queue="", exclusive=True)
        callback_queue = result.method.queue

        # Generate a unique correlation ID for this request
        correlation_id = str(uuid.uuid4())
        response = None

        # Define a callback function to capture the response
        def on_response(ch, method, properties, body):
            nonlocal response
            if properties.correlation_id == correlation_id:
                response = json.loads(body)

        # Set up subscription to the callback queue
        channel.basic_consume(queue=callback_queue, on_message_callback=on_response, auto_ack=True)

        # Publish the message with reply-to and correlation_id properties
        channel.basic_publish(
            exchange="",
            routing_key=RABBITMQ_QUEUE,
            body=json.dumps(message, default=str),
            properties=pika.BasicProperties(
                reply_to=callback_queue,
                correlation_id=correlation_id,
                delivery_mode=2,
            ),
        )

        # Wait for the response
        while response is None:
            connection.process_data_events()

        # Close the connection
        connection.close()

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
