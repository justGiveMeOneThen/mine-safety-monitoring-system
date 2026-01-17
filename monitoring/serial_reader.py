# monitoring/serial_reader.py
"""
ESP32 Serial Port Reader for IoT Integration
This module will be used to read sensor data from ESP32 via USB serial cable

IMPORTANT: This is for FUTURE USE when IoT components are set up.
Currently, the system uses mock data in views.py
"""

import serial
import json
import time
from datetime import datetime
from django.conf import settings
from .models import SensorReading, Sector, ESP32Device

class ESP32SerialReader:
    """
    Reads data from ESP32 microcontroller via serial port
    Expected data format from ESP32: {"co": 35.2, "temp": 28.5, "device_id": "ESP32_001"}
    """
    
    def __init__(self, port='/dev/ttyUSB0', baudrate=9600, timeout=1):
        """
        Initialize serial connection
        
        Args:
            port: Serial port (Linux: /dev/ttyUSB0, Windows: COM3)
            baudrate: Communication speed (default: 9600)
            timeout: Read timeout in seconds
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_connection = None
        self.is_connected = False
        
    def connect(self):
        """Establish serial connection to ESP32"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )
            self.is_connected = True
            print(f"✅ Connected to ESP32 on {self.port} at {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"❌ Failed to connect to {self.port}: {e}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """Close serial connection"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            self.is_connected = False
            print("🔌 Disconnected from ESP32")
    
    def read_sensor_data(self):
        """
        Read one line of sensor data from ESP32
        
        Returns:
            dict: Parsed sensor data or None if read fails
            Example: {'co': 35.2, 'temp': 28.5, 'device_id': 'ESP32_001'}
        """
        if not self.is_connected:
            print("⚠️ Not connected to ESP32")
            return None
        
        try:
            # Read line from serial port
            if self.serial_connection.in_waiting > 0:
                line = self.serial_connection.readline().decode('utf-8').strip()
                
                # Parse JSON data
                data = json.loads(line)
                
                # Validate required fields
                if 'co' in data and 'temp' in data:
                    return {
                        'carbon_monoxide': float(data['co']),
                        'temperature': float(data['temp']),
                        'device_id': data.get('device_id', 'UNKNOWN'),
                        'timestamp': datetime.now(),
                        'raw_data': data
                    }
                else:
                    print(f"⚠️ Invalid data format: {data}")
                    return None
                    
        except json.JSONDecodeError as e:
            print(f"❌ JSON parsing error: {e}")
            return None
        except Exception as e:
            print(f"❌ Error reading sensor data: {e}")
            return None
    
    def save_to_database(self, sensor_data, sector_name='Sector 1'):
        """
        Save sensor reading to database
        
        Args:
            sensor_data: Dict containing sensor readings
            sector_name: Name of the mine sector
        """
        try:
            sector = Sector.objects.get(name=sector_name)
            
            reading = SensorReading.objects.create(
                sector=sector,
                carbon_monoxide=sensor_data['carbon_monoxide'],
                temperature=sensor_data['temperature'],
                device_id=sensor_data.get('device_id'),
                raw_data=sensor_data.get('raw_data'),
                timestamp=sensor_data['timestamp']
            )
            
            # Update ESP32 device status
            device_id = sensor_data.get('device_id')
            if device_id:
                ESP32Device.objects.update_or_create(
                    device_id=device_id,
                    defaults={
                        'sector': sector,
                        'is_online': True,
                        'last_seen': datetime.now()
                    }
                )
            
            print(f"✅ Saved reading: CO={reading.carbon_monoxide}ppm, Temp={reading.temperature}°C")
            return reading
            
        except Sector.DoesNotExist:
            print(f"❌ Sector '{sector_name}' not found in database")
            return None
        except Exception as e:
            print(f"❌ Error saving to database: {e}")
            return None
    
    def continuous_read(self, sector_name='Sector 1', interval=5):
        """
        Continuously read sensor data and save to database
        
        Args:
            sector_name: Name of the mine sector
            interval: Seconds between reads
        """
        print(f"🔄 Starting continuous read from {self.port}...")
        
        while self.is_connected:
            try:
                data = self.read_sensor_data()
                if data:
                    self.save_to_database(data, sector_name)
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                print("\n⏹️ Stopping continuous read...")
                break
            except Exception as e:
                print(f"❌ Error in continuous read: {e}")
                time.sleep(interval)


# Utility functions for Django management commands

def start_esp32_reader(port='/dev/ttyUSB0', sector_name='Sector 1'):
    """
    Start reading from ESP32 (to be called from management command)
    
    Usage in Django management command:
        from monitoring.serial_reader import start_esp32_reader
        start_esp32_reader(port='/dev/ttyUSB0', sector_name='Sector 1')
    """
    reader = ESP32SerialReader(port=port)
    
    if reader.connect():
        try:
            reader.continuous_read(sector_name=sector_name)
        finally:
            reader.disconnect()
    else:
        print("❌ Failed to start ESP32 reader")


def test_connection(port='/dev/ttyUSB0'):
    """
    Test ESP32 connection and read one sample
    
    Usage:
        from monitoring.serial_reader import test_connection
        test_connection('/dev/ttyUSB0')
    """
    reader = ESP32SerialReader(port=port)
    
    if reader.connect():
        print("📡 Testing connection... Reading one sample:")
        time.sleep(2)  # Wait for ESP32 to send data
        
        data = reader.read_sensor_data()
        if data:
            print(f"✅ Received: {data}")
        else:
            print("❌ No data received")
        
        reader.disconnect()
    else:
        print("❌ Connection test failed")


# Example ESP32 Arduino code that this reader expects:
"""
// ESP32 Code Example (Arduino IDE)
#include <ArduinoJson.h>

const int MQ2_PIN = 34;   // MQ2 sensor analog pin
const int LM35_PIN = 35;  // LM35 sensor analog pin

void setup() {
  Serial.begin(9600);
}

void loop() {
  // Read sensors
  int mq2Value = analogRead(MQ2_PIN);
  int lm35Value = analogRead(LM35_PIN);
  
  // Convert to actual values
  float coLevel = map(mq2Value, 0, 4095, 0, 100);  // Convert to ppm
  float temperature = (lm35Value * 3.3 / 4095) * 100;  // Convert to Celsius
  
  // Create JSON object
  StaticJsonDocument<200> doc;
  doc["co"] = coLevel;
  doc["temp"] = temperature;
  doc["device_id"] = "ESP32_001";
  
  // Send to serial
  serializeJson(doc, Serial);
  Serial.println();
  
  delay(5000);  // Send every 5 seconds
}
"""