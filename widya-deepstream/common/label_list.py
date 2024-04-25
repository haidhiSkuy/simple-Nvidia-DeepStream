import configparser
from collections import defaultdict


def get_label(pgie_config_path : str) -> list: 
    config = configparser.ConfigParser()
    config.read(pgie_config_path)  
    pgie_section = config['property']
    pgie_label_path = pgie_section.get('labelfile-path')
    pgie_section = config['property']
    with open(pgie_label_path, 'r') as file:
        labels = [line.strip() for line in file]

    return labels 

def print_counter(obj_counter : defaultdict, labels : list) -> str:
    result = ""
    for i in range(len(labels)): 
        key = list(obj_counter.keys())[i] 
        result += f"{labels[key]}_count={obj_counter[i]} "
    return result