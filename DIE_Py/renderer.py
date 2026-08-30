import pygame
from Entity import Angel, Devil, Box, Crown, Grail
import textures_loader


def draw_menu(screen, logo_surf, logo_rect, play_surf, play_rect, mouse_pos):
    """Renders the main menu with a hover effect."""
    screen.fill((0, 0, 0))

    # Hover effect for the PLAY button
    if play_rect.collidepoint(mouse_pos):
        play_surf.set_alpha(180)
    else:
        play_surf.set_alpha(255)

    screen.blit(logo_surf, logo_rect)
    screen.blit(play_surf, play_rect)


def draw_level_selection(screen, title_surf, title_rect, back_surf, back_rect,
                         level_buttons, mouse_pos):
    """Renders the level selection screen with hover effects."""
    screen.fill((0, 0, 0))

    # Drawing the header
    screen.blit(title_surf, title_rect)

    # Drawing the level buttons
    for lvl_surf, lvl_rect, lvl_num in level_buttons:
        if lvl_rect.collidepoint(mouse_pos):
            lvl_surf.set_alpha(255)
        else:
            lvl_surf.set_alpha(140)
        screen.blit(lvl_surf, lvl_rect)

    # Drawing the BACK button
    if back_rect.collidepoint(mouse_pos):
        back_surf.set_alpha(255)
    else:
        back_surf.set_alpha(140)
    screen.blit(back_surf, back_rect)


def draw_board(screen, board):
    """Renders the actual game board (Your original function)."""
    screen.fill((0, 0, 0))
    ts = textures_loader.TILE_SIZE
    textures = textures_loader.textures

    for row in range(board.height):
        for col in range(board.width):
            x = col * ts
            y = row * ts
            tile_type = board.board[row][col].name

            if tile_type != 'WALL' and tile_type != 'RIFT':
                if 'EMPTY' in textures:
                    screen.blit(textures['EMPTY'], (x, y))

            if tile_type in textures and tile_type != 'EMPTY':
                screen.blit(textures[tile_type], (x, y))

    for entity in board.entities:
        if "dead" in entity.effects:
            continue

        ex = entity.x * ts
        ey = entity.y * ts

        if isinstance(entity, Angel):
            entity_key = 'ANGEL_CROWN' if 'crown' in entity.effects else 'ANGEL'
        elif isinstance(entity, Devil):
            entity_key = 'DEVIL'
        elif isinstance(entity, Box):
            entity_key = 'BOX'
        elif isinstance(entity, Crown):
            entity_key = 'CROWN'
        elif isinstance(entity, Grail):
            entity_key = 'GRAIL'
        else:
            continue

        if entity_key in textures:
            screen.blit(textures[entity_key], (ex, ey))