import asyncio
import random
import ssl
import json
import time
import uuid
import subprocess
import sys
import argparse

# List of required modules
required_modules = [
    "loguru",
    "websockets",
    "aiohttp",
    "weakref",
]

# Function to check and install missing modules
def check_and_install_modules():
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            subprocess.check_call([sys.executable, "-m", "pip", "install", module])

check_and_install_modules()

from loguru import logger
from websockets.exceptions import ConnectionClosedError, WebSocketException
from aiohttp import web
import weakref
import os

# Load user proxies from configuration JSON file
USER_PROXIES_FILE = "user_proxies.json"
try:
    with open(USER_PROXIES_FILE, 'r') as f:
        user_proxies = json.load(f)
except FileNotFoundError:
    user_proxies = {}

# Keep track of active websocket connections
active_connections = weakref.WeakSet()

def save_working_proxy(user_id, proxy):
    # Remove proxy support, only saving user_id related data
    pass

async def send_ping(websocket, user_id):
    try:
        while True:
            send_message = json.dumps({
                "id": str(uuid.uuid4()),
                "version": "1.0.0",
                "action": "PING",
                "data": {}
            })
            await websocket.send(send_message)
            await asyncio.sleep(20)
    except (ConnectionClosedError, WebSocketException, asyncio.CancelledError):
        await asyncio.sleep(5)
        raise

async def connect_and_maintain(proxy_info, user_id):
    device_id = str(uuid.uuid3(uuid.NAMESPACE_DNS, proxy_info['url']))
    
    # Find username for this user_id
    username = next((name for name, info in user_proxies.items() if info['id'] == user_id), None)
    
    connection_attempts = 0
    while True:
        try:
            await asyncio.sleep(random.randint(1, 10) / 10)
            # add more user agents here (bUT THIS IS DESKTOP NODE USER AGENT)
            custom_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
            }
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = "wss://proxy2.wynd.network:4650/"
            server_hostname = "proxy.wynd.network"

            # No proxy support here, direct WebSocket connection
            async with websockets.connect(uri, ssl=ssl_context, extra_headers=custom_headers) as websocket:
                
                # Reset connection attempts on successful connection
                connection_attempts = 0
                
                # Track active connection
                active_connections.add(websocket)
                if username:
                    user_proxies[username]['active_connections'] += 1
                logger.info(f"Connected with server {uri}")

                # Save working proxy
                save_working_proxy(user_id, proxy_info['url'])

                ping_task = asyncio.create_task(send_ping(websocket, user_id))

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
                                    "user_id": user_id,
                                    "user_agent": custom_headers['User-Agent'],
                                    "timestamp": int(time.time()),
                                    "device_type": "desktop",
                                    "version": "4.28.2"
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
                    # Remove from active connections
                    active_connections.discard(websocket)
                    if username:
                        user_proxies[username]['active_connections'] = max(0, user_proxies[username]['active_connections'] - 1)
                    logger.info(f"Disconnected from server {uri}")

        except (ConnectionClosedError, WebSocketException, asyncio.CancelledError) as e:
            connection_attempts += 1
            logger.error(f"Error with connection to {uri}: {e} (Attempt {connection_attempts})")
            if connection_attempts >= 10:
                logger.warning(f"Connection to {uri} failed 10 times, generating new session ID")
                connection_attempts = 0
            await asyncio.sleep(5)
        except Exception as e:
            connection_attempts += 1
            logger.error(f"Unexpected error: {e}")
            await asyncio.sleep(5)

async def manage_proxies(user_id, proxy_count, base_urls, base_urls_suffix):
    while True:  # Keep trying to maintain connections
        tasks = []
        
        # First try to use working proxies from previous runs (this part is simplified as no proxies are used now)
        if user_id in working_proxies:
            for proxy in working_proxies[user_id][:proxy_count]:
                tasks.append(asyncio.create_task(connect_and_maintain(proxy, user_id)))
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"Error in manage_proxies: {e}")
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.sleep(5)  # Wait before retrying

async def print_proxy_status():
    while True:
        print("\033[H\033[J")
        print("Proxy Status")
        print("============")
        for user_id, user_info in user_proxies.items():
            print(f"User: {user_id}")
            print(f"ID: {user_info['id']}")
            print(f"Working Proxies: {user_info['count']}")
            print(f"Active Connections: {user_info['active_connections']}")
        await asyncio.sleep(5)

# API endpoint handlers
async def get_status(request):
    status = {
        'total_active_connections': len(active_connections),
        'users': {
            user: {
                'total_proxies': info['count'],
                'active_connections': info['active_connections']
            }
            for user, info in user_proxies.items()
        }
    }
    return web.json_response(status)

async def run_api():
    app = web.Application()
    app.router.add_get('/status', get_status)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8080)
    await site.start()

async def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="Manage WebSocket connections with user ID")
    parser.add_argument('user_id', type=str, help='User ID to connect with')
    args = parser.parse_args()

    tasks = []
    # Start API server
    tasks.append(asyncio.create_task(run_api()))
    
    # Initialize user_id for connection management
    tasks.append(asyncio.create_task(manage_proxies(args.user_id, 5, ["base_url1", "base_url2"], ["suffix1", "suffix2"])))
    
    tasks.append(asyncio.create_task(print_proxy_status()))
    
    try:
        await asyncio.gather(*tasks)
    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()

if __name__ == '__main__':
    asyncio.run(main())