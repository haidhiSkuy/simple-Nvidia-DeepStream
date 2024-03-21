import sys
import time

import argparse
import configparser
from pathlib import Path

import gi
gi.require_version('Gst', '1.0')
from gi.repository import GLib, Gst

import sys
import pyds
import math
import platform
from ctypes import *

from common.FPS import PERF_DATA
from common.bus_call import bus_call
from common.is_aarch_64 import is_aarch64


MAX_DISPLAY_LEN=64
PGIE_CLASS_ID_VEHICLE = 0
PGIE_CLASS_ID_BICYCLE = 1
PGIE_CLASS_ID_PERSON = 2
PGIE_CLASS_ID_ROADSIGN = 3
MUXER_OUTPUT_WIDTH=1920
MUXER_OUTPUT_HEIGHT=1080
MUXER_BATCH_TIMEOUT_USEC = 33000
TILED_OUTPUT_WIDTH=1280
TILED_OUTPUT_HEIGHT=720
GST_CAPS_FEATURES_NVMM="memory:NVMM"
OSD_PROCESS_MODE= 0
OSD_DISPLAY_TEXT= 1
pgie_classes_str= ["Vehicle", "TwoWheeler", "Person","RoadSign"]


class DeepStreamApp3: 
    def __init__(
            self, 
            source_files : list, 
            config_file : str,
            requested_pgie : str, 

            no_display : bool = False,
            disable_probe : bool = False,
            file_loop : bool = False,
            silent : bool = False
            ): 
        self.source_files = source_files
        self.config_file = config_file
        self.requested_pgie = requested_pgie

        self.no_display = no_display 
        self.disable_probe = disable_probe
        self.file_loop = file_loop
        self.silent = silent

    def pgie_src_pad_buffer_probe(self, pad, info, u_data):
        frame_number=0
        num_rects=0
        got_fps = False
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
            l_obj=frame_meta.obj_meta_list
            num_rects = frame_meta.num_obj_meta
            obj_counter = {
            PGIE_CLASS_ID_VEHICLE:0,
            PGIE_CLASS_ID_PERSON:0,
            PGIE_CLASS_ID_BICYCLE:0,
            PGIE_CLASS_ID_ROADSIGN:0
            }
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
            if not self.silent:
                print("Frame Number=", frame_number, "Number of Objects=",num_rects,"Vehicle_count=",obj_counter[PGIE_CLASS_ID_VEHICLE],"Person_count=",obj_counter[PGIE_CLASS_ID_PERSON])

            # Update frame rate through this probe
            stream_index = "stream{0}".format(frame_meta.pad_index)
            self.perf_data.update_fps(stream_index)

            try:
                l_frame=l_frame.next
            except StopIteration:
                break

        return Gst.PadProbeReturn.OK

    def cb_newpad(self, decodebin, decoder_src_pad, data):
        print("In cb_newpad\n")
        caps = decoder_src_pad.get_current_caps()
        if not caps:
            caps = decoder_src_pad.query_caps()
        gststruct = caps.get_structure(0)
        gstname = gststruct.get_name()
        source_bin = data
        features = caps.get_features(0)

        # Need to check if the pad created by the decodebin is for video and not
        # audio.
        print("gstname=",gstname)
        if(gstname.find("video")!=-1):
            # Link the decodebin pad only if decodebin has picked nvidia
            # decoder plugin nvdec_*. We do this by checking if the pad caps contain
            # NVMM memory features.
            print("features=",features)
            if features.contains("memory:NVMM"):
                # Get the source bin ghost pad
                bin_ghost_pad=source_bin.get_static_pad("src")
                if not bin_ghost_pad.set_target(decoder_src_pad):
                    sys.stderr.write("Failed to link decoder src pad to source bin ghost pad\n")
            else:
                sys.stderr.write(" Error: Decodebin did not pick nvidia decoder plugin.\n")

    def decodebin_child_added(self, child_proxy, Object, name, user_data):
        print("Decodebin child added:", name, "\n")
        if(name.find("decodebin") != -1):
            Object.connect("child-added", self.decodebin_child_added, user_data)

        if "source" in name:
            source_element = child_proxy.get_by_name("source")
            if source_element.find_property('drop-on-latency') != None:
                Object.set_property("drop-on-latency", True)

    def create_source_bin(self, index, uri):
        print("Creating source bin")

        # Create a source GstBin to abstract this bin's content from the rest of the
        # pipeline
        bin_name = "source-bin-%02d" %index
        print(bin_name)
        nbin = Gst.Bin.new(bin_name)
        if not nbin:
            sys.stderr.write(" Unable to create source bin \n")

        # Source element for reading from the uri.
        # We will use decodebin and let it figure out the container format of the
        # stream and the codec and plug the appropriate demux and decode plugins.
        if self.file_loop:
            # use nvurisrcbin to enable file-loop
            uri_decode_bin=Gst.ElementFactory.make("nvurisrcbin", "uri-decode-bin")
            uri_decode_bin.set_property("file-loop", 1)
            uri_decode_bin.set_property("cudadec-memtype", 0)
        else:
            uri_decode_bin=Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
        if not uri_decode_bin:
            sys.stderr.write(" Unable to create uri decode bin \n")
        # We set the input uri to the source element
        uri_decode_bin.set_property("uri",uri)
        # Connect to the "pad-added" signal of the decodebin which generates a
        # callback once a new pad for raw data has beed created by the decodebin
        uri_decode_bin.connect("pad-added", self.cb_newpad, nbin)
        uri_decode_bin.connect("child-added", self.decodebin_child_added, nbin)

        # We need to create a ghost pad for the source bin which will act as a proxy
        # for the video decoder src pad. The ghost pad will not have a target right
        # now. Once the decode bin creates the video decoder and generates the
        # cb_newpad callback, we will set the ghost pad target to the video decoder
        # src pad.
        Gst.Bin.add(nbin,uri_decode_bin)
        bin_pad = nbin.add_pad(Gst.GhostPad.new_no_target("src",Gst.PadDirection.SRC))
        if not bin_pad:
            sys.stderr.write(" Failed to add ghost pad in source bin \n")
            return None
        return nbin

    def setup(self): 

        self.perf_data = PERF_DATA(len(self.source_files))
        number_sources = len(self.source_files)

        # Standard GStreamer initialization
        Gst.init(None)

        # Create gstreamer elements */
        # Create Pipeline element that will form a connection of other elements
        print("Creating Pipeline \n ")
        self.pipeline = Gst.Pipeline()
        is_live = False

        if not self.pipeline:
            sys.stderr.write(" Unable to create Pipeline \n")
        print("Creating streamux \n ")

        # Create nvstreammux instance to form batches from one or more sources.
        streammux = Gst.ElementFactory.make("nvstreammux", "Stream-muxer")
        if not streammux:
            sys.stderr.write(" Unable to create NvStreamMux \n")

        self.pipeline.add(streammux)
        for i in range(number_sources):
            print("Creating source_bin ",i," \n ")
            uri_name = self.source_files[i]
            if uri_name.find("rtsp://") == 0 :
                is_live = True
            source_bin = self.create_source_bin(i, uri_name)
            if not source_bin:
                sys.stderr.write("Unable to create source bin \n")
            self.pipeline.add(source_bin)
            padname = "sink_%u" %i
            sinkpad = streammux.get_request_pad(padname) 
            if not sinkpad:
                sys.stderr.write("Unable to create sink pad bin \n")
            srcpad = source_bin.get_static_pad("src")
            if not srcpad:
                sys.stderr.write("Unable to create src pad bin \n")
            srcpad.link(sinkpad)

        queue1 = Gst.ElementFactory.make("queue","queue1")
        queue2 = Gst.ElementFactory.make("queue","queue2")
        queue3 = Gst.ElementFactory.make("queue","queue3")
        queue4 = Gst.ElementFactory.make("queue","queue4")
        queue5 = Gst.ElementFactory.make("queue","queue5")
        self.pipeline.add(queue1)
        self.pipeline.add(queue2)
        self.pipeline.add(queue3)
        self.pipeline.add(queue4)
        self.pipeline.add(queue5)

        nvdslogger = None

        print("Creating Pgie \n ")
        if self.requested_pgie != None and (self.requested_pgie == 'nvinferserver' or self.requested_pgie == 'nvinferserver-grpc') :
            self.pgie = Gst.ElementFactory.make("nvinferserver", "primary-inference")
        elif self.requested_pgie != None and self.requested_pgie == 'nvinfer':
            self.pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
        else:
            self.pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")

        if not self.pgie:
            sys.stderr.write(" Unable to create pgie :  %s\n" % self.requested_pgie)

        if self.disable_probe:
            # Use nvdslogger for perf measurement instead of probe function
            print("Creating nvdslogger \n")
            nvdslogger = Gst.ElementFactory.make("nvdslogger", "nvdslogger")

        print("Creating tiler \n ")
        tiler = Gst.ElementFactory.make("nvmultistreamtiler", "nvtiler")
        if not tiler:
            sys.stderr.write(" Unable to create tiler \n")
        print("Creating nvvidconv \n ")
        nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "convertor")
        if not nvvidconv:
            sys.stderr.write(" Unable to create nvvidconv \n")
        print("Creating nvosd \n ")
        nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
        if not nvosd:
            sys.stderr.write(" Unable to create nvosd \n")
        nvosd.set_property('process-mode',OSD_PROCESS_MODE)
        nvosd.set_property('display-text',OSD_DISPLAY_TEXT)

        if self.file_loop:
            if is_aarch64():
                # Set nvbuf-memory-type=4 for aarch64 for file-loop (nvurisrcbin case)
                streammux.set_property('nvbuf-memory-type', 4)
            else:
                # Set nvbuf-memory-type=2 for x86 for file-loop (nvurisrcbin case)
                streammux.set_property('nvbuf-memory-type', 2)

        if self.no_display:
            print("Creating Fakesink \n")
            sink = Gst.ElementFactory.make("fakesink", "fakesink")
            sink.set_property('enable-last-sample', 0)
            sink.set_property('sync', 0)
        else:
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

        if not sink:
            sys.stderr.write(" Unable to create sink element \n")

        if is_live:
            print("At least one of the sources is live")
            streammux.set_property('live-source', 1)

        streammux.set_property('width', 1920)
        streammux.set_property('height', 1080)
        streammux.set_property('batch-size', number_sources)
        streammux.set_property('batched-push-timeout', MUXER_BATCH_TIMEOUT_USEC)

        if self.requested_pgie == "nvinferserver" and self.config != None:
            self.pgie.set_property('config-file-path', self.config)
        elif self.requested_pgie == "nvinferserver-grpc" and self.config != None:
            self.pgie.set_property('config-file-path', self.config)
        elif self.requested_pgie == "nvinfer" and self.config != None:
            self.pgie.set_property('config-file-path', self.config)
        else:
            self.pgie.set_property('config-file-path', self.config_file)

        pgie_batch_size = self.pgie.get_property("batch-size")
        if(pgie_batch_size != number_sources):
            print("WARNING: Overriding infer-config batch-size",pgie_batch_size," with number of sources ", number_sources," \n")
            self.pgie.set_property("batch-size",number_sources)
        tiler_rows=int(math.sqrt(number_sources))
        tiler_columns=int(math.ceil((1.0*number_sources)/tiler_rows))
        tiler.set_property("rows",tiler_rows)
        tiler.set_property("columns",tiler_columns)
        tiler.set_property("width", TILED_OUTPUT_WIDTH)
        tiler.set_property("height", TILED_OUTPUT_HEIGHT)
        sink.set_property("qos",0)

        print("Adding elements to Pipeline \n")
        self.pipeline.add(self.pgie)
        if nvdslogger:
            self.pipeline.add(nvdslogger)
        self.pipeline.add(tiler)
        self.pipeline.add(nvvidconv)
        self.pipeline.add(nvosd)
        self.pipeline.add(sink)

        print("Linking elements in the Pipeline \n")
        streammux.link(queue1)
        queue1.link(self.pgie)
        self.pgie.link(queue2)
        if nvdslogger:
            queue2.link(nvdslogger)
            nvdslogger.link(tiler)
        else:
            queue2.link(tiler)
        tiler.link(queue3)
        queue3.link(nvvidconv)
        nvvidconv.link(queue4)
        queue4.link(nvosd)
        nvosd.link(queue5)
        queue5.link(sink)  

    def run(self): 
        loop = GLib.MainLoop()
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect ("message", bus_call, loop)
        pgie_src_pad = self.pgie.get_static_pad("src")
        if not pgie_src_pad:
            sys.stderr.write(" Unable to get src pad \n")
        else:
            if not self.disable_probe:
                pgie_src_pad.add_probe(
                    Gst.PadProbeType.BUFFER, 
                    self.pgie_src_pad_buffer_probe, 
                    0
                )
                # perf callback function to print fps every 5 sec
                GLib.timeout_add(5000, self.perf_data.perf_print_callback)

        # List the sources
        print("Now playing...")
        for i, source in enumerate(self.source_files):
            print(i, ": ", source)

        print("Starting pipeline \n")
        # start play back and listed to events		
        self.pipeline.set_state(Gst.State.PLAYING)
        try:
            loop.run()
        except:
            pass
        # cleanup
        print("Exiting app\n")
        self.pipeline.set_state(Gst.State.NULL) 


