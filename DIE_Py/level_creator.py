import sys
import os
import json
import pygame
import textures_loader

# --- DEFAULT WINDOW AND GRID PARAMETERS (Used when the file does not exist) ---
GRID_WIDTH = 7
GRID_HEIGHT = 5
FIXED_TILE_SIZE = 80  # Rigid tile size for the editor
LEVELS_DIR = "levels"  # Target folder for levels
FILENAME = '10.json'

# --- KEYBOARD MAPPING ---
TILE_MAP = {
    pygame.K_1: 1,  # EMPTY
    pygame.K_2: 2,  # WALL
    pygame.K_3: 3,  # SPIKES
    pygame.K_4: 4,  # RIFT
    pygame.K_5: 5  # FIRE
}

ENTITY_MAP = {
    pygame.K_q: "angel",
    pygame.K_w: "devil",
    pygame.K_e: "box",
    pygame.K_r: "crown",
    pygame.K_t: "grail"
}

TILE_NAMES = {1: 'EMPTY', 2: 'WALL', 3: 'SPIKES', 4: 'RIFT', 5: 'FIRE'}
ENTITY_NAMES = {
    "angel": 'ANGEL',
    "devil": 'DEVIL',
    "box": 'BOX',
    "crown": 'CROWN',
    "grail": 'GRAIL'
}


def save_level(filename, board_matrix, entities_dict, width, height):
    """Saves the level to a clean, custom-formatted JSON."""
    if not os.path.exists(LEVELS_DIR):
        os.makedirs(LEVELS_DIR)

    full_path = os.path.join(LEVELS_DIR, filename)

    entities_list = []
    for (x, y), eid in entities_dict.items():
        entities_list.append({"eid": eid, "x": x, "y": y})

    # Constructing readable JSON with matrix rows in a single line
    board_rows_json = []
    for row in board_matrix:
        board_rows_json.append("    " + json.dumps(row))
    board_formatted = "[\n" + ",\n".join(board_rows_json) + "\n  ]"

    entities_formatted = json.dumps(entities_list, indent=4).replace("\n",
                                                                     "\n  ")

    json_output = (
        "{\n"
        f'  "width": {width},\n'
        f'  "height": {height},\n'
        f'  "board": {board_formatted},\n'
        f'  "entities": {entities_formatted}\n'
        "}"
    )

    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(json_output)
    print(f"Level saved successfully as: {full_path}")


