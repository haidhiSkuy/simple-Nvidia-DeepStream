import yaml
import argparse
from widya_pipeline import PipelineCommon

parser = argparse.ArgumentParser(description="Widya Deepstream")
parser.add_argument( # 1
    "-s", "--yaml-config", help="Path yaml config file", 
    default="/workspaces/tes2/widya-deepstream/run.yaml"
)
args = parser.parse_args() 

if __name__ == "__main__":
    with open(args.yaml_config, 'r') as file:
        yaml_data = yaml.safe_load(file)

    pipeline = PipelineCommon(
        source_files=yaml_data['source_files'], 
        pgie_config_file=yaml_data['pgie_config_path'], 
        sgie1_path=yaml_data['sgie1_config_path'], 
        sgie2_path=yaml_data['sgie2_config_path'],
        tracker_path=yaml_data['tracker_config_path'], 
        nvods_func_name=yaml_data['nvods'], 
        redis_config=yaml_data['redis_config'],  
        saved_frames_folder=yaml_data['save_frames_folder']
    ) 

    pipeline.build_pipeline()
    pipeline.linking_pipeline()
    pipeline.run()
    
