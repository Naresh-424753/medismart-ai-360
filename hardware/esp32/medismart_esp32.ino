/*
 * MediSmart AI 360 - ESP32 vitals sender
 * Sends readings to POST /vitals/ingest with header X-Device-Key.
 * Get the key: log in as patient -> Vitals -> Register device.
 *
 * Libraries: WiFi, HTTPClient (built-in), ArduinoJson (install from Library Manager).
 * Sensors (examples): MAX30102 (heart rate/SpO2), DS18B20 (temperature), MPU6050 (fall).
 * The read*() functions below return SIMULATED values so the demo works with no sensors.
 * Replace each with your sensor library calls.
 */
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID   = "YOUR_WIFI";
const char* WIFI_PASS   = "YOUR_PASSWORD";
const char* SERVER_URL  = "http://192.168.1.10:8000/vitals/ingest";  // your PC's LAN IP
const char* DEVICE_KEY  = "PASTE_DEVICE_API_KEY";
const unsigned long INTERVAL_MS = 10000;

float readHeartRate()   { return 72 + random(-6, 7); }            // TODO: MAX30102
float readSpO2()        { return 97 + random(-1, 2); }            // TODO: MAX30102
float readTemperature() { return 36.6 + random(-3, 4) / 10.0; }  // TODO: DS18B20
bool  readFall()        { return false; }                         // TODO: MPU6050 threshold

void connectWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi connected: " + WiFi.localIP().toString());
}

void setup() {
  Serial.begin(115200);
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) connectWifi();

  StaticJsonDocument<256> doc;
  doc["heart_rate"]  = readHeartRate();
  doc["spo2"]        = readSpO2();
  doc["temperature"] = readTemperature();
  doc["fall_detected"] = readFall();
  String body; serializeJson(doc, body);

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Key", DEVICE_KEY);
  int code = http.POST(body);
  Serial.printf("POST %s -> %d\n", body.c_str(), code);
  http.end();
  delay(INTERVAL_MS);
}
