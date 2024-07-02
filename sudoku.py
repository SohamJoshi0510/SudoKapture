# sudoku.py

def is_valid(board, row, col, num):
    # Check if 'num' is not in the current row
    if num in board[row]:
        return False

    # Check if 'num' is not in the current column
    for i in range(9):
        if board[i][col] == num:
            return False

    # Check if 'num' is not in the current 3x3 box
    start_row, start_col = 3 * (row // 3), 3 * (col // 3)
    for i in range(start_row, start_row + 3):
        for j in range(start_col, start_col + 3):
            if board[i][j] == num:
                return False

    return True

def count_non_zero(board):
    """ Helper function to count non-zero elements in the board """
    count = 0
    for row in board:
        for num in row:
            if num != 0:
                count += 1
    return count

def is_valid_interpretation(board):
    """
    Check if the input board is a valid Sudoku puzzle.
    """
    # Check all rows
    for row in range(9):
        seen = set()
        for col in range(9):
            num = board[row][col]
            if num > 9:
                return False
            if num != 0:
                if num in seen:
                    return False
                seen.add(num)
    
    # Check all columns
    for col in range(9):
        seen = set()
        for row in range(9):
            if num > 9:
                return False
            num = board[row][col]
            if num != 0:
                if num in seen:
                    return False
                seen.add(num)

    # Check all 3x3 sub-grids
    for box_row in range(3):
        for box_col in range(3):
            seen = set()
            for i in range(3):
                for j in range(3):
                    num = board[3 * box_row + i][3 * box_col + j]
                    if num > 9:
                        return False
                    if num != 0:
                        if num in seen:
                            return False
                        seen.add(num)
    
    return True
            
def solve_sudoku(board):
    # Check if there are at least 17 non-zero elements (helper digits)
    if count_non_zero(board) < 17:
        return False
    
    # Proceed with backtracking to solve the Sudoku
    for row in range(9):
        for col in range(9):
            if board[row][col] == 0:
                for num in range(1, 10):
                    if is_valid(board, row, col, num):
                        board[row][col] = num
                        if solve_sudoku(board):
                            return True
                        board[row][col] = 0
                return False
    return True
