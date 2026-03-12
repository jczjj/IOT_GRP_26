#include <SPI.h>
#include <lmic.h>
#include <hal/hal.h>
#include <LoRa.h>

#define SS   10
#define RST  7
#define DIO0 2
#define MY_DEVICE_ID 0x02   // <-- change this per device (0x01, 0x02, 0x03...)

bool useLoRaWAN = true;
bool waitingForAck = false;

// For P2P repeated sending
unsigned long lastSendTime = 0;
const unsigned long sendInterval = 2000;
int retryCount = 0;
const int maxRetries = 1;

// ================= LORAWAN KEYS =================
static const u1_t PROGMEM APPEUI[8] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }

static const u1_t PROGMEM DEVEUI[8] = { 0xE0, 0x61, 0x07, 0xD0, 0x7E, 0xD5, 0xB3, 0x70 };
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }

static const u1_t PROGMEM APPKEY[16] = {
  0xC6, 0x48, 0xA6, 0xD4, 0xBD, 0x92, 0xA5, 0x1A, 0x13, 0x0A, 0x43, 0x64, 0x95, 0xFD, 0xCA, 0x76
};
void os_getDevKey (u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

static osjob_t sendjob;
static uint8_t mydata[] = { 0x01, MY_DEVICE_ID };  // [device ID, data]
const unsigned TX_INTERVAL = 30;

const lmic_pinmap lmic_pins = {
  .nss = SS,
  .rxtx = LMIC_UNUSED_PIN,
  .rst = RST,
  .dio = {DIO0, 5, 6},
};

// ================= LORAWAN SEND =================
void do_send(osjob_t* j) {
  if (!(LMIC.opmode & OP_TXRXPEND)) {
    LMIC_setTxData2(1, mydata, sizeof(mydata), 0);
  }
}

// ================= SWITCH TO P2P =================
void switchToLoRa() {

  LMIC_shutdown();

  useLoRaWAN = false;
  waitingForAck = true;

  LoRa.setPins(SS, RST, DIO0);

  if (!LoRa.begin(915E6)) {
    while (1);
  }
}

// ================= SWITCH BACK TO LORAWAN =================
void switchToLoRaWAN() {

  LoRa.end();

  useLoRaWAN = true;
  waitingForAck = false;

  os_init();
  LMIC_reset();

  LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);
  LMIC_selectSubBand(1);

  do_send(&sendjob);
}

// ================= LORAWAN EVENTS =================
void onEvent (ev_t ev) {

  if (ev == EV_TXCOMPLETE) {

    if (LMIC.dataLen) {

      uint8_t firstByte = LMIC.frame[LMIC.dataBeg];

      // Command 0x01 → switch to P2P mode
      if (firstByte == 0x01) {
        switchToLoRa();
        return;
      }

      // Command 0x02 → print full payload
      else if (firstByte == 0x02) {

        for (uint8_t i = 0; i < LMIC.dataLen; i++) {
          Serial.write(LMIC.frame[LMIC.dataBeg + i]);  // send raw byte
        }
      }
    
    }

    os_setTimedCallback(&sendjob,
      os_getTime() + sec2osticks(TX_INTERVAL),
      do_send);
  }
}

// ================= SETUP =================
void setup() {
  Serial.begin(9600);
  delay(1000);

  os_init();
  LMIC_reset();

  LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);
  LMIC_selectSubBand(1);

  do_send(&sendjob);
}

// ================= LOOP =================
void loop() {

  if (useLoRaWAN) {
    os_runloop_once();
  }
  else {

    // Send repeatedly every 2 seconds
    if (millis() - lastSendTime > sendInterval && retryCount < maxRetries) {

      LoRa.beginPacket();
      LoRa.write(0x1A);
      LoRa.write(0x2B);
      LoRa.write(MY_DEVICE_ID);  // byte[0] = device ID
      LoRa.endPacket();
      delay(2000);

      lastSendTime = millis();
      retryCount++;
    }

    // Listen for ACK
    int packetSize = LoRa.parsePacket();
    if (packetSize) {

      String received = "";
      while (LoRa.available()) {
        received += (char)LoRa.read();
      }

      if (received == "ACK") {
        retryCount = 0;
        switchToLoRaWAN();
      }
    }

    // If max retries reached without ACK
    if (retryCount >= maxRetries) {
      retryCount = 0;
      switchToLoRaWAN();
    }
  }
}