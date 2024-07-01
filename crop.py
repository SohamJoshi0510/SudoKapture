import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import os

def select_image():
    file_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp *.gif")])
    if not file_path:
        return None, None
    image = Image.open(file_path)
    max_dimension = 600
    image.thumbnail((max_dimension, max_dimension))
    return image, file_path

def crop_image(image, coords):
    if not coords:
        return None
    x1, y1, x2, y2 = map(int, coords)
    x1, y1 = max(0, min(x1, image.width)), max(0, min(y1, image.height))
    x2, y2 = max(0, min(x2, image.width)), max(0, min(y2, image.height))
    cropped_image = image.crop((x1, y1, x2, y2))
    return cropped_image

def display_image_window(root, image, file_path, callback):
    window = tk.Toplevel(root)
    window.title("Image Cropper")
    info_label = tk.Label(window, text="Select the cropping area with your mouse.\nYou can click OK directly to send the full image.", font=('Arial', 12), bg='#007BFF', fg='white')
    info_label.pack(pady=10)
    tk_image = ImageTk.PhotoImage(image)
    canvas = tk.Canvas(window, width=image.width, height=image.height)
    canvas.pack()
    canvas.create_image(0, 0, anchor=tk.NW, image=tk_image)
    crop_rectangle = None
    start_x = start_y = None

    def on_button_press(event):
        nonlocal start_x, start_y, crop_rectangle
        if crop_rectangle:
            canvas.delete(crop_rectangle)
        start_x, start_y = event.x, event.y
        crop_rectangle = canvas.create_rectangle(start_x, start_y, start_x, start_y, outline='red', width=2)

    def on_move_press(event):
        nonlocal start_x, start_y, crop_rectangle
        curX, curY = event.x, event.y
        canvas.coords(crop_rectangle, start_x, start_y, curX, curY)

    canvas.bind("<ButtonPress-1>", on_button_press)
    canvas.bind("<B1-Motion>", on_move_press)

    def on_ok():
        if crop_rectangle is None:
            window.destroy()
            callback(file_path)
        else:
            coords = canvas.coords(crop_rectangle)
            cropped_image = crop_image(image, coords)
            if cropped_image:
                file_name, file_ext = os.path.splitext(file_path)
                count = ''
                cropped_file_path = f'{file_name}_cropped{count}{file_ext}'
                while(os.path.exists(cropped_file_path)):
                    if(count == ''):
                        count = 1 
                        cropped_file_path = f'{file_name}_cropped({count}){file_ext}'
                    else:
                        count += 1
                cropped_image.save(cropped_file_path)
            window.destroy()
            callback(cropped_file_path)

    def on_cancel():
        window.destroy()
        callback(None)

    def on_closing():
        window.destroy()
        callback(None)

    button_style = {'font': ('Arial', 14), 'bg': '#007BFF', 'fg': 'white'}
    ok_button = tk.Button(window, text="OK", command=on_ok, **button_style)
    ok_button.pack(side=tk.LEFT, padx=10, pady=10)
    cancel_button = tk.Button(window, text="Cancel", command=on_cancel, **button_style)
    cancel_button.pack(side=tk.RIGHT, padx=10, pady=10)

    window.protocol("WM_DELETE_WINDOW", on_closing)
    window.image = tk_image
    window.mainloop()

def GUI(root, callback):
    root.geometry("380x120")
    root.title("Select puzzle")
    button_style = {'font': ('Arial', 40), 'bg': '#007BFF', 'fg': 'white'}
    select_button = tk.Button(root, text="Select Image", command=lambda: start_selection(root, callback), **button_style)
    select_button.pack(side=tk.TOP, padx=10, pady=10)
    root.mainloop()

def start_selection(root, callback):
    image, file_path = select_image()
    if not file_path:
        messagebox.showerror("No file selected", "No file selected")
        return
    display_image_window(root, image, file_path, callback)
