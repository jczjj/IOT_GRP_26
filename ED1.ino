#include <SPI.h>
#include <lmic.h>
#include <hal/hal.h>
#include <LoRa.h>

#define SS   10
#define RST  7
#define DIO0 2
#define MY_DEVICE_ID 0x01   // <-- change this per device (0x01, 0x02, 0x03...)

bool useLoRaWAN = true;

// For P2P repeated sending
unsigned long lastSendTime = 0;
const unsigned long sendInterval = 2000;
int retryCount = 0;
const int maxRetries = 1;

// ================= LORAWAN KEYS =================
static const u1_t PROGMEM APPEUI[8] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }

static const u1_t PROGMEM DEVEUI[8] = { 0x71, 0x5D, 0x07, 0xD0, 0x7E, 0xD5, 0xB3, 0x70 };
void os_getDevEui (u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }

static const u1_t PROGMEM APPKEY[16] = {
  0x72, 0x62, 0xD1, 0x80, 0x02, 0x75, 0xD9, 0x19,
  0x90, 0x51, 0x06, 0xF9, 0x28, 0x3A, 0xB5, 0xCE
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
  if (LMIC.opmode & OP_TXRXPEND) {
    // If MAC is busy (join/TX/RX), retry scheduling instead of dropping heartbeat.
    os_setTimedCallback(&sendjob,
      os_getTime() + sec2osticks(5),
      do_send);
    return;
  }

  LMIC_setTxData2(1, mydata, sizeof(mydata), 0);
}

// ================= SWITCH TO P2P =================
void switchToLoRa() {

  LMIC_shutdown();

  useLoRaWAN = false;
  retryCount = 0;
  lastSendTime = 0;

  LoRa.setPins(SS, RST, DIO0);

  if (!LoRa.begin(915E6)) {
    Serial.println("LoRa P2P init failed");
    while (1) {
      delay(1000);
    }
  }
  LoRa.setTxPower(10);
}

// ================= SWITCH BACK TO LORAWAN =================
void switchToLoRaWAN() {

  LoRa.end();

  useLoRaWAN = true;
  retryCount = 0;

  // Reinitialize LMIC runtime after LMIC_shutdown() before resetting MAC state.
  os_init();
  LMIC_reset();

  LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);
  LMIC_selectSubBand(1);

  do_send(&sendjob);
}

// ================= LORAWAN EVENTS =================
void onEvent (ev_t ev) {

  if (ev == EV_JOIN_FAILED || ev == EV_REJOIN_FAILED) {
    // Retry after a delay so the heartbeat loop self-recovers if join fails.
    os_setTimedCallback(&sendjob,
      os_getTime() + sec2osticks(TX_INTERVAL),
      do_send);
    return;
  }

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

    // Send attempts every sendInterval until maxRetries is reached.
    if ((millis() - lastSendTime >= sendInterval) && retryCount < maxRetries) {

      LoRa.beginPacket();
      LoRa.write(0x1A);
      LoRa.write(0x2B);
      LoRa.write(MY_DEVICE_ID);  // byte[0] = device ID
      LoRa.endPacket();

      lastSendTime = millis();
      retryCount++;
    }

    // Listen for ACK
    int packetSize = LoRa.parsePacket();
    if (packetSize) {

      char ackBuf[3];
      uint8_t ackLen = 0;

      while (LoRa.available() && ackLen < sizeof(ackBuf)) {
        ackBuf[ackLen++] = (char)LoRa.read();
      }
      while (LoRa.available()) {
        LoRa.read();
      }

      if (ackLen == 3 && ackBuf[0] == 'A' && ackBuf[1] == 'C' && ackBuf[2] == 'K') {
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
