#include <SPI.h>
#include <lmic.h>
#include <hal/hal.h>
#include <LoRa.h>

#define SS   10
#define RST  7
#define DIO0 2

bool useLoRaWAN = false;
bool sendPending = false;
int8_t lastRSSI = 0;
uint8_t sourceDeviceID = 0x00;

#define PAYLOAD_TYPE_RSSI 0x01

// ================= LORAWAN KEYS =================
static const u1_t PROGMEM APPEUI[8] = { 0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00 };
void os_getArtEui (u1_t* buf) { memcpy_P(buf, APPEUI, 8); }

static const u1_t PROGMEM DEVEUI[8] = { 0xDF, 0x61, 0x07, 0xD0, 0x7E, 0xD5, 0xB3, 0x70 };
void os_getDevEui(u1_t* buf) { memcpy_P(buf, DEVEUI, 8); }

static const u1_t PROGMEM APPKEY[16] = {
  0x44, 0xA0, 0x1B, 0x33, 0x17, 0xA8, 0x6B, 0x68,
  0x7B, 0xFD, 0x53, 0x3F, 0xA5, 0xB7, 0x23, 0x15
};
void os_getDevKey(u1_t* buf) { memcpy_P(buf, APPKEY, 16); }

const lmic_pinmap lmic_pins = {
  .nss = SS,
  .rxtx = LMIC_UNUSED_PIN,
  .rst = RST,
  .dio = {DIO0, 5, 6},
};

// ================= SEND RSSI PAYLOAD =================
void send_rssi_payload(int rssi) {
  if (!(LMIC.opmode & OP_TXRXPEND)) {
    uint8_t payload[4];
    int16_t rssi16 = (int16_t)rssi;
    payload[0] = PAYLOAD_TYPE_RSSI;
    payload[1] = sourceDeviceID;
    payload[2] = highByte(rssi16);
    payload[3] = lowByte(rssi16);
    LMIC_setTxData2(1, payload, 4, 0);
    Serial.print("Sending RSSI ");
  }
}

// ================= SWITCH TO LORA P2P RX =================
void switchToLoRaRX() {
  Serial.println("Switching to LoRa P2P RX mode...");

  LMIC_shutdown();

  useLoRaWAN = false;
  sendPending = false;

  LoRa.setPins(SS, RST, DIO0);

  int retryCount = 0;
  while (!LoRa.begin(915E6)) {
    Serial.println("LoRa init failed! Retrying...");
    delay(500);
    retryCount++;
    if (retryCount > 5) {
      Serial.println("LoRa failed after multiple retries.");
      while (1);
    }
  }

  delay(200); // Allow hardware to settle
  LoRa.receive();
  Serial.println("Listening for LoRa packets...");
}

// ================= SWITCH TO LORAWAN =================
void switchToLoRaWAN() {
  Serial.println("Switching to LoRaWAN mode...");

  LoRa.end();
  delay(200);

  useLoRaWAN = true;
  sendPending = false;

  os_init();
  LMIC_reset();

  LMIC_setClockError(MAX_CLOCK_ERROR * 1 / 100);
  LMIC_selectSubBand(1);

  LMIC_startJoining();
  Serial.println("Joining LoRaWAN...");
}

// ================= LORAWAN EVENTS =================
void onEvent(ev_t ev) {
  switch (ev) {

    case EV_JOINING:
      Serial.println("Joining...");
      break;

    case EV_JOINED:
      Serial.println("Join OK!");
      LMIC_setLinkCheckMode(0);
      LMIC_setDrTxpow(DR_SF7, 14);
      LMIC.globalDutyAvail = os_getTime();
      sendPending = true;
      break;

    case EV_TXCOMPLETE:
      Serial.println("TX Complete! Switching back to LoRa RX.");
      switchToLoRaRX();
      break;

    case EV_JOIN_FAILED:
      Serial.println("Join FAILED. Retrying...");
      LMIC_startJoining();
      break;

    case EV_REJOIN_FAILED:
      Serial.println("Rejoin FAILED.");
      break;

    default:
      break;
  }
}

// ================= SETUP =================
void setup() {
  Serial.begin(9600);
  delay(1000);
  Serial.println("SN 3");
  Serial.println("Starting in LoRa P2P RX mode...");

  LoRa.setPins(SS, RST, DIO0);

  int retryCount = 0;
  while (!LoRa.begin(915E6)) {
    Serial.println("LoRa init failed! Retrying...");
    delay(500);
    retryCount++;
    if (retryCount > 5) {
      Serial.println("LoRa failed after multiple retries.");
      while (1);
    }
  }

  delay(200); // Allow hardware to settle
  LoRa.receive();
  Serial.println("Listening for LoRa packets...");
}

// ================= LOOP =================
void loop() {

  if (!useLoRaWAN) {
    int packetSize = LoRa.parsePacket();
    if (packetSize) {
      // Read first three bytes for protocol
      uint8_t header1 = 0, header2 = 0, id = 0;
      if (LoRa.available()) header1 = LoRa.read();
      if (LoRa.available()) header2 = LoRa.read();
      if (LoRa.available()) id = LoRa.read();
      // Flush remaining bytes
      while (LoRa.available()) LoRa.read();
      lastRSSI = (int8_t)LoRa.packetRssi();

      // Only switch to LoRaWAN if header matches
      if (header1 == 0x1A && header2 == 0x2B) {
        sourceDeviceID = id;
        Serial.print("Packet received! Source ID = 0x");
        Serial.print(sourceDeviceID, HEX);
        Serial.print(" RSSI = ");
        Serial.println(lastRSSI);
        switchToLoRaWAN();
      }
    }
  }
  else {
    os_runloop_once();
    if (sendPending && !(LMIC.opmode & OP_TXRXPEND)) {
      send_rssi_payload(lastRSSI);
      sendPending = false;
    }
  }
}

