import serial
import time
from datetime import datetime
import gpiod
import sys
import select

# --- Configuração UART Toradex ---
SERIAL_PORT = "/dev/verdin-uart1"
BAUD_RATE = 9600

# --- Configuração GPIO Toradex (OUTPUTS) ---
# VOCÊ PRECISA AJUSTAR ESTES VALORES PARA SEU VERDIN ESPECÍFICO!
# Use o script main.py (o exemplo que você forneceu) para listar os chips e linhas e encontrar os offsets corretos.
GPIO_CHIP = "/dev/gpiochip0" # Ex: /dev/gpiochip0, /dev/gpiochip1, etc.
# Mapeamento para os pinos GPIO 27, 28, 29, 30 no seu Verdin (offfsets de linha)
# Estes são os OFFSETS DENTRO DO GPIO_CHIP que serão SAÍDAS.
GPIO_LINE_OFFSETS = {
    1: 0, # Tecla '1' controla GPIO 27 (Saída Toradex)
    2: 1, # Tecla '2' controla GPIO 28 (Saída Toradex)
    3: 5, # Tecla '3' controla GPIO 29 (Saída Toradex)
    4: 6  # Tecla '4' controla GPIO 30 (Saída Toradex)
}

# Estado inicial dos pinos (desligados)
# Não precisamos mais armazenar os estados para transmitir, apenas para controlar localmente
current_gpio_output_states = {offset: gpiod.line.Value.INACTIVE for offset in GPIO_LINE_OFFSETS.values()}

# Função para configurar e controlar o GPIO
def setup_gpios():
    chip = None
    try:
        chip = gpiod.Chip(GPIO_CHIP)
        requests = {}
        for line_offset in GPIO_LINE_OFFSETS.values():
            requests[line_offset] = gpiod.LineSettings(
                direction=gpiod.line.Direction.OUTPUT,
                output_value=gpiod.line.Value.INACTIVE # Inicia desligado
            )
        
        return chip, gpiod.request_lines(
            GPIO_CHIP,
            consumer="TORADEX_GPIO_APP",
            config=requests
        )
    except Exception as e:
        print(f"Erro ao configurar GPIOs: {e}")
        if chip:
            chip.close()
        return None, None

ser = None
gpio_chip = None
gpio_request = None

try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, 8, 'N', 1, timeout=0.1) # timeout menor para não bloquear
    print(f"UART configurada e aberta na porta {SERIAL_PORT} com baud rate {BAUD_RATE}")

    gpio_chip, gpio_request_context = setup_gpios()
    if gpio_chip is None or gpio_request_context is None:
        raise Exception("Falha ao configurar GPIOs. Saindo.")
    
    with gpio_request_context as request:
        print("GPIOs da Toradex configuradas. Pressione 1-4 para ligar/desligar um pino.")
        print("Pressione 'q' para sair.")

        while True:
            # --- Leitura do Teclado para Controlar GPIOs da Toradex ---
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                char_input = sys.stdin.read(1).strip()
                if char_input in ['1', '2', '3', '4']:
                    pin_num_selected = int(char_input)
                    if pin_num_selected in GPIO_LINE_OFFSETS:
                        line_offset_to_control = GPIO_LINE_OFFSETS[pin_num_selected]
                        
                        # Inverte o estado do pino de saída da Toradex
                        current_state = current_gpio_output_states[line_offset_to_control]
                        new_state = gpiod.line.Value.ACTIVE if current_state == gpiod.line.Value.INACTIVE else gpiod.line.Value.INACTIVE
                        
                        request.set_value(line_offset_to_control, new_state)
                        current_gpio_output_states[line_offset_to_control] = new_state
                        
                        status_str = "LIGADO" if new_state == gpiod.line.Value.ACTIVE else "DESLIGADO"
                        print(f"Pino GPIO {line_offset_to_control} (tecla {pin_num_selected}) da Toradex {status_str}.")
                    else:
                        print(f"Pino {char_input} não mapeado para um offset de linha GPIO na Toradex.")
                elif char_input == 'q':
                    print("Saindo...")
                    break
            
            # --- Leitura da UART (vindo do Raspberry Pi) ---
            data_byte = ser.read(1) # Lê 1 byte
            if data_byte:
                int_value = int.from_bytes(data_byte, 'big')
                # Converte para string de bits, preenchendo com zeros à esquerda para ter 4 bits
                bit_string = bin(int_value)[2:].zfill(4)
                
                # Assume que a ordem dos bits é P35 (bit 3), P36 (bit 2), P37 (bit 1), P38 (bit 0)
                formatted_bits = f"{bit_string[0]} {bit_string[1]} {bit_string[2]} {bit_string[3]}"
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"{timestamp}: Raspberry Pi GPIOs (35-38) recebidas via UART: {formatted_bits}")
            
            time.sleep(0.05) # Pequena pausa para evitar consumo excessivo de CPU

except serial.SerialException as e:
    print(f"Erro ao abrir ou usar a porta serial: {e}")
    print(f"Verifique se a porta serial '{SERIAL_PORT}' existe e se o contêiner Docker tem permissões para acessá-la.")
except Exception as e:
    print(f"Ocorreu um erro: {e}")
except KeyboardInterrupt:
    print("Recepção interrompida pelo usuário.")
finally:
    if 'ser' in locals() and ser.is_open:
        ser.close()
        print("Porta serial fechada.")
    if gpio_chip:
        gpio_chip.close()
        print("GPIO chip fechado.")
    print("Programa encerrado.")