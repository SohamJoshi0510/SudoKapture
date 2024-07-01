# digit_extraction.py

import cv2
import pytesseract

def extract_digits(warped, cell_size=28, border=4):
    grid_size = warped.shape[0] // 9

    digits = []
    all_cells = []
    for row in range(9):
        initial_list = []
        row_list = []
        for col in range(9):
            x1 = col * grid_size
            y1 = row * grid_size
            x2 = (col + 1) * grid_size
            y2 = (row + 1) * grid_size
            cell = warped[y1:y2, x1:x2]

            cropped_cell = cell[border:-border, border:-border]

            gray_cell = cv2.cvtColor(cropped_cell, cv2.COLOR_BGR2GRAY)
            _, thresh_cell = cv2.threshold(gray_cell, 128, 255, cv2.THRESH_BINARY_INV)

            resized_cell = cv2.resize(thresh_cell, (cell_size, cell_size))

            digit = pytesseract.image_to_string(resized_cell, config='--psm 10 digits')

            if digit.strip().isdigit():
                row_list.append(int(digit))
                initial_list.append(int(digit))
            else:
                row_list.append(0)
                initial_list.append(0)
        digits.append(row_list)
        all_cells.append(initial_list)

    return digits, all_cells
