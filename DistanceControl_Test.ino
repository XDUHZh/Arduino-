#include <LiquidCrystal.h>

// LCD:
// RS=12, E=11, D4=5, D5=4, D6=3, D7=2
LiquidCrystal lcd(12, 11, 5, 4, 3, 2);

const int sensorPin = A0;
const int motorPin  = 7;

// ========================
// 学号接收
// ========================
char studentID[12] = "";   // 11位学号 + '\0'
int idIndex = 0;
bool idReceived = false;

// 收到学号后根据末位计算阈值
float threshold = 35.0;

// ========================
// 定时发送
// ========================
unsigned long lastSendTime = 0;
const unsigned long SEND_INTERVAL = 500;


// ========================
// GP2D12距离换算
// 根据你刚才实测数据拟合
// ========================
float readDistance() {
  int adc = analogRead(sensorPin);

  if (adc <= 28) {
    return 80.0;
  }

  float distance = 4922.0 / (adc - 27.11);

  if (distance < 10.0)
    distance = 10.0;

  if (distance > 80.0)
    distance = 80.0;

  return distance;
}


// ========================
// 接收PC发送的11位学号
// ========================
void receiveStudentID() {
  while (Serial.available() > 0) {

    char c = Serial.read();

    // 只接收数字，自动忽略回车换行
    if (c >= '0' && c <= '9') {

      studentID[idIndex] = c;
      idIndex++;

      // 收满11位
      if (idIndex == 11) {

        studentID[11] = '\0';

        idReceived = true;
        idIndex = 0;

        // 学号末位
        int lastDigit = studentID[10] - '0';

        // 阈值 = 30 + 学号末位
        threshold = 30.0 + lastDigit;
      }
    }
  }
}


// ========================
// LCD显示
// ========================
void updateLCD(float distance) {

  lcd.setCursor(0, 0);

  if (idReceived) {
    lcd.print("ID:");
    lcd.print(studentID);
    lcd.print("  ");
  }
  else {
    lcd.print("Waiting ID...   ");
  }


  lcd.setCursor(0, 1);

  lcd.print("DIST:");
  lcd.print(distance, 1);
  lcd.print("cm   ");
}


// ========================
// 电机控制
// ========================
void controlMotor(float distance) {

  if (distance > threshold) {
    digitalWrite(motorPin, HIGH);
  }
  else {
    digitalWrite(motorPin, LOW);
  }
}


// ========================
// 返回距离给PC
// ========================
void sendDistance(float distance) {

  // 按题目要求：
  // PC发送学号以后Arduino才返回距离
  if (!idReceived)
    return;

  if (millis() - lastSendTime >= SEND_INTERVAL) {

    lastSendTime = millis();

    Serial.print("DIST:");
    Serial.println(distance, 1);
  }
}


// ========================
// 初始化
// ========================
void setup() {

  Serial.begin(9600);

  lcd.begin(16, 2);

  pinMode(motorPin, OUTPUT);
  digitalWrite(motorPin, LOW);

  lcd.setCursor(0, 0);
  lcd.print("Waiting ID...");

  lcd.setCursor(0, 1);
  lcd.print("DIST:---.-cm");
}


// ========================
// 主循环
// ========================
void loop() {

  receiveStudentID();

  float distance = readDistance();

  controlMotor(distance);

  updateLCD(distance);

  sendDistance(distance);

  delay(50);
}