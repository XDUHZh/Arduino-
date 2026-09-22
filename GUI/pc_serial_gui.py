"""Arduino 距离测量 PC 上位机。"""

from __future__ import annotations

import os
import queue
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

try:
    import winreg
except ImportError:
    winreg = None

from serial_protocol import make_command, parse_distance

STUDENT_ID = "23079100075"
STUDENT_NAME = "郑辉"
BAUD_RATES = (9600, 19200, 38400, 57600, 115200)
COLORS = {
    "navy": "#102A43", "blue": "#2878B5", "teal": "#0E9F9A",
    "teal_dark": "#087F7B", "background": "#F3F6FA",
    "card": "#FFFFFF", "border": "#DCE5EE", "text": "#243B53",
    "muted": "#6B7C8F", "success": "#18A558", "warning": "#D97706",
    "danger": "#D64545", "console": "#F7F9FC",
}


def _port_sort_key(device: str) -> tuple[str, int]:
    match = re.fullmatch(r"([A-Za-z]+)(\d+)", device)
    return (match.group(1).upper(), int(match.group(2))) if match else (device.upper(), 0)


def detect_serial_ports() -> list[tuple[str, str]]:
    """用 pyserial 和 Windows 注册表双重检测串口。"""
    found: dict[str, str] = {}
    if list_ports is not None:
        try:
            for info in list_ports.comports(include_links=True):
                device = str(info.device).upper()
                description = str(info.description or "串口设备")
                if description.lower() in {"n/a", device.lower()}:
                    description = "串口设备"
                found[device] = description
        except Exception:
            pass

    if os.name == "nt" and winreg is not None:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DEVICEMAP\SERIALCOMM") as key:
                index = 0
                while True:
                    try:
                        _, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    device = str(value).upper()
                    if re.fullmatch(r"COM\d+", device):
                        found.setdefault(device, "Windows 串口")
                    index += 1
        except OSError:
            pass
    return sorted(found.items(), key=lambda item: _port_sort_key(item[0]))


class SerialWorker:
    def __init__(self, inbox: queue.Queue[tuple[str, object]]) -> None:
        self.inbox = inbox
        self.connection = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_open(self) -> bool:
        return bool(self.connection and self.connection.is_open)

    def open(self, port: str, baudrate: int) -> None:
        if serial is None:
            raise RuntimeError("缺少 pyserial，请执行：python -m pip install pyserial")
        self.connection = serial.Serial(
            port=port, baudrate=baudrate, bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
            timeout=0.2, write_timeout=1,
        )
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop_event.set()
        connection, self.connection = self.connection, None
        if connection and connection.is_open:
            connection.close()

    def send(self, payload: bytes) -> None:
        if not self.is_open:
            raise RuntimeError("请先打开串口")
        self.connection.write(payload)
        self.connection.flush()

    def clear_input(self) -> None:
        """清除尚未处理的旧距离，确保单次测量取到的是新结果。"""
        if self.is_open:
            self.connection.reset_input_buffer()

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            connection = self.connection
            if not connection or not connection.is_open:
                break
            try:
                raw = connection.readline()
                if raw:
                    text = raw.decode("utf-8", errors="replace").strip()
                    if text:
                        self.inbox.put(("data", text))
            except (serial.SerialException, OSError) as exc:
                if not self._stop_event.is_set():
                    self.inbox.put(("error", str(exc)))
                break


