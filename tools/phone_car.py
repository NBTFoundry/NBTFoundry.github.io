#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""The landing page's phone-beside-car images, composed from the two repositories' captures.

    python3 -I tools/phone_car.py themes <phone folder> <car folder>
    python3 -I tools/phone_car.py install <mobile-install.webp> <manager-install.gif>

themes   site/assets/theme-{bmw,mini,supra}.webp from <phone folder>/theme-<name>.png (the phone
         app's `scripts/capture_screens.py --themes`) and <car folder>/<name>-settings.png (the
         manager's simulator with NBT_THEME=<name>, a 1280x480 still of Settings).
install  site/assets/phone-install.webp and its still from the two repositories' install clips
         (`docs/assets/`), each warped in time so that both show the same moment. After a new
         recording, set PHONE and CAR again: --sheet <png> lays a clip out over time.

Needs Pillow.
"""
import argparse
import bisect
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence

ASSETS = Path(__file__).resolve().parents[1] / 'site' / 'assets'
BACKGROUND = (10, 13, 18)
# (second of the result, second of the recording). The result: the tap at 1.6, the car's review
# from 2.3, the driver's confirmation at 4.9, the result at 9, then the phone's page and its list
# (two cuts in its recording).
PHONE = [(0, 2.2), (1.6, 3.8), (2.3, 4.5), (4.9, 7.0), (9.0, 9.2), (9.3, 9.5), (10.7, 10.9), (10.701, 14.8),
         (11.7, 15.8), (11.701, 18.3), (13.5, 20.1)]
CAR = [(0, 0.0), (2.3, 1.25), (2.4, 1.35), (4.9, 3.9), (9.0, 8.0), (10.7, 9.7), (13.5, 11.0)]
STILL_AT = 10.4


def themes(phone, car):
    width, height, phone_h, car_size = 1800, 675, 615, (1260, 472)
    for theme in ('bmw', 'mini', 'supra'):
        shot = Image.open(phone / f'theme-{theme}.png').convert('RGBA')
        shot = shot.resize((shot.width * phone_h // shot.height, phone_h), Image.LANCZOS)
        screen = Image.open(car / f'{theme}-settings.png').convert('RGB').resize(car_size, Image.LANCZOS)
        slide = Image.new('RGB', (width, height), BACKGROUND)
        slide.paste(shot, (111, (height - phone_h) // 2), shot)
        slide.paste(screen, (474, (height - car_size[1]) // 2))
        slide.save(ASSETS / f'theme-{theme}.webp', quality=86, method=6)


def load(path, size=None):
    times, frames, second = [], [], 0.0
    for frame in ImageSequence.Iterator(Image.open(path)):
        picture = frame.convert('RGBA')
        times.append(second)
        frames.append(picture.resize(size, Image.LANCZOS) if size else picture)
        second += frame.info.get('duration', 83) / 1000.0
    return times, frames, second


def at(clip, second):
    return clip[1][max(0, bisect.bisect_right(clip[0], second) - 1)]


def warp(points, second):
    for (out0, in0), (out1, in1) in zip(points, points[1:]):
        if out0 <= second <= out1:
            return in0 + (in1 - in0) * (second - out0) / (out1 - out0)
    return points[-1][1]


def install(phone_path, car_path):
    phone, car = load(phone_path, (190, 410)), load(car_path, (840, 315))
    step, frames, second = 1 / 6.0, [], 0.0
    while second <= PHONE[-1][0] + 1e-6:
        frame = Image.new('RGB', (1200, 450), BACKGROUND)
        shot = at(phone, warp(PHONE, second))
        frame.paste(shot, (74, 20), shot)
        frame.paste(at(car, warp(CAR, second)).convert('RGB'), (316, 67))
        frames.append(frame)
        second += step
    frames[0].save(ASSETS / 'phone-install.webp', save_all=True, append_images=frames[1:],
                   duration=int(step * 1000), loop=0, quality=62, method=4)
    frames[int(STILL_AT / step)].save(ASSETS / 'phone-install-still.webp', quality=84, method=6)


def sheet(path, target, step=0.5, columns=10, height=240):
    """One picture of `path` every `step` seconds, each under its second."""
    clip = load(path)
    width = clip[1][0].width * height // clip[1][0].height
    count = int(clip[2] / step) + 1
    page = Image.new('RGB', (columns * (width + 4), -(-count // columns) * (height + 16)), (50, 50, 50))
    draw = ImageDraw.Draw(page)
    for n in range(count):
        x, y = (n % columns) * (width + 4), (n // columns) * (height + 16)
        picture = at(clip, n * step).resize((width, height))
        page.paste(picture, (x, y + 14), picture)
        draw.text((x + 2, y + 1), f'{n * step:.1f}', fill=(255, 255, 0))
    page.save(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('what', choices=('themes', 'install'))
    parser.add_argument('phone', type=Path)
    parser.add_argument('car', type=Path)
    parser.add_argument('--sheet', type=Path, help='install: only lay the phone clip out over time, here')
    args = parser.parse_args()
    if args.what == 'themes':
        themes(args.phone, args.car)
    elif args.sheet:
        sheet(args.phone, args.sheet)
    else:
        install(args.phone, args.car)


if __name__ == '__main__':
    main()
