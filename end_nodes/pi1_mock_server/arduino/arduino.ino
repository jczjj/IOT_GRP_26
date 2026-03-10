#include <SPI.h>
#include <LoRa.h>

void setup() {
  Serial.begin(9600);
  while (!Serial);
  if (!LoRa.begin(915E6)) { Serial.println("LORA_FAIL"); while (1); }
  Serial.println("ROUTER_READY");
}

void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize) {
    String msg = LoRa.readString();
    if (msg.startsWith("REG_REQ:")) {
      String nodeID = msg.substring(8);
      Serial.println("FOUND_NODE:" + nodeID);
    }
  }

  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');
    if (cmd.startsWith("ASSIGN:")) {
      LoRa.beginPacket();
      LoRa.print(cmd); 
      LoRa.endPacket();
      Serial.println("ASSIGNMENT_SENT");
    }
  }
}
