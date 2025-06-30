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
GPIO_CHIP = "/dev/gpiochip0" 
GPIO_LINE_OFFSETS = {
    1: 0, # Tecla '1' controla o offset de linha 0 (Tool changer)
    2: 1, # Tecla '2' controla o offset de linha 1 (Vácuo inferior)
    3: 5, # Tecla '3' controla o offset de linha 5 (Cilindro)
    4: 6  # Tecla '4' controla o offset de linha 6 (Vácuo superior)
}

# Dicionário para rastrear os estados lógicos (ACTIVE/INACTIVE) das GPIOs da Toradex
current_gpio_output_states = {offset: gpiod.line.Value.INACTIVE for offset in GPIO_LINE_OFFSETS.values()}

# Dicionários para manter o estado descritivo para cada componente
COMPONENT_STATUS = {
    GPIO_LINE_OFFSETS[1]: { # Tool Changer (não tem estado transiente)
        gpiod.line.Value.INACTIVE: "TRAVADO",
        gpiod.line.Value.ACTIVE: "DESTRAVADO"
    },
    GPIO_LINE_OFFSETS[2]: { # Vácuo Inferior
        "OFF": "DESLIGADO",
        "PENDING_ON": "LIGANDO",
        "ON": "LIGADO"
    },
    GPIO_LINE_OFFSETS[3]: { # Cilindro
        "RETRACTED": "RETORNADO",
        "PENDING_EXTEND": "AVANÇANDO",
        "EXTENDED": "AVANÇADO",
        "PENDING_RETRACT": "RETORNANDO"
    },
    GPIO_LINE_OFFSETS[4]: { # Vácuo Superior
        "OFF": "DESLIGADO",
        "PENDING_ON": "LIGANDO",
        "ON": "LIGADO"
    }
}

# Variáveis para rastrear o estado interno de cada componente (além do estado da GPIO)
tool_changer_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[1]][gpiod.line.Value.INACTIVE]
vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["OFF"]
cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["RETRACTED"]
vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["OFF"]