def main():
    # We take the globals so we can safely overwrite them with dimensions from the file
    current_width = GRID_WIDTH
    current_height = GRID_HEIGHT

    filename = FILENAME
    filename = os.path.basename(filename)
    full_path = os.path.join(LEVELS_DIR, filename)

    pygame.init()

    # STEP 1: Checking dimensions in the JSON file before creating the window
    if os.path.exists(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if "width" in data and "height" in data:
                    current_width = data["width"]
                    current_height = data["height"]
        except Exception as e:
            print(f"Error reading dimensions: {e}. Using defaults.")

    # STEP 2: Initialization of the Pygame window at the exact board dimensions
    screen = pygame.display.set_mode(
        (current_width * FIXED_TILE_SIZE, current_height * FIXED_TILE_SIZE))
    pygame.display.set_caption(f"Editor: {full_path}")

    # STEP 3: LOADING TEXTURES ONLY AFTER DISPLAY.SET_MODE (Key in Pygame for .convert())
    textures_loader.init_all_textures()
    textures_loader.scale_textures_for_level(FIXED_TILE_SIZE)
    textures = textures_loader.textures

    # Creation of a default matrix at the proper, dynamic size
    board_matrix = [[1 for _ in range(current_width)] for _ in
                    range(current_height)]
    entities_dict = {}

    # STEP 4: Loading tile and entity contents with padding using ones
    if os.path.exists(full_path):
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

                json_board = data.get("board", [])
                json_height = len(json_board)

                for y in range(current_height):
                    if y < json_height:
                        json_row = json_board[y]
                        json_width = len(json_row)
                        for x in range(current_width):
                            if x < json_width:
                                board_matrix[y][x] = json_row[x]
                            else:
                                board_matrix[y][x] = 1
                    else:
                        for x in range(current_width):
                            board_matrix[y][x] = 1

                for ent in data.get("entities", []):
                    if 0 <= ent["x"] < current_width and 0 <= ent[
                        "y"] < current_height:
                        entities_dict[(ent["x"], ent["y"])] = ent["eid"]

            print(
                f"Loaded level {full_path} ({current_width}x{current_height}).")
        except Exception as e:
            print(
                f"Failed to parse contents, starting from a clean board. Error: {e}")

    current_brush_type = "tile"
    current_brush_value = 1

    clock = pygame.time.Clock()
    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    save_level(filename, board_matrix, entities_dict,
                               current_width, current_height)
                    running = False
                elif event.key in (pygame.K_BACKSPACE, pygame.K_z):
                    current_brush_type = "eraser"
                elif event.key in TILE_MAP:
                    current_brush_type = "tile"
                    current_brush_value = TILE_MAP[event.key]
                elif event.key in ENTITY_MAP:
                    current_brush_type = "entity"
                    current_brush_value = ENTITY_MAP[event.key]

        mouse_pressed = pygame.mouse.get_pressed()
        if mouse_pressed[0]:
            mx, my = pygame.mouse.get_pos()
            tile_x = mx // FIXED_TILE_SIZE
            tile_y = my // FIXED_TILE_SIZE

            if 0 <= tile_x < current_width and 0 <= tile_y < current_height:
                if current_brush_type == "tile":
                    board_matrix[tile_y][tile_x] = current_brush_value
                elif current_brush_type == "entity":
                    entities_dict[(tile_x, tile_y)] = current_brush_value
                elif current_brush_type == "eraser":
                    if (tile_x, tile_y) in entities_dict:
                        del entities_dict[(tile_x, tile_y)]

        if mouse_pressed[2]:
            mx, my = pygame.mouse.get_pos()
            tile_x = mx // FIXED_TILE_SIZE
            tile_y = my // FIXED_TILE_SIZE
            if 0 <= tile_x < current_width and 0 <= tile_y < current_height:
                if (tile_x, tile_y) in entities_dict:
                    del entities_dict[(tile_x, tile_y)]

        screen.fill((0, 0, 0))

        # Drawing tiles (We use dynamic loops current_height / current_width)
        for y in range(current_height):
            for x in range(current_width):
                tx = x * FIXED_TILE_SIZE
                ty = y * FIXED_TILE_SIZE
                tile_id = board_matrix[y][x]
                tile_name = TILE_NAMES[tile_id]

                if tile_name != 'WALL':
                    if 'EMPTY' in textures:
                        screen.blit(textures['EMPTY'], (tx, ty))

                if tile_name != 'EMPTY':
                    if tile_name in textures:
                        screen.blit(textures[tile_name], (tx, ty))

        # Drawing entities
        for (ex, ey), eid in entities_dict.items():
            tex_key = ENTITY_NAMES[eid]
            if tex_key in textures:
                screen.blit(textures[tex_key],
                            (ex * FIXED_TILE_SIZE, ey * FIXED_TILE_SIZE))

        # Helper grid fitted to the actual dimensions
        for x in range(current_width + 1):
            pygame.draw.line(screen, (30, 30, 30), (x * FIXED_TILE_SIZE, 0),
                             (x * FIXED_TILE_SIZE,
                              current_height * FIXED_TILE_SIZE))
        for y in range(current_height + 1):
            pygame.draw.line(screen, (30, 30, 30), (0, y * FIXED_TILE_SIZE),
                             (current_width * FIXED_TILE_SIZE,
                              y * FIXED_TILE_SIZE))

        pygame.display.flip()
        clock.tick(60)

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()