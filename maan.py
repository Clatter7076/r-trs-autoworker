import asyncio
import random
import ssl
import json
import time
import uuid
import subprocess
import sys
import argparse
import websockets
from loguru import logger
from websockets.exceptions import ConnectionClosedError, WebSocketException
from aiohttp import web
import weakref
import os

# Function to handle the connection directly to the URI
async def connect_and_maintain(user_id):
    # Hardcoded connection details
    uri = "wss://proxy2.wynd.network:4650/"
    server_hostname = "proxy.wynd.network"
    
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, uri))  # Use URI for device_id

    # Add user-agent and other headers
    custom_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
    }
    
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    connection_attempts = 0
    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)  # Random delay
            # Establish connection
            async with websockets.connect(uri, ssl=ssl_context, extra_headers=custom_headers) as websocket:
                connection_attempts = 0  # Reset connection attempts

                # Log successful connection
                logger.info(f"Connected to {uri} with user_id {user_id}")

                # Send a ping every 20 seconds to keep connection alive
                ping_task = asyncio.create_task(send_ping(websocket))

                try:
                    while True:
                        response = await websocket.recv()
                        message = json.loads(response)

                        if message.get("action") == "AUTH":
                            auth_response = {
                                "id": message["id"],
                                "origin_action": "AUTH",
                                "result": {
                                    "browser_id": device_id,
                                    "user_agent": custom_headers['User-Agent'],
                                    "timestamp": int(time.time()),
                                    "device_type": "desktop",
                                    "version": "4.28.2",
                                    "user_id": user_id
                                }
                            }
                            await websocket.send(json.dumps(auth_response))
                            logger.info(f"Authenticated with user_id {user_id}")

                        elif message.get("action") == "PONG":
                            pong_response = {"id": message["id"], "origin_action": "PONG"}
                            await websocket.send(json.dumps(pong_response))

                except (ConnectionClosedError, WebSocketException) as e:
                    logger.error(f"Connection error: {e}")
                    raise
                finally:
                    ping_task.cancel()
                    try:
                        await ping_task
                    except asyncio.CancelledError:
                        pass

        except (ConnectionClosedError, WebSocketException, asyncio.CancelledError) as e:
            connection_attempts += 1
            logger.error(f"Error with connection {uri}: {e} (Attempt {connection_attempts})")
            if connection_attempts >= 10:
                logger.warning(f"Connection {uri} failed 10 times, retrying...")
            await asyncio.sleep(5)  # Retry after delay
        except Exception as e:
            connection_attempts += 1
            logger.error(f"Unexpected error: {e}")
            await asyncio.sleep(5)

async def send_ping(websocket):
    try:
        while True:
            send_message = json.dumps({
                "id": str(uuid.uuid4()),
                "version": "1.0.0",
                "action": "PING",
                "data": {}
            })
            await websocket.send(send_message)
            await asyncio.sleep(20)  # Send ping every 20 seconds
    except (ConnectionClosedError, WebSocketException, asyncio.CancelledError):
        await asyncio.sleep(5)
        raise

# API endpoint handlers
async def get_status(request):
    status = {
        'total_active_connections': 1,  # Only one connection active (for simplicity)
    }
    return web.json_response(status)

async def run_api():
    app = web.Application()
    app.router.add_get('/status', get_status)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()

async def main(user_id):
    tasks = []
    # Start API server
    tasks.append(asyncio.create_task(run_api()))
    
    # Start the connection maintenance
    tasks.append(asyncio.create_task(connect_and_maintain(user_id)))

    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

if __name__ == '__main__':
    # Argument parser to accept user_id as a command-line argument
    parser = argparse.ArgumentParser(description="WebSocket Client")
    parser.add_argument('user_id', type=str, help="The user ID for the connection")
    args = parser.parse_args()
    
    asyncio.run(main(args.user_id))