# digit_extraction.py

import cv2
import numpy as np
import pytesseract

def extract_digits(warped, cell_size=28, border_percent=0.15):
    """
    Extract digits from a warped Sudoku grid image.
    
    Args:
        warped: Preprocessed Sudoku grid image (BGR format)
        cell_size: Size to resize each cell to for OCR
        border_percent: Percentage of cell to crop as border (0.15 = 15%)
    
    Returns:
        digits: 9x9 list of detected digits (0 for empty cells)
        all_cells: Copy of digits (for initial state tracking)
    """
    grid_size = warped.shape[0] // 9
    
    digits = []
    all_cells = []
    
    for row in range(9):
        row_list = []
        initial_list = []
        
        for col in range(9):
            # Extract cell
            x1 = col * grid_size
            y1 = row * grid_size
            x2 = (col + 1) * grid_size
            y2 = (row + 1) * grid_size
            cell = warped[y1:y2, x1:x2]
            
            # Dynamic border calculation
            border = int(grid_size * border_percent)
            cropped_cell = cell[border:-border, border:-border]
            
            # Convert to grayscale
            if len(cropped_cell.shape) == 3:
                gray_cell = cv2.cvtColor(cropped_cell, cv2.COLOR_BGR2GRAY)
            else:
                gray_cell = cropped_cell
            
            # Apply adaptive thresholding (better for varying lighting)
            thresh_cell = cv2.adaptiveThreshold(
                gray_cell, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            # Noise removal
            kernel = np.ones((2, 2), np.uint8)
            thresh_cell = cv2.morphologyEx(thresh_cell, cv2.MORPH_CLOSE, kernel)
            
            # Check if cell contains significant content
            pixel_sum = np.sum(thresh_cell)
            cell_area = thresh_cell.shape[0] * thresh_cell.shape[1]
            
            # If less than 5% of pixels are white, likely empty
            if pixel_sum < cell_area * 255 * 0.05:
                row_list.append(0)
                initial_list.append(0)
                continue
            
            # Find largest contour (likely the digit)
            contours, _ = cv2.findContours(
                thresh_cell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                # Get largest contour
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                
                # Filter out noise (too small or wrong aspect ratio)
                if w < 5 or h < 5 or w / h > 1.5 or h / w > 3:
                    row_list.append(0)
                    initial_list.append(0)
                    continue
                
                # Extract digit region with padding
                padding = 2
                x1_digit = max(0, x - padding)
                y1_digit = max(0, y - padding)
                x2_digit = min(thresh_cell.shape[1], x + w + padding)
                y2_digit = min(thresh_cell.shape[0], y + h + padding)
                
                digit_img = thresh_cell[y1_digit:y2_digit, x1_digit:x2_digit]
                
                # Resize to square for better OCR
                resized_cell = cv2.resize(digit_img, (cell_size, cell_size))
                
                # Add border for better OCR
                bordered = cv2.copyMakeBorder(
                    resized_cell, 4, 4, 4, 4,
                    cv2.BORDER_CONSTANT, value=0
                )
            else:
                # No contours found
                resized_cell = cv2.resize(thresh_cell, (cell_size, cell_size))
                bordered = resized_cell
            
            # OCR with strict configuration
            config = '--psm 10 --oem 3 -c tessedit_char_whitelist=123456789'
            digit = pytesseract.image_to_string(bordered, config=config).strip()
            
            # Validate digit
            if digit.isdigit() and 1 <= int(digit) <= 9:
                row_list.append(int(digit))
                initial_list.append(int(digit))
            else:
                row_list.append(0)
                initial_list.append(0)
        
        digits.append(row_list)
        all_cells.append(initial_list)
    
    return digits, all_cells


def extract_digits_with_debug(warped, output_dir='debug_cells'):
    """
    Version with debug output to save processed cells for inspection.
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    grid_size = warped.shape[0] // 9
    border_percent = 0.15
    cell_size = 28
    
    digits = []
    all_cells = []
    
    for row in range(9):
        row_list = []
        initial_list = []
        
        for col in range(9):
            x1 = col * grid_size
            y1 = row * grid_size
            x2 = (col + 1) * grid_size
            y2 = (row + 1) * grid_size
            cell = warped[y1:y2, x1:x2]
            
            border = int(grid_size * border_percent)
            cropped_cell = cell[border:-border, border:-border]
            
            if len(cropped_cell.shape) == 3:
                gray_cell = cv2.cvtColor(cropped_cell, cv2.COLOR_BGR2GRAY)
            else:
                gray_cell = cropped_cell
            
            thresh_cell = cv2.adaptiveThreshold(
                gray_cell, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2
            )
            
            kernel = np.ones((2, 2), np.uint8)
            thresh_cell = cv2.morphologyEx(thresh_cell, cv2.MORPH_CLOSE, kernel)
            
            # Save for debugging
            cv2.imwrite(f'{output_dir}/cell_{row}_{col}.png', thresh_cell)
            
            pixel_sum = np.sum(thresh_cell)
            cell_area = thresh_cell.shape[0] * thresh_cell.shape[1]
            
            if pixel_sum < cell_area * 255 * 0.05:
                row_list.append(0)
                initial_list.append(0)
                continue
            
            contours, _ = cv2.findContours(
                thresh_cell, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if contours:
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                
                if w < 5 or h < 5 or w / h > 1.5 or h / w > 3:
                    row_list.append(0)
                    initial_list.append(0)
                    continue
                
                padding = 2
                x1_digit = max(0, x - padding)
                y1_digit = max(0, y - padding)
                x2_digit = min(thresh_cell.shape[1], x + w + padding)
                y2_digit = min(thresh_cell.shape[0], y + h + padding)
                
                digit_img = thresh_cell[y1_digit:y2_digit, x1_digit:x2_digit]
                resized_cell = cv2.resize(digit_img, (cell_size, cell_size))
                bordered = cv2.copyMakeBorder(
                    resized_cell, 4, 4, 4, 4,
                    cv2.BORDER_CONSTANT, value=0
                )
            else:
                resized_cell = cv2.resize(thresh_cell, (cell_size, cell_size))
                bordered = resized_cell
            
            config = '--psm 10 --oem 3 -c tessedit_char_whitelist=123456789'
            digit = pytesseract.image_to_string(bordered, config=config).strip()
            
            detected = int(digit) if digit.isdigit() and 1 <= int(digit) <= 9 else 0
            row_list.append(detected)
            initial_list.append(detected)
            
            print(f"Cell [{row},{col}]: detected '{digit}' -> {detected}")
        
        digits.append(row_list)
        all_cells.append(initial_list)
    
    return digits, all_cells