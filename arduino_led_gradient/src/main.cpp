#include <Arduino.h>
#include <Adafruit_NeoPixel.h>

// ============ 설정 파라미터 ============
#define SAUSAGE_LEDS   3
#define TOMATO_LEDS    6
#define TEA_LEDS       12
#define SAUSAGE_PIN    6    // 소시지 LED (D6)
#define TOMATO_PIN     5    // 토마토 졸이기 LED (D5)
#define TEA_PIN        4    // 차 우려내기 LED (D4)
#define BUTTON1_PIN    2    // 버튼1: 소시지/토마토 (D2)
#define BUTTON2_PIN    3    // 버튼2: 차 우려내기 (D3)
#define DEBOUNCE_MS    200
// ======================================

Adafruit_NeoPixel sausageLed(SAUSAGE_LEDS, SAUSAGE_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel tomatoLed(TOMATO_LEDS, TOMATO_PIN, NEO_GRB + NEO_KHZ800);
Adafruit_NeoPixel teaLed(TEA_LEDS, TEA_PIN, NEO_GRB + NEO_KHZ800);

// 버튼1 (소시지/토마토)
unsigned long btn1DurationMs = 10000UL;
uint8_t btn1TaskMode = 1;  // 1=소시지, 2=토마토
bool btn1LastState = HIGH;
bool btn1Active = false;
unsigned long btn1StartTime = 0;
unsigned long btn1DebounceTime = 0;

// 버튼2 (차 우려내기)
unsigned long btn2DurationMs = 10000UL;
bool btn2LastState = HIGH;
bool btn2Active = false;
unsigned long btn2StartTime = 0;
unsigned long btn2DebounceTime = 0;

char serialBuf[32];
uint8_t serialIdx = 0;

const char* btn1TaskName() {
  return (btn1TaskMode == 1) ? "SAUSAGE" : "TOMATO";
}

// 소시지 굽기: 분홍 → 갈색 → 빨강
void sausageColor(float progress, uint8_t &r, uint8_t &g, uint8_t &b) {
  if (progress <= 1.0) {
    r = 255 - (uint8_t)(95.0 * progress);
    g = 105 - (uint8_t)(25.0 * progress);
    b = 180 - (uint8_t)(160.0 * progress);
  } else {
    float bp = (progress - 1.0) / 0.3;
    r = 160 + (uint8_t)(95.0 * bp);
    g =  80 - (uint8_t)(80.0 * bp);
    b =  20 - (uint8_t)(20.0 * bp);
  }
}

// 토마토 소스 졸이기: 연한 빨강 → 진한 빨강 → 짙은 적갈색
void tomatoColor(float progress, uint8_t &r, uint8_t &g, uint8_t &b) {
  if (progress <= 1.0) {
    r = 255 - (uint8_t)(55.0 * progress);
    g = 120 - (uint8_t)(80.0 * progress);
    b =  80 - (uint8_t)(60.0 * progress);
  } else {
    float bp = (progress - 1.0) / 0.3;
    r = 200 - (uint8_t)(50.0 * bp);
    g =  40 - (uint8_t)(25.0 * bp);
    b =  20 - (uint8_t)(10.0 * bp);
  }
}

// 차 우려내기: 흰색 → 연두 → 초록 → 진한 초록
void teaColor(float progress, uint8_t &r, uint8_t &g, uint8_t &b) {
  if (progress <= 1.0) {
    // 흰색(200,255,200) → 초록(0,180,0)
    r = 200 - (uint8_t)(200.0 * progress);  // 200 → 0
    g = 255 - (uint8_t)(75.0 * progress);   // 255 → 180
    b = 200 - (uint8_t)(200.0 * progress);  // 200 → 0
  } else {
    // 초록(0,180,0) → 진한 초록(0,80,0)
    float bp = (progress - 1.0) / 0.3;
    r = 0;
    g = 180 - (uint8_t)(100.0 * bp);  // 180 → 80
    b = 0;
  }
}

void processSerialCommand(const char* cmd) {
  if (cmd[0] == 'D' || cmd[0] == 'd') {
    // D1:10000 = 버튼1 duration, D2:10000 = 버튼2 duration, D10000 = 둘 다
    if (cmd[1] == '1' && cmd[2] == ':') {
      unsigned long val = atol(cmd + 3);
      if (val > 0) { btn1DurationMs = val;
        Serial.print("[SET] Btn1 Duration = "); Serial.print(val); Serial.println("ms"); }
    } else if (cmd[1] == '2' && cmd[2] == ':') {
      unsigned long val = atol(cmd + 3);
      if (val > 0) { btn2DurationMs = val;
        Serial.print("[SET] Btn2 Duration = "); Serial.print(val); Serial.println("ms"); }
    } else {
      unsigned long val = atol(cmd + 1);
      if (val > 0) { btn1DurationMs = val; btn2DurationMs = val;
        Serial.print("[SET] All Duration = "); Serial.print(val); Serial.println("ms"); }
    }
  } else if (cmd[0] == 'T' || cmd[0] == 't') {
    uint8_t val = atoi(cmd + 1);
    if (val >= 1 && val <= 2) {
      btn1TaskMode = val;
      Serial.print("[SET] Btn1 Task = "); Serial.println(btn1TaskName());
    }
  } else if (cmd[0] == 'S' || cmd[0] == 's') {
    Serial.print("[STATUS] Btn1: "); Serial.print(btn1TaskName());
    Serial.print(" "); Serial.print(btn1DurationMs); Serial.print("ms ");
    Serial.println(btn1Active ? "ACTIVE" : "OFF");
    Serial.print("[STATUS] Btn2: TEA ");
    Serial.print(btn2DurationMs); Serial.print("ms ");
    Serial.println(btn2Active ? "ACTIVE" : "OFF");
  }
}

void setup() {
  Serial.begin(9600);
  pinMode(BUTTON1_PIN, INPUT_PULLUP);
  pinMode(BUTTON2_PIN, INPUT_PULLUP);

  sausageLed.begin(); sausageLed.clear(); sausageLed.show();
  tomatoLed.begin();  tomatoLed.clear();  tomatoLed.show();
  teaLed.begin();     teaLed.clear();     teaLed.show();

  Serial.println("=== LED Gradient Ready ===");
  Serial.println("Btn1(D2): T1=sausage T2=tomato");
  Serial.println("Btn2(D3): tea");
  Serial.println("Cmds: D<ms>, D1:<ms>, D2:<ms>, T1/T2, S");
}

void loop() {
  // 시리얼 수신
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (serialIdx > 0) {
        serialBuf[serialIdx] = '\0';
        processSerialCommand(serialBuf);
        serialIdx = 0;
      }
    } else if (serialIdx < sizeof(serialBuf) - 1) {
      serialBuf[serialIdx++] = c;
    }
  }

  // === 버튼1: 소시지/토마토 ===
  bool btn1State = digitalRead(BUTTON1_PIN);
  if (btn1State == LOW && btn1LastState == HIGH
      && (millis() - btn1DebounceTime) > DEBOUNCE_MS) {
    btn1DebounceTime = millis();
    btn1Active = !btn1Active;
    if (btn1Active) {
      btn1StartTime = millis();
      Serial.print("[BTN1 ON] "); Serial.print(btn1TaskName());
      Serial.print(" ("); Serial.print(btn1DurationMs / 1000); Serial.println("s)");
    } else {
      sausageLed.clear(); sausageLed.show();
      tomatoLed.clear();  tomatoLed.show();
      Serial.println("[BTN1 OFF]");
    }
  }
  btn1LastState = btn1State;

  // === 버튼2: 차 우려내기 ===
  bool btn2State = digitalRead(BUTTON2_PIN);
  if (btn2State == LOW && btn2LastState == HIGH
      && (millis() - btn2DebounceTime) > DEBOUNCE_MS) {
    btn2DebounceTime = millis();
    btn2Active = !btn2Active;
    if (btn2Active) {
      btn2StartTime = millis();
      Serial.print("[BTN2 ON] TEA (");
      Serial.print(btn2DurationMs / 1000); Serial.println("s)");
    } else {
      teaLed.clear(); teaLed.show();
      Serial.println("[BTN2 OFF]");
    }
  }
  btn2LastState = btn2State;

  // === 버튼1 LED 업데이트 ===
  if (btn1Active) {
    unsigned long elapsed = millis() - btn1StartTime;
    float progress = (float)elapsed / (float)btn1DurationMs;
    if (progress > 1.3) progress = 1.3;

    uint8_t r, g, b;
    Adafruit_NeoPixel *led;
    if (btn1TaskMode == 1) { sausageColor(progress, r, g, b); led = &sausageLed; }
    else                   { tomatoColor(progress, r, g, b);  led = &tomatoLed; }

    for (uint16_t i = 0; i < led->numPixels(); i++) led->setPixelColor(i, led->Color(r, g, b));
    led->show();

    static unsigned long lastPrint1 = 0;
    if (millis() - lastPrint1 >= 5000) {
      lastPrint1 = millis();
      Serial.print("["); Serial.print(btn1TaskName()); Serial.print(" ");
      Serial.print(elapsed / 1000); Serial.print("s] R="); Serial.print(r);
      Serial.print(" G="); Serial.print(g); Serial.print(" B="); Serial.print(b);
      Serial.print(" ("); Serial.print((int)(progress * 100)); Serial.println("%)");
    }
  }

  // === 버튼2 LED 업데이트 ===
  if (btn2Active) {
    unsigned long elapsed = millis() - btn2StartTime;
    float progress = (float)elapsed / (float)btn2DurationMs;
    if (progress > 1.3) progress = 1.3;

    uint8_t r, g, b;
    teaColor(progress, r, g, b);

    for (uint16_t i = 0; i < teaLed.numPixels(); i++) teaLed.setPixelColor(i, teaLed.Color(r, g, b));
    teaLed.show();

    static unsigned long lastPrint2 = 0;
    if (millis() - lastPrint2 >= 5000) {
      lastPrint2 = millis();
      Serial.print("[TEA "); Serial.print(elapsed / 1000); Serial.print("s] R=");
      Serial.print(r); Serial.print(" G="); Serial.print(g);
      Serial.print(" B="); Serial.print(b);
      Serial.print(" ("); Serial.print((int)(progress * 100)); Serial.println("%)");
    }
  }

  delay(50);
}
