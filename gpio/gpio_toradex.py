import serial
import time
from datetime import datetime
import gpiod
import sys # Para ler entrada do teclado de forma não bloqueante

# --- Configuração UART Toradex ---
SERIAL_PORT = "/dev/verdin-uart1"
BAUD_RATE = 9600

# --- Configuração GPIO Toradex ---
# VOCÊ PRECISA AJUSTAR ESTES VALORES PARA SEU VERDIN ESPECÍFICO!
# Use o script main.py para listar os chips e linhas e encontrar os offsets corretos.
GPIO_CHIP = "/dev/gpiochip0" # Ex: /dev/gpiochip0, /dev/gpiochip1, etc.
# Mapeamento para os pinos GPIO 27, 28, 29, 30 no seu Verdin (offfsets de linha)
GPIO_LINE_OFFSETS = {
    1: 27, # Corresponde ao pino 27 da Verdin (input 1 no teclado)
    2: 28, # Corresponde ao pino 28 da Verdin (input 2 no teclado)
    3: 29, # Corresponde ao pino 29 da Verdin (input 3 no teclado)
    4: 30  # Corresponde ao pino 30 da Verdin (input 4 no teclado)
}

# Estado inicial dos pinos (desligados)
current_gpio_states = {offset: gpiod.line.Value.INACTIVE for offset in GPIO_LINE_OFFSETS.values()}

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
        
        # Use gpiod.request_lines como um gerenciador de contexto para garantir limpeza
        # Esta é uma abordagem para gerenciar múltiplas linhas juntas.
        # Se preferir controle individual, pode abrir e fechar a cada alteração, mas não é ideal.
        # Para este caso, vamos gerenciar um request globalmente.
        return chip, gpiod.request_lines(
            GPIO_CHIP,
            consumer="UART_GPIO_APP",
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
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, 8, 'N', 1, timeout=0.1) # timeout menor para não bloquear a leitura do teclado
    print(f"UART configurada e aberta na porta {SERIAL_PORT} com baud rate {BAUD_RATE}")

    gpio_chip, gpio_request_context = setup_gpios()
    if gpio_chip is None or gpio_request_context is None:
        raise Exception("Falha ao configurar GPIOs. Saindo.")
    
    # Entra no contexto de request das linhas GPIO
    with gpio_request_context as request:
        print("GPIOs configuradas. Pressione 1-4 para ligar/desligar um pino.")
        print("Pressione 'q' para sair.")

        while True:
            # --- Leitura da UART ---
            data_byte = ser.read(1) # Lê 1 byte
            if data_byte:
                # Decodifica o byte para 4 bits
                int_value = int.from_bytes(data_byte, 'big')
                # Converte para string de bits, preenchendo com zeros à esquerda para ter 4 bits
                bit_string = bin(int_value)[2:].zfill(4)
                
                # Formata a saída
                formatted_bits = ' '.join(list(bit_string))
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"{timestamp}: pin Raspberry Pi (35-38): {formatted_bits}")

            # --- Leitura do Teclado ---
            if sys.stdin in sys.stdin.select([sys.stdin], [], [], 0)[0]:
                char_input = sys.stdin.read(1).strip()
                if char_input in ['1', '2', '3', '4']:
                    pin_num_selected = int(char_input)
                    if pin_num_selected in GPIO_LINE_OFFSETS:
                        line_offset_to_control = GPIO_LINE_OFFSETS[pin_num_selected]
                        
                        # Inverte o estado do pino
                        current_state = current_gpio_states[line_offset_to_control]
                        new_state = gpiod.line.Value.ACTIVE if current_state == gpiod.line.Value.INACTIVE else gpiod.line.Value.INACTIVE
                        
                        request.set_value(line_offset_to_control, new_state)
                        current_gpio_states[line_offset_to_control] = new_state
                        
                        status_str = "LIGADO" if new_state == gpiod.line.Value.ACTIVE else "DESLIGADO"
                        print(f"Pino GPIO {line_offset_to_control} ({pin_num_selected}) na Toradex {status_str}.")
                    else:
                        print(f"Pino {char_input} não mapeado.")
                elif char_input == 'q':
                    print("Saindo...")
                    break
                
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
        gpio_chip.close() # Libera o chip GPIO
        print("GPIO chip fechado.")
    print("Programa encerrado.")