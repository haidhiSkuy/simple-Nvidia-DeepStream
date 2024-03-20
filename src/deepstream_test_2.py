import os
import sys

import platform
import configparser 

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import pyds
from common.bus_call import bus_call
from common.is_aarch_64 import is_aarch64 

PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_BATCH_TIMEOUT_USEC = 33000 

class DeepStreamApp2: 
    def __init__(
        self, 
        source_file : str, 
        pgie_config_path : str, 
        sgie_config_path1 : str, 
        sgie_config_path2 : str,
        tracker_config_path : str
        ) -> None:
        self.source_file = source_file 
        self.pgie_config_path = pgie_config_path 
        self.sgie_config_path1 = sgie_config_path1
        self.sgie_config_path2 = sgie_config_path2 
        self.tracker_config_path = tracker_config_path 
    
    def setup(self): 
        Gst.init(None)

        # Create gstreamer elements
        # Create Pipeline element that will form a connection of other elements
        print("Creating Pipeline \n ")
        self.pipeline = Gst.Pipeline()

        if not self.pipeline:
            sys.stderr.write(" Unable to create Pipeline \n")

        # Source element for reading from the file
        print("Creating Source \n ")
        source = Gst.ElementFactory.make("filesrc", "file-source")
        if not source:
            sys.stderr.write(" Unable to create Source \n")

        # Since the data format in the input file is elementary h264 stream,
        # we need a h264parser
        print("Creating H264Parser \n")
        h264parser = Gst.ElementFactory.make("h264parse", "h264-parser")
        if not h264parser:
            sys.stderr.write(" Unable to create h264 parser \n")

        # Use nvdec_h264 for hardware accelerated decode on GPU
        print("Creating Decoder \n")
        decoder = Gst.ElementFactory.make("nvv4l2decoder", "nvv4l2-decoder")
        if not decoder:
            sys.stderr.write(" Unable to create Nvv4l2 Decoder \n")

        # Create nvstreammux instance to form batches from one or more sources.
        streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not streammux:
            sys.stderr.write(" Unable to create NvStreamMux \n")

        # Use nvinfer to run inferencing on decoder's output,
        # behaviour of inferencing is set through config file
        pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
        if not pgie:
            sys.stderr.write(" Unable to create pgie \n")

        tracker = Gst.ElementFactory.make("nvtracker", "tracker")
        if not tracker:
            sys.stderr.write(" Unable to create tracker \n")

        sgie1 = Gst.ElementFactory.make("nvinfer", "secondary1-nvinference-engine")
        if not sgie1:
            sys.stderr.write(" Unable to make sgie1 \n")


        sgie2 = Gst.ElementFactory.make("nvinfer", "secondary2-nvinference-engine")
        if not sgie2:
            sys.stderr.write(" Unable to make sgie2 \n")

        nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
        if not nvvidconv:
            sys.stderr.write(" Unable to create nvvidconv \n")

        # Create OSD to draw on the converted RGBA buffer
        self.nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")

        if not self.nvosd:
            sys.stderr.write(" Unable to create nvosd \n")

        # Finally render the osd output
        if is_aarch64():
            print("Creating nv3dsink \n")
            sink = Gst.ElementFactory.make("nv3dsink", "nv3d-sink")
            if not sink:
                sys.stderr.write(" Unable to create nv3dsink \n")
        else:
            print("Creating EGLSink \n")
            # sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")
            sink = Gst.ElementFactory.make("fakesink", "nvvideo-renderer")
            if not sink:
                sys.stderr.write(" Unable to create egl sink \n")

        print("Playing file %s " %self.source_file)
        source.set_property('location', self.source_file)
        streammux.set_property('width', 1920)
        streammux.set_property('height', 1080)
        streammux.set_property('batch-size', 1)
        streammux.set_property('batched-push-timeout', MUXER_BATCH_TIMEOUT_USEC)

        #Set properties of pgie and sgie
        pgie.set_property('config-file-path', self.pgie_config_path)
        sgie1.set_property('config-file-path', self.sgie_config_path1)
        sgie2.set_property('config-file-path', self.sgie_config_path2 )

        #Set properties of tracker
        config = configparser.ConfigParser()
        config.read(self.tracker_config_path)
        config.sections()

        for key in config['tracker']:
            if key == 'tracker-width' :
                tracker_width = config.getint('tracker', key)
                tracker.set_property('tracker-width', tracker_width)
            if key == 'tracker-height' :
                tracker_height = config.getint('tracker', key)
                tracker.set_property('tracker-height', tracker_height)
            if key == 'gpu-id' :
                tracker_gpu_id = config.getint('tracker', key)
                tracker.set_property('gpu_id', tracker_gpu_id)
            if key == 'll-lib-file' :
                tracker_ll_lib_file = config.get('tracker', key)
                tracker.set_property('ll-lib-file', tracker_ll_lib_file)
            if key == 'll-config-file' :
                tracker_ll_config_file = config.get('tracker', key)
                tracker.set_property('ll-config-file', tracker_ll_config_file)

        print("Adding elements to Pipeline \n")
        self.pipeline.add(source)
        self.pipeline.add(h264parser)
        self.pipeline.add(decoder)
        self.pipeline.add(streammux)
        self.pipeline.add(pgie)
        self.pipeline.add(tracker)
        self.pipeline.add(sgie1)
        self.pipeline.add(sgie2)
        self.pipeline.add(nvvidconv)
        self.pipeline.add(self.nvosd)
        self.pipeline.add(sink)

        # we link the elements together
        # file-source -> h264-parser -> nvh264-decoder ->
        # nvinfer -> nvvidconv -> nvosd -> video-renderer
        print("Linking elements in the Pipeline \n")
        source.link(h264parser)
        h264parser.link(decoder)

        sinkpad = streammux.get_request_pad("sink_0")
        if not sinkpad:
            sys.stderr.write(" Unable to get the sink pad of streammux \n")
        srcpad = decoder.get_static_pad("src")
        if not srcpad:
            sys.stderr.write(" Unable to get source pad of decoder \n")
        srcpad.link(sinkpad)
        streammux.link(pgie)
        pgie.link(tracker)
        tracker.link(sgie1)
        sgie1.link(sgie2)
        sgie2.link(nvvidconv)
        nvvidconv.link(self.nvosd)
        self.nvosd.link(sink)
    
    def osd_sink_pad_buffer_probe(self, pad, info, u_data):
        frame_number=0
        #Intiallizing object counter with 0.
        obj_counter = {
            PGIE_CLASS_ID_VEHICLE:0,
            PGIE_CLASS_ID_PERSON:0,
            PGIE_CLASS_ID_BICYCLE:0,
            PGIE_CLASS_ID_ROADSIGN:0
        }
        num_rects=0
        gst_buffer = info.get_buffer()
        if not gst_buffer:
            print("Unable to get GstBuffer ")
            return

        # Retrieve batch metadata from the gst_buffer
        # Note that pyds.gst_buffer_get_nvds_batch_meta() expects the
        # C address of gst_buffer as input, which is obtained with hash(gst_buffer)
        batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
        l_frame = batch_meta.frame_meta_list
        while l_frame is not None:
            try:
                # Note that l_frame.data needs a cast to pyds.NvDsFrameMeta
                # The casting is done by pyds.NvDsFrameMeta.cast()
                # The casting also keeps ownership of the underlying memory
                # in the C code, so the Python garbage collector will leave
                # it alone.
                frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
            except StopIteration:
                break

            frame_number=frame_meta.frame_num
            num_rects = frame_meta.num_obj_meta
            l_obj=frame_meta.obj_meta_list
            while l_obj is not None:
                try:
                    # Casting l_obj.data to pyds.NvDsObjectMeta
                    obj_meta=pyds.NvDsObjectMeta.cast(l_obj.data)
                except StopIteration:
                    break
                obj_counter[obj_meta.class_id] += 1
                try: 
                    l_obj=l_obj.next
                except StopIteration:
                    break

            # Acquiring a display meta object. The memory ownership remains in
            # the C code so downstream plugins can still access it. Otherwise
            # the garbage collector will claim it when this probe function exits.
            display_meta=pyds.nvds_acquire_display_meta_from_pool(batch_meta)
            display_meta.num_labels = 1
            py_nvosd_text_params = display_meta.text_params[0]
            # Setting display text to be shown on screen
            # Note that the pyds module allocates a buffer for the string, and the
            # memory will not be claimed by the garbage collector.
            # Reading the display_text field here will return the C address of the
            # allocated string. Use pyds.get_string() to get the string content.
            py_nvosd_text_params.display_text = "Frame Number={} Number of Objects={} Vehicle_count={} Person_count={}".format(frame_number, num_rects, obj_counter[PGIE_CLASS_ID_VEHICLE], obj_counter[PGIE_CLASS_ID_PERSON])

            # Now set the offsets where the string should appear
            py_nvosd_text_params.x_offset = 10
            py_nvosd_text_params.y_offset = 12

            # Font , font-color and font-size
            py_nvosd_text_params.font_params.font_name = "Serif"
            py_nvosd_text_params.font_params.font_size = 10
            # set(red, green, blue, alpha); set to White
            py_nvosd_text_params.font_params.font_color.set(1.0, 1.0, 1.0, 1.0)

            # Text background color
            py_nvosd_text_params.set_bg_clr = 1
            # set(red, green, blue, alpha); set to Black
            py_nvosd_text_params.text_bg_clr.set(0.0, 0.0, 0.0, 1.0)
            # Using pyds.get_string() to get display_text as string
            print(pyds.get_string(py_nvosd_text_params.display_text))
            pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)
            try:
                l_frame=l_frame.next
            except StopIteration:
                break
        #past tracking meta data
        l_user=batch_meta.batch_user_meta_list
        while l_user is not None:
            try:
                # Note that l_user.data needs a cast to pyds.NvDsUserMeta
                # The casting is done by pyds.NvDsUserMeta.cast()
                # The casting also keeps ownership of the underlying memory
                # in the C code, so the Python garbage collector will leave
                # it alone
                user_meta=pyds.NvDsUserMeta.cast(l_user.data)
            except StopIteration:
                break
            if(user_meta and user_meta.base_meta.meta_type==pyds.NvDsMetaType.NVDS_TRACKER_PAST_FRAME_META):
                try:
                    # Note that user_meta.user_meta_data needs a cast to pyds.NvDsTargetMiscDataBatch
                    # The casting is done by pyds.NvDsTargetMiscDataBatch.cast()
                    # The casting also keeps ownership of the underlying memory
                    # in the C code, so the Python garbage collector will leave
                    # it alone
                    pPastDataBatch = pyds.NvDsTargetMiscDataBatch.cast(user_meta.user_meta_data)
                except StopIteration:
                    break
                for miscDataStream in pyds.NvDsTargetMiscDataBatch.list(pPastDataBatch):
                    print("streamId=",miscDataStream.streamID)
                    print("surfaceStreamID=",miscDataStream.surfaceStreamID)
                    for miscDataObj in pyds.NvDsTargetMiscDataStream.list(miscDataStream):
                        print("numobj=",miscDataObj.numObj)
                        print("uniqueId=",miscDataObj.uniqueId)
                        print("classId=",miscDataObj.classId)
                        print("objLabel=",miscDataObj.objLabel)
                        for miscDataFrame in pyds.NvDsTargetMiscDataObject.list(miscDataObj):
                            print('frameNum:', miscDataFrame.frameNum)
                            print('tBbox.left:', miscDataFrame.tBbox.left)
                            print('tBbox.width:', miscDataFrame.tBbox.width)
                            print('tBbox.top:', miscDataFrame.tBbox.top)
                            print('tBbox.right:', miscDataFrame.tBbox.height)
                            print('confidence:', miscDataFrame.confidence)
                            print('age:', miscDataFrame.age)
            try:
                l_user=l_user.next
            except StopIteration:
                break
        return Gst.PadProbeReturn.OK	

    def run(self): 
        # create and event loop and feed gstreamer bus mesages to it
        loop = GLib.MainLoop()

        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect ("message", bus_call, loop)

        # Lets add probe to get informed of the meta data generated, we add probe to
        # the sink pad of the osd element, since by that time, the buffer would have
        # had got all the metadata.
        osdsinkpad = self.nvosd.get_static_pad("sink")
        if not osdsinkpad:
            sys.stderr.write(" Unable to get sink pad of nvosd \n")
        osdsinkpad.add_probe(
            Gst.PadProbeType.BUFFER, 
            self.osd_sink_pad_buffer_probe, 
            0
        )


        print("Starting pipeline \n")
    
        # start play back and listed to events
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
          loop.run()
        except:
          pass

        # cleanup
        self.pipeline.set_state(Gst.State.NULL) 

