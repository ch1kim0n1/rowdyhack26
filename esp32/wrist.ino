// The Appraisal Job, wrist unit.
//
// ESP32 + SSD1306 (I2C, 0x3C). Polls the hat Pi's /wrist.json every POLL_MS
// and renders case no, running take, exhibit count, and the top-5 loot.
// Board: any ESP32-WROOM dev board. Libs (Arduino IDE -> Library Manager):
//   Adafruit SSD1306, Adafruit GFX Library, ArduinoJson
//
// Fill in WIFI_SSID / WIFI_PASS / HUB below before flashing.

#include <ArduinoJson.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <Wire.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <freertos/task.h>

#define WIFI_SSID "your-hotspot"
#define WIFI_PASS "your-pass"
#define HUB "http://raspberrypi.local:5000"
// Hub's RIG_TOKEN, when the crew locks the LAN. Empty = open demo mode.
#define RIG_TOKEN ""

#define OLED_W 128
#define OLED_H 64
#define OLED_ADDR 0x3C
#define SDA_PIN 21
#define SCL_PIN 22
// Long-poll: ask the hub to hold the request open for WAIT_S and answer the
// instant the case changes, so a new find shows on the wrist in tens of ms
// instead of waiting out a fixed poll. IDLE_MS is just the gap between
// requests. Needs a hub that supports /wrist.json?since=&wait= (this repo).
#define WAIT_S 5
#define IDLE_MS 150

// Optional: must match the hub's RIG_TOKEN when the hub runs in token mode.
#define RIG_TOKEN ""

Adafruit_SSD1306 oled(OLED_W, OLED_H, &Wire, -1);
bool linkUp = false;
JsonDocument latest;
SemaphoreHandle_t stateLock;
unsigned long phaseReceived = 0;
unsigned int recPhase = 0;
String deadReason = "joining net...";

void networkLoop(void *);

void draw(const JsonDocument &d) {
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  oled.setTextSize(1);
  oled.setCursor(0, 0);
  oled.printf("CASE NO. %04d", d["case_no"] | 0);
  bool fled = d["revealed"] | false;
  bool recording = (recPhase + millis() - phaseReceived) % 2000 < 1000;
  oled.setCursor(104, 0);
  if (fled) oled.print("FLED");
  else if (recording) oled.print("REC");

  if (fled) {
    oled.setCursor(0, 17);
    oled.print("TOTAL TAKE");
    oled.setTextSize(2);
    oled.setCursor(0, 29);
    // Seven characters ($999999) fit in the 128 px panel at 12 px each.
    oled.printf("$%.0f", d["take"] | 0.0);
    oled.setTextSize(1);
    oled.setCursor(0, 54);
    oled.printf("%02d EXHIBITS FILED", d["count"] | 0);
    oled.display();
    return;
  }

  oled.setCursor(0, 10);
  oled.printf("$%.0f", d["take"] | 0.0);
  oled.setCursor(104, 10);
  oled.printf("%02d", d["count"] | 0);

  int y = 20;   // five rows at 9px: 20..62 on the 64px panel
  for (JsonObjectConst it : d["top"].as<JsonArrayConst>()) {
    oled.setCursor(0, y);
    String name = it["item"] | "?";
    if (name.length() > 12) name = name.substring(0, 12);
    oled.print(name);
    oled.setCursor(78, y);
    oled.printf("$%.0f", it["value_usd"] | 0.0);
    y += 9;
    if (y > OLED_H - 6) break;
  }
  oled.display();
}

void drawDead(const char *line) {
  oled.clearDisplay();
  oled.setTextSize(1);
  oled.setTextColor(SSD1306_WHITE);
  oled.setCursor(0, 24);
  oled.println("LINE DEAD");
  oled.setCursor(0, 40);
  oled.println(line);
  oled.display();
}

void setup() {
  Wire.begin(SDA_PIN, SCL_PIN);
  oled.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR);
  oled.clearDisplay();
  oled.setTextColor(SSD1306_WHITE);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  WiFi.setAutoReconnect(true);   // a wifi blink rejoins on its own
  drawDead("joining net...");
  stateLock = xSemaphoreCreateMutex();
  xTaskCreate(networkLoop, "wrist-poll", 8192, nullptr, 1, nullptr);
}

// Poll on a worker so HTTP timeouts cannot freeze the local REC cadence.
void networkLoop(void *) {
  static unsigned long lastV = 0;   // last case version seen; the hub pushes past it
  for (;;) {
    JsonDocument received;
    String error;
    bool healthy = false;
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.reconnect();
      error = "no wifi";
    } else {
      HTTPClient http;
      http.begin(String(HUB) + "/wrist.json?since=" + lastV + "&wait=" + WAIT_S);
      http.setTimeout((WAIT_S + 3) * 1000);   // must outlast the hub's hold
      if (RIG_TOKEN[0]) http.addHeader("X-Rig-Token", RIG_TOKEN);
      int code = http.GET();
      if (code == 200) {
        healthy = deserializeJson(received, http.getString()) == DeserializationError::Ok;
        if (!healthy) error = "bad json";
      } else error = "hub unreachable";
      http.end();
    }
    xSemaphoreTake(stateLock, portMAX_DELAY);
    linkUp = healthy;
    if (healthy) {
      latest = received;
      recPhase = received["rec_phase_ms"] | 0;
      phaseReceived = millis();
      lastV = received["v"] | lastV;   // advance so the next request waits for the next change
    } else deadReason = error;
    xSemaphoreGive(stateLock);
    vTaskDelay(pdMS_TO_TICKS(IDLE_MS));
  }
}

void loop() {
  xSemaphoreTake(stateLock, portMAX_DELAY);
  if (linkUp) draw(latest);
  else drawDead(deadReason.c_str());
  xSemaphoreGive(stateLock);
  delay(50);
}
