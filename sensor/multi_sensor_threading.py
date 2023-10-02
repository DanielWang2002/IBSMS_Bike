import json
import threading
import time
import smbus
import math
import RPi.GPIO as GPIO
import mfrc522
import warnings
from gy521 import init_gy521, read_gy521_data, read_word_2c, read_word
from gpiozero import Button
from flask import Flask, request, jsonify
from mqtt import publish_mqtt_message

app = Flask(__name__)

warnings.filterwarnings('ignore')

"""
params: {
    bikeId: string            // 車輛編號
    timestamp: number         // 時間戳記
    isBrake: boolean          // 是否煞車
    seat_tube: number[]       // 加速度(5s)
    seat_rotate: number       // 傾斜角度
    keyes_pressure: number    // 坐管鬆脫數值
    tire_pressure: {}         // 胎壓、溫度、電壓
    }
"""
data = {
    'bikeId': "KKH-1000",
    'timestamp': int(time.time()),
    'isBrake': None,
    'seat_tube': None,
    'seat_rotate': None,
    'keyes_pressure': None,
    'tire_pressure': None,
}

# 每秒執行幾次
frequency = 0.2

# 定義Button GPIO腳位
button_pin = 26

# 創建 Button 物件
button = Button(button_pin)

# GY-521 設備地址
DEVICE_ADDRESS_GY521 = 0x68

# PCF8591 模組地址
DEVICE_ADDRESS_PCF8591 = 0x48

# PCF8591 模組的 AIN0 輸入通道
CHANNEL = 0x00

# 建立 I2C 總線 (Keyes-Pressure)
bus = smbus.SMBus(1)

# 建立 RC522 實例
MIFAREReader = mfrc522.MFRC522()

@app.route('/data', methods=['POST'])
def update_data():
    # 從 Node.js 端獲取資料
    node_data = request.json
    if 'pressure_psi' in node_data:
        data['tire_pressure'] = [node_data['pressure_psi'], node_data['temperature'], node_data['voltage']]
    print(data)
    return jsonify({"message": "Data updated successfully!"}), 200

def button_press():
    while True:
        # if button.is_pressed:
        #     print("按鍵已按下")
        # else:
        #     print("按鍵已釋放")

        data['isBrake'] = button.is_pressed
        time.sleep(1 / frequency)

def gy_521():
    # 初始化GY-521模組
    if init_gy521() == False:
        exit()

    # 用於存儲加速度x軸的數據
    accel_x_data = []

    # 持續讀取陀螺儀和加速度傳感器的資料
    while True:
        # 加上 try...catch防止出錯
        try:
            accel_x, accel_y, accel_z, gyro_x, gyro_y, gyro_z = read_gy521_data()
            # print("加速度 (g): x={:.2f} y={:.2f} z={:.2f}".format(accel_x, accel_y, accel_z))
            # print("陀螺儀 (deg/s): x={:.2f} y={:.2f} z={:.2f}".format(gyro_x, gyro_y, gyro_z))
            # print("傾斜角 (deg): roll={:.2f} pitch={:.2f}".format(roll, pitch))

            # 記錄加速度x軸的數據
            accel_x_data.append(accel_x)
            
            # 如果加速度x軸的數據超過5筆，則移除最舊的數據
            if len(accel_x_data) > 5:
                accel_x_data.pop(0)

            # 計算傾角
            roll = math.atan(accel_y / math.sqrt(accel_x ** 2 + accel_z ** 2)) * 180.0 / math.pi
            pitch = math.atan2(-accel_x, accel_z) * 180.0 / math.pi

            # 更新全局數據
            data['seat_tube'] = accel_x_data
            data['seat_rotate'] = [roll, pitch]

            # 等待一秒（我假設您想要每秒記錄一次）
            time.sleep(1)

        except ZeroDivisionError:
            print('ZeroDivisionError')
            pass


def keyes_pressure():
    while True:
        # 將您的 Keyes 壓力感測器代碼放在這裡
        bus.write_byte(DEVICE_ADDRESS_PCF8591, CHANNEL)
        time.sleep(0.1)
        value = bus.read_byte(DEVICE_ADDRESS_PCF8591)
        # print("薄膜壓力感測器的類比信號值為：{}".format(value))
        data['keyes_pressure'] = value
        time.sleep(1 / frequency)

def rc522():
    while True:
        # 檢測 RFID 訊息
        (status, TagType) = MIFAREReader.MFRC522_Request(MIFAREReader.PICC_REQIDL)
        # 如果檢測到 RFID 訊息，繼續讀取卡片 UID
        # if status == MIFAREReader.MI_OK:
        #     print("Card detected")

        # 讀取卡片 UID
        (status, uid) = MIFAREReader.MFRC522_Anticoll()

        # 如果成功讀取卡片 UID，顯示 UID 資訊
        # if status == MIFAREReader.MI_OK:
        #     print("Card UID: %s,%s,%s,%s" % (uid[0], uid[1], uid[2], uid[3]))
        

        card_data = {
            "status": status,
            "uid": uid if status == MIFAREReader.MI_OK else None
        }
        # data['rc522'] = card_data

        # 等待一段時間
        time.sleep(1 / frequency)

def run_flask_app():
    app.run(host='0.0.0.0', port=5000, threaded=True)

def send_data_periodically():
    # 每5秒send一次data的內容

    # 如果有薄膜壓力&胎壓的數據(讀取最慢)，則發送 MQTT 訊息
    if (data['keyes_pressure'] != None) and (data['tire_pressure'] != None): publish_mqtt_message('bike_data', data)

    # 更新timestamp
    data['timestamp'] = int(time.time())

    # 設定下一次send的時間
    threading.Timer(5, send_data_periodically).start()

# 創建並啟動線程
t1 = threading.Thread(target=button_press)
t2 = threading.Thread(target=gy_521)
t3 = threading.Thread(target=keyes_pressure)
t4 = threading.Thread(target=rc522)
t5 = threading.Thread(target=run_flask_app)
t6 = threading.Thread(target=send_data_periodically)

t1.start()
t2.start()
t3.start()
t4.start()
t5.start()
t6.start()