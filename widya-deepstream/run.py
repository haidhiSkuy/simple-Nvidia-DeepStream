import argparse
from widya_pipeline import PipelineCommon

parser = argparse.ArgumentParser(description="Widya Deepstream")
parser.add_argument( # 1
    "-i", "--input", help="Path to input streams", 
    metavar="URIs", nargs="+",
    default=[
        "file:///opt/nvidia/deepstream/deepstream-6.4/samples/streams/sample_720p.mp4", 
    ])
parser.add_argument( # 2
    "-c", "--configfile", metavar="config_location.txt",
    default="/workspaces/tes2/widya-deepstream/configs/widya-config-yolox.txt", 
    help="Choose the config-file to be used with specified pgie",
)
args = parser.parse_args() 


if __name__ == "__main__":
    pipeline = PipelineCommon(
        args.input, 
        args.configfile, 
    ) 
    pipeline.build_pipeline()
    pipeline.linking_pipeline()
    pipeline.run()
    
