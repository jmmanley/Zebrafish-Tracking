import sys
import argparse
import glob
import os
import numpy as np
import tracking
from multiprocessing import Pool
from itertools import repeat

# parse arguments
parser = argparse.ArgumentParser()
parser.add_argument("-v", "--video", help="Path containing videos you want to track.", required=True)
parser.add_argument("-p", "--params", help="Path to the tracking parameters npz file.", required=True)
parser.add_argument("-o", "--output", help="Path to where to save tracking output.", required=True)
parser.add_argument("-n", "--npool", help="Number of workers to run.", required=True)
args = parser.parse_args()

# extract video path, tracking params and tracking path
video_path = args.video
params = dict(np.load(args.params))
params = params['params'][()]
params['save_video'] = False
params['use_multiprocessing'] = False
npool = int(args.npool)
tracking_path = args.output

videos = glob.glob(os.path.join(video_path, '*.avi'))

toAnalyze = []

for video in videos:
	if not os.path.exists(os.path.join(tracking_path, video[:len(video)-4]+'_tracking.npz')):
		toAnalyze.append(video)

# track the video

with Pool(npool) as p:
	p.starmap(tracking.open_and_track_video, zip(toAnylyze, repeat(None), repeat(params), repeat(tracking_path)))