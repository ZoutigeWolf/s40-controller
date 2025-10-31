#include <ESP32Encoder.h>

enum AccessoryPower {
  OFF,
  AUTO,
  ON
};

ESP32Encoder encoder;

const int pinA = 22;   // encoder A
const int pinB = 23;   // encoder B
const int buttonPin = 21;
const int optoPin = 12;
const int relay0Pin = 26;
const int relay1Pin = 27;

unsigned long lastMillis = 0;
int32_t lastPosition = 0;
bool powerState = false;
AccessoryPower accessoryPowerState = AUTO;
long powerGracePeriod = 10;
float powerTimer = 0;

void setup() {
  Serial.begin(115200);
  Serial.setTimeout(20);

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
  delay(5);
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
  }
}

void setRelay(int relayNum, bool on) {
  int pin = relayNum == 0 ? relay0Pin : relay1Pin;

  digitalWrite(pin, !on ? HIGH : LOW);
}