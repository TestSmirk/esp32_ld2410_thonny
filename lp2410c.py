import network
import socket
import time
import json
from machine import UART, Pin

# ============ Wi-Fi 配置 (按顺序尝试连接) ============
WIFI_LIST = [
 
]

# ============ 服务器配置 ============
# 支持 IP 或者 域名 （比如部署在宝塔上的域名 mydomain.com）
SERVER_HOST = ""  
SERVER_PORT = 18081         # 宝塔上记得在安全/防火墙放行 8081 (TCP) 和 8080 (WS) 端口

# 连接 Wi-Fi
wlan = network.WLAN(network.STA_IF)
wlan.active(True)

def connect_wifi():
    if wlan.isconnected():
        return wlan.ifconfig()[0]
        
    for wifi in WIFI_LIST:
        print(f"\n尝试连接 WiFi: {wifi['ssid']}...")
        wlan.connect(wifi['ssid'], wifi['pwd'])
        # 尝试等待 10 秒
        for _ in range(20):
            if wlan.isconnected():
                print(f"\n✅ WiFi [{wifi['ssid']}] 连接成功! IP: {wlan.ifconfig()[0]}")
                return wlan.ifconfig()[0]
            time.sleep(0.5)
            print(".", end="")
        wlan.disconnect()
        print(f"\n❌ [{wifi['ssid']}] 连接失败或超时，尝试下一个...")
        
    print("所有 WiFi 均连接失败！")
    return None

connect_wifi()

tcp_socket = None

def connect_tcp():
    global tcp_socket
    while True:
        try:
            print(f"正在解析域名并连接到服务器 {SERVER_HOST}:{SERVER_PORT} ...")
            # 使用 getaddrinfo 兼容域名的解析
            addr_info = socket.getaddrinfo(SERVER_HOST, SERVER_PORT)
            addr = addr_info[0][-1]
            
            tcp_socket = socket.socket()
            tcp_socket.connect(addr)
            print("🚀 服务器 TCP 连接成功！")
            break
        except Exception as e:
            print("连接出错或断开，2秒后重试...", e)
            time.sleep(2)

connect_tcp()

uart = UART(1, baudrate=256000, tx=1, rx=2)
do = Pin(4, Pin.IN, Pin.PULL_UP)

buffer = bytearray()
last_send_time = 0

def parse_frame(frame):
    global last_send_time, tcp_socket
    if len(frame) < 10:
        return

    data_len = frame[4] | (frame[5] << 8)
    if len(frame) < 6 + data_len + 4:
        return

    mode = frame[6]
    if frame[7] != 0xAA:
        return

    target_status = frame[8]
    moving_distance = frame[9] | (frame[10] << 8)
    moving_energy = frame[11]
    static_distance = frame[12] | (frame[13] << 8)
    static_energy = frame[14]
    detect_distance = frame[15] | (frame[16] << 8)
    
    # 网络发送与打印不要太快，限制约 100ms 刷新一次 (10FPS) 以防丢包
    current_time = time.ticks_ms()
    if time.ticks_diff(current_time, last_send_time) < 100:
        return
    last_send_time = current_time

    data = {
        "target_status": target_status,
        "moving_distance": moving_distance,
        "moving_energy": moving_energy,
        "static_distance": static_distance,
        "static_energy": static_energy,
        "detect_distance": detect_distance,
        "mode": "normal"
    }

    if mode == 0x01 and data_len >= 0x23:
        data["mode"] = "engineering"
        data["max_moving_gate"] = frame[17]
        data["max_static_gate"] = frame[18]
        data["moving_gates"] = list(frame[19:28])
        data["static_gates"] = list(frame[28:37])
        data["light"] = frame[37]
        data["out_state"] = frame[38]

    # 将数据序列化为 JSON 字符串，加上换行符表示结尾 (服务器按行为单位读取)
    json_str = json.dumps(data) + "\n"
    
    # 本地控制台也顺带打印一下看看
#    try:
#        print(json_str.strip())
#    except Exception:
#        pass
        
    # 通过 TCP 发送给远端服务器
    try:
        if tcp_socket:
            tcp_socket.send(json_str.encode('utf-8'))
    except Exception as e:
        print("发送失败，尝试重连...", e)
        # 如果断开，尝试关闭旧的，并死循环重连直至连上
        try:
            tcp_socket.close()
        except:
            pass
        tcp_socket = None
        connect_tcp()

def parse_buffer():
    global buffer

    while len(buffer) > 8:
        if buffer[0:4] == b'\xF4\xF3\xF2\xF1':
            length = buffer[4] | (buffer[5] << 8)
            frame_len = 4 + 2 + length + 4

            if len(buffer) < frame_len:
                return

            frame = buffer[:frame_len]
            buffer = buffer[frame_len:]

            parse_frame(frame)

        else:
            buffer = buffer[1:]

while True:
    if uart.any():
        data = uart.read()
        buffer.extend(data)
        parse_buffer()

    time.sleep(0.01)