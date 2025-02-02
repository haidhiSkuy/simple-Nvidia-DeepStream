import os
import logging

from app.pipelines import Pipeline, AnonymizationPipeline, ReIDPipeline, SegmentationPipeline
from app.config import CONFIGS_DIR, LOGLEVEL

logging.basicConfig(level=LOGLEVEL)


def run_pipeline(video_uri: str):
    pipeline = Pipeline(
        video_uri=video_uri,
        pgie_config_path="/workspaces/tes2/DeepstreamPython/configs/pgies/yolox.txt",
        tracker_config_path="/workspaces/tes2/DeepstreamPython/configs/trackers/nvdcf.txt",
        output_format="mp4",
        redis=False #{'host':'localhost', 'port':6379, 'db':0, 'channel':'yolox'}
    )
    pipeline.run()


def run_segmentation_pipeline(video_uri: str):
    pipeline = SegmentationPipeline(
        video_uri=video_uri,
        pgie_config_path="/workspaces/tes2/configs/pgies/dstest1_pgie_config.txt",#os.path.join(CONFIGS_DIR, "pgies/segmentation.txt"),
        tracker_config_path="/workspaces/tes2/configs/tracker/dstest2_tracker_config.txt",#os.path.join(CONFIGS_DIR, "trackers/nvdcf.txt"),
        output_format="mp4",
    )
    pipeline.run()


def run_anonymization_pipeline(video_uri: str):
    pipeline = AnonymizationPipeline(
        video_uri=video_uri,
        pgie_config_path=os.path.join(CONFIGS_DIR, "pgies/yolov4.txt"),
        tracker_config_path=os.path.join(CONFIGS_DIR, "trackers/nvdcf.txt"),
        target_classes=[2],
        enable_osd=False,
    )
    pipeline.run()


def run_reid_pipeline(video_uri: str):
    pipeline = ReIDPipeline(
        video_uri=video_uri,
        target_classes=[0],
        save_crops=False,
    )
    pipeline.run()