# --- Configuração de Frequência de Impressão ---
DISPLAY_UPDATE_INTERVAL_SECONDS = 1 

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
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, 8, 'N', 1, timeout=0.1)
    print(f"UART configurada e aberta na porta {SERIAL_PORT} com baud rate {BAUD_RATE}")

    gpio_chip, gpio_request_context = setup_gpios()
    if gpio_chip is None or gpio_request_context is None:
        raise Exception("Falha ao configurar GPIOs. Saindo.")
    
    with gpio_request_context as request:
        print("Controle de Atuadores. Pressione:")
        print("1 - Tool Changer (TRAVAR/DESTRAVAR)")
        print("2 - Vácuo Inferior (LIGAR/DESLIGAR)")
        print("3 - Cilindro (AVANÇAR/RETORNAR)")
        print("4 - Vácuo Superior (LIGAR/DESLIGAR)")
        print("Pressione 'q' para sair.")

        last_display_update_time = time.time() 

        while True:
            current_loop_time = time.time() 

            # --- Leitura do Teclado para Controlar GPIOs da Toradex ---
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                char_input = sys.stdin.read(1).strip()
                if char_input in ['1', '2', '3', '4']:
                    pin_num_selected = int(char_input)
                    line_offset_to_control = GPIO_LINE_OFFSETS.get(pin_num_selected)
                    
                    if line_offset_to_control is not None:
                        # Inverte o estado lógico da GPIO
                        current_gpio_state = current_gpio_output_states[line_offset_to_control]
                        new_gpio_state = gpiod.line.Value.ACTIVE if current_gpio_state == gpiod.line.Value.INACTIVE else gpiod.line.Value.INACTIVE
                        
                        request.set_value(line_offset_to_control, new_gpio_state)
                        current_gpio_output_states[line_offset_to_control] = new_gpio_state
                        
                        # ATUALIZAÇÃO IMEDIATA DO ESTADO INTERNO PARA O ESTADO PENDENTE/COMANDO ENVIADO
                        if pin_num_selected == 1: 
                            tool_changer_internal_state = COMPONENT_STATUS[line_offset_to_control][new_gpio_state]
                            print(f"Tool Changer: {tool_changer_internal_state} (comando enviado)")
                        elif pin_num_selected == 2:
                            vac_inferior_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_ON"] if new_gpio_state == gpiod.line.Value.ACTIVE else COMPONENT_STATUS[line_offset_to_control]["OFF"]
                            print(f"Vácuo Inferior: {vac_inferior_internal_state} (comando enviado)")
                        elif pin_num_selected == 3:
                            if new_gpio_state == gpiod.line.Value.ACTIVE:
                                cilindro_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_EXTEND"]
                            else:
                                cilindro_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_RETRACT"]
                            print(f"Cilindro: {cilindro_internal_state} (comando enviado)")
                        elif pin_num_selected == 4:
                            vac_superior_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_ON"] if new_gpio_state == gpiod.line.Value.ACTIVE else COMPONENT_STATUS[line_offset_to_control]["OFF"]
                            print(f"Vácuo Superior: {vac_superior_internal_state} (comando enviado)")
                    else:
                        print(f"Pino {char_input} não mapeado para uma função.")
                elif char_input == 'q':
                    print("Saindo...")
                    break
                
            # --- Leitura da UART (vindo do Raspberry Pi) ---
            data_byte = ser.read(1) # Lê 1 byte
            if data_byte:
                int_value = int.from_bytes(data_byte, 'big')
                bit_string = bin(int_value)[2:].zfill(4)
                
                # Mapeia os bits recebidos para o feedback de status
                tool_changer_feedback_bit = bit_string[0] 
                vac_inferior_feedback_bit = bit_string[1] 
                cilindro_feedback_bit = bit_string[2] 
                vac_superior_feedback_bit = bit_string[3] 

                # Atualiza os estados internos baseados no feedback (estado final)
                tool_changer_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[1]][gpiod.line.Value.ACTIVE] if tool_changer_feedback_bit == '1' else COMPONENT_STATUS[GPIO_LINE_OFFSETS[1]][gpiod.line.Value.INACTIVE]

                # Vácuo Inferior
                if vac_inferior_feedback_bit == '1': # Se o feedback é '1', está LIGADO
                    vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["ON"]
                elif vac_inferior_feedback_bit == '0': # Se o feedback é '0'
                    # Se o comando Toradex para o Vácuo Inferior está DESATIVO (LOW)
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[2]] == gpiod.line.Value.INACTIVE:
                        vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["OFF"]
                    # Else (comando ainda ATIVO e feedback 0): Mantenha PENDING_ON (pois ainda está esperando o 1)
                    elif vac_inferior_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["PENDING_ON"]:
                        pass 
                    # Else (qualquer outro caso para feedback 0, teoricamente não deveria acontecer se o fluxo estiver correto)
                    # vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["OFF"] # Como fallback

                # Cilindro
                if cilindro_feedback_bit == '1': # Se o feedback é '1', está AVANÇADO
                    cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["EXTENDED"]
                elif cilindro_feedback_bit == '0': # Se o feedback é '0'
                    # Se o comando Toradex para o Cilindro está DESATIVO (LOW)
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[3]] == gpiod.line.Value.INACTIVE:
                        cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["RETRACTED"]
                    # Else (comando ainda ATIVO/INATIVO e estado PENDING): Mantenha PENDING
                    elif cilindro_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["PENDING_EXTEND"] or \
                         cilindro_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["PENDING_RETRACT"]:
                        pass
                    # Else (qualquer outro caso para feedback 0)
                    # cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["RETRACTED"] # Como fallback

                # Vácuo Superior
                if vac_superior_feedback_bit == '1': # Se o feedback é '1', está LIGADO
                    vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["ON"]
                elif vac_superior_feedback_bit == '0': # Se o feedback é '0'
                    # Se o comando Toradex para o Vácuo Superior está DESATIVO (LOW)
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[4]] == gpiod.line.Value.INACTIVE:
                        vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["OFF"]
                    # Else (comando ainda ATIVO e feedback 0): Mantenha PENDING_ON
                    elif vac_superior_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["PENDING_ON"]:
                        pass
                    # Else (qualquer outro caso para feedback 0)
                    # vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["OFF"] # Como fallback


            # Imprime o status atual APENAS se o intervalo de tempo passou
            if (current_loop_time - last_display_update_time) >= DISPLAY_UPDATE_INTERVAL_SECONDS:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n{timestamp}: Status Atual:")
                print(f"Tool changer: {tool_changer_internal_state}")
                print(f"Vácuo inferior: {vac_inferior_internal_state}")
                print(f"Cilindro: {cilindro_internal_state}")
                print(f"Vácuo superior: {vac_superior_internal_state}")
                last_display_update_time = current_loop_time 
                
            time.sleep(0.05) 

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