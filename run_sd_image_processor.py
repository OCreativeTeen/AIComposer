from utility.sd_image_processor import SDProcessor
import os
import config
from pathlib import Path

# Example usage
def main():
    channel = "temp"
    # Initialize the service
    sd_image_processor = SDProcessor("test", "tw", channel)


    # find all png files with prefix "f_2_r_" in the give folder   
    # the one by one read the file, remove the background, and save the image to the same folder with the same name + "_tp.png"
    for file in os.listdir(config.get_channel_path(channel)):
        stem = Path(file).stem
        ext = Path(file).suffix
        if ext == ".png":
            file_path = config.get_channel_path(channel) + "/" + file
            r_figure_img = sd_image_processor.read_image(file_path)
            r_figure_img = sd_image_processor.remove_background(r_figure_img)
            sd_image_processor.save_image(r_figure_img, file_path.replace(".png", "_tp.png"))

if __name__ == "__main__":
    main()