if __name__ == "__main__": 
    import argparse
    parser = argparse.ArgumentParser(description="Deepstream test-app 2") 
    parser.add_argument(
        "--source-file",
        type=str,
        default="/opt/nvidia/deepstream/deepstream/samples/streams/sample_720p.h264",
        help="Path to the source file",
    )
    parser.add_argument(
        "--pgie-config-path",
        type=str,
        default="configs/pgies/dstest2_pgie_config.txt",
        help="Path to the pgie config file",
    )
    parser.add_argument(
        "--sgie-config-path1",
        type=str,
        default="configs/sgies/dstest2_sgie1_config.txt",
        help="Path to the sgie1 config file",
    )
    parser.add_argument(
        "--sgie-config-path2",
        type=str,
        default="configs/sgies/dstest2_sgie2_config.txt",
        help="Path to the sgie2 config file",
    )
    parser.add_argument(
        "--tracker-config-path",
        type=str,
        default="configs/tracker/dstest2_tracker_config.txt",
        help="Path to the tracker config file",
    )

    args = parser.parse_args()

    pipeline = DeepStreamApp2(
        args.source_file, 
        args.pgie_config_path, 
        args.sgie_config_path1, 
        args.sgie_config_path2, 
        args.tracker_config_path
    )
    pipeline.setup()
    pipeline.run()