if __name__ == "__main__": 
    import argparse 
    parser = argparse.ArgumentParser(description="Deepstream test-app 3")
    parser.add_argument( # 1
        "-i", "--input", help="Path to input streams", 
        metavar="URIs", nargs="+",
        default=[
            "file:///opt/nvidia/deepstream/deepstream-6.4/samples/streams/sample_cam5.mp4", 
            "file:///opt/nvidia/deepstream/deepstream-6.4/samples/streams/sample_cam6.mp4"
        ])
    parser.add_argument( # 2
        "-c", "--configfile", metavar="config_location.txt",
        default="configs/pgies/dstest3_pgie_config.txt", 
        help="Choose the config-file to be used with specified pgie",
    )
    parser.add_argument( # 3
        "-g", "--pgie", default=None, help="Choose Primary GPU Inference Engine",
        choices=["nvinfer", "nvinferserver", "nvinferserver-grpc"], 
    )
    parser.add_argument( # 4
        "--no-display", action="store_true", default=False,
        dest='no_display', help="Disable display of video output",
    )
    parser.add_argument( # 5
        "--file-loop", action="store_true", default=False,
        dest='file_loop', help="Loop the input file sources after EOS",
    )
    parser.add_argument( # 6
        "--disable-probe", action="store_true", 
        dest='disable_probe', default=False,
        help="Disable the probe function and use nvdslogger for FPS",
    )
    parser.add_argument( # 7
        "-s", "--silent", action="store_true", default=False,
        dest='silent', help="Disable verbose output",
    ) 

    args = parser.parse_args() 
    source_files = args.input 
    config_file = args.configfile 
    requested_pgie = args.pgie
    no_display = False # args.no_display 
    file_loop = args.file_loop 
    disable_probe = args.disable_probe
    silent = args.silent  

    pipeline = DeepStreamApp3( 
        source_files, 
        config_file, 
        requested_pgie, 
        no_display, 
        file_loop, 
        disable_probe, 
        silent
    )
    pipeline.setup()
    pipeline.run()
