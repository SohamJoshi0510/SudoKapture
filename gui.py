# gui.py

import tkinter as tk
from tkinter import ttk, messagebox
from sudoku import is_valid_interpretation
from sudoku import solve_sudoku

# Global variables to track solve action
solve_clicked = False
board_snapshot = None

def create_gui(board, initial_board):
    global solve_clicked, board_snapshot

    root = tk.Tk()
    root.title("Sudoku Solver")

    entries = []
    for i in range(9):
        row = []
        for j in range(9):
            entry = ttk.Entry(root, width=2, font=('Arial', 18, 'bold'))
            entry.grid(row=i, column=j, padx=1, pady=1)
            entry.insert(0, str(board[i][j]) if board[i][j] != 0 else '')
            row.append(entry)
        entries.append(row)

    # Informative message
    info_label = ttk.Label(root, text="The program can make mistakes.\nKindly edit the misinterpretations, if any.", font=('Arial', 12, 'italic'))
    info_label.grid(row=10, column=0, columnspan=9, pady=10)

    def solve_and_update():
        global solve_clicked, board_snapshot
        solve_clicked = True

        # Update the board with the current entries
        for i in range(9):
            for j in range(9):
                try:
                    board[i][j] = int(entries[i][j].get())
                    initial_board[i][j] = int(entries[i][j].get())
                except ValueError:
                    board[i][j] = 0

        # Save the current board state for reset
        board_snapshot = [row[:] for row in board]
        if is_valid_interpretation(board):
            if solve_sudoku(board):
                for i in range(9):
                    for j in range(9):
                        entries[i][j].config(state='normal')
                        entries[i][j].delete(0, tk.END)
                        entries[i][j].insert(0, str(board[i][j]))
                        entries[i][j].config(state='disabled')
                solve_button.config(state='disabled')
            else:
                messagebox.showinfo("No Solution", "No unique solution exists.")
        else:
            messagebox.showinfo("Invalid interpretation", "Invalid interpretation(fails to follow the rules of Sudoku).")

    def reset_board():
        global solve_clicked, board_snapshot
        solve_button.config(state='normal')
        
        if solve_clicked:
            # Reset to state before solve
            for i in range(9):
                for j in range(9):
                    entries[i][j].config(state='normal')
                    board[i][j] = board_snapshot[i][j]
                    entries[i][j].delete(0, tk.END)
                    entries[i][j].insert(0, str(board[i][j]) if board[i][j] != 0 else '')
        else:
            # Reset to state after last reset
            for i in range(9):
                for j in range(9):
                    entries[i][j].config(state='normal')
                    board[i][j] = initial_board[i][j]
                    entries[i][j].delete(0, tk.END)
                    entries[i][j].insert(0, str(board[i][j]) if board[i][j] != 0 else '')

    solve_button = ttk.Button(root, text="Solve!!", command=solve_and_update)
    solve_button.grid(row=9, column=0, columnspan=4, pady=10)

    reset_button = ttk.Button(root, text="Reset Puzzle", command=reset_board)
    reset_button.grid(row=9, column=5, columnspan=4, pady=10)

    root.mainloop()
