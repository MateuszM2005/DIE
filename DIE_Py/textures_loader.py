import os
import pygame

# Tile size will be changed dynamically per level
TILE_SIZE = 80
textures = {}
raw_textures = {}  # Here we keep the originals at high resolution

def load_texture_raw(path, colorkey=None):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    full_path = os.path.join(base_dir, path)
    try:
        img = pygame.image.load(full_path).convert()
        if colorkey is not None:
            img.set_colorkey(colorkey)
        return img  # We return the original size without transform.scale
    except pygame.error:
        print(f"Cannot load: {full_path}. Creating a fallback.")
        surf = pygame.Surface((256, 256))  # Large fallback for scaling
        surf.fill((20, 20, 20) if colorkey is None else (0, 0, 0))
        if colorkey is not None:
            surf.set_colorkey(colorkey)
        return surf

def init_all_textures():
    global raw_textures
    # We load the full, large graphics into memory once
    raw_textures = {
        'EMPTY': load_texture_raw('textures/MAP/TILE.png', colorkey=None),
        'WALL': load_texture_raw('textures/MAP/WALL.png', colorkey=None),
        'FIRE': load_texture_raw('textures/MAP/FIRE.png', colorkey=(0, 0, 0)),
        'RIFT': load_texture_raw('textures/MAP/RIFT.png', colorkey=(0, 0, 0)),
        'SPIKES': load_texture_raw('textures/MAP/SPIKES.png', colorkey=(0, 0, 0)),
        'BOX': load_texture_raw('textures/ENTITY/BOX.png', colorkey=(0, 0, 0)),
        'ANGEL': load_texture_raw('textures/ENTITY/ANGEL.png', colorkey=(0, 0, 0)),
        'DEVIL': load_texture_raw('textures/ENTITY/DEVIL.png', colorkey=(0, 0, 0)),
        'CROWN': load_texture_raw('textures/ENTITY/CROWN.png', colorkey=(0, 0, 0)),
        'GRAIL': load_texture_raw('textures/ENTITY/GRAIL.png', colorkey=(0, 0, 0)),
        'ANGEL_CROWN': load_texture_raw('textures/ENTITY/ANGEL_CROWN.png', colorkey=(0, 0, 0))
    }

def scale_textures_for_level(target_size):
    """Scales textures from raw_textures to the required tile size."""
    global TILE_SIZE, textures
    TILE_SIZE = target_size
    textures = {}
    for key, img in raw_textures.items():
        textures[key] = pygame.transform.smoothscale(img, (TILE_SIZE, TILE_SIZE))