class ArduinoSerialApp(tk.Tk):
    POLL_INTERVAL_MS = 80
    AUTO_REFRESH_MS = 2000

    def __init__(self) -> None:
        super().__init__()
        self.inbox: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker = SerialWorker(self.inbox)
        self._port_by_label: dict[str, str] = {}
        self._last_port_devices: tuple[str, ...] = ()
        self.port_var = tk.StringVar()
        self.baud_var = tk.StringVar(value="9600")
        self.status_var = tk.StringVar(value="正在检测串口…")
        self.port_hint_var = tk.StringVar(value="正在读取 Windows 串口设备")
        self.distance_var = tk.StringVar(value="--.-")
        self.distance_unit_var = tk.StringVar(value="cm")
        self.measurement_mode = "paused"
        self.mode_var = tk.StringVar(value="测量状态：已停止")
        self._configure_window()
        self._build_styles()
        self._build_ui()
        self.refresh_ports()
        self.after(self.POLL_INTERVAL_MS, self._process_inbox)
        self.after(self.AUTO_REFRESH_MS, self._auto_refresh_ports)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_window(self) -> None:
        self.title(f"{STUDENT_ID} {STUDENT_NAME}｜Arduino 距离测量上位机")
        self.minsize(980, 680)
        self.configure(bg=COLORS["background"])
        x = max((self.winfo_screenwidth() - 1180) // 2, 0)
        y = max((self.winfo_screenheight() - 780) // 2, 0)
        self.geometry(f"1180x780+{x}+{y}")

    def _build_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Card.TFrame", background=COLORS["card"])
        style.configure("TLabel", background=COLORS["background"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Microsoft YaHei UI", 10))
        style.configure("Muted.Card.TLabel", background=COLORS["card"], foreground=COLORS["muted"], font=("Microsoft YaHei UI", 9))
        style.configure("Identity.TLabel", background=COLORS["card"], foreground=COLORS["navy"], font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("StudentId.TLabel", background=COLORS["card"], foreground=COLORS["blue"], font=("Consolas", 22, "bold"))
        style.configure("Distance.TLabel", background=COLORS["card"], foreground=COLORS["teal"], font=("Consolas", 39, "bold"))
        style.configure("Unit.TLabel", background=COLORS["card"], foreground=COLORS["teal"], font=("Microsoft YaHei UI", 17, "bold"))
        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 9), background=COLORS["teal"], foreground="#FFFFFF", borderwidth=0)
        style.map("Primary.TButton", background=[("active", COLORS["teal_dark"]), ("disabled", "#A8B8C4")], foreground=[("disabled", "#F0F3F5")])
        style.configure("Secondary.TButton", font=("Microsoft YaHei UI", 10), padding=(13, 8), background="#E9F1F7", foreground=COLORS["navy"], borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#D7E7F2")])
        style.configure("Danger.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=(16, 9), background=COLORS["danger"], foreground="#FFFFFF", borderwidth=0)
        style.map("Danger.TButton", background=[("active", "#B93636")])
        style.configure("TCombobox", padding=7, font=("Microsoft YaHei UI", 10))

    def _build_ui(self) -> None:
        self._build_header()
        body = ttk.Frame(self, style="App.TFrame", padding=(22, 18, 22, 14))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=4)
        body.columnconfigure(1, weight=7)
        body.rowconfigure(2, weight=1)
        self._build_identity_card(body)
        self._build_serial_card(body)
        self._build_send_card(body)
        self._build_receive_card(body)
        self._build_status_bar()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["navy"], height=112)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Arduino 距离测量上位机", bg=COLORS["navy"], fg="#FFFFFF", font=("Microsoft YaHei UI", 23, "bold")).pack(pady=(19, 2))
        tk.Label(header, text=f"学生：{STUDENT_NAME}    ·    学号：{STUDENT_ID}", bg=COLORS["navy"], fg="#B9D8EC", font=("Microsoft YaHei UI", 10)).pack()

    @staticmethod
    def _new_card(parent: ttk.Frame, row: int, column: int, **grid_options: object) -> tk.Frame:
        card = tk.Frame(parent, bg=COLORS["card"], highlightthickness=1, highlightbackground=COLORS["border"])
        card.grid(row=row, column=column, sticky="nsew", padx=7, pady=7, **grid_options)
        return card

    @staticmethod
    def _section_title(parent: tk.Frame, title: str, subtitle: str = "") -> None:
        title_row = tk.Frame(parent, bg=COLORS["card"])
        title_row.pack(fill="x", padx=20, pady=(17, 12))
        tk.Frame(title_row, bg=COLORS["teal"], width=4, height=22).pack(side="left", padx=(0, 10))
        tk.Label(title_row, text=title, bg=COLORS["card"], fg=COLORS["navy"], font=("Microsoft YaHei UI", 12, "bold")).pack(side="left")
        if subtitle:
            tk.Label(title_row, text=subtitle, bg=COLORS["card"], fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side="right")

    def _build_identity_card(self, parent: ttk.Frame) -> None:
        card = self._new_card(parent, 0, 0)
        self._section_title(card, "学生信息", "已固定")
        details = ttk.Frame(card, style="Card.TFrame")
        details.pack(fill="both", expand=True, padx=22, pady=(0, 17))
        ttk.Label(details, text="姓名", style="Muted.Card.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 2))
        ttk.Label(details, text=STUDENT_NAME, style="Identity.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(details, text="学号", style="Muted.Card.TLabel").grid(row=0, column=1, sticky="w", padx=(38, 0), pady=(0, 2))
        ttk.Label(details, text=STUDENT_ID, style="StudentId.TLabel").grid(row=1, column=1, sticky="w", padx=(38, 0))

    def _build_serial_card(self, parent: ttk.Frame) -> None:
        card = self._new_card(parent, 0, 1)
        self._section_title(card, "串口连接", "自动检测设备插拔")
        content = ttk.Frame(card, style="Card.TFrame")
        content.pack(fill="both", expand=True, padx=20, pady=(0, 15))
        content.columnconfigure(1, weight=1)
        ttk.Label(content, text="串口设备", style="Card.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=4)
        self.port_box = ttk.Combobox(content, textvariable=self.port_var, state="readonly")
        self.port_box.grid(row=0, column=1, sticky="ew", pady=4)
        self.refresh_button = ttk.Button(content, text="刷新", style="Secondary.TButton", command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Label(content, text="波特率", style="Card.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=4)
        self.baud_box = ttk.Combobox(content, textvariable=self.baud_var, values=BAUD_RATES, state="readonly", width=13)
        self.baud_box.grid(row=1, column=1, sticky="w", pady=4)
        self.connection_button = ttk.Button(content, text="打开串口", style="Primary.TButton", command=self.toggle_connection)
        self.connection_button.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 3))
        ttk.Label(content, textvariable=self.port_hint_var, style="Muted.Card.TLabel").grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _build_send_card(self, parent: ttk.Frame) -> None:
        card = self._new_card(parent, 1, 0, columnspan=2)
        self._section_title(card, "发送窗口", f"固定发送学号 {STUDENT_ID}")
        controls = ttk.Frame(card, style="Card.TFrame")
        controls.pack(fill="x", padx=20, pady=(0, 11))
        ttk.Button(controls, text="发送学号", style="Primary.TButton", command=self.send_student_id).pack(side="left", padx=(0, 7))
        self.single_button = ttk.Button(controls, text="单次测距", style="Secondary.TButton", command=self.single_measure)
        self.single_button.pack(side="left", padx=4)
        self.continuous_button = ttk.Button(controls, text="开始连续测量", style="Secondary.TButton", command=self.start_continuous)
        self.continuous_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(controls, text="停止连续测量", style="Danger.TButton", command=self.stop_continuous)
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(controls, text="清空记录", style="Secondary.TButton", command=lambda: self._clear_text(self.send_text)).pack(side="right")
        self.send_text = self._make_text_area(card, height=5)
        self._append_log(self.send_text, f"待发送学号：{STUDENT_ID}")

    def _build_receive_card(self, parent: ttk.Frame) -> None:
        card = self._new_card(parent, 2, 0, columnspan=2)
        self._section_title(card, "接收窗口", "实时显示 Arduino 距离数据")
        top = ttk.Frame(card, style="Card.TFrame")
        top.pack(fill="x", padx=20, pady=(0, 8))
        ttk.Label(top, text="当前距离", style="Card.TLabel").pack(side="left", padx=(0, 20))
        ttk.Label(top, textvariable=self.distance_var, style="Distance.TLabel").pack(side="left")
        ttk.Label(top, textvariable=self.distance_unit_var, style="Unit.TLabel").pack(side="left", padx=(9, 0), pady=(12, 0))
        ttk.Button(top, text="清空记录", style="Secondary.TButton", command=lambda: self._clear_text(self.receive_text)).pack(side="right")
        ttk.Label(top, textvariable=self.mode_var, style="Muted.Card.TLabel").pack(side="right", padx=(0, 18))
        self.receive_text = self._make_text_area(card, height=7)

    def _build_status_bar(self) -> None:
        bar = tk.Frame(self, bg="#E5ECF3", height=37)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)
        self.status_dot = tk.Label(bar, text="●", bg="#E5ECF3", fg="#90A4B7", font=("Arial", 11))
        self.status_dot.pack(side="left", padx=(22, 7), pady=7)
        tk.Label(bar, textvariable=self.status_var, bg="#E5ECF3", fg=COLORS["text"], font=("Microsoft YaHei UI", 9)).pack(side="left", pady=7)
        tk.Label(bar, text=f"{STUDENT_ID}  ·  {STUDENT_NAME}", bg="#E5ECF3", fg=COLORS["muted"], font=("Microsoft YaHei UI", 9)).pack(side="right", padx=22, pady=7)

    @staticmethod
    def _make_text_area(parent: tk.Frame, height: int) -> tk.Text:
        container = tk.Frame(parent, bg=COLORS["card"])
        container.pack(fill="both", expand=True, padx=20, pady=(0, 17))
        text = tk.Text(container, height=height, wrap="word", relief="flat", borderwidth=0, bg=COLORS["console"], fg=COLORS["text"], insertbackground=COLORS["text"], selectbackground="#B9D9EE", font=("Consolas", 10), padx=12, pady=9)
        scrollbar = ttk.Scrollbar(container, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return text

    def refresh_ports(self, silent: bool = False) -> None:
        ports = detect_serial_ports()
        old_device = self._selected_device()
        self._port_by_label.clear()
        labels: list[str] = []
        for device, description in ports:
            label = f"{device}  —  {description}"
            labels.append(label)
            self._port_by_label[label] = device
        devices = tuple(device for device, _ in ports)
        ports_changed = devices != self._last_port_devices
        self._last_port_devices = devices
        self.port_box["values"] = labels
        selected_label = next((label for label, device in self._port_by_label.items() if device == old_device), "")
        self.port_var.set(selected_label or (labels[0] if labels else ""))
        if self.worker.is_open:
            return
        self.port_box.configure(state="readonly" if labels else "disabled")
        if serial is None:
            self.connection_button.configure(state="disabled")
            if labels:
                self.port_hint_var.set(f"已发现 {len(labels)} 个端口；安装 pyserial 后即可连接")
                self.status_var.set("缺少 pyserial：请执行 python -m pip install pyserial")
            else:
                self.port_hint_var.set("缺少 pyserial，且 Windows 未发现可用串口")
                self.status_var.set("请连接 Arduino，并安装 pyserial")
            self.status_dot.configure(fg=COLORS["warning"])
        elif labels:
            self.connection_button.configure(state="normal")
            self.port_hint_var.set(f"已检测到 {len(labels)} 个串口，选择 Arduino 对应端口")
            if not silent or ports_changed:
                self.status_var.set(f"已检测到 {len(labels)} 个串口")
            self.status_dot.configure(fg=COLORS["blue"])
        else:
            self.connection_button.configure(state="disabled")
            self.port_hint_var.set("未发现串口，请连接 Arduino 后刷新")
            if not silent or ports_changed:
                self.status_var.set("未检测到串口设备")
            self.status_dot.configure(fg=COLORS["warning"])

    def _auto_refresh_ports(self) -> None:
        if not self.worker.is_open:
            self.refresh_ports(silent=True)
        self.after(self.AUTO_REFRESH_MS, self._auto_refresh_ports)

    def _selected_device(self) -> str:
        return self._port_by_label.get(self.port_var.get(), "")

    def toggle_connection(self) -> None:
        if self.worker.is_open:
            self._disconnect()
            return
        port = self._selected_device()
        if not port:
            messagebox.showwarning("打开串口", "未选择串口。请连接 Arduino，然后点击刷新。")
            return
        try:
            self.worker.open(port, int(self.baud_var.get()))
        except Exception as exc:
            messagebox.showerror("串口打开失败", f"无法打开 {port}。\n\n{exc}\n\n请检查：\n1. Arduino IDE 的串口监视器是否已关闭；\n2. 端口是否选择正确；\n3. USB 驱动和数据线是否正常。")
            self.status_var.set(f"打开 {port} 失败")
            self.status_dot.configure(fg=COLORS["danger"])
            return
        self.connection_button.configure(text="关闭串口", style="Danger.TButton")
        self.port_box.configure(state="disabled")
        self.baud_box.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self.status_dot.configure(fg=COLORS["success"])
        self.port_hint_var.set(f"{port} 已连接，通信参数 8-N-1")
        self._set_measurement_mode("paused")
        self.status_var.set(f"已连接 {port}，测量处于停止状态")

    def _disconnect(self) -> None:
        self.worker.close()
        self._set_measurement_mode("paused")
        self.connection_button.configure(text="打开串口", style="Primary.TButton")
        self.baud_box.configure(state="readonly")
        self.refresh_button.configure(state="normal")
        self.status_dot.configure(fg="#90A4B7")
        self.status_var.set("串口已关闭")
        self.refresh_ports(silent=True)

    def send_student_id(self) -> None:
        self._send(make_command("ID", STUDENT_ID), f"发送学号：{STUDENT_ID}")

    def single_measure(self) -> None:
        """只显示下一条新距离，然后自动恢复停止状态。"""
        if not self.worker.is_open:
            messagebox.showwarning("单次测距", "请先打开串口")
            return
        self.worker.clear_input()
        self._set_measurement_mode("single")
        # 先停止可能仍在运行的连续模式，再请求一条新数据。
        payload = make_command("STOP") + make_command("MEASURE")
        if not self._send(payload, "控制命令：切换为单次测距 (STOP + MEASURE)"):
            self._set_measurement_mode("paused")

    def start_continuous(self) -> None:
        if not self.worker.is_open:
            messagebox.showwarning("连续测量", "请先打开串口")
            return
        self.worker.clear_input()
        self._set_measurement_mode("continuous")
        if not self._send(make_command("START"), "控制命令：开始连续测量 (START)"):
            self._set_measurement_mode("paused")

    def stop_continuous(self) -> None:
        """先停止界面接收，再通知 Arduino 停止发送。"""
        self._set_measurement_mode("paused")
        if not self.worker.is_open:
            self.status_var.set("测量已停止；串口当前未连接")
            return
        self._send(make_command("STOP"), "控制命令：停止连续测量 (STOP)")
        self.status_var.set("连续测量已停止，后续距离数据不再显示")

    def _set_measurement_mode(self, mode: str) -> None:
        self.measurement_mode = mode
        labels = {
            "paused": "测量状态：已停止",
            "single": "测量状态：等待单次结果…",
            "continuous": "测量状态：连续测量中",
        }
        self.mode_var.set(labels[mode])
        if hasattr(self, "single_button"):
            self.single_button.configure(style="Primary.TButton" if mode == "single" else "Secondary.TButton")
            self.continuous_button.configure(style="Primary.TButton" if mode == "continuous" else "Secondary.TButton")
            self.stop_button.configure(style="Danger.TButton" if mode == "paused" else "Secondary.TButton")

    def _send(self, payload: bytes, log_message: str) -> bool:
        try:
            self.worker.send(payload)
        except RuntimeError as exc:
            messagebox.showwarning("发送失败", str(exc))
            return False
        except Exception as exc:
            messagebox.showerror("发送失败", str(exc))
            return False
        self._append_log(self.send_text, log_message)
        self.status_var.set("数据发送成功")
        return True

    def _process_inbox(self) -> None:
        try:
            while True:
                kind, payload = self.inbox.get_nowait()
                if kind == "data":
                    self._handle_received(str(payload))
                elif kind == "error":
                    self._append_log(self.receive_text, f"[串口错误] {payload}")
                    self._disconnect()
                    messagebox.showerror("串口通信中断", str(payload))
        except queue.Empty:
            pass
        self.after(self.POLL_INTERVAL_MS, self._process_inbox)

    def _handle_received(self, message: str) -> None:
        parsed = parse_distance(message)
        if parsed:
            # Arduino 即使仍在持续上传，暂停模式也会丢弃距离，接收窗口不会再刷新。
            if self.measurement_mode == "paused":
                return
            value, unit = parsed
            self.distance_var.set(f"{value:g}")
            self.distance_unit_var.set(unit)
            self._append_log(self.receive_text, f"距离：{value:g} {unit}    原始数据：{message}")
            if self.measurement_mode == "single":
                self._set_measurement_mode("paused")
                self.status_var.set("单次测距完成，已自动停止接收")
            else:
                self.status_var.set("连续测量中：已接收距离数据")
        else:
            self._append_log(self.receive_text, f"消息：{message}")

    @staticmethod
    def _append_log(widget: tk.Text, message: str) -> None:
        widget.insert("end", f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        widget.see("end")

    @staticmethod
    def _clear_text(widget: tk.Text) -> None:
        widget.delete("1.0", "end")

    def _on_close(self) -> None:
        self.worker.close()
        self.destroy()


if __name__ == "__main__":
    ArduinoSerialApp().mainloop()
