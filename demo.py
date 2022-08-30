import sys

sys.path.append('core')

import argparse
import glob
import numpy as np
import torch
from tqdm import tqdm
from pathlib import Path
from raft_stereo import RAFTStereo
from utils.utils import InputPadder
from PIL import Image
from matplotlib import pyplot as plt
import re
import os

DEVICE = 'cuda'
root = r"../Utils/rectified_rendered_data"


def num_sort(input):
    return list(map(int, re.findall(r"\d+", input)))


def load_image(imfile):
    img = np.array(Image.open(imfile)).astype(np.uint8)
    img = torch.from_numpy(img).permute(2, 0, 1).float()
    return img[None].to(DEVICE)


def demo(args):
    model = torch.nn.DataParallel(RAFTStereo(args), device_ids=[0])
    model.load_state_dict(torch.load(args.restore_ckpt))

    model = model.module
    model.to(DEVICE)
    model.eval()

    output_directory = Path(args.output_directory)
    output_directory.mkdir(exist_ok=True)

    with torch.no_grad():
        left_images = []
        right_images = []
        if args.rendered:
            with open("splits/new_rendered/test_files.txt", "r") as tf:
                test_lists = tf.readlines()
                for line in test_lists:
                    view = line.split()[0]
                    index = line.split()[1]
                    if view == "Left":
                        left_images.append(os.path.join(root, "Left", f"rgb_{index}.PNG"))
                    else:
                        right_images.append(os.path.join(root, "Right", f"rgb_{index}.PNG"))
        else:
            left_images = sorted(glob.glob(args.left_imgs, recursive=True))
            right_images = sorted(glob.glob(args.right_imgs, recursive=True))

        left_images.sort(key=num_sort)
        right_images.sort(key=num_sort)

        print(f"Found {len(left_images)} images. Saving files to {output_directory}/")

        for (imfile1, imfile2) in tqdm(list(zip(left_images, right_images))):
            image1 = load_image(imfile1)
            image2 = load_image(imfile2)

            padder = InputPadder(image1.shape, divis_by=32)
            image1, image2 = padder.pad(image1, image2)

            _, flow_up = model(image1, image2, iters=args.valid_iters, test_mode=True)
            file_stem = imfile1.split('/')[-2]

            folder = args.folder
            if os.path.exists(output_directory):
                pass
            else:
                os.mkdir(output_directory)

            if os.path.exists(os.path.join(output_directory, folder)):
                pass
            else:
                os.mkdir(os.path.join(output_directory, folder))

            if os.path.exists(os.path.join(output_directory, folder, file_stem)):
                pass
            else:
                os.mkdir(os.path.join(output_directory, folder, file_stem))

            if args.save_numpy:
                np.save(os.path.join(output_directory, folder, file_stem, re.split(r"[/.]", imfile1)[-2] + r".npy"),
                        flow_up.cpu().numpy().squeeze())

            plt.imsave(os.path.join(output_directory, folder, file_stem, imfile1.split("/")[-1]),
                       -flow_up.cpu().numpy().squeeze(), cmap='jet')
            # plt.imsave(output_directory / f"{file_stem}.png", -flow_up.cpu().numpy().squeeze(), cmap='jet', vmax=255)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--vmax", type=int, default=255)
    parser.add_argument("--vmin", type=int)
    parser.add_argument('--folder', help="restore checkpoint", default=r"60k_val")
    parser.add_argument('--output_directory', help="directory to save output", default="demo_output/rendered/")
    parser.add_argument("--rendered", action="store_true")
    parser.add_argument('--restore_ckpt', help="restore checkpoint",
                        default=r"checkpoints_new/60000_raft_stereo_rendered.pth")

    parser.add_argument('--save_numpy', action='store_true', help='save output as numpy arrays', default=True)
    parser.add_argument('-l', '--left_imgs', help="path to all first (left) frames",
                        default="../Utils/test_raw/left/tl4_2021-09-29_13A/*.png")
    parser.add_argument('-r', '--right_imgs', help="path to all second (right) frames",
                        default="../Utils/test_raw/right/tl_2021-09-29_13A/*.png")
    parser.add_argument('--mixed_precision', action='store_true', help='use mixed precision')
    parser.add_argument('--valid_iters', type=int, default=32, help='number of flow-field updates during forward pass')

    # Architecture choices
    parser.add_argument('--hidden_dims', nargs='+', type=int, default=[128] * 3,
                        help="hidden state and context dimensions")
    parser.add_argument('--corr_implementation', choices=["reg", "alt", "reg_cuda", "alt_cuda"], default="reg",
                        help="correlation volume implementation")
    parser.add_argument('--shared_backbone', action='store_true',
                        help="use a single backbone for the context and feature encoders")
    parser.add_argument('--corr_levels', type=int, default=4, help="number of levels in the correlation pyramid")
    parser.add_argument('--corr_radius', type=int, default=4, help="width of the correlation pyramid")
    parser.add_argument('--n_downsample', type=int, default=3, help="resolution of the disparity field (1/2^K)")
    parser.add_argument('--slow_fast_gru', action='store_true', help="iterate the low-res GRUs more frequently")
    parser.add_argument('--n_gru_layers', type=int, default=3, help="number of hidden GRU levels")

    args = parser.parse_args()

    demo(args)
