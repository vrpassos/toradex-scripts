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

# --- Inicializa a flag should_print_status ---
should_print_status = False

# --- NOVAS CONSTANTES PARA TIMEOUT E REENVIO ---
COMMAND_TIMEOUT_SECONDS = 5  # Tempo limite para o sensor responder
RETRY_DELAY_SECONDS = 1      # Tempo para aguardar antes de reenviar o comando

# Dicionário para rastrear o estado de cada comando que PRECISA de feedback
# A chave é o offset da GPIO, o valor é um dicionário com:
# 'pending': True se um comando foi enviado e estamos aguardando feedback
# 'start_time': Timestamp de quando o comando foi enviado
# 'original_command_type': 'ACTIVE' or 'INACTIVE' - stores the state that was initially commanded to retry later
command_states = {
    GPIO_LINE_OFFSETS[2]: {'pending': False, 'start_time': None, 'original_command_type': None}, # Vácuo Inferior
    GPIO_LINE_OFFSETS[3]: {'pending': False, 'start_time': None, 'original_command_type': None}, # Cilindro
    GPIO_LINE_OFFSETS[4]: {'pending': False, 'start_time': None, 'original_command_type': None}  # Vácuo Superior
}

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

        # Função local para evitar repetição no print de status
        def print_current_status_to_console():
            print(f"Tool changer: {tool_changer_internal_state}")
            print(f"Vácuo inferior: {vac_inferior_internal_state}")
            print(f"Cilindro: {cilindro_internal_state}")
            print(f"Vácuo superior: {vac_superior_internal_state}")

        # Imprime o status inicial uma vez
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n{timestamp}: Status Inicial:")
        print_current_status_to_console()

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

                        # Set GPIO state
                        request.set_value(line_offset_to_control, new_gpio_state)
                        current_gpio_output_states[line_offset_to_control] = new_gpio_state

                        # ATUALIZAÇÃO IMEDIATA DO ESTADO INTERNO PARA O ESTADO PENDENTE/COMANDO ENVIADO
                        if pin_num_selected == 1:
                            tool_changer_internal_state = COMPONENT_STATUS[line_offset_to_control][new_gpio_state]
                            print(f"Tool Changer: {tool_changer_internal_state} (comando enviado)")
                            # Tool Changer doesn't have sensor feedback, so no timeout needed
                            if line_offset_to_control in command_states: # Ensure it's reset if it was somehow pending
                                command_states[line_offset_to_control]['pending'] = False
                                command_states[line_offset_to_control]['original_command_type'] = None # Clear original command type
                        elif pin_num_selected in [2, 3, 4]: # These require sensor feedback
                            state_entry = command_states[line_offset_to_control]

                            if new_gpio_state == gpiod.line.Value.ACTIVE: # Only start timeout for "turn on" commands
                                state_entry['pending'] = True
                                state_entry['start_time'] = current_loop_time
                                state_entry['original_command_type'] = gpiod.line.Value.ACTIVE # Store original command
                                if pin_num_selected == 2:
                                    vac_inferior_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_ON"]
                                    print(f"Vácuo Inferior: {vac_inferior_internal_state} (comando enviado)")
                                elif pin_num_selected == 3:
                                    cilindro_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_EXTEND"]
                                    print(f"Cilindro: {cilindro_internal_state} (comando enviado)")
                                elif pin_num_selected == 4:
                                    vac_superior_internal_state = COMPONENT_STATUS[line_offset_to_control]["PENDING_ON"]
                                    print(f"Vácuo Superior: {vac_superior_internal_state} (comando enviado)")
                            else: # Command to turn OFF/RETRACT - no pending feedback expected for retry
                                state_entry['pending'] = False
                                state_entry['original_command_type'] = gpiod.line.Value.INACTIVE # Store original command
                                if pin_num_selected == 2:
                                    vac_inferior_internal_state = COMPONENT_STATUS[line_offset_to_control]["OFF"]
                                    print(f"Vácuo Inferior: {vac_inferior_internal_state} (comando enviado)")
                                elif pin_num_selected == 3:
                                    cilindro_internal_state = COMPONENT_STATUS[line_offset_to_control]["RETRACTED"] # Changed to RETRACTED directly
                                    print(f"Cilindro: {cilindro_internal_state} (comando enviado)")
                                elif pin_num_selected == 4:
                                    vac_superior_internal_state = COMPONENT_STATUS[line_offset_to_control]["OFF"]
                                    print(f"Vácuo Superior: {vac_superior_internal_state} (comando enviado)")

                        # Sinaliza para imprimir o status após o comando do teclado
                        should_print_status = True
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

                # ATENÇÃO: Armazena o estado ANTIGO das variáveis INTERNAS antes de atualizá-las
                old_tool_changer_state = tool_changer_internal_state
                old_vac_inferior_state = vac_inferior_internal_state
                old_cilindro_state = cilindro_internal_state
                old_vac_superior_state = vac_superior_internal_state

                # Mapeia os bits recebidos para o feedback de status
                tool_changer_feedback_bit = bit_string[0]
                vac_inferior_feedback_bit = bit_string[1]
                cilindro_feedback_bit = bit_string[2]
                vac_superior_feedback_bit = bit_string[3]


                # Atualiza os estados internos baseados no feedback (estado final)
                tool_changer_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[1]][gpiod.line.Value.ACTIVE] if tool_changer_feedback_bit == '1' else COMPONENT_STATUS[GPIO_LINE_OFFSETS[1]][gpiod.line.Value.INACTIVE]

                # Vácuo Inferior
                if vac_inferior_feedback_bit == '1':
                    if command_states[GPIO_LINE_OFFSETS[2]]['pending']:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Vácuo Inferior: Sensor confirmou acionamento.")
                    vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["ON"]
                    command_states[GPIO_LINE_OFFSETS[2]]['pending'] = False # Feedback received, clear pending
                elif vac_inferior_feedback_bit == '0':
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[2]] == gpiod.line.Value.INACTIVE:
                        vac_inferior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["OFF"]
                        command_states[GPIO_LINE_OFFSETS[2]]['pending'] = False # If command is OFF, clear pending
                    elif vac_inferior_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[2]]["PENDING_ON"]:
                        pass # Still pending, waiting for sensor HIGH

                # Cilindro
                if cilindro_feedback_bit == '1':
                    if command_states[GPIO_LINE_OFFSETS[3]]['pending']:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Cilindro: Sensor confirmou acionamento.")
                    cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["EXTENDED"]
                    command_states[GPIO_LINE_OFFSETS[3]]['pending'] = False # Feedback received, clear pending
                elif cilindro_feedback_bit == '0':
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[3]] == gpiod.line.Value.INACTIVE:
                        cilindro_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["RETRACTED"]
                        command_states[GPIO_LINE_OFFSETS[3]]['pending'] = False # If command is OFF, clear pending
                    elif cilindro_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["PENDING_EXTEND"] or \
                         cilindro_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[3]]["PENDING_RETRACT"]:
                        pass # Still pending, waiting for sensor HIGH or LOW based on original command

                # Vácuo Superior
                if vac_superior_feedback_bit == '1':
                    if command_states[GPIO_LINE_OFFSETS[4]]['pending']:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Vácuo Superior: Sensor confirmou acionamento.")
                    vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["ON"]
                    command_states[GPIO_LINE_OFFSETS[4]]['pending'] = False # Feedback received, clear pending
                elif vac_superior_feedback_bit == '0':
                    if current_gpio_output_states[GPIO_LINE_OFFSETS[4]] == gpiod.line.Value.INACTIVE:
                        vac_superior_internal_state = COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["OFF"]
                        command_states[GPIO_LINE_OFFSETS[4]]['pending'] = False # If command is OFF, clear pending
                    elif vac_superior_internal_state == COMPONENT_STATUS[GPIO_LINE_OFFSETS[4]]["PENDING_ON"]:
                        pass # Still pending, waiting for sensor HIGH

                # NOVO: Verifica se qualquer estado interno mudou APÓS o processamento do feedback UART
                # Isso deve ser feito APÓS TODAS as variáveis internas serem atualizadas
                if (tool_changer_internal_state != old_tool_changer_state or
                    vac_inferior_internal_state != old_vac_inferior_state or
                    cilindro_internal_state != old_cilindro_state or
                    vac_superior_internal_state != old_vac_superior_state):
                    should_print_status = True # Sinaliza para imprimir o status

            # --- Lógica de Timeout e Reenvio ---
            for line_offset, state in command_states.items():
                if state['pending']: # Only process if a command is pending feedback
                    # Check for Timeout
                    if (current_loop_time - state['start_time']) >= COMMAND_TIMEOUT_SECONDS:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        component_name = ""
                        if line_offset == GPIO_LINE_OFFSETS[2]:
                            component_name = "Vácuo Inferior"
                        elif line_offset == GPIO_LINE_OFFSETS[3]:
                            component_name = "Cilindro"
                        elif line_offset == GPIO_LINE_OFFSETS[4]:
                            component_name = "Vácuo Superior"

                        print(f"\n[{timestamp}] TIMEOUT: {component_name} não respondeu após {COMMAND_TIMEOUT_SECONDS}s.")
                        sys.stdout.flush()

                        # --- First part: Reset the bit to zero ---
                        print(f"[{timestamp}] DEBUG: Setting GPIO {line_offset} to INACTIVE (0) for reset.")
                        request.set_value(line_offset, gpiod.line.Value.INACTIVE)
                        current_gpio_output_states[line_offset] = gpiod.line.Value.INACTIVE

                        # IMPORTANT: REMOVED internal state update here as requested.
                        # It will be updated to PENDING_EXTEND/ON after re-send.

                        should_print_status = True # Force a status print after reset

                        # Force print current status immediately
                        if should_print_status:
                            timestamp = datetime.now().strftime("%H:%M:%S")
                            print(f"\n{timestamp}: Status Atual:")
                            print_current_status_to_console()
                            should_print_status = False # Reset immediately after printing

                        # --- Wait for RETRY_DELAY_SECONDS ---
                        time.sleep(RETRY_DELAY_SECONDS)
                        current_loop_time = time.time() # Update time after sleep for accurate timestamping

                        # --- Second part: Re-send the command ---
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Reenviando comando para {component_name}.")
                        sys.stdout.flush()

                        if state['original_command_type'] == gpiod.line.Value.ACTIVE:
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] DEBUG: Setting GPIO {line_offset} to ACTIVE (1) for retry.")
                            request.set_value(line_offset, gpiod.line.Value.ACTIVE)
                            current_gpio_output_states[line_offset] = gpiod.line.Value.ACTIVE
                            
                            # Reset pending state and timer for the *new* attempt
                            state['pending'] = True # It's now pending again after re-send
                            state['start_time'] = current_loop_time # Reset timer for the new attempt

                            # Update internal state for component to PENDING again
                            if line_offset == GPIO_LINE_OFFSETS[2]:
                                vac_inferior_internal_state = COMPONENT_STATUS[line_offset]["PENDING_ON"]
                            elif line_offset == GPIO_LINE_OFFSETS[3]:
                                cilindro_internal_state = COMPONENT_STATUS[line_offset]["PENDING_EXTEND"]
                            elif line_offset == GPIO_LINE_OFFSETS[4]:
                                vac_superior_internal_state = COMPONENT_STATUS[line_offset]["PENDING_ON"]
                        else: # Should not happen if 'pending' is true, but as a safeguard
                            state['pending'] = False

                        should_print_status = True # Force a status print after retry
                        # The loop will continue, and this pending state will be monitored again.


            # Imprime o status APENAS se houver mudança
            if should_print_status:
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n{timestamp}: Status Atual:")
                print_current_status_to_console()

                # Reseta a flag após imprimir
                should_print_status = False

            time.sleep(0.05) # Small pause to prevent high CPU in the loop.

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