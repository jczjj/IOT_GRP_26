#include <SPI.h>
#include <LoRa.h>

void setup() {
  Serial.begin(9600);
  while (!Serial);
  LoRa.begin(915E6);
  Serial.println("NODE_READY");
}

void loop() {
  if (Serial.available()) {
    String hardwareID = Serial.readStringUntil('\n');
    hardwareID.trim();
    delay(random(500, 2000)); // CSMA Backoff
    LoRa.beginPacket();
    LoRa.print("REG_REQ:" + hardwareID);
    LoRa.endPacket();

    while (true) {
      if (LoRa.parsePacket()) {
        if (LoRa.readString() == "ASSIGN:02") {
          Serial.println("TRIGGER:ASSIGN_02");
          return;
        }
      }
    }
  }
}
