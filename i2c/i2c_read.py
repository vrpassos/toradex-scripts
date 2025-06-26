import time
import smbus2

# Configurações do ADS1115
I2C_BUS = 3
ADS1115_ADDRESS = 0x48  # Endereço ajustado para 0x48
CONFIG_REG = 0x01
CONVERSION_REG = 0x00

# Inicializar o barramento I2C
# try:
#     time.sleep(2)
#     #bus = smbus2.SMBus(I2C_BUS)    
#     print(f"DEBUG: Barramento I2C {I2C_BUS} inicializado com sucesso.")
# except Exception as e:
#     print(f"ERROR: Erro ao inicializar o barramento I2C: {e}")
#     exit(1) # Sair com código de erro

try:
    time.sleep(2)    
    bus = smbus2.SMBus('/dev/i2c-3')
    print(f"DEBUG: Barramento I2C {I2C_BUS} inicializado com sucesso.")
except Exception as e:
    print(f"ERROR: Erro ao inicializar o barramento I2C: {e}")
    exit(1) # Sair com código de erro

def read_ads1115(channel):
    config = 0xC183 | (channel << 12)  # Config: single-shot, 4.096V, 860SPS
    try:
        bus.write_i2c_block_data(ADS1115_ADDRESS, CONFIG_REG, [(config >> 8) & 0xFF, config & 0xFF])
    except Exception as e: # Capture a exceção específica
        print(f"Erro ao escrever no ADS1115: {e}") # Imprima a mensagem de erro
        return 0 # Ou algum valor de erro para indicar falha
    time.sleep(0.01)  # Aguardar conversão
    
    # ----- Ponto Crucial: Selecionar o registro de leitura ANTES de ler -----
    # O ADS1115 usa um ponteiro. Primeiro, enviamos o endereço do registro que queremos ler.
    try:
        bus.write_byte(ADS1115_ADDRESS, CONVERSION_REG) # Envia o endereço do registro de conversão para o ponteiro
    except Exception as e:
        print(f"Erro ao selecionar o registrador de conversão no ADS1115: {e}")
        return 0
    
    try:
        # Agora, lemos 2 bytes do registrador de conversão
        data = bus.read_i2c_block_data(ADS1115_ADDRESS, CONVERSION_REG, 2) # O CONVERSION_REG aqui pode ser ignorado por alguns drivers, mas é boa prática manter.
    except Exception as e:
        print(f"Erro ao ler do ADS1115 (data): {e}")
        return 0
    
    raw = (data[0] << 8) | data[1]
    if raw & 0x8000:  # Conversão para número com sinal
        raw -= 65536
    voltage = raw * 4.096 / 32768  # Escala para volts (FSR = 4.096V)
    return voltage

# Loop para ler os canais A0 e A1
try:
    while True:
        voltage1 = read_ads1115(0)  # Canal A0
        voltage2 = read_ads1115(1)  # Canal A1
        hora_atual = time.strftime("%H:%M:%S", time.localtime())
        print(f"{hora_atual}")
        print(f"A0: {voltage1:.3f} V, A1: {voltage2:.3f} V")        
        print("---")
        time.sleep(2)
except KeyboardInterrupt:
    print("Programa encerrado pelo usuário")
finally:
    bus.close()  # Fechar o barramento I2C apenas ao encerrar