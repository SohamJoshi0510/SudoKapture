# SudoKapture

This project is a Sudoku solver implemented in Python using Tkinter for the GUI, OpenCV for image processing, and Tesseract for digit extraction from Sudoku puzzle images. The solver uses a backtracking algorithm to find the solution to the puzzle.

## Features

- **Image Selection and Cropping:** Allows users to select a Sudoku puzzle image, crop it to focus on the puzzle area using a GUI, and process it for digit extraction.
- **Perspective Transformation:** Uses OpenCV to detect and transform the Sudoku grid from a given image for easier processing.
- **Digit Extraction:** Utilizes Tesseract OCR to extract digits from each cell of the Sudoku grid.
- **Sudoku Solving:** Implements a backtracking algorithm to solve the extracted Sudoku puzzle.
- **GUI for Solution Display:** Displays the solved Sudoku puzzle in a Tkinter GUI where users can interact and see the solution.

## Detailed Description of Functional Components

### `main.py`
This file is the entry point of the application. It handles the main logic and orchestrates the different components of the project. The `main.py` file initializes the Tkinter GUI, manages user interactions, and calls functions from other modules to perform image processing, digit extraction, and Sudoku solving.

### `crop.py`
The `crop.py` file provides functionality for selecting and cropping the Sudoku puzzle image. It includes a GUI that allows users to select the area of the image containing the Sudoku grid. This cropped image is then used for further processing to isolate the Sudoku grid.

### `sudoku.py`
The `sudoku.py` file contains the Sudoku solving algorithm. It uses a backtracking approach to find the solution to the Sudoku puzzle. The algorithm checks each cell of the grid, trying different numbers until it finds a valid solution that satisfies all Sudoku rules.

### `warp.py`
The `warp.py` file is responsible for warping the image to isolate the Sudoku grid. It uses OpenCV to detect the four corners of the Sudoku grid and performs a perspective transformation to get a top-down view of the grid. This transformation makes it easier to extract digits from each cell.

### `digit_extraction.py`
The `digit_extraction.py` file handles extracting digits from the warped image using Tesseract OCR. It preprocesses the image to improve OCR accuracy and then uses Tesseract to recognize the digits in each cell. The extracted digits are stored in a format suitable for the Sudoku solving algorithm.

### `gui.py`
The `gui.py` file manages the GUI for displaying and interacting with the Sudoku puzzle solution. It uses Tkinter to create a user-friendly interface where users can view the solved puzzle. The GUI allows users to load images, crop them, and see the solution displayed on the screen.

## Requirements

- Python 3.x
- Tkinter
- OpenCV
- Tesseract OCR

