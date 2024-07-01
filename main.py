import tkinter as tk
from tkinter import messagebox
from matplotlib import pyplot as plt
from crop import GUI
from warp import warp_image
from digit_extraction import extract_digits
from gui import create_gui
from cv2 import cvtColor, COLOR_BGR2RGB

def process_file(file_path, root):
    if file_path:
        image, warped_image = warp_image(file_path, root)
        if warped_image is not None:
            plt.imshow(cvtColor(image, COLOR_BGR2RGB))
            plt.title("Uploaded Image")
            plt.axis('off')
            plt.show(block=False)

            temp_message = tk.Toplevel()
            temp_message.title("Please wait")
            tk.Label(temp_message, text="Extracting digits... Count to 10 :)", font=('Arial', 14)).pack(pady=20, padx=20)
            temp_message.update()

            digits, all_cells = extract_digits(warped_image)
            temp_message.destroy()
            create_gui(digits, all_cells)
        else:
            root.quit()

def main():
    root = tk.Tk()
    def callback(file_path):
        if file_path:
            process_file(file_path, root)
        else:
            messagebox.showinfo("No file selected", "No file selected.")
        root.quit()
    GUI(root, callback)

if __name__ == "__main__":
    main()
