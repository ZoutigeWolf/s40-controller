#include <ESP32Encoder.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <string.h>

enum AccessoryPower {
  OFF,
  AUTO,
  ON
};

ESP32Encoder encoder;
U8G2_SH1122_256X64_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

const int pinA = 19;
const int pinB = 18;
const int buttonPin = 5;
const int optoPin = 12;
const int relay0Pin = 26;
const int relay1Pin = 27;

unsigned long lastMillis = 0;
int32_t lastPosition = 0;
bool powerState = false;
AccessoryPower accessoryPowerState = AUTO;
long powerGracePeriod = 10;
float powerTimer = 0;

String track_title = "";
String track_artist= "";
long track_duration = 0;
long track_elapsed = 0;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);

  Wire.begin(21, 22);
  
  u8g2.begin();

  // Encoder setup
  ESP32Encoder::useInternalWeakPullResistors = puType::up;
  encoder.attachFullQuad(pinB, pinA);
  encoder.clearCount();

  // Button setup
  pinMode(buttonPin, INPUT_PULLUP);

  // Optocoupler setup
  pinMode(optoPin, INPUT_PULLUP);

  // Relay setup
  pinMode(relay0Pin, OUTPUT);
  pinMode(relay1Pin, OUTPUT);
  digitalWrite(relay0Pin, HIGH);
  digitalWrite(relay1Pin, HIGH);
}

void loop() {
  handlePowerTimer();
  handleEncoder();
  handleButton();
  handleOpto();
  handlePowerState();
  handleSerial();
  updateDisplay();
  delay(5);
}

void updateDisplay() {
  u8g2.clearBuffer();

  u8g2.setFont(u8g2_font_6x10_mf);
  u8g2.drawStr(0, 8, "13.2 V  AUTO  UP");

  u8g2.setFont(u8g2_font_10x20_mf);
  u8g2.drawStr(0, 30, track_title.c_str());

  u8g2.setFont(u8g2_font_7x13_mf);
  u8g2.drawStr(0, 48, track_artist.c_str());

  String elapsed = msToTime(track_elapsed);
  u8g2.setFont(u8g2_font_5x7_mf);
  u8g2.drawStr(0, 61, elapsed.c_str());

  String duration = msToTime(track_duration);
  int len = u8g2.getStrWidth(duration.c_str());
  u8g2.setFont(u8g2_font_5x7_mf);
  u8g2.drawStr(256 - len, 61, duration.c_str());

  int width = map(track_elapsed, 0, track_duration, 0, 256);
  u8g2.drawBox(0, 63, width, 1);

  u8g2.sendBuffer();
}

void handlePowerTimer() {
  unsigned long elapsed = millis() - lastMillis;
  powerTimer -= (elapsed / 1000.0f);
  if (powerTimer < 0) powerTimer = 0;

  lastMillis = millis();
}

// --- Encoder ---
void handleEncoder() {
  int32_t pos = encoder.getCount();
  if (pos != lastPosition) {
    Serial.println(pos > lastPosition ? "VOLUME_UP" : "VOLUME_DOWN");
    lastPosition = pos;
  }
}

// --- Button ---
void handleButton() {
  static bool buttonPressed = false;
  bool state = digitalRead(buttonPin) == LOW;
  if (state && !buttonPressed) {
    Serial.println("MUTE");
    buttonPressed = true;
  } else if (!state && buttonPressed) {
    buttonPressed = false;
  }
}

// --- Optocoupler ---
void handleOpto() {
  bool pValue = digitalRead(optoPin) == LOW;
  if (pValue != powerState) {
    powerState = pValue;
    Serial.println(powerState ? "POWER_ON" : "POWER_OFF");

    if (!powerState && accessoryPowerState == AUTO) {
      powerTimer = powerGracePeriod;
    }
  }
}

void handlePowerState() {
  if (accessoryPowerState == ON) setRelay(1, true);
  if (accessoryPowerState == OFF) setRelay(1, false);
  if (accessoryPowerState == AUTO) setRelay(1, powerState || powerTimer > 0);
}

// --- Serial Command Handler ---
void handleSerial() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');  // waits until newline or timeout
    cmd.trim();  // remove CR/LF

    processCommand(cmd);
  }
}

void processCommand(const String &cmd) {
  if (cmd.startsWith("ANTENNA_UP;")) {
    setRelay(1, true);
  } else if (cmd.startsWith("ANTENNA_DOWN;")) {
    setRelay(1, false);
  } else if (cmd.startsWith("SET_ACC_POWER;")) {
    int state = cmd.substring(14).toInt();

    if (state < 0 || state > 2) return;

    accessoryPowerState = static_cast<AccessoryPower>(state);

    if (accessoryPowerState != AUTO) powerTimer = 0;
  } else if (cmd.startsWith("SET_POWER_GRACE_PERIOD;")) {
    long period = cmd.substring(23).toInt();

    if (period < 0) period = 0;

    powerGracePeriod = period;
  } else if (cmd.startsWith("SET_TRACK;")) {
    String action = cmd.substring(10);

    if (action.startsWith("TITLE;")) {
      track_title = action.substring(6);

    } else if (action.startsWith("ARTIST;")) {
      track_artist = action.substring(7);
    } else if (action.startsWith("ELAPSED;")) {
      track_elapsed = action.substring(8).toInt();
    } else if (action.startsWith("DURATION;")) {
      track_duration = action.substring(9).toInt();
    }
  }
}

void setRelay(int relayNum, bool on) {
  int pin = relayNum == 0 ? relay0Pin : relay1Pin;

  digitalWrite(pin, !on ? HIGH : LOW);
}

String msToTime(unsigned long ms) {
  unsigned long totalSeconds = ms / 1000;
  unsigned int minutes = totalSeconds / 60;
  unsigned int seconds = totalSeconds % 60;

  char buffer[6]; // "mm:ss" + null terminator
  sprintf(buffer, "%u:%02u", minutes, seconds);
  return String(buffer);
}