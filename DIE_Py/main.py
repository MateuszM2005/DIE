import os
import sys
import copy
import pygame
import textures_loader
import renderer

pygame.init()

# --- 1. GETTING THE NATIVE MONITOR RESOLUTION ---
monitor_info = pygame.display.Info()
MONITOR_W = monitor_info.current_w
MONITOR_H = monitor_info.current_h

screen = pygame.display.set_mode((MONITOR_W, MONITOR_H), pygame.FULLSCREEN)
pygame.display.set_caption("DIE - Game")

# --- 2. INITIALIZATION OF GAME RESOURCES ---
textures_loader.init_all_textures()

raw_fonts = {}
font_sprites = {}
FONT_DIR = "font"


def load_custom_font_raw():
    needed_chars = [
        'D', 'I', 'E', 'P', 'L', 'A', 'Y', 'B', 'C', 'K', 'Q', 'U', 'T', 'V',
        '0', '1', '2', '3', '4', '5', '6', '7', '8', '9'
    ]
    for char in needed_chars:
        file_path = os.path.join(FONT_DIR, f"{char}.png")
        if os.path.exists(file_path):
            raw_fonts[char] = pygame.image.load(file_path).convert_alpha()
        else:
            raw_fonts[char] = pygame.Surface((300, 300), pygame.SRCALPHA)


def scale_font_for_interface(scale_factor=1.0):
    """Generates letter versions fitted directly to the physical monitor."""
    global font_sprites
    font_sprites = {}
    for char, img in raw_fonts.items():
        base_w, base_h = img.get_size()
        target_w = int(base_w * scale_factor)
        target_h = int(base_h * scale_factor)
        font_sprites[char] = pygame.transform.smoothscale(img,
                                                          (target_w, target_h))


def render_string(text):
    if not text:
        fallback = pygame.Surface((10, 10), pygame.SRCALPHA)
        return fallback, fallback.get_rect()

    char_w = font_sprites[text[0]].get_width()
    char_h = font_sprites[text[0]].get_height()
    spacing = int(char_w * 0.65)

    total_width = char_w + (len(text) - 1) * spacing
    text_surface = pygame.Surface((total_width, char_h), pygame.SRCALPHA)

    for i, char in enumerate(text):
        if char == " ":
            continue
        if char in font_sprites:
            text_surface.blit(font_sprites[char], (i * spacing, 0))

    return text_surface, text_surface.get_rect()


# We load gigantic raw graphics
load_custom_font_raw()

# DYNAMIC FONT SCALE: We fit the base size to the monitor screen height.
# For a Fullscreen monitor (1080p) the factor will be 1080 / 2000 ≈ 0.54,
# which gives ideal sharpness directly on the physical pixels of the monitor.
# --- DYNAMIC FONT SCALE FOR THE INTERFACE ---
# We fit the base size to the monitor screen height.
UI_SCALE = MONITOR_H / 2000.0
scale_font_for_interface(scale_factor=UI_SCALE)

# Game states
STATE_MENU = "menu"
STATE_LEVEL_SELECT = "level_select"
current_state = STATE_MENU

# --- POSITIONING OF INTERFACE ELEMENTS ---
# Game title "DIE" - generated at a larger scale directly from raw_fonts for ideal sharpness
# We multiply the base UI_SCALE so the logo is clearly larger than the PLAY/QUIT buttons
LOGO_SCALE = UI_SCALE * 2.2
base_w, base_h = raw_fonts["D"].get_size()
target_w = int(base_w * LOGO_SCALE)
target_h = int(base_h * LOGO_SCALE)

# We generate dedicated large textures for the logo
logo_font_sprites = {}
for char in ['D', 'I', 'E']:
    logo_font_sprites[char] = pygame.transform.smoothscale(raw_fonts[char], (target_w, target_h))

# Assembling the DIE caption from larger tiles
def render_logo_string(text):
    char_w = logo_font_sprites[text[0]].get_width()
    char_h = logo_font_sprites[text[0]].get_height()
    spacing = int(char_w * 0.65)
    total_width = char_w + (len(text) - 1) * spacing
    text_surface = pygame.Surface((total_width, char_h), pygame.SRCALPHA)
    for i, char in enumerate(text):
        if char in logo_font_sprites:
            text_surface.blit(logo_font_sprites[char], (i * spacing, 0))
    return text_surface, text_surface.get_rect()

