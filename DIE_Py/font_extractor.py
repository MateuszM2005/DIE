import os
from PIL import Image


def extract_font(image_path, output_dir="extracted_font2"):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    # Opening the image and conversion to RGBA format
    img = Image.open(image_path).convert("RGBA")
    width, height = img.size

    # Exact mapping of the character layout from the FONT_TOEDIT.png file
    grid_chars = [
        ['A', 'B', 'C', 'D', 'E', 'F'],
        ['G', 'H', 'I', 'J', 'J2', 'K'],
        ['L', 'M', 'M2', 'N', 'O', 'P'],
        ['Q', 'V', 'U', 'T', 'W', 'X'],
        ['Y', 'Z', '1', '2', '4', '5'],
        ['6', '7', '8', '9', '0', 'star']
    ]

    rows = len(grid_chars)
    cols = len(grid_chars[0])

    tile_w = width // cols
    tile_h = height // rows

    # Increased safety margin to cut off the divider lines
    # 15 pixels from the left and right side will completely remove the vertical bars
    padding_x = 40
    padding_y = 20

    print(f"Image size: {width}x{height}")
    print(
        f"Cutting tiles with a safety margin: X={padding_x}px, Y={padding_y}px")

    for r in range(rows):
        for c in range(cols):
            char_name = grid_chars[r][c]

            # Calculating the base coordinates of the tile
            left = c * tile_w
            top = r * tile_h
            right = left + tile_w
            bottom = top + tile_h

            # Narrowing the crop area by the defined margin
            cropped = img.crop((
                left + padding_x,
                top + padding_y,
                right - padding_x,
                bottom - padding_y
            ))

            # Processing transparency on a black background
            datas = cropped.getdata()
            new_data = []

            for item in datas:
                r_val, g_val, b_val, a_val = item

                # Tolerance for dirty black (values below 10)
                if r_val < 10 or g_val < 10 or b_val < 10:
                    new_data.append((0, 0, 0, 0))  # Full transparency
                else:
                    new_data.append(item)  # Keeping the white character

            cropped.putdata(new_data)

            # Saving the cropped and cleaned character
            file_name = f"{char_name}.png"
            output_path = os.path.join(output_dir, file_name)
            cropped.save(output_path, "PNG")

    print(
        f"Done! You will find the cleaned characters without bars in the folder: '{output_dir}'")


if __name__ == "__main__":
    extract_font("textures/FONT_TOEDIT.png")