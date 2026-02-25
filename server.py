import asyncio
import json
import websockets
from websockets.server import serve

# 保存所有连上来的前端 WebSocket 客户端
frontend_clients = set()
latest_data = None

async def ws_handler(websocket):
    print("📡 有前端页面连接到了 WebSocket。")
    frontend_clients.add(websocket)
    try:
        # 刚连上时如果已经有数据了，先发一次最新的过去
        if latest_data:
            await websocket.send(latest_data)
        
        # 保持连接不主动断开（前端只收不发）
        async for message in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        print("⚠️ 前端页面断开了连接。")
        frontend_clients.remove(websocket)

async def tcp_handler(reader, writer):
    global latest_data
    addr = writer.get_extra_info('peername')
    print(f"🔌 ESP32 设备已连接 TCP: {addr}")
    
    try:
        while True:
            data = await reader.readline()
            if not data:
                break
            
            line = data.decode('utf-8', errors='ignore').strip()
            if line.startswith('{') and line.endswith('}'):
                latest_data = line
                # 广播给所有连着的前端页面
                # 注意: websockets.broadcast 在老版本中可能不支持，这里用循环降级兼容
                for ws in list(frontend_clients):
                    try:
                        await ws.send(latest_data)
                    except Exception:
                        pass
    except Exception as e:
        print(f"❌ ESP32 读取出现异常: {e}")
    finally:
        print(f"� ESP32 设备断开连接: {addr}")
        writer.close()
        await writer.wait_closed()

async def main():
    # 启动 WebSocket 服务器，面向前端网页 (端口 8080)
    # 使用 0.0.0.0 允许公网或局域网的其他设备访问
    ws_server = await websockets.serve(ws_handler, "0.0.0.0", 18080)
    print("🚀 WebSocket 服务器(面向前端)已启动: ws://0.0.0.0:18080")
    
    # 启动 TCP 服务器，面向 ESP32 (端口 8081)
    tcp_server = await asyncio.start_server(tcp_handler, "0.0.0.0", 18081)
    print("🚀 TCP 服务器(面向ESP32)已启动: 0.0.0.0:18081")
    
    async with ws_server, tcp_server:
        await asyncio.Future()  # 永久保持运行

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("服务器关闭。")
