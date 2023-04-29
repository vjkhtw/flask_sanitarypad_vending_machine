#include <WiFi.h>
#include <MFRC522.h>
#include <HTTPClient.h>

#define SS_PIN 10
#define RST_PIN 9

const char* ssid = "wifi_ssid";
const char* password = "wifi_password";
const char* server_url = "http://127.0.0.1:5000";

MFRC522 mfrc522(SS_PIN, RST_PIN);   // Create MFRC522 instance.
WiFiClient client;
HTTPClient http;

void setup() 
{
  //pinMode(4, OUTPUT);
  Serial.begin(9600);   // Initiate a serial communication
  SPI.begin();      // Initiate  SPI bus
  mfrc522.PCD_Init();   // Initiate MFRC522
   WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  Serial.println("Connected to WiFi");
  Serial.println("Approximate your card to the reader...");
  Serial.println();

}
void loop() 
{
  // Look for new cards
  if ( ! mfrc522.PICC_IsNewCardPresent()) 
  {
    return;
  }
  // Select one of the cards
  if ( ! mfrc522.PICC_ReadCardSerial()) 
  {
    return;
  }
  //Show UID on serial monitor
  Serial.print("UID tag :");
  String content= "";
  byte letter;
  for (byte i = 0; i < mfrc522.uid.size; i++) 
  {
     Serial.print(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " ");
     Serial.print(mfrc522.uid.uidByte[i], HEX);
     content.concat(String(mfrc522.uid.uidByte[i] < 0x10 ? " 0" : " "));
     content.concat(String(mfrc522.uid.uidByte[i], HEX));
  }
  Serial.println();
  Serial.print("Message : ");
  content.toUpperCase();
  if (content.substring(1) == "60 B3 37 21") //change here the UID of the card/cards that you want to give access
  {    
    Serial.println("Authorized access");
    Serial.println();
    http.begin(client, server_url "/vend");
    http.addHeader("Content-Type", "application/x-www-form-urlencoded");
    http.POST("rfid=60B33721&location=location1"); //Change the RFID and location values as per your requirement
    http.end();
    delay(5000);
  }
  else {
    Serial.println("Access denied");
    delay(3000);
  }
}
