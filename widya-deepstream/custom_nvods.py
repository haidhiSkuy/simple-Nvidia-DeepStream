import cv2 
import pyds 
import time
import numpy as np
from typing import List
from collections import defaultdict
from common.label_list import get_label, print_counter
from common.FPS import PERF_DATA, GETFPS
import redis
import json 

class CustomNvosd:
    def __init__(
            self, 
            pgie_config_path : str,
            fps_streams : dict
            ): 
        self.pgie_config_path = pgie_config_path
        self.fps_streams = fps_streams
        self.labels = get_label(self.pgie_config_path)
        self.colors = [tuple(np.random.randint(0, 255, size=3)) for i in range(len(self.labels))]


    def write_osd_analytics(self, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]):
            obj_counter = defaultdict(int)
            for i in range(len(self.labels)): 
                obj_counter[i] = 0

            for frame_meta, l_obj_meta in zip(l_frame_meta, ll_obj_meta):
                frame_number = frame_meta.frame_num
                num_rects = frame_meta.num_obj_meta

                for obj_meta in l_obj_meta:
                    obj_counter[obj_meta.class_id] += 1
                    obj_meta.rect_params.border_color.set(0.0, 0.0, 1.0, 0.0)

                display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
                display_meta.num_labels = 1
                py_nvosd_text_params = display_meta.text_params[0]
                # py_nvosd_text_params.display_text = \
                #     "Frame Number={} Number of Objects={} Vehicle_count={} Person_count={}".format(
                #         frame_number, num_rects, obj_counter[pgie_class_id_vehicle],
                #         obj_counter[pgie_class_id_person])

                py_nvosd_text_params.x_offset = 10
                py_nvosd_text_params.y_offset = 12
                py_nvosd_text_params.font_params.font_name = "Serif"
                py_nvosd_text_params.font_params.font_size = 10
                py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)
                py_nvosd_text_params.set_bg_clr = 1
                py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)

        
                print(print_counter(obj_counter, self.labels))

                pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)


    def write_frame(self, frames, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]): 
        
        for frame, frame_meta, l_obj_meta in zip(frames, l_frame_meta, ll_obj_meta):
            frame_copy = frame.copy()
            frame_copy = cv2.cvtColor(frame_copy, cv2.COLOR_RGBA2BGR)

            for obj_meta in l_obj_meta:
                rect_params = obj_meta.rect_params
                x1 = int(rect_params.left)
                y1 = int(rect_params.top)
                x2 = int(rect_params.left) + int(rect_params.width)
                y2 = int(rect_params.top) +  int(rect_params.height)

                label_str = self.labels[obj_meta.class_id]
                color = self.colors[obj_meta.class_id]
                color = tuple(map(int, color))

                cv2.rectangle(frame_copy, (x1, y1), (x2, y2), color, 2)
                (w, h), _ = cv2.getTextSize(str(label_str), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
                frame_copy = cv2.rectangle(frame_copy, (x1, y1-20), (x1+w, y1), color, -1)
                frame_copy = cv2.putText(frame_copy, str(label_str), (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0), 2)

            frame_num = frame_meta.frame_num
            cv2.imwrite(f"/workspaces/tes2/widya-deepstream/frames/img{frame_num}.jpg", frame_copy) 
            print(f"frame {frame_num}")

    def redis(self, frames, batch_meta, l_frame_meta: List, ll_obj_meta: List[List]):
        r = redis.Redis(host='localhost', port=6379, db=0) 
        obj_counter = defaultdict(int) 
        for frame, frame_meta, l_obj_meta in zip(frames, l_frame_meta, ll_obj_meta):
            for obj_meta in l_obj_meta:
                obj_counter['frame_num'] = frame_meta.frame_num
                obj_counter['total_object'] = frame_meta.num_obj_meta
                obj_counter[self.labels[obj_meta.class_id]] += 1

            

            r.publish('yolox', json.dumps(dict(obj_counter)))