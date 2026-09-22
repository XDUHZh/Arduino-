#include <LiquidCrystal.h>
#include <string.h>

// LCD: RS=12, E=11, D4=5, D5=4, D6=3, D7=2
LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

const int SENSOR_PIN = A0;
const int MOTOR_PIN = 7;
const unsigned long SEND_INTERVAL = 500;

char studentID[12] = "";  // 11 位学号 + '\0'
bool idReceived = false;
float threshold = 35.0;

// PC 控制状态：默认不向 PC 连续上传。
bool continuousMode = false;
bool singleRequested = false;
unsigned long lastSendTime = 0;

// PC 每条命令都以换行结束，最大命令为 ID:xxxxxxxxxxx。
char commandBuffer[32] = "";
byte commandIndex = 0;


float readDistance() {
  int adc = analogRead(SENSOR_PIN);
  if (adc <= 28) {
    return 80.0;
  }

  float distance = 4922.0 / (adc - 27.11);
  if (distance < 10.0) distance = 10.0;
  if (distance > 80.0) distance = 80.0;
  return distance;
}


void saveStudentID(const char* value) {
  // 必须正好是 11 位数字。
  if (strlen(value) != 11) {
    Serial.println("ERROR:INVALID_ID");
    return;
  }

  for (byte i = 0; i < 11; i++) {
    if (value[i] < '0' || value[i] > '9') {
      Serial.println("ERROR:INVALID_ID");
      return;
    }
  }

  strcpy(studentID, value);
  idReceived = true;
  threshold = 30.0 + (studentID[10] - '0');

  Serial.print("ID_OK:");
  Serial.println(studentID);
}


void handleCommand(const char* command) {
  if (strncmp(command, "ID:", 3) == 0) {
    saveStudentID(command + 3);
  } else if (strcmp(command, "MEASURE") == 0) {
    // 切出连续模式，下一次 loop 只发送一条距离。
    continuousMode = false;
    singleRequested = true;
  } else if (strcmp(command, "START") == 0) {
    continuousMode = true;
    singleRequested = false;
    lastSendTime = 0;
    Serial.println("START_OK");
  } else if (strcmp(command, "STOP") == 0) {
    continuousMode = false;
    singleRequested = false;
    Serial.println("STOP_OK");
  } else if (command[0] != '\0') {
    Serial.println("ERROR:UNKNOWN_COMMAND");
  }
}


void receiveCommand() {
  while (Serial.available() > 0) {
    char c = Serial.read();

    if (c == '\r') {
      continue;
    }

    if (c == '\n') {
      commandBuffer[commandIndex] = '\0';
      handleCommand(commandBuffer);
      commandIndex = 0;
      commandBuffer[0] = '\0';
    } else if (commandIndex < sizeof(commandBuffer) - 1) {
      commandBuffer[commandIndex++] = c;
    } else {
      // 命令过长时丢弃，避免数组越界。
      commandIndex = 0;
      commandBuffer[0] = '\0';
      Serial.println("ERROR:COMMAND_TOO_LONG");
    }
  }
}


void updateLCD(float distance) {
  lcd.setCursor(0, 0);
  if (idReceived) {
    lcd.print("ID:");
    lcd.print(studentID);
    lcd.print("  ");
  } else {
    lcd.print("Waiting ID...   ");
  }

  lcd.setCursor(0, 1);
  lcd.print("DIST:");
  lcd.print(distance, 1);
  lcd.print("cm   ");
}


void controlMotor(float distance) {
  digitalWrite(MOTOR_PIN, distance > threshold ? HIGH : LOW);
}


void writeDistance(float distance) {
  Serial.print("DIST:");
  Serial.print(distance, 1);
  Serial.println(" cm");
}


void processDistanceTransmission(float distance) {
  if (!idReceived) {
    return;
  }

  // 单次测量：无视 500 ms 定时器，只发送当前这一条。
  if (singleRequested) {
    singleRequested = false;
    writeDistance(distance);
    return;
  }

  // 连续测量：每 500 ms 发送一条；STOP 后 continuousMode 为 false。
  if (continuousMode && millis() - lastSendTime >= SEND_INTERVAL) {
    lastSendTime = millis();
    writeDistance(distance);
  }
}


void setup() {
  Serial.begin(9600);
  lcd.begin(16, 2);
  pinMode(MOTOR_PIN, OUTPUT);
  digitalWrite(MOTOR_PIN, LOW);

  lcd.setCursor(0, 0);
  lcd.print("Waiting ID...");
  lcd.setCursor(0, 1);
  lcd.print("DIST:---.-cm");
}


void loop() {
  receiveCommand();

  float distance = readDistance();
  controlMotor(distance);
  updateLCD(distance);
  processDistanceTransmission(distance);

  delay(50);
}