# Main Menu - Generating elements
logo_surf, logo_rect = render_logo_string("DIE")
logo_rect.center = (MONITOR_W // 2, MONITOR_H // 4)

play_surf, play_rect = render_string("PLAY")
play_rect.center = (MONITOR_W // 2, MONITOR_H // 2)

quit_surf, quit_rect = render_string("QUIT")
quit_rect.center = (MONITOR_W // 2, MONITOR_H // 1.45)

# Level Selection
level_title_surf, level_title_rect = render_string("LEVELS")
level_title_rect.center = (MONITOR_W // 2, int(MONITOR_H * 0.1))

back_surf, back_rect = render_string("BACK")
back_rect.center = (MONITOR_W // 2, MONITOR_H - int(MONITOR_H * 0.1))

# Dynamic grid of level buttons laid out based on the physical screen
NUM_LEVELS = 15
COLS = 5
START_X = MONITOR_W // 2 - int(MONITOR_W * 0.22)
START_Y = int(MONITOR_H * 0.3)
SPACING_X = int(MONITOR_W * 0.11)
SPACING_Y = int(MONITOR_H * 0.16)

level_buttons = []
for i in range(1, NUM_LEVELS + 1):
    col = (i - 1) % COLS
    row = (i - 1) // COLS
    x = START_X + col * SPACING_X
    y = START_Y + row * SPACING_Y

    lvl_surf, lvl_rect = render_string(str(i))
    lvl_rect.center = (x, y)
    level_buttons.append((lvl_surf, lvl_rect, i))


def blit_canvas_with_letterbox(target_screen, source_canvas):
    """Used only and exclusively for ideal drawing of the board in the game."""
    canvas_w, canvas_h = source_canvas.get_size()
    scale = min(MONITOR_W / canvas_w, MONITOR_H / canvas_h)

    new_w = int(canvas_w * scale)
    new_h = int(canvas_h * scale)

    scaled_canvas = pygame.transform.smoothscale(source_canvas, (new_w, new_h))

    offset_x = (MONITOR_W - new_w) // 2
    offset_y = (MONITOR_H - new_h) // 2

    target_screen.blit(scaled_canvas, (offset_x, offset_y))


def start_fullscreen_level(level_file):
    from Board import Board
    try:
        board = Board(level_file)
    except FileNotFoundError:
        print(f"Error: File not found {level_file}")
        return

    tile_w_needed = MONITOR_W // board.width
    tile_h_needed = MONITOR_H // board.height
    dynamic_tile_size = min(tile_w_needed, tile_h_needed)

    textures_loader.scale_textures_for_level(dynamic_tile_size)

    game_virtual_w = board.width * dynamic_tile_size
    game_virtual_h = board.height * dynamic_tile_size
    game_canvas = pygame.Surface((game_virtual_w, game_virtual_h))

    level_clock = pygame.time.Clock()
    game_status = "PLAYING"
    history = []
    moves_count = 0

    # --- VARIABLES FOR HANDLING WASD HOLD ---
    current_key = None
    key_pressed_time = 0
    last_repeat_time = 0
    DELAY_BEFORE_REPEAT = 450  # Increased delay after the first click (from 300ms)
    REPEAT_INTERVAL = 90  # Marginally faster series of steps (from 110ms)

    # --- VARIABLES FOR HANDLING "Q" HOLD (UNDO REPEAT) ---
    q_is_held = False
    q_pressed_time = 0
    q_last_repeat_time = 0
    Q_DELAY_BEFORE_REPEAT = 450  # Increased delay after the first click (from 300ms)
    Q_REPEAT_INTERVAL = 130  # Marginally faster undo series (from 160ms)

    DIR_MAP = {
        pygame.K_w: (0, -1),
        pygame.K_s: (0, 1),
        pygame.K_a: (-1, 0),
        pygame.K_d: (1, 0)
    }

    level_running = True
    while level_running:
        current_time = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    level_running = False
                    break

                # REGISTRATION OF THE FIRST PRESS OF THE "Q" KEY
                elif event.key == pygame.K_q:
                    q_is_held = True
                    q_pressed_time = current_time
                    q_last_repeat_time = current_time

                    # EXECUTION OF THE FIRST UNDO (IMMEDIATELY)
                    if history:
                        board = history.pop()
                        game_status = "PLAYING"
                        moves_count -= 1
                        current_key = None  # Block of moves during undoing
                    continue

                if game_status == "PLAYING" and event.key in DIR_MAP:
                    current_key = event.key
                    key_pressed_time = current_time
                    last_repeat_time = current_time

                    direction = DIR_MAP[current_key]
                    history.append(copy.deepcopy(board))

                    from Entity import Angel, Devil
                    moved = False
                    for entity in list(board.entities):
                        if isinstance(entity, (Angel, Devil)):
                            old_x, old_y = entity.x, entity.y
                            entity.move(direction, board)
                            if entity.x != old_x or entity.y != old_y:
                                moved = True

                    if moved:
                        moves_count += 1
                    else:
                        history.pop()

                    game_status = board.update_turn()

            if event.type == pygame.KEYUP:
                # Stopping movement repeat
                if event.key == current_key:
                    current_state_keys = pygame.key.get_pressed()
                    next_key = next(
                        (k for k in DIR_MAP if current_state_keys[k]), None)
                    if next_key:
                        current_key = next_key
                        key_pressed_time = current_time
                        last_repeat_time = current_time
                    else:
                        current_key = None

                # STOPPING UNDO REPEAT AFTER RELEASING THE "Q" KEY
                elif event.key == pygame.K_q:
                    q_is_held = False

        if not level_running:
            break

        # --- AUTOREPEAT LOGIC FOR "Q" (UNDO SERIES) ---
        if q_is_held:
            if current_time - q_pressed_time >= Q_DELAY_BEFORE_REPEAT:
                if current_time - q_last_repeat_time >= Q_REPEAT_INTERVAL:
                    if history:
                        board = history.pop()
                        game_status = "PLAYING"
                        moves_count -= 1
                        q_last_repeat_time = current_time  # Update of the series step time
                    else:
                        q_is_held = False  # We stop the loop when the history is already empty

        # --- WASD KEY HOLD LOGIC ---
        if game_status == "PLAYING" and current_key is not None and not q_is_held:
            if current_time - key_pressed_time >= DELAY_BEFORE_REPEAT:
                if current_time - last_repeat_time >= REPEAT_INTERVAL:
                    direction = DIR_MAP[current_key]
                    history.append(copy.deepcopy(board))

                    from Entity import Angel, Devil
                    moved = False
                    for entity in list(board.entities):
                        if isinstance(entity, (Angel, Devil)):
                            old_x, old_y = entity.x, entity.y
                            entity.move(direction, board)
                            if entity.x != old_x or entity.y != old_y:
                                moved = True

                    if moved:
                        moves_count += 1
                        last_repeat_time = current_time
                    else:
                        history.pop()

                    game_status = board.update_turn()

        # Board render
        renderer.draw_board(game_canvas, board)
        screen.fill((0, 0, 0))
        blit_canvas_with_letterbox(screen, game_canvas)

        # Drawing the move counter
        moves_surf, moves_rect = render_string(str(moves_count))
        moves_rect.topright = (MONITOR_W - 40, 40)
        screen.blit(moves_surf, moves_rect)

        pygame.display.flip()
        level_clock.tick(30)

        if game_status == "WIN":
            pygame.time.wait(1500)
            level_running = False

# --- MAIN INTERFACE LOOP ---
clock = pygame.time.Clock()
running = True

while running:
    # We get the direct mouse position from the monitor (without converting back!)
    mouse_pos = pygame.mouse.get_pos()

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if current_state == STATE_MENU:
                if play_rect.collidepoint(mouse_pos):
                    current_state = STATE_LEVEL_SELECT
                elif quit_rect.collidepoint(mouse_pos):
                    running = False

            elif current_state == STATE_LEVEL_SELECT:
                if back_rect.collidepoint(mouse_pos):
                    current_state = STATE_MENU

                for lvl_surf, lvl_rect, lvl_num in level_buttons:
                    if lvl_rect.collidepoint(mouse_pos):
                        start_fullscreen_level(f"levels/{lvl_num}.json")
                        current_state = STATE_LEVEL_SELECT

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if current_state == STATE_LEVEL_SELECT:
                    current_state = STATE_MENU
                elif current_state == STATE_MENU:
                    running = False

    # Clearing the physical monitor
    screen.fill((0, 0, 0))

    # We draw the menu directly on the screen
    if current_state == STATE_MENU:
        if play_rect.collidepoint(mouse_pos):
            play_surf.set_alpha(180)
            quit_surf.set_alpha(255)
        elif quit_rect.collidepoint(mouse_pos):
            play_surf.set_alpha(255)
            quit_surf.set_alpha(180)
        else:
            play_surf.set_alpha(255)
            quit_surf.set_alpha(255)

        screen.blit(logo_surf, logo_rect)
        screen.blit(play_surf, play_rect)
        screen.blit(quit_surf, quit_rect)

    elif current_state == STATE_LEVEL_SELECT:
        renderer.draw_level_selection(screen, level_title_surf,
                                      level_title_rect, back_surf, back_rect,
                                      level_buttons, mouse_pos)

    pygame.display.flip()
    clock.tick(60)

pygame.quit()
sys.exit()