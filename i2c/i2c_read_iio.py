import time
import os
import sys # Importar sys para saída de erro

# Caminho exato para o seu dispositivo ADS1115/ADS1015 IIO
ADS1115_IIO_PATH = "/sys/bus/iio/devices/iio:device0"

# O nome do dispositivo, para depuração (opcional)
DEVICE_NAME_FILE = os.path.join(ADS1115_IIO_PATH, "name")

# Caminhos para os arquivos de leitura de dados e escala
RAW_CHANNEL_0 = os.path.join(ADS1115_IIO_PATH, "in_voltage0_raw")
RAW_CHANNEL_1 = os.path.join(ADS1115_IIO_PATH, "in_voltage1_raw")
SCALE_FILE = os.path.join(ADS1115_IIO_PATH, "in_voltage0_scale")

def debug_print(message):
    print(f"DEBUG: {message}", file=sys.stderr) # Imprimir para stderr para garantir visibilidade

debug_print("Iniciando script i2c_read_iio.py")

# Verificar se os arquivos e o dispositivo existem
if not os.path.exists(ADS1115_IIO_PATH):
    debug_print(f"ERROR: Dispositivo IIO {ADS1115_IIO_PATH} não encontrado. Saindo.")
    sys.exit(1)

debug_print(f"Caminho do dispositivo IIO encontrado: {ADS1115_IIO_PATH}")

if not os.path.exists(RAW_CHANNEL_0):
    debug_print(f"ERROR: Arquivo de leitura 'raw' para canal 0 não encontrado: {RAW_CHANNEL_0}. Saindo.")
    sys.exit(1)
if not os.path.exists(RAW_CHANNEL_1):
    debug_print(f"ERROR: Arquivo de leitura 'raw' para canal 1 não encontrado: {RAW_CHANNEL_1}. Saindo.")
    sys.exit(1)
if not os.path.exists(SCALE_FILE):
    debug_print(f"ERROR: Arquivo de escala '{SCALE_FILE}' não encontrado. Saindo.")
    sys.exit(1)

debug_print("Todos os arquivos IIO necessários parecem existir.")

# Ler o fator de escala UMA VEZ ao iniciar o programa
scale_factor_uv_per_lsb = 0.0
device_name = "desconhecido"

try:
    with open(SCALE_FILE, "r") as f:
        scale_factor_uv_per_lsb = float(f.read().strip())
    debug_print(f"Fator de escala lido: {scale_factor_uv_per_lsb} uV/LSB")
    
    with open(DEVICE_NAME_FILE, "r") as f:
        device_name = f.read().strip()
    debug_print(f"Nome do dispositivo IIO: {device_name}")

except Exception as e:
    debug_print(f"ERROR: Erro ao ler o fator de escala ou nome do dispositivo: {e}. Saindo.")
    sys.exit(1)

def read_ads1115_channel(raw_file_path):
    try:
        with open(raw_file_path, "r") as f:
            raw_value = int(f.read().strip())
        
        voltage = (raw_value * scale_factor_uv_per_lsb) / 1000000.0 # Converte uV para V
        return voltage

    except Exception as e:
        debug_print(f"ERROR: Erro ao ler canal {raw_file_path} via IIO: {e}")
        return 0.0

debug_print("Entrando no loop principal de leitura...")

# Loop principal para ler os canais A0 e A1
try:
    while True:
        voltage0 = read_ads1115_channel(RAW_CHANNEL_0)  # Canal A0
        voltage1 = read_ads1115_channel(RAW_CHANNEL_1)  # Canal A1 (se conectado)

        hora_atual = time.strftime("%H:%M:%S", time.localtime())
        print(f"{hora_atual}")
        print(f"A0: {voltage0:.3f} V, A1: {voltage1:.3f} V")        
        print("---")
        time.sleep(2)
except KeyboardInterrupt:
    debug_print("Programa encerrado pelo usuário (KeyboardInterrupt).")
except Exception as e:
    debug_print(f"Um erro inesperado ocorreu no loop principal: {e}")
    sys.exit(1) # Sai com erro se houver outro tipo de exceção
finally:
    debug_print("Script finalizado.")
