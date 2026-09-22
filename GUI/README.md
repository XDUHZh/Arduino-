# Arduino 距离测量 PC 上位机

这是一个使用 Python/Tkinter 编写的串口上位机，支持：

- 在标题栏显示学号和姓名；
- 自动检测、打开和关闭串口；
- 发送学号并在发送窗口留下记录；
- 接收 Arduino 的距离值并实时显示；
- 单次测距、开始连续测量、停止连续测量；
- 固定显示学号 `23079100075` 和姓名“郑辉”；
- 每 2 秒自动检测一次串口插拔，并支持手动刷新。

## 运行方法

电脑需安装 Python 3.10 或更高版本。在本目录打开终端并执行：

```powershell
python -m pip install -r requirements.txt
python pc_serial_gui.py
```

学生信息已固定，无需输入。连接 Arduino，选择对应串口，波特率应与 Arduino 程序一致（示例为 9600），然后点击“打开串口”。程序会同时使用 pyserial 和 Windows 注册表检测端口。

如果界面提示“缺少 pyserial”，请关闭程序后执行：

```powershell
python -m pip install pyserial
```

如果能看到端口但无法打开，请先关闭 Arduino IDE 的串口监视器，避免端口被占用。

## 通信协议

每条消息以换行结束，编码为 UTF-8/ASCII。

| 方向 | 内容示例 | 含义 |
| --- | --- | --- |
| PC → Arduino | `ID:23079100075` | 发送固定学号 |
| PC → Arduino | `MEASURE` | 请求一次测距 |
| PC → Arduino | `START` | 开始连续测距 |
| PC → Arduino | `STOP` | 停止连续测距 |
| Arduino → PC | `DIST:25.40 cm` | 返回距离 |

程序也能识别 `Distance=120mm`、`距离: 1.2米` 或单独的数字（默认单位 cm）。`arduino_distance_demo.ino` 是配套的 HC-SR04 示例，可直接用 Arduino IDE 打开并上传。

## 打包为 Windows EXE（可选）

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name Arduino距离上位机 pc_serial_gui.py
```

生成的程序位于 `dist` 文件夹，学号和姓名已经内置。
