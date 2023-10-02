const noble = require('@abandonware/noble');
const fs = require('fs');
const axios = require('axios');

const config = JSON.parse(fs.readFileSync('/home/pi/Desktop/IBSMS/tire_pressure_ble_scan/config.json', 'utf8'));
const bike_id = config.bike_id;

// Flask API 的 URL
const API_URL = 'http://localhost:5000/data';
var postData = require('./latest_data.json');

noble.on('stateChange', function(state) {
  if (state === 'poweredOn') {
    noble.startScanning();
  }
});

noble.on('discover', async function(peripheral) {
  if (peripheral.advertisement.localName === "BR") {
    const buffer = Buffer.from(peripheral.advertisement.manufacturerData, 'hex');
    const data = [];
    for (var i = 0; i < buffer.length; i++) {
      data.push(buffer.readUInt8(i));
    }

    if (data.length == 5) {
      const voltage = data[1] / 10;
      const temperature = data[2];
      const pressure_original = data[3] * 256 + data[4];
      const pressure_psi = (pressure_original / 10 - 14.6).toFixed(1);
      // console.log(`voltage: ${voltage}V, temperature: ${temperature}°C, pressure: ${pressure_psi}psi`);

      postData = {
        pressure_psi: parseFloat(pressure_psi),
        temperature: parseFloat(temperature),
        voltage: parseFloat(voltage)
      };

      // 將postData寫入latest_data.json
      fs.writeFileSync('./latest_data.json', JSON.stringify(postData));

    }
  }

  noble.startScanning();
});

noble.on('scanStart', function() {
  // console.log('Scanning for BLE devices...');
});

noble.on('scanStop', function() {
  console.log('Scan stopped.');
  noble.startScanning();
});

noble.on('warning', function(message) {
  console.log('Warning:', message);
});

noble.on('error', function(error) {
  console.error('Error:', error);
});

// 初始化BLE
noble.on('stateChange', function(state) {
  if (state === 'poweredOn') {
    console.log('BLE initialized and ready.');
  } else {
    console.log('BLE not available or powered off.');
  }
});

// 設置每5秒發送一次POST請求的定時器
setInterval(async () => {
  try {
    const response = await axios.post(API_URL, postData);
    console.log(response.data.message);
  } catch (error) {
    console.error('Error sending data to Flask API:', error);
  }
}, 5000);