# ui_dashboard.py — Dashboard agnóstico basado en Curses / ANSI para Chelo-Harness
import curses
import time

def run_curses_dashboard(title, steps, logs_dict):
    """
    Renderiza un dashboard agnóstico en pantalla completa usando Curses nativo.
    - steps: lista de tuplas (nombre, estado: 'DONE', 'IN_PROGRESS', 'PENDING')
    - logs_dict: dict con claves como 'backend', 'qa', 'mock' y listas de líneas de log.
    """
    def _draw(stdscr):
        curses.curs_set(0)
        curses.start_color()
        curses.use_default_colors()

        # Configurar pares de colores universales
        curses.init_pair(1, curses.COLOR_CYAN, -1)
        curses.init_pair(2, curses.COLOR_GREEN, -1)
        curses.init_pair(3, curses.COLOR_YELLOW, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)

        max_y, max_x = stdscr.getmaxyx()
        if max_y < 15 or max_x < 50:
            stdscr.addstr(0, 0, "Terminal demasiado chica para Dashboard TUI. Presioná 'q' para salir.")
            stdscr.refresh()
            stdscr.getch()
            return

        stdscr.clear()

        # 1. Cabecera
        header = f" 🛡️  CHELO-HARNESS DASHBOARD — {title} "
        stdscr.attron(curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(1, 2, header[:max_x-4])
        stdscr.attroff(curses.A_BOLD | curses.color_pair(1))

        # 2. Barra de Estados / Pasos
        col_x = 2
        stdscr.addstr(3, 2, "Hitos: ")
        col_x += 7
        for name, status in steps:
            if status == "DONE":
                st_str = f"[✓ {name}] "
                stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
            elif status == "IN_PROGRESS":
                st_str = f"[▶ {name}] "
                stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
            else:
                st_str = f"[○ {name}] "
                stdscr.attron(curses.A_DIM)

            if col_x + len(st_str) < max_x - 2:
                stdscr.addstr(3, col_x, st_str)
                col_x += len(st_str)
            stdscr.attroff(curses.color_pair(2) | curses.color_pair(3) | curses.A_BOLD | curses.A_DIM)

        # 3. Cajas de Logs divididas
        half_x = max_x // 2
        box_y_start = 5
        box_height = max_y - 7

        # Caja Izquierda: Backend / Implementación
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(box_y_start, 2, "🤖 AGENTE EN ACCIÓN (Output):")
        stdscr.attroff(curses.A_BOLD)
        back_logs = logs_dict.get("agent", [])[-(box_height-2):]
        for idx, line in enumerate(back_logs):
            stdscr.addstr(box_y_start + 1 + idx, 2, line[:half_x-4])

        # Caja Derecha: Pruebas Hurl & Mock
        stdscr.attron(curses.A_BOLD)
        stdscr.addstr(box_y_start, half_x + 1, "🧪 QA / TESTS & PRISM MOCK:")
        stdscr.attroff(curses.A_BOLD)
        qa_logs = logs_dict.get("qa", [])[-(box_height-2):]
        for idx, line in enumerate(qa_logs):
            stdscr.addstr(box_y_start + 1 + idx, half_x + 1, line[:max_x - half_x - 3])

        # Pie
        stdscr.addstr(max_y - 1, 2, "Presioná 'q' o Ctrl+C para continuar...", curses.A_DIM)
        stdscr.refresh()
        stdscr.nodelay(True)
        time.sleep(0.05)

    try:
        curses.wrapper(_draw)
    except Exception:
        pass
