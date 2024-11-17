import asyncio
import random
import ssl
import json
import time
import uuid
import argparse
import websockets
from loguru import logger
from websockets.exceptions import ConnectionClosedError, WebSocketException
from aiohttp import web

async def connect_and_maintain(user_id):
    uri = "wss://proxy2.wynd.network:4650/"
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, uri))

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
            async with websockets.connect(
                uri,
                ssl=ssl_context,
                subprotocols=None,
                compression=None
            ) as websocket:
                # Send custom headers after connection
                for key, value in custom_headers.items():
                    await websocket.send(f"{key}: {value}")

                connection_attempts = 0  # Reset connection attempts

                logger.info(f"Connected to {uri} with user_id {user_id}")

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
    return runner, site

async def main(user_id):
    api_runner, api_site = await run_api()
    
    try:
        await connect_and_maintain(user_id)
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        await api_runner.cleanup()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="WebSocket Client")
    parser.add_argument('user_id', type=str, help="The user ID for the connection")
    args = parser.parse_args()
    
    asyncio.run(main(args.user_id))