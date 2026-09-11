// ============================================================
//  ESP32 MINI — Wi-Fi Diagnostic & Hotspot Connection Test
// ============================================================
//  Hardware: ESP32 Mini ONLY (No LED pins used)
//  Target SSID: Mmesomachukwu
//  Serial Monitor: 115200 baud
// ============================================================

#include <WiFi.h>

#define TARGET_SSID "Mmesomachukwu"
#define TARGET_PASS "12345678"

// Helper: translate Wi-Fi disconnect reason codes to human readable text
const char* getDisconnectReason(uint8_t reason) {
  switch (reason) {
    case 1:   return "UNSPECIFIED";
    case 2:   return "AUTH_EXPIRE";
    case 3:   return "AUTH_LEAVE";
    case 4:   return "ASSOC_EXPIRE";
    case 5:   return "ASSOC_TOOMANY";
    case 6:   return "NOT_AUTHED";
    case 7:   return "NOT_ASSOCED";
    case 8:   return "ASSOC_LEAVE";
    case 9:   return "ASSOC_NOT_AUTHED";
    case 13:  return "IE_INVALID";
    case 14:  return "MIC_FAILURE";
    case 15:  return "4WAY_HANDSHAKE_TIMEOUT (Usually wrong password!)";
    case 16:  return "GROUP_KEY_UPDATE_TIMEOUT";
    case 17:  return "IE_IN_4WAY_DIFFERS";
    case 18:  return "GROUP_CIPHER_INVALID";
    case 19:  return "PAIRWISE_CIPHER_INVALID";
    case 20:  return "AKMP_INVALID";
    case 21:  return "UNSUPP_RSN_IE_VERSION";
    case 22:  return "INVALID_RSN_IE_CAP";
    case 23:  return "802_1X_AUTH_FAILED";
    case 24:  return "CIPHER_SUITE_REJECTED";
    case 200: return "BEACON_TIMEOUT (Signal lost or hotspot turned off)";
    case 201: return "NO_AP_FOUND (SSID not found! Check 2.4GHz / spelling)";
    case 202: return "AUTH_FAIL";
    case 203: return "ASSOC_FAIL";
    case 204: return "HANDSHAKE_TIMEOUT";
    case 205: return "CONNECTION_FAIL";
    default:  return "UNKNOWN_REASON";
  }
}

