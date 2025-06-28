import serial
import time
from datetime import datetime

# Configuração da porta serial UART na Toradex Verdin
# Conforme o exemplo, a porta é /dev/verdin-uart1
SERIAL_PORT = "/dev/verdin-uart1"
BAUD_RATE = 9600 # Deve ser o mesmo que o do Raspberry Pi

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, 8, 'N', 1, timeout=1)
    print(f"UART configurada e aberta na porta {SERIAL_PORT} com baud rate {BAUD_RATE}")

    while True:
        data = ser.readline()
        if data:
            data = data.decode("utf-8", "ignore").rstrip()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"{timestamp}: string recebida: '{data}'")
        time.sleep(0.1) # Pequena pausa para evitar consumo excessivo de CPU

except serial.SerialException as e:
    print(f"Erro ao abrir ou usar a porta serial: {e}")
    print(f"Verifique se a porta serial '{SERIAL_PORT}' existe e se o contêiner Docker tem permissões para acessá-la.")
except KeyboardInterrupt:
    print("Recepção interrompida pelo usuário.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Porta serial fechada.")