// Wi-Fi Event Callbacks
void onWiFiEvent(WiFiEvent_t event, WiFiEventInfo_t info) {
  switch (event) {
    case ARDUINO_EVENT_WIFI_STA_START:
      Serial.println("[Wi-Fi Event] Station Mode started.");
      break;

    case ARDUINO_EVENT_WIFI_STA_CONNECTED:
      Serial.println("[Wi-Fi Event] Connected to AP (association successful)!");
      break;

    case ARDUINO_EVENT_WIFI_STA_GOT_IP:
      Serial.println("[Wi-Fi Event] Got IP Address!");
      Serial.printf("  >> IP Address: %s\n", WiFi.localIP().toString().c_str());
      break;

    case ARDUINO_EVENT_WIFI_STA_DISCONNECTED: {
      uint8_t reason = info.wifi_sta_disconnected.reason;
      Serial.printf("[Wi-Fi Event] Disconnected! Reason code: %d (%s)\n",
                    reason, getDisconnectReason(reason));
      break;
    }

    default:
      break;
  }
}

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println("===============================================================");
  Serial.println("     ESP32 MINI — HOTSPOT CONNECTION TEST (Mmesomachukwu)      ");
  Serial.println("===============================================================");
  Serial.printf("  CPU Frequency   : %d MHz\n", ESP.getCpuFreqMHz());
  Serial.printf("  Flash Chip Size : %d MB\n", ESP.getFlashChipSize() / (1024 * 1024));
  Serial.printf("  ESP32 MAC (UID) : %s\n", WiFi.macAddress().c_str());
  Serial.println("===============================================================");
  Serial.println();

  // Register Wi-Fi event handler for detailed diagnostics
  WiFi.onEvent(onWiFiEvent);

  // Set mode to STA
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(500);

  // Step 1: Scan to see if Mmesomachukwu is broadcasting on 2.4 GHz
  Serial.println("[Step 1] Scanning for 'Mmesomachukwu' in 2.4 GHz airwaves...");
  int n = WiFi.scanNetworks(false, true);
  bool foundTarget = false;
  int targetRssi = 0;
  int targetChannel = 0;

  if (n == 0) {
    Serial.println("  [!] Zero Wi-Fi networks detected.");
  } else {
    Serial.printf("  Scan finished: %d network(s) detected.\n", n);
    for (int i = 0; i < n; ++i) {
      String ssid = WiFi.SSID(i);
      if (ssid == TARGET_SSID) {
        foundTarget = true;
        targetRssi = WiFi.RSSI(i);
        targetChannel = WiFi.channel(i);
        Serial.printf("  >>> FOUND TARGET: '%s' | Signal: %d dBm | Channel: %d <<<\n",
                      ssid.c_str(), targetRssi, targetChannel);
      }
    }
  }
  WiFi.scanDelete();

  if (!foundTarget) {
    Serial.println();
    Serial.println("  [WARNING] 'Mmesomachukwu' was NOT found in the 2.4 GHz scan!");
    Serial.println("  If you are using a phone hotspot:");
    Serial.println("   - iPhone: Turn ON 'Maximize Compatibility' (hotspot must be 2.4 GHz).");
    Serial.println("   - Android: Set AP Band to '2.4 GHz' (ESP32 cannot see 5 GHz).");
    Serial.println("   - Make sure hotspot is actively visible/broadcasting.");
    Serial.println();
  } else {
    Serial.println("  Target hotspot is broadcasting on 2.4 GHz. Proceeding to connect!");
    Serial.println();
  }

  // Step 2: Attempt direct connection
  Serial.printf("[Step 2] Connecting to SSID: '%s' with Password: '%s'...\n", TARGET_SSID, TARGET_PASS);
  WiFi.begin(TARGET_SSID, TARGET_PASS);

  unsigned long startTime = millis();
  const unsigned long timeoutMs = 25000; // 25 seconds timeout

  while (WiFi.status() != WL_CONNECTED && millis() - startTime < timeoutMs) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();

  // Step 3: Check result
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println();
    Serial.println("===============================================================");
    Serial.println("          SUCCESSFULLY CONNECTED TO MMESOMACHUKWU!             ");
    Serial.println("===============================================================");
    Serial.printf("  IP Address      : %s\n", WiFi.localIP().toString().c_str());
    Serial.printf("  Subnet Mask     : %s\n", WiFi.subnetMask().toString().c_str());
    Serial.printf("  Gateway IP      : %s\n", WiFi.gatewayIP().toString().c_str());
    Serial.printf("  DNS Server      : %s\n", WiFi.dnsIP().toString().c_str());
    Serial.printf("  Signal Strength : %d dBm\n", WiFi.RSSI());
    Serial.printf("  Wi-Fi Channel   : %d\n", WiFi.channel());
    Serial.println("===============================================================");
    Serial.println("Your phone hotspot connection is 100% verified working!");
    Serial.println();
  } else {
    Serial.println();
    Serial.println("===============================================================");
    Serial.println("               FAILED TO CONNECT WITHIN 25s                    ");
    Serial.println("===============================================================");
    Serial.printf("  Current Status Code: %d\n", (int)WiFi.status());
    Serial.println("  Check the [Wi-Fi Event] reason code above to identify why:");
    Serial.println("   - Reason 201 (NO_AP_FOUND): Hotspot not detected or 5 GHz only.");
    Serial.println("   - Reason 15 (4WAY_HANDSHAKE_TIMEOUT): Password mismatch or security error.");
    Serial.println("   - Reason 202/203 (AUTH/ASSOC FAIL): Phone hotspot rejected connection.");
    Serial.println("===============================================================");
  }
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("[Connected] RSSI: %d dBm | IP: %s\n", WiFi.RSSI(), WiFi.localIP().toString().c_str());
  } else {
    Serial.printf("[Disconnected] Wi-Fi Status: %d\n", (int)WiFi.status());
  }
  delay(5000